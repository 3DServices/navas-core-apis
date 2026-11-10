#!/usr/bin/env python3
"""My audit scripts were measuring the wrong column, and said the corpus was fine.

Both printed "of those, from an approved source: 2679" using `WHERE s.active`.
`active` is not the gate. Retrieval has two, and neither is `active`:

    _search(): where = ["c.search_vector @@ q",
                        "c.audience = ANY(%(audiences)s)"]
               if not include_unapproved:
                   where.append("c.review_status = 'approved'")

and from the migrations:

    035: review_status VARCHAR(20) NOT NULL DEFAULT 'pending'
    041: audience      VARCHAR(16) NOT NULL DEFAULT 'staff'

So a freshly ingested corpus is invisible twice over, and the ingester says so
out loud: "Every source lands with review_status = 'pending' ... nothing reaches
a customer until a person runs --approve". approve() then sets review_status and
*only* review_status — audience stays 'staff', and _audiences('everyone')
returns ['everyone'], so an approved document is still invisible to every
customer until someone changes its audience (the CMS does that, via
/assistant/console/sources/{source_uid}/audience).

Reporting `active` instead of these two is how a tool meant to find gaps ended
up hiding the biggest one. Fixed here: both scripts now report what retrieval
actually filters on, and say plainly what a customer can see as opposed to what
a staff member can.

Idempotent.
"""
import ast
import io
import sys

AUDIT = 'scripts/waswa_audit.py'
CORPUS = 'scripts/waswa_corpus_audit.py'

OLD_ROWS = """        ('  of those, from an approved source',
         "SELECT COUNT(*) FROM dll_waswa_chunks c JOIN dll_waswa_sources s "
         "ON s.source_uid = c.source_uid WHERE s.active"),"""

NEW_ROWS = """        # The two gates retrieval really applies. `active` is not one of them,
        # and reporting it made an invisible corpus look healthy.
        ('  of those, APPROVED (else unsearchable)',
         "SELECT COUNT(*) FROM dll_waswa_chunks "
         "WHERE review_status = 'approved'"),
        ('  of those, visible to CUSTOMERS',
         "SELECT COUNT(*) FROM dll_waswa_chunks "
         "WHERE review_status = 'approved' AND audience = 'everyone'"),
        ('  staff-only (audience = staff)',
         "SELECT COUNT(*) FROM dll_waswa_chunks WHERE audience = 'staff'"),"""

OLD_EMPTY = """    chunks = _count(cur, "SELECT COUNT(*) FROM dll_waswa_chunks")
    if isinstance(chunks, int) and chunks == 0:
        print('\\n   >> The knowledge base is EMPTY. Every question that is not')
        print('      about a vehicle is currently answered from gpt-4o\\'s own')
        print('      training, which knows nothing about NAVAS or OLIWA.')
        print('      Run: python scripts/ingest_waswa_knowledge.py')"""

NEW_EMPTY = """    chunks = _count(cur, "SELECT COUNT(*) FROM dll_waswa_chunks")
    if isinstance(chunks, int) and chunks == 0:
        print('\\n   >> The knowledge base is EMPTY. Every question that is not')
        print('      about a vehicle is currently answered from gpt-4o\\'s own')
        print('      training, which knows nothing about NAVAS or OLIWA.')
        print('      Run: python scripts/ingest_waswa_knowledge.py')
        return

    # Loaded is not the same as reachable, and the difference is the whole
    # explanation for a corpus that answers staff and not customers.
    approved = _count(cur, "SELECT COUNT(*) FROM dll_waswa_chunks "
                           "WHERE review_status = 'approved'")
    public = _count(cur, "SELECT COUNT(*) FROM dll_waswa_chunks "
                         "WHERE review_status = 'approved' "
                         "AND audience = 'everyone'")
    if isinstance(approved, int) and approved == 0:
        print('\\n   >> NOTHING IS APPROVED, so knowledge_search can never match.')
        print('      review_status defaults to \\'pending\\' and retrieval requires')
        print('      \\'approved\\'. The documents are loaded and unreachable.')
        print('      Fix: python scripts/ingest_waswa_knowledge.py --approve-all')
        print('      (or --approve <name> one at a time, which is safer)')
    elif isinstance(public, int) and public == 0:
        print('\\n   >> Approved, but NO chunk is visible to a customer.')
        print('      audience defaults to \\'staff\\', and --approve does not')
        print('      change it, so staff get answers and customers get none.')
        print('      Fix: set each customer-facing source\\'s audience to')
        print('      \\'everyone\\' in the CMS. Leave the level-5 internal')
        print('      documents on staff — they must not reach a customer.')"""

