#!/usr/bin/env python3
"""
gdoc_to_knowledge_md.py — clean a Google Docs markdown export into corpus text.

The sibling of pdf_to_knowledge_md.py, for the documents that live in Drive as
Google Docs rather than as PDFs. Those export as markdown already, so the
headings are real headings and nothing has to be guessed from font size — but
the export carries a lot of noise that would otherwise be indexed as content:

  * Everything bold, and bold markers escaped: `\\*\\*Discount limits\\*\\*`.
    Left alone, a search for "discount limits" still matches, but the chunk
    text read back to a person is unreadable.
  * `&#10;` where the document had a line break inside a table cell.
  * Runs of empty bold pairs and stray backslashes from escaped punctuation.
  * Non-breaking spaces and smart quotes.

What it does NOT do is restructure. Headings, tables and list nesting are the
document's own, and they are what the chunker splits on.

    python scripts/gdoc_to_knowledge_md.py export.json -o database/knowledge \\
        --name sales_procedures_3ds_qms_pr_09_v26 \\
        --title "Sales Procedures 3DS-QMS-PR-09 ver26"

The input is either a plain .md/.txt file or a .json file with the text under a
top-level key (``fileContent`` by default) — the shape a Drive read returns.
"""

import argparse
import json
import os
import re
import unicodedata


# Decorative codepoints, and the mojibake they turn into when an export
# round-trips through the wrong encoding. Neither is searchable, and both end
# up inside heading_path where a person reads them.
#
# Built from ranges rather than written as a literal character class, because
# a class of raw emoji in the source is unreadable and impossible to review.
# Deliberately narrow: U+2600-U+27BF is NOT stripped, since the check marks and
# crosses in a compliance table and the arrows a procedure uses for "escalates
# to" are content, as are the maths signs.
_DECORATIVE_RANGES = (
    (0x1F000, 0x1FAFF),   # emoji and pictographs
    (0x2B00, 0x2BFF),     # arrows and stars used as bullets
    (0x23E0, 0x23FA),     # clock and media faces
    (0x20E0, 0x20E3),     # combining enclosing keycap
    (0xFE0F, 0xFE0F),     # variation selector 16
    (0x200D, 0x200D),     # zero-width joiner
)
DECORATION = re.compile(
    '[' + ''.join(f'{chr(lo)}-{chr(hi)}' for lo, hi in _DECORATIVE_RANGES) + ']')

# A latin-1 byte followed by continuation bytes: UTF-8 read as the wrong
# encoding, which is what emoji become in some Google Docs exports.
MOJIBAKE = re.compile('[À-ÿ][\u0080-¿ -⁯]{1,4}')


def load(path, key):
    """The text, whether the file is markdown or a JSON envelope around it.

    Sniffed from the content rather than the extension: a Drive read lands in a
    file named .txt whose content is JSON, and keying off the name silently
    "cleans" the JSON wrapper instead of the document — producing a file full of
    literal \\n and escaped asterisks that looks like a parser bug rather than a
    file-type mistake.
    """
    with open(path, encoding='utf-8') as handle:
        raw = handle.read()

    stripped = raw.lstrip()
    if stripped[:1] in '{[':
        try:
            payload = json.loads(raw)
        except ValueError:
            return raw
        if isinstance(payload, dict):
            if key in payload:
                return payload[key]
            for candidate in ('fileContent', 'content', 'text', 'body'):
                if candidate in payload:
                    print(f"note: used '{candidate}' rather than '{key}'")
                    return payload[candidate]
            raise SystemExit(
                f"{path} is JSON with no text key (found: "
                f"{', '.join(list(payload)[:6])}). Pass --key.")
    return raw


