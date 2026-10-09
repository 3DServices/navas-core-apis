#!/usr/bin/env python3
"""
i1_retrieval_funnel.py -- which filter drops the VEBA chunks?

Three of the six open I1 flags are Waswa saying it has no document on a
subject the corpus demonstrably covers:

    "what is veba?"                 -> "I don't have any approved documents"
                                       ...against 132 approved, active,
                                       everyone-visible chunks in 6 documents
    "how do I created a new geofence" -> "I don't have the specific steps"
                                       ...against 54 chunks in the CMS manual

So the corpus is fine and retrieval is losing them. Reading the code narrowed
it to a handful of candidates but could not choose between them, and guessing
has been wrong repeatedly on this codebase. This counts how many chunks
survive each filter in turn, so the funnel names the culprit instead.

The chain, from endpoints/waswa_knowledge.py and vw_waswa_retrievable:

    body ILIKE '%term%'                 the honest baseline
    -> s.active AND s.superseded_by IS NULL
    -> a.may_quote = TRUE               an authority level can be unquotable
    -> review_status = 'approved'
    -> audience = ANY(caller's)         'everyone' unless the caller is staff
    -> search_vector @@ <tsquery>       the text match itself
    -> ts_rank_cd * ((7-authority)/6) >= _MIN_SCORE

The last two are the interesting ones. The authority multiplier HALVES a
level-4 chunk's score and takes a level-5 chunk to a third, so the threshold
bites unevenly -- a chunk can match the query perfectly and still be cut for
sitting in a less authoritative document.

Read-only. It also runs the real knowledge_search() so the funnel can be
checked against what Waswa actually gets.

Usage:
    python scripts/i1_retrieval_funnel.py
    python scripts/i1_retrieval_funnel.py --query "what is veba?" --term VEBA
"""

import argparse
import sys

sys.path.insert(0, '.')

