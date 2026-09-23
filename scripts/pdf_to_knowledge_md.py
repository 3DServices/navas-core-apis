#!/usr/bin/env python3
"""
pdf_to_knowledge_md.py — turn an approved PDF into heading-structured markdown.

This is the front half of ingestion, kept separate on purpose. The ingestion
script that writes to the database needs nothing but psycopg2; PDF parsing is
fiddly, version-sensitive and occasionally wrong, so it happens here, offline,
where the output can be read by a person before anything reaches the corpus.
Markdown in database/knowledge/ is the reviewable artefact between the two.

    pip install pdfplumber
    python scripts/pdf_to_knowledge_md.py "path/to/doc.pdf" -o database/knowledge
    python scripts/pdf_to_knowledge_md.py "path/to/folder" -o database/knowledge

Heading detection, in order of trust:

  1. Bold. Where the PDF has a bold face, a mostly-bold short line is a heading.
     This is the only signal that comes from the document rather than from us.
  2. Size. A line set larger than the document's body size.
  3. Shape. ALL-CAPS lines, and 'Module 3:' / '4.2 Something' openers.

Several documents in this corpus (the vision-scope paper, OPERATION WOW) are
exported with one font at one size and no bold at all, so for those only rule 3
applies and the headings are a best effort. That is why the markdown is
reviewed rather than ingested straight from the PDF: a wrong heading makes a
chunk harder to retrieve, and we would rather see that in a diff than in an
answer.
"""

import argparse
import hashlib
import os
import re
import statistics
import sys
import unicodedata

try:
    import pdfplumber
except ImportError:
    raise SystemExit("pdfplumber is required:  pip install pdfplumber")

BULLETS = {'●': 1, '•': 1, '▪': 2, '○': 2, '◦': 2,
           '–': 1, '—': 1, '-': 1, '*': 1, '·': 1, '■': 2}

HEADING_SHAPES = (
    re.compile(r'^(module|section|chapter|appendix|part|phase|annex)\s+[\w.]+\s*[:.\-]', re.I),
    re.compile(r'^\d+(\.\d+)*\.?\s+[A-Z]'),
    re.compile(r'^[IVX]+\.\s+[A-Z]'),
)

# Repeated on every page: page numbers, running footers. Dropped so they do not
# become a chunk of their own or pollute every chunk's text.
NOISE = re.compile(r'^\s*(page\s+)?\d+\s*(of\s+\d+)?\s*$', re.I)

# Typographic furniture from plain-text exports: rules of ===== or -----, and
# the literal '=== PAGE BREAK ===' the vision-scope document uses instead of a
# real page break. Dropped rather than kept as headings.
RULE = re.compile(r'^[=\-_*~—–\s]*(page\s*break)?[=\-_*~—–\s]*$', re.I)
LEADING_RULE = re.compile(r'^[=\-_*~]{3,}\s*')


def clean(text):
    text = unicodedata.normalize('NFKC', text)
    text = text.replace('’', "'").replace('‘', "'")
    text = text.replace('“', '"').replace('”', '"')
    text = text.replace(' ', ' ')
    return re.sub(r'[ \t]+', ' ', text).strip()


def lines_of(page):
    """Words grouped into visual lines, each with its bold share and size."""
    try:
        words = page.extract_words(extra_attrs=['fontname', 'size'],
                                   use_text_flow=False)
    except Exception:
        return []
    rows = {}
    for word in words:
        key = round(word['top'] / 3.0)          # ~3pt tolerance
        rows.setdefault(key, []).append(word)

    out = []
    for key in sorted(rows):
        group = sorted(rows[key], key=lambda w: w['x0'])
        text = clean(' '.join(w['text'] for w in group))
        if not text:
            continue
        chars = sum(len(w['text']) for w in group) or 1
        bold = sum(len(w['text']) for w in group
                   if 'bold' in w.get('fontname', '').lower()) / chars
        sizes = [w.get('size', 0) for w in group if w.get('size')]
        out.append({'text': text, 'bold': bold, 'x0': group[0]['x0'],
                    'size': round(statistics.median(sizes), 1) if sizes else 0})
    return out


def profile(all_lines):
    """The document's body size, and whether it uses bold at all."""
    sizes = [ln['size'] for ln in all_lines if ln['size']]
    body_size = statistics.mode(sizes) if sizes else 0
    has_bold = any(ln['bold'] > 0.6 for ln in all_lines)
    return body_size, has_bold