def clean(text):
    text = unicodedata.normalize('NFKC', text)
    text = text.replace('\u00a0', ' ')
    text = text.replace('\u2019', "'").replace('\u2018', "'")
    text = text.replace('\u201c', '"').replace('\u201d', '"')

    # A line break inside a table cell, exported as an HTML entity.
    text = text.replace('&#10;', '\n').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>')

    # Escaped markdown: \*\* -> **, \< -> <, \> -> >, \| -> |
    text = re.sub(r'\\([*_<>|&~!=`\[\]()#.+-])', r'\1', text)

    # Google Docs marks whole tables bold, which after unescaping leaves
    # ****text**** and stray empty pairs. Emphasis on everything is emphasis on
    # nothing, so it goes: the chunk has to read as prose to be useful.
    text = re.sub(r'\*{2,}', '', text)

    lines = []
    for line in text.split('\n'):
        line = re.sub(r'[ \t]+', ' ', line).rstrip()
        # A table row whose cells are all empty or all separators.
        if re.fullmatch(r'\|[\s|:\-]*\|?', line or '|'):
            if lines and lines[-1].startswith('|'):
                lines.append(line)          # keep the header separator
            continue
        lines.append(line)
    text = '\n'.join(lines)

    text = DECORATION.sub('', text)
    text = MOJIBAKE.sub('', text)
    text = re.sub(r'(?m)[ \t]+$', '', text)

    # Horizontal rules the export scatters between sections.
    text = re.sub(r'(?m)^\s*-{3,}\s*$', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() + '\n'


# The amount must END in a digit, so a list separator is not swallowed:
# "UGX 323, OLIWA ..." would otherwise redact "323," and lose the comma that
# separates the items.
_AMOUNT = r'(?:\d(?:[\d,]*\d)?(?:\.\d+)?)'
CURRENCY = re.compile(
    r'\b(UGX|KES|Ksh|KSh|USD|EUR|GBP|TZS|RWF)\s?(' + _AMOUNT + r')|'
    r'(\$)\s?(' + _AMOUNT + r')')


def redact_currency(text):
    """Replace currency amounts with a visible marker, and say what was removed.

    Waswa's runtime prompt refuses every pricing question outright, because no
    approved price list exists and Odoo is not wired. A document that is
    otherwise the best operational reference in the corpus can still carry a
    couple of worked examples with real figures in them — the CMS user manual
    has two lines of published time-token values in an operational aside.

    Deleting those lines quietly would break the property the whole pipeline
    rests on: that the markdown in git IS what was ingested, reviewable by
    eye. So the figure goes and a marker stays, the marker is searchable, and
    the removal is printed and recorded in the manifest. A reader of the chunk
    sees that a number was withheld rather than reading a stale price as fact.
    """
    removed = []

    def swap(match):
        code = match.group(1) or match.group(3)
        amount = match.group(2) or match.group(4)
        removed.append(f'{code} {amount}')
        return f'{code} [amount withheld: pricing]'

    return CURRENCY.sub(swap, text), removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='.json, .md or .txt export')
    parser.add_argument('-o', '--out', default='database/knowledge')
    parser.add_argument('--name', required=True,
                        help='output filename stem (also the manifest key)')
    parser.add_argument('--title', help='H1 to put at the top')
    parser.add_argument('--redact-currency', action='store_true',
                        help='replace currency amounts with a visible marker '
                             '(use for any document that carries worked '
                             'examples with real figures)')
    parser.add_argument('--key', default='fileContent',
                        help="JSON key holding the text (default: fileContent)")
    args = parser.parse_args()

    body = clean(load(args.source, args.key))

    removed = []
    if args.redact_currency:
        body, removed = redact_currency(body)
    if args.title and not body.lstrip().startswith('# '):
        body = f"# {args.title}\n\n{body}"

    os.makedirs(args.out, exist_ok=True)
    target = os.path.join(args.out, f'{args.name}.md')
    with open(target, 'w', encoding='utf-8') as handle:
        handle.write(body)

    scan = CURRENCY.findall(body)
    headings = len(re.findall(r'(?m)^#{1,6} ', body))
    print(f"wrote {target}")
    print(f"  {len(body):,} chars, {headings} headings, "
          f"{body.count(chr(10)) + 1:,} lines")
    if removed:
        print(f"  REDACTED {len(removed)} currency amount(s): "
              f"{', '.join(removed[:8])}"
              f"{' ...' if len(removed) > 8 else ''}")
        print("  Record this in the manifest notes — a redaction nobody wrote "
              "down is indistinguishable from a document that never had the "
              "figure.")
    elif scan:
        print(f"  WARNING: {len(scan)} currency amount(s) still in the text. "
              f"Waswa must never quote a price — re-run with "
              f"--redact-currency, or leave this document out.")
    print("  Add it to database/knowledge/manifest.json with an authority "
          "level, then:")
    print(f"  python scripts/ingest_waswa_knowledge.py "
          f"--only {args.name}.md --commit")


if __name__ == '__main__':
    main()
