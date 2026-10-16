#!/usr/bin/env python3
"""
i1_corpus_coverage.py -- does the corpus actually contain what Waswa said it
could not find?

Three of the six open I1 flags are Waswa reporting that it has no approved
document on a subject:

    [1] "What is VEBA escrow?"       -> recited user stories (prompt v6)
    [2] "what is veba?"              -> "no approved documents" (prompt v9)
    [4] "how do I created a new geofence" -> "I don't have the specific steps"

But flag [1]'s own answer cites the NAVAS Ecosystem Vision Scope Document, and
that file is sitting in database/knowledge/. So the knowledge exists. The
question is which link in the chain is broken, and the four candidates need
different fixes:

    not ingested      the file was never turned into a source + chunks
    not approved      review_status is not approved, so the gate hides it
    not active        superseded or removed
    not retrieved     ingested, approved, active -- but the search does not
                      find it for these words

This checks all four. Read-only: SELECTs only, no writes, no ingestion.

Usage:
    python scripts/i1_corpus_coverage.py
    python scripts/i1_corpus_coverage.py --term VEBA --term geofence
"""

import argparse
import sys

sys.path.insert(0, '.')

DEFAULT_TERMS = ['VEBA', 'escrow', 'geofence', 'geozone']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--term', action='append', default=None)
    args = ap.parse_args()
    terms = args.term or DEFAULT_TERMS

    import psycopg2
    import psycopg2.extras
    from config import DB_LINK

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # ---- 1. what is registered at all
            cur.execute("""
                SELECT review_status, active, (superseded_by IS NOT NULL) AS superseded,
                       COUNT(*) AS n, SUM(COALESCE(chunk_count, 0)) AS chunks
                FROM dll_waswa_sources
                GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
            """)
            print('dll_waswa_sources, by state')
            print('   %-16s %-7s %-11s %6s %8s'
                  % ('review_status', 'active', 'superseded', 'docs', 'chunks'))
            total = 0
            for r in cur.fetchall():
                total += r['n']
                print('   %-16s %-7s %-11s %6d %8s'
                      % (r['review_status'], r['active'], r['superseded'],
                         r['n'], r['chunks']))
            if not total:
                print('   (no sources registered at all -- nothing was ever ingested)')

            # ---- 2. is each term present, and WHICH SOURCE carries it
            #
            # The first version of this matched the term against document
            # TITLES. Nothing is titled "VEBA", so the title list came back
            # empty and `any([])` reported "no approved document carries it"
            # -- the exact opposite of the truth, while the summary table
            # above said all 12 documents are approved and active. Resolve
            # the chunks through to their own source instead.
            print('')
            print('Which approved source carries each term')
            for term in terms:
                print('')
                print('  %r' % term)
                cur.execute("""
                    SELECT s.title, s.review_status, s.active,
                           s.audience, s.authority_level,
                           COUNT(*) AS chunks
                    FROM dll_waswa_chunks c
                    JOIN dll_waswa_sources s ON s.source_uid = c.source_uid
                    WHERE c.body ILIKE %s
                    GROUP BY 1, 2, 3, 4, 5
                    ORDER BY chunks DESC
                """, ('%' + term + '%',))
                rows = cur.fetchall()
                if not rows:
                    print('     -> NOT IN THE CORPUS. Waswa was telling the truth;')
                    print('        this is an ingestion gap (resolution `document`).')
                    continue
                for r in rows:
                    print('     %-46s %-9s active=%-5s audience=%-9s auth=%s  %d chunk(s)'
                          % (str(r['title'])[:46], r['review_status'], r['active'],
                             r['audience'], r['authority_level'], r['chunks']))

                live = [r for r in rows
                        if r['review_status'] == 'approved' and r['active']]
                everyone = [r for r in live if r['audience'] == 'everyone']
                if not live:
                    print('     -> present, but nothing APPROVED + ACTIVE carries it.')
                    print('        The gate is hiding it (resolution `document`).')
                elif not everyone:
                    print('     -> approved and active, but STAFF-ONLY. A customer')
                    print('        asking this is correctly told there is nothing.')
                    print('        Fix is a customer-safe curated answer')
                    print('        (`correction`), not a document change.')
                else:
                    print('     -> approved, active and visible to everyone. If Waswa')
                    print('        still said it had nothing, the failure is')
                    print('        RETRIEVAL, not the corpus.')

            # ---- 3. the files on disk that were never registered
            print('')
            print('Files in database/knowledge/ vs registered sources')
            import os
            import glob
            disk = sorted(os.path.basename(p)
                          for p in glob.glob('database/knowledge/*.md'))
            cur.execute('SELECT title, source_uid FROM dll_waswa_sources')
            known = ' '.join(str(r['title'] or '') for r in cur.fetchall()).lower()
            for name in disk:
                stem = name.replace('.md', '').replace('_', ' ')[:38]
                seen = any(w in known for w in stem.split() if len(w) > 5)
                print('   %-52s %s' % (name, 'registered' if seen
                                       else 'NOT REGISTERED'))
    finally:
        conn.close()

    print('')
    print('  Reading this:')
    print('    NOT IN THE CORPUS   -> resolution `document`: ingest it')
    print('    gate is hiding it   -> resolution `document`: approve it')
    print('    RETRIEVAL           -> not a document fix. The search needs')
    print('                           work, or the answer needs curating')
    print('                           (`correction`).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
