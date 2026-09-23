#!/usr/bin/env python3
"""
ingest_waswa_knowledge.py — load the approved corpus into dll_waswa_chunks.

Reads markdown from database/knowledge/ plus the metadata in manifest.json,
splits each document into retrievable chunks, and writes them. Needs nothing
but psycopg2: PDFs were turned into markdown earlier, by
scripts/pdf_to_knowledge_md.py, so that the parsing step and the database step
fail separately and the thing a human reviews is a text file in git.

    python scripts/ingest_waswa_knowledge.py                  # dry run
    python scripts/ingest_waswa_knowledge.py --commit
    python scripts/ingest_waswa_knowledge.py --commit --only oliwa_user_stories_26_03_09.md
    python scripts/ingest_waswa_knowledge.py --approve sales
    python scripts/ingest_waswa_knowledge.py --approve-all
    python scripts/ingest_waswa_knowledge.py --remove oliwa_user_stories_26_03_09.md --commit
    python scripts/ingest_waswa_knowledge.py --report

## How a document is split

By heading, then by size. A chunk is the text under one heading, carrying the
full heading path above it ("PART I: OLIWA CORE APP > Module 6: FUEL"), because
a chunk that says "the threshold is three attempts" without its heading is
unusable to a reader and near-unfindable to a search.

Where a section is longer than MAX_CHARS it is split at paragraph boundaries,
with the previous paragraph repeated at the head of the next chunk. The overlap
costs storage and buys the thing overlap always buys: a sentence that answers a
question does not become unanswerable because it fell across a cut.

Sections shorter than MIN_CHARS are folded into the following chunk rather than
stored alone. Tables of contents and heading-only pages would otherwise become
hundreds of chunks that match every query and answer none.

## What it will not do

* Ingest a file that is not in manifest.json. Authority level cannot be guessed
  from a filename, and a document at the wrong level is worse than a missing
  one — it gets quoted with confidence it has not earned.
* Ingest the same bytes twice. A re-run of an unchanged document reports "no
  change" and touches nothing.
* Mark anything approved. Every source lands with review_status = 'pending',
  and retrieval defaults to approved sources only, so nothing reaches a
  customer until a person runs --approve. That takes any unambiguous part of
  the filename — --approve sales — because the full names run past a hundred
  characters on the command line and a wrapped command is its own kind of bug.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK      # noqa: E402

KNOWLEDGE_DIR = 'database/knowledge'
MANIFEST = os.path.join(KNOWLEDGE_DIR, 'manifest.json')

MAX_CHARS = 1800          # ~450 tokens; several fit in a prompt with room left
MIN_CHARS = 180           # below this a chunk is a heading, not an answer
OVERLAP_PARAGRAPHS = 1
OVERLAP_MAX_CHARS = 400   # a paragraph bigger than this is not worth repeating

PAGE_MARKER = re.compile(r'^<!--\s*page\s+(\d+)\s*-->$')
HEADING = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')


# ── chunking ────────────────────────────────────────────────────────────────

def normalise(text):
    """For hashing only. Whitespace and quote style must not create a new chunk."""
    text = unicodedata.normalize('NFKC', text).lower()
    return re.sub(r'\s+', ' ', text).strip()


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sections(markdown):
    """(heading_path, page_from, page_to, body) for each heading in the file."""
    path, page, buffer = [], 1, []
    first_page = 1
    out = []

    def close():
        body = '\n'.join(buffer).strip()
        if body or path:
            # path[0] is the document title, already on the source row. Empty
            # entries appear where a level is skipped (an H3 under an H1) and
            # would otherwise show up as '  >  A01 INSPECTA'.
            trail = [part for part in path[1:] if part]
            out.append(('  >  '.join(trail) or (path[0] if path else ''),
                        first_page, page, body))
        buffer.clear()

    for line in markdown.splitlines():
        marker = PAGE_MARKER.match(line.strip())
        if marker:
            page = int(marker.group(1))
            continue
        heading = HEADING.match(line)
        if heading:
            close()
            first_page = page
            level = len(heading.group(1))
            path = path[:level - 1]
            while len(path) < level - 1:
                path.append('')
            path.append(heading.group(2))
            continue
        buffer.append(line)
    close()
    return [(h, a, b, body) for h, a, b, body in out]


def split_body(body):
    """Paragraph-aligned pieces of at most MAX_CHARS, with overlap."""
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
    if not paragraphs:
        return []

    pieces, current = [], []
    for paragraph in paragraphs:
        # A single paragraph longer than the budget is cut at sentence ends.
        if len(paragraph) > MAX_CHARS:
            if current:
                pieces.append(current)
                current = []
            sentences = re.split(r'(?<=[.!?])\s+', paragraph)
            run = ''
            for sentence in sentences:
                if run and len(run) + len(sentence) + 1 > MAX_CHARS:
                    pieces.append([run])
                    run = sentence
                else:
                    run = f'{run} {sentence}'.strip()
            if run:
                current = [run]
            continue

        length = sum(len(p) + 2 for p in current)
        if current and length + len(paragraph) > MAX_CHARS:
            pieces.append(current)
            # Carry the previous paragraph into the next chunk only if it is
            # small. Overlap exists so a short connective paragraph — "the
            # threshold below applies per branch" — is not separated from what
            # it qualifies. Repeating a 1,700-character block instead just
            # doubles the chunk and stores the same text twice.
            carry = current[-OVERLAP_PARAGRAPHS:] if OVERLAP_PARAGRAPHS else []
            current = [p for p in carry if len(p) <= OVERLAP_MAX_CHARS]
        current.append(paragraph)
    if current:
        pieces.append(current)
    return ['\n\n'.join(p) for p in pieces]


def chunk_document(markdown):
    """Chunks as (heading_path, page_from, page_to, body).

    A section shorter than MIN_CHARS is held and merged into the next one. When
    that happens the swallowed section's own heading is written into the body,
    so a chunk headed '5. System Entry Latency' that also contains section 6
    says where 6 starts instead of filing its bullets under 5.
    """
    chunks = []
    held_head, held_page, held_parts = None, None, []

    for heading_path, page_from, page_to, body in sections(markdown):
        if held_parts:
            head, start = held_head, held_page
            if body and heading_path:
                leaf = heading_path.split('  >  ')[-1]
                body = f'{leaf}\n{body}'
        else:
            head, start = heading_path, page_from

        parts = held_parts + ([body] if body else [])
        held_head, held_page, held_parts = None, None, []
        text = '\n\n'.join(parts).strip()

        # A heading with nothing under it — a contents entry, or a divider the
        # following heading owns. Dropped: as a chunk it would match every
        # query on its words and answer none of them.
        if not text:
            continue
        if len(text) < MIN_CHARS:
            held_head, held_page, held_parts = head, start, parts
            continue
        for piece in split_body(text):
            chunks.append((head, start, page_to, piece))

    if held_parts:
        text = '\n\n'.join(held_parts).strip()
        if text:
            chunks.append((held_head, held_page, held_page, text))
    return chunks


# ── database ────────────────────────────────────────────────────────────────

def load_manifest():
    if not os.path.exists(MANIFEST):
        raise SystemExit(f"No manifest at {MANIFEST}.")
    with open(MANIFEST, encoding='utf-8') as handle:
        return {d['file']: d for d in json.load(handle)['documents']}


def resolve_product(cur, name):
    """A product_uid for a manifest product_name, or None with a reason.

    Case-insensitive and alias-aware, because the catalogue stores names in
    lower case and the documents write them in capitals.
    """
    if not name:
        return None, None
    cur.execute(
        "SELECT product_uid FROM abi_products_manager "
        "WHERE LOWER(product_name) = LOWER(%s) "
        "ORDER BY CASE WHEN product_uid LIKE '3D-PRD-%%' THEN 0 ELSE 1 END "
        "LIMIT 1", (name,))
    if cur.rowcount:
        return cur.fetchone()[0], None
    cur.execute(
        "SELECT product_uid FROM abi_product_aliases "
        "WHERE LOWER(alias) = LOWER(%s) LIMIT 1", (name,))
    if cur.rowcount:
        return cur.fetchone()[0], None
    return None, (f"product '{name}' is not in abi_products_manager or its "
                  f"aliases — chunks stored without a product link")


def ingest_one(cur, entry, commit):
    path = os.path.join(KNOWLEDGE_DIR, entry['file'])
    if not os.path.exists(path):
        return {'file': entry['file'], 'status': 'missing',
                'note': f'{path} not found'}

    with open(path, encoding='utf-8') as handle:
        markdown = handle.read()
    file_hash = sha256(markdown)
    source_uid = 'WK-' + file_hash[:20]

    cur.execute(
        "SELECT source_uid, chunk_count, review_status FROM dll_waswa_sources "
        "WHERE file_hash = %s", (file_hash,))
    if cur.rowcount:
        existing, count, review = cur.fetchone()
        return {'file': entry['file'], 'status': 'unchanged',
                'source_uid': existing, 'chunks': count,
                'note': f'already ingested, review_status = {review}'}

    # A different hash for a file we have ingested before under another hash is
    # an edited document. The old rows stay and are marked superseded, so an
    # answer given last week can still be traced to what it was read from.
    cur.execute(
        "SELECT source_uid FROM dll_waswa_sources "
        "WHERE filename = %s AND superseded_by IS NULL", (entry['file'],))
    previous = cur.fetchone()[0] if cur.rowcount else None

    chunks = chunk_document(markdown)
    if not chunks:
        return {'file': entry['file'], 'status': 'empty',
                'note': 'no chunks — is the markdown empty?'}

    product_uid, product_note = resolve_product(cur, entry.get('product_name'))

    result = {'file': entry['file'], 'source_uid': source_uid,
              'chunks': len(chunks), 'supersedes': previous,
              'status': 'to ingest' if not commit else 'ingested',
              'note': product_note,
              'chars': sum(len(c[3]) for c in chunks),
              'longest': max(len(c[3]) for c in chunks)}
    if not commit:
        return result

    cur.execute(
        "INSERT INTO dll_waswa_sources "
        "(source_uid, title, filename, document_type, authority_level, "
        " version_label, document_date, country_scope, customer_class_scope, "
        " language, product_uid, service_type, category, file_hash, "
        " chunk_count, ingested_by, notes) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (source_uid, entry['title'], entry['file'],
         entry.get('document_type'), entry['authority_level'],
         entry.get('version_label'), entry.get('document_date'),
         entry.get('country_scope'), entry.get('customer_class_scope'),
         entry.get('language', 'en'), product_uid, entry.get('service_type'),
         entry.get('category'), file_hash, len(chunks),
         'ingest_waswa_knowledge.py', entry.get('notes')))

    written = 0
    for ordinal, (heading_path, page_from, page_to, body) in enumerate(chunks, 1):
        content_hash = sha256(normalise(body))
        cur.execute(
            "INSERT INTO dll_waswa_chunks "
            "(chunk_uid, source_uid, ordinal, heading_path, page_from, page_to, "
            " body, char_count, content_hash, authority_level, document_type, "
            " country_scope, customer_class_scope, language, product_uid, "
            " service_type, category) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (source_uid, content_hash) DO NOTHING",
            (f'{source_uid}-{ordinal:05d}', source_uid, ordinal,
             heading_path[:500] or None, page_from, page_to, body, len(body),
             content_hash, entry['authority_level'], entry.get('document_type'),
             entry.get('country_scope'), entry.get('customer_class_scope'),
             entry.get('language', 'en'), product_uid,
             entry.get('service_type'), entry.get('category')))
        written += cur.rowcount

    if written != len(chunks):
        result['note'] = ((result['note'] + '; ') if result['note'] else '') + \
            f'{len(chunks) - written} repeated chunk(s) folded by content hash'
    cur.execute(
        "UPDATE dll_waswa_sources SET chunk_count = %s WHERE source_uid = %s",
        (written, source_uid))
    result['chunks'] = written

    if previous:
        cur.execute(
            "UPDATE dll_waswa_sources SET superseded_by = %s, updated_at = NOW() "
            "WHERE source_uid = %s", (source_uid, previous))
    return result


def approve(cur, name, everything, by):
    """Approve by a fragment of the filename, or all at once.

    Matching on a fragment is not laziness: the full command with a filename
    like sales_procedures_3ds_qms_pr_09_v26.md runs past a hundred characters,
    and a terminal that wraps it turns the filename into its own command line
    and a confusing error. A short command that cannot wrap is a correctness
    feature here, not a convenience.

    An ambiguous fragment is refused with the candidates listed, because
    approving the wrong document is exactly the mistake this step exists to
    prevent.
    """
    cur.execute(
        "SELECT filename, title, review_status FROM dll_waswa_sources "
        "WHERE superseded_by IS NULL ORDER BY filename")
    sources = cur.fetchall() if cur.rowcount > 0 else []
    if not sources:
        raise SystemExit("No sources ingested yet.")

    if everything:
        targets = [s[0] for s in sources if s[2] != 'approved']
        if not targets:
            print("Every source is already approved.")
            return
    else:
        matches = [s for s in sources if name.lower() in s[0].lower()]
        if not matches:
            print(f"Nothing matches {name!r}. Ingested sources:")
            for filename, title, status in sources:
                print(f"   {status:<9} {filename}")
            raise SystemExit(1)
        if len(matches) > 1:
            print(f"{name!r} matches {len(matches)} sources — be more specific:")
            for filename, title, status in matches:
                print(f"   {filename}")
            raise SystemExit(1)
        targets = [matches[0][0]]

    for filename in targets:
        cur.execute(
            "UPDATE dll_waswa_sources "
            "SET review_status = 'approved', reviewed_by = %s, "
            "    reviewed_at = NOW(), updated_at = NOW() "
            "WHERE filename = %s AND superseded_by IS NULL", (by, filename))
        print(f"   approved  {filename}")

    cur.execute("SELECT COUNT(*) FROM vw_waswa_retrievable "
                "WHERE review_status = 'approved'")
    print(f"\n{len(targets)} source(s) approved by {by}. "
          f"{cur.fetchone()[0]} chunk(s) now quotable to a customer.")


def report(cur):
    cur.execute(
        "SELECT title, authority_level, authority_label, authority_confirmed, "
        "       review_status, chunk_count, embedded_chunks "
        "FROM vw_waswa_corpus")
    rows = cur.fetchall() if cur.rowcount > 0 else []
    if not rows:
        print("The corpus is empty.")
        return
    print(f"{'lvl':>3}  {'review':<9} {'chunks':>6}  title")
    for title, level, label, confirmed, review, count, embedded in rows:
        flag = '' if confirmed else ' (level unconfirmed)'
        print(f"{level:>3}  {review:<9} {count:>6}  {title}{flag}")

    cur.execute("SELECT COUNT(*) FROM dll_waswa_chunks")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM vw_waswa_retrievable "
                "WHERE review_status = 'approved'")
    quotable = cur.fetchone()[0]
    print(f"\n{total} chunk(s) stored; {quotable} currently quotable to a customer.")
    if total and not quotable:
        print("Nothing is approved yet, so knowledge_search will find nothing "
              "until someone runs --approve. That is the intended default.")

    cur.execute("SELECT sources, sample FROM vw_waswa_chunk_echoes LIMIT 5")
    echoes = cur.fetchall() if cur.rowcount > 0 else []
    if echoes:
        print(f"\nIdentical text in more than one document ({len(echoes)} shown):")
        for count, sample in echoes:
            print(f"   {count} sources: {sample[:90]}...")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', action='store_true',
                        help='write (default is a dry run)')
    parser.add_argument('--only', metavar='FILE',
                        help='ingest just this file from the manifest')
    parser.add_argument('--approve', metavar='NAME',
                        help='approve a source for customer-facing answers. '
                             'Any unambiguous part of the filename will do: '
                             '--approve sales')
    parser.add_argument('--approve-all', action='store_true',
                        help='approve every ingested source at once')
    parser.add_argument('--by',
                        default=(os.environ.get('USER')
                                 or os.environ.get('USERNAME') or 'unknown'),
                        help='recorded as reviewed_by (defaults to the '
                             'logged-in user)')
    parser.add_argument('--remove', metavar='FILE',
                        help='delete a source and its chunks')
    parser.add_argument('--report', action='store_true',
                        help='show what is in the corpus and stop')
    args = parser.parse_args()

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn:
            with conn.cursor() as cur:
                if args.report:
                    return report(cur)

                if args.approve or args.approve_all:
                    return approve(cur, args.approve, args.approve_all, args.by)

                if args.remove:
                    cur.execute(
                        "SELECT source_uid, chunk_count FROM dll_waswa_sources "
                        "WHERE filename = %s", (args.remove,))
                    rows = cur.fetchall() if cur.rowcount > 0 else []
                    if not rows:
                        raise SystemExit(f"No source named {args.remove}.")
                    for source_uid, count in rows:
                        print(f"   {'deleting' if args.commit else 'would delete'} "
                              f"{source_uid} ({count} chunks)")
                        if args.commit:
                            cur.execute(
                                "DELETE FROM dll_waswa_sources WHERE source_uid = %s",
                                (source_uid,))
                    if not args.commit:
                        print("\nDry run — nothing deleted. Add --commit.")
                    return

                manifest = load_manifest()
                listed = {f for f in os.listdir(KNOWLEDGE_DIR)
                          if f.endswith('.md')}
                orphans = sorted(listed - set(manifest))
                if orphans:
                    print("Markdown with no manifest entry — NOT ingested:")
                    for name in orphans:
                        print(f"   {name}")
                    print("   Add it to manifest.json with an authority level.\n")

                entries = [manifest[args.only]] if args.only else list(manifest.values())
                if args.only and args.only not in manifest:
                    raise SystemExit(f"{args.only} is not in the manifest.")

                results = [ingest_one(cur, entry, args.commit) for entry in entries]

                print(f"{'chunks':>7}  {'status':<10} file")
                for row in results:
                    print(f"{row.get('chunks', 0):>7}  {row['status']:<10} {row['file']}")
                    if row.get('note'):
                        print(f"{'':>7}  {'':<10} note: {row['note']}")
                    if row.get('supersedes'):
                        print(f"{'':>7}  {'':<10} supersedes {row['supersedes']}")
                    if row.get('longest'):
                        print(f"{'':>7}  {'':<10} "
                              f"{row['chars']:,} chars, longest chunk "
                              f"{row['longest']}")

                total = sum(r.get('chunks', 0) for r in results)
                print(f"\n{total} chunk(s) "
                      f"{'written' if args.commit else 'would be written'}.")
                if not args.commit:
                    print("Dry run — nothing written. Add --commit.")
                else:
                    print("Every source is review_status = 'pending'. Nothing is "
                          "quotable to a customer until you approve it:")
                    print("   python scripts/ingest_waswa_knowledge.py "
                          "--approve <file>")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