def bullet_of(text):
    if not text:
        return None, text
    marker = text[0]
    if marker in BULLETS and len(text) > 1 and text[1] in ' \t':
        return BULLETS[marker], text[1:].strip()
    return None, text


def is_heading(line, body_size, has_bold):
    text = line['text']
    if len(text) > 140 or len(text) < 3:
        return False
    if bullet_of(text)[0]:
        return False
    # A sentence is not a heading, even a short one. This rules out the
    # numbered PROSE that fills the vision-scope document ("1. Convert the
    # broad legacy vision into an implementation-grade blueprint.") while
    # keeping its numbered section titles, which carry no full stop.
    if text.endswith(('.', ';', ',', ':')) and not HEADING_SHAPES[0].match(text):
        return False
    letters = [c for c in text if c.isalpha()]
    # Separator runs ("======", "------") are not ALL-CAPS headings.
    if len(letters) < 3:
        return False
    if has_bold and line['bold'] >= 0.7:
        return True
    if body_size and line['size'] >= body_size + 1.4:
        return True
    if len(text.split()) >= 2 and \
            sum(c.isupper() for c in letters) / len(letters) > 0.85:
        return True
    # Shape alone is the weakest signal, so it gets the tightest length limit.
    # Without it, a wrapped line of numbered prose ("4. Convert token billing
    # from a loose commercial idea into a universal, auditable, composable")
    # becomes a heading and takes the rest of its own sentence with it.
    return len(text) <= 80 and any(shape.match(text) for shape in HEADING_SHAPES)


def heading_level(line, body_size, has_bold):
    if body_size and line['size'] >= body_size + 6:
        return 1
    if body_size and line['size'] >= body_size + 2.5:
        return 2
    match = re.match(r'^(\d+(?:\.\d+)*)', line['text'])
    if match:
        return min(2 + match.group(1).count('.'), 5)
    if has_bold and line['bold'] >= 0.7:
        return 3
    return 2


def convert_records(path, pattern, title_end, title=None):
    """For a spreadsheet exported as a PDF.

    MarketPlace_USER STORIES.pdf is one 792pt page of 6pt text with no ruling
    lines, no bold and no size variation — a table dumped to PDF. pdfplumber
    finds no table in it, and prose extraction yields one 6,600-character
    paragraph, which as a chunk is useless: retrieval would return the whole
    sheet for every query.

    So records are cut by a caller-supplied pattern instead. Each row becomes
    its own section, which is what it already was before the export flattened
    it. The pattern is passed in rather than guessed, because a wrong split
    silently mixes two rows into one chunk.
    """
    with pdfplumber.open(path) as pdf:
        text = ' '.join(clean(page.extract_text() or '') for page in pdf.pages)

    starts = [m.start() for m in re.finditer(pattern, text)]
    if len(starts) < 2:
        raise SystemExit(f"{path}: --record-pattern matched {len(starts)} "
                         f"time(s). Nothing to split on.")

    out = [f"# {title or os.path.splitext(os.path.basename(path))[0]}", '']
    if starts[0] > 0:
        out += [text[:starts[0]].strip(), '']          # the header row
    bounds = starts + [len(text)]
    for index in range(len(starts)):
        record = text[bounds[index]:bounds[index + 1]].strip()
        if not record:
            continue
        cut = re.search(title_end, record)
        head = record[:cut.start()].strip() if cut else ' '.join(record.split()[:6])
        out += [f"### {head[:80] or f'Record {index + 1}'}", '',
                record[len(head):].strip() if cut else record, '']
    stats = {'headings': len(starts), 'bullets': 0,
             'paragraphs': len(starts), 'dropped': 0}
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).strip() + '\n', stats, 1