CORPUS_OLD = """        cur.execute(\"\"\"
            SELECT s.title, s.document_type, s.authority_level, s.category,
                   s.chunk_count, COUNT(c.chunk_uid)
              FROM dll_waswa_sources s
              LEFT JOIN dll_waswa_chunks c ON c.source_uid = s.source_uid
             GROUP BY s.title, s.document_type, s.authority_level, s.category,
                      s.chunk_count
             ORDER BY s.authority_level, s.title\"\"\")"""

CORPUS_NEW = """        cur.execute(\"\"\"
            SELECT s.title, s.document_type, s.authority_level, s.category,
                   s.chunk_count, COUNT(c.chunk_uid),
                   s.review_status, s.audience
              FROM dll_waswa_sources s
              LEFT JOIN dll_waswa_chunks c ON c.source_uid = s.source_uid
             GROUP BY s.title, s.document_type, s.authority_level, s.category,
                      s.chunk_count, s.review_status, s.audience
             ORDER BY s.authority_level, s.title\"\"\")"""

CORPUS_OLD_PRINT = """    print(f'   {"L":<3}{"type":<18}{"category":<18}{"chunks":>7}  title')
    for title, dtype, level, cat, declared, actual in rows:
        print(f'   {level:<3}{str(dtype)[:17]:<18}{str(cat)[:17]:<18}'
              f'{actual:>7}  {str(title)[:52]}')
        if declared and actual != declared:
            print(f'       !! manifest said {declared} chunks, {actual} present')"""

CORPUS_NEW_PRINT = """    print(f'   {"L":<3}{"status":<10}{"audience":<10}{"chunks":>7}  title')
    blocked = []
    for title, dtype, level, cat, declared, actual, status, audience in rows:
        print(f'   {level:<3}{str(status)[:9]:<10}{str(audience)[:9]:<10}'
              f'{actual:>7}  {str(title)[:46]}')
        if declared and actual != declared:
            print(f'       !! manifest said {declared} chunks, {actual} present')
        if status != 'approved':
            blocked.append((title, f'not approved ({status})'))
        elif audience != 'everyone' and level <= 4:
            blocked.append((title, 'approved but staff-only'))

    if blocked:
        print('\\n   Unreachable by a customer, and why:')
        for title, why in blocked:
            print(f'     - {str(title)[:56]:<58} {why}')
        print('\\n   These are loaded. They are not missing. They are gated.')"""


def patch(path, pairs, label):
    src = io.open(path, encoding='utf-8', newline='').read()
    done = []
    for old, new, note in pairs:
        if new.strip().splitlines()[0] in src or note in done:
            continue
        if old not in src:
            return f'!! {label}: could not find "{note}" verbatim'
        src = src.replace(old, new, 1)
        done.append(note)
    if not done:
        return f'{label}: already corrected'
    ast.parse(src)
    io.open(path, 'w', encoding='utf-8', newline='').write(src)
    return f'{label}: ' + ', '.join(done)


def main():
    print('  ' + patch(AUDIT, [
        (OLD_ROWS, NEW_ROWS, 'reports approved + customer-visible counts'),
        (OLD_EMPTY, NEW_EMPTY, 'names the gate that is shut'),
    ], 'waswa_audit'))
    print('  ' + patch(CORPUS, [
        (CORPUS_OLD, CORPUS_NEW, 'selects review_status and audience'),
        (CORPUS_OLD_PRINT, CORPUS_NEW_PRINT, 'lists what is gated and why'),
    ], 'waswa_corpus_audit'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