CASES = [
    ('what is veba?', 'VEBA'),
    ('What is VEBA escrow?', 'VEBA'),
    ('how do I created a new geofence', 'geofence'),
    ('how do I create a geofence', 'geofence'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--query')
    ap.add_argument('--term')
    ap.add_argument('--audience', default='everyone')
    args = ap.parse_args()
    cases = [(args.query, args.term or args.query)] if args.query else CASES

    import psycopg2
    import psycopg2.extras
    from config import DB_LINK
    from endpoints import waswa_knowledge as wk

    # knowledge_search() reads current_app.config, so it needs an application
    # context. Without one it raises "Working outside of application context"
    # and the funnel silently loses the one measurement that matters -- which
    # is exactly what the first version of this script did.
    from app import app
    _ctx = app.app_context()
    _ctx.push()

    print('_MIN_SCORE = %s   audience = %r' % (wk._MIN_SCORE, args.audience))

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT authority_level, label, may_quote, confirmed "
                        "FROM dll_waswa_authority_levels ORDER BY 1")
            print('')
            print('authority levels (may_quote FALSE removes a level entirely)')
            for r in cur.fetchall():
                mark = '' if r['may_quote'] else '   <-- UNQUOTABLE'
                print('   %d  %-34s may_quote=%-5s confirmed=%-5s%s'
                      % (r['authority_level'], str(r['label'])[:34],
                         r['may_quote'], r['confirmed'], mark))

            for query, term in cases:
                print('')
                print('=' * 78)
                print('  query %r   (term %r)' % (query, term))
                print('=' * 78)

                steps = [
                    ('body mentions the term',
                     "SELECT COUNT(*) AS n FROM dll_waswa_chunks c "
                     "WHERE c.body ILIKE %(like)s"),
                    ('+ source active, not superseded',
                     "SELECT COUNT(*) AS n FROM dll_waswa_chunks c "
                     "JOIN dll_waswa_sources s ON s.source_uid=c.source_uid "
                     "WHERE c.body ILIKE %(like)s AND s.active "
                     "AND s.superseded_by IS NULL"),
                    ('+ authority may_quote',
                     "SELECT COUNT(*) AS n FROM vw_waswa_retrievable c "
                     "WHERE c.body ILIKE %(like)s"),
                    ("+ review_status approved",
                     "SELECT COUNT(*) AS n FROM vw_waswa_retrievable c "
                     "WHERE c.body ILIKE %(like)s "
                     "AND c.review_status='approved'"),
                    ('+ audience visible to caller',
                     "SELECT COUNT(*) AS n FROM vw_waswa_retrievable c "
                     "WHERE c.body ILIKE %(like)s "
                     "AND c.review_status='approved' "
                     "AND c.audience = ANY(%(aud)s)"),
                    ('+ search_vector matches the tsquery',
                     "SELECT COUNT(*) AS n FROM vw_waswa_retrievable c, "
                     "plainto_tsquery('english', %(q)s) AS q "
                     "WHERE c.search_vector @@ q "
                     "AND c.review_status='approved' "
                     "AND c.audience = ANY(%(aud)s)"),
                    ('+ score >= _MIN_SCORE  (THE THRESHOLD)',
                     "SELECT COUNT(*) AS n FROM vw_waswa_retrievable c, "
                     "plainto_tsquery('english', %(q)s) AS q "
                     "WHERE c.search_vector @@ q "
                     "AND c.review_status='approved' "
                     "AND c.audience = ANY(%(aud)s) "
                     "AND ts_rank_cd(c.search_vector, q, 32) "
                     "    * ((7 - c.authority_level)::numeric/6) >= %(minscore)s"),
                ]
                params = {'like': '%' + term + '%', 'q': query,
                          'aud': wk._audiences(args.audience),
                          'minscore': wk._MIN_SCORE}
                previous = None
                for label, sql in steps:
                    cur.execute(sql, params)
                    n = cur.fetchone()['n']
                    drop = '' if previous is None or n == previous \
                        else '   (-%d)' % (previous - n)
                    flag = '   <<< everything lost here' if (
                        previous and n == 0) else ''
                    print('   %-42s %5d%s%s' % (label, n, drop, flag))
                    previous = n

                # what scores do the matching chunks actually get?
                cur.execute(
                    "SELECT c.source_title, c.authority_level, "
                    "       ts_rank_cd(c.search_vector, q, 32) AS raw, "
                    "       ts_rank_cd(c.search_vector, q, 32) "
                    "         * ((7 - c.authority_level)::numeric/6) AS scaled "
                    "FROM vw_waswa_retrievable c, "
                    "     plainto_tsquery('english', %(q)s) AS q "
                    "WHERE c.search_vector @@ q "
                    "AND c.review_status='approved' "
                    "AND c.audience = ANY(%(aud)s) "
                    "ORDER BY scaled DESC LIMIT 5", params)
                top = cur.fetchall()
                if top:
                    print('')
                    print('   best scores among the matching chunks:')
                    for r in top:
                        verdict = 'passes' if float(r['scaled']) >= wk._MIN_SCORE \
                            else 'CUT by the threshold'
                        print('     %-40s auth=%d raw=%.5f scaled=%.5f  %s'
                              % (str(r['source_title'])[:40],
                                 r['authority_level'], r['raw'], r['scaled'],
                                 verdict))

                # The funnel above only exercises plainto_tsquery -- tier 2
                # of three. _search() tries websearch_to_tsquery first and an
                # OR-of-terms tier last, and that last tier is what should
                # rescue a query like "how do I created a NEW geofence" where
                # the AND of every word matches nothing. Only the real call
                # shows which tier answered.
                print('')
                try:
                    result = wk.knowledge_search(query, limit=5)
                    hits = (result.get('results') or result.get('chunks')
                            or result.get('passages') or [])
                    how = (result.get('how_matched') or result.get('matched_by')
                           or result.get('match') or '?')
                    print('   knowledge_search() -> %d result(s), matched by %r%s'
                          % (len(hits), how,
                             '   <<< THIS is what Waswa saw' if not hits else ''))
                    for h in hits[:3]:
                        print('      %-46s auth=%s'
                              % (str(h.get('source_title') or h.get('title'))[:46],
                                 h.get('authority_level', '?')))
                    if not hits:
                        print('      all three tiers returned nothing, so the')
                        print('      refusal was honest for THIS query text.')
                    else:
                        print('      retrieval had material. If Waswa still said')
                        print('      it had nothing, the tool was not called or')
                        print('      its results were ignored -- not a search bug.')
                except Exception as error:          # noqa: BLE001
                    print('   knowledge_search() raised: %s'
                          % str(error).split('\n')[0][:70])
    finally:
        conn.close()

    print('')
    print('  Read the funnel for the row where the count falls to zero.')
    print('  If it is the THRESHOLD row, the fix is _MIN_SCORE or the')
    print('  authority multiplier, not the corpus and not the prompt.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