def convert(path, title=None):
    with pdfplumber.open(path) as pdf:
        pages = [lines_of(page) for page in pdf.pages]

    flat = [ln for page in pages for ln in page]
    if not flat:
        raise SystemExit(f"{path}: no extractable text. If this is a scan it "
                         f"needs OCR, which this script does not do.")
    body_size, has_bold = profile(flat)

    # Lines that appear on most pages are furniture, not content.
    seen = {}
    for page in pages:
        for text in {ln['text'] for ln in page}:
            seen[text] = seen.get(text, 0) + 1
    furniture = {t for t, n in seen.items()
                 if len(pages) > 3 and n >= max(3, int(len(pages) * 0.6))}

    out = [f"# {title or os.path.splitext(os.path.basename(path))[0]}", '']
    pending = []                                  # paragraph being assembled
    stats = {'headings': 0, 'bullets': 0, 'paragraphs': 0, 'dropped': 0}

    def flush():
        if pending:
            out.append(' '.join(pending))
            out.append('')
            stats['paragraphs'] += 1
            pending.clear()

    for index, page in enumerate(pages, 1):
        out.append(f"<!-- page {index} -->")
        for line in page:
            text = line['text']
            if not text or NOISE.match(text) or RULE.match(text) \
                    or text in furniture:
                stats['dropped'] += 1
                continue
            text = LEADING_RULE.sub('', text)
            if not text:
                stats['dropped'] += 1
                continue
            line = dict(line, text=text)

            if is_heading(line, body_size, has_bold):
                flush()
                level = heading_level(line, body_size, has_bold)
                out.append(f"{'#' * level} {text}")
                out.append('')
                stats['headings'] += 1
                continue

            depth, stripped = bullet_of(text)
            if depth:
                flush()
                out.append(f"{'  ' * (depth - 1)}- {stripped}")
                stats['bullets'] += 1
                continue

            # A continuation of the previous bullet, not a new paragraph.
            if out and out[-1].lstrip().startswith('- ') and line['x0'] > 90:
                out[-1] = out[-1] + ' ' + text
                continue

            pending.append(text)
        flush()

    # Collapse the blank lines the page markers leave behind.
    text = re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).strip() + '\n'
    return text, stats, len(pages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='a PDF, or a folder of PDFs')
    parser.add_argument('-o', '--out', default='database/knowledge',
                        help='output folder (default: database/knowledge)')
    parser.add_argument('--overwrite', action='store_true',
                        help='replace markdown that already exists')
    parser.add_argument('--record-pattern', metavar='REGEX',
                        help='treat the PDF as a flattened table and start a '
                             'new section at each match (e.g. "\\bA\\d{2}\\s")')
    parser.add_argument('--record-title-end', metavar='REGEX',
                        default=r'\bAs an?\b',
                        help='within a record, where the title stops '
                             r'(default: "\bAs an?\b")')
    args = parser.parse_args()

    if os.path.isdir(args.source):
        paths = sorted(os.path.join(args.source, f)
                       for f in os.listdir(args.source)
                       if f.lower().endswith('.pdf'))
    else:
        paths = [args.source]
    if not paths:
        raise SystemExit(f"No PDFs at {args.source}")

    os.makedirs(args.out, exist_ok=True)

    # Identical files under different names are common in this corpus — two of
    # the ten documents in Downloads/Documents are duplicates. Converting both
    # produces two markdown files that ingestion would then have to reject, so
    # the duplicate is reported here where the reason is obvious.
    by_hash = {}
    for path in paths:
        with open(path, 'rb') as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        if digest in by_hash:
            print(f"  DUPLICATE  {os.path.basename(path)}")
            print(f"             byte-identical to "
                  f"{os.path.basename(by_hash[digest])} — not converted")
            continue
        by_hash[digest] = path

        name = re.sub(r'[^a-z0-9]+', '_',
                      os.path.splitext(os.path.basename(path))[0].lower()
                      ).strip('_') + '.md'
        target = os.path.join(args.out, name)
        if os.path.exists(target) and not args.overwrite:
            print(f"  skip       {name} (exists; --overwrite to replace)")
            continue

        if args.record_pattern:
            markdown, stats, pages = convert_records(
                path, args.record_pattern, args.record_title_end)
        else:
            markdown, stats, pages = convert(path)
        with open(target, 'w', encoding='utf-8') as handle:
            handle.write(markdown)
        print(f"  wrote      {name}")
        print(f"             {pages} pages, {stats['headings']} headings, "
              f"{stats['bullets']} bullets, {stats['paragraphs']} paragraphs, "
              f"{len(markdown):,} chars")
        if stats['headings'] < max(3, pages // 8):
            print(f"             CHECK: only {stats['headings']} headings for "
                  f"{pages} pages. This document probably has no bold and no "
                  f"size variation — read the markdown before ingesting it.")

    print(f"\n{len(by_hash)} document(s) converted into {args.out}.")
    print("Read them, fix any headings that came out wrong, then:")
    print("  python scripts/ingest_waswa_knowledge.py --dry-run")


if __name__ == '__main__':
    sys.exit(main())
