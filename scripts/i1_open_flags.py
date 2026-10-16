#!/usr/bin/env python3
"""
i1_open_flags.py -- read the open Waswa feedback flags, with their context.

I1 is not a code defect. `dll_waswa_feedback` holds verdicts users gave on
Waswa's answers ('wrong', 'unhelpful', 'good'), and an open flag is one nobody
has acted on. Resolving each one means choosing between four outcomes, and
which is correct depends entirely on what the user actually flagged:

    correction   Waswa's answer was wrong and a curated answer should
                 override it           -> dll_waswa_answers
    document     the corpus was missing or wrong  -> upload / fix a document
    data_fix     the platform data behind the answer was wrong
    dismissed    the flag was not valid

So nothing can be decided without reading them. This prints each open flag
with the question that was asked, the answer Waswa gave, the user's note, and
the model/prompt version that produced it -- which is enough to make the call
for each one.

Read-only: SELECTs only. Nothing is resolved by this script; resolution goes
through POST /assistant/console/feedback/<uid>/resolve, which is permission
gated and writes an audit row.

Usage:
    python scripts/i1_open_flags.py
    python scripts/i1_open_flags.py --status open,in_review
    python scripts/i1_open_flags.py --verdict wrong
    python scripts/i1_open_flags.py --full        # untruncated answer text
"""

import argparse
import sys
import textwrap

sys.path.insert(0, '.')

QUERY = """
SELECT f.feedback_uid, f.verdict, f.status, f.note, f.surface,
       f.account_uid, f.created_at, f.assigned_to,
       f.message_uid, f.conversation_uid,
       a.content      AS answer_text,
       a.model, a.prompt_version, a.router_tier, a.intent,
       q.content      AS question_text,
       c.surface      AS conv_surface, c.language
FROM dll_waswa_feedback f
LEFT JOIN dll_waswa_messages a
       ON a.message_uid = f.message_uid
LEFT JOIN dll_waswa_conversations c
       ON c.conversation_uid = f.conversation_uid
-- the user turn immediately before the answer that was flagged
LEFT JOIN LATERAL (
    SELECT m.content
    FROM dll_waswa_messages m
    WHERE m.conversation_uid = f.conversation_uid
      AND m.role = 'user'
      AND m.turn_index < COALESCE(a.turn_index, 2147483647)
    ORDER BY m.turn_index DESC
    LIMIT 1
) q ON TRUE
WHERE f.status = ANY(%s)
  AND (%s IS NULL OR f.verdict = %s)
ORDER BY f.created_at ASC;
"""

COUNTS = """
SELECT status, verdict, COUNT(*)
FROM dll_waswa_feedback
GROUP BY status, verdict
ORDER BY status, verdict;
"""


def wrap(text, indent, width=86):
    if text is None:
        return indent + '(none)'
    body = ' '.join(str(text).split())
    return textwrap.fill(body, width=width,
                         initial_indent=indent, subsequent_indent=indent)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--status', default='open')
    ap.add_argument('--verdict', default=None)
    ap.add_argument('--full', action='store_true')
    args = ap.parse_args()

    import psycopg2
    import psycopg2.extras
    from config import DB_LINK

    statuses = [s.strip() for s in args.status.split(',') if s.strip()]

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            cur.execute(COUNTS)
            tally = cur.fetchall()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(QUERY, (statuses, args.verdict, args.verdict))
            rows = cur.fetchall()
    finally:
        conn.close()

    print('All feedback in dll_waswa_feedback')
    print('   %-12s %-12s %s' % ('status', 'verdict', 'count'))
    for status, verdict, n in tally:
        print('   %-12s %-12s %d' % (status, verdict, n))
    if not tally:
        print('   (the table is empty)')

    print('')
    print('=' * 92)
    print('  %d flag(s) with status in %s%s'
          % (len(rows), statuses,
             ', verdict=%s' % args.verdict if args.verdict else ''))
    print('=' * 92)

    for i, r in enumerate(rows, 1):
        print('')
        print('  [%d] %s   %s / %s   %s   %s'
              % (i, r['feedback_uid'], r['verdict'], r['status'],
                 r['created_at'], r['surface'] or r['conv_surface'] or '-'))
        print('      from %s%s'
              % (r['account_uid'],
                 '   assigned to %s' % r['assigned_to']
                 if r['assigned_to'] else ''))
        print('')
        print('      ASKED:')
        print(wrap(r['question_text'], ' ' * 8))
        print('')
        print('      WASWA ANSWERED  (model %s, prompt v%s, tier %s, intent %s):'
              % (r['model'] or '?', r['prompt_version'] or '?',
                 r['router_tier'] or '?', r['intent'] or '-'))
        answer = r['answer_text']
        if answer and not args.full and len(answer) > 700:
            answer = answer[:700] + ' ... [--full for the rest]'
        print(wrap(answer, ' ' * 8))
        print('')
        print('      THEIR NOTE:')
        print(wrap(r['note'], ' ' * 8))
        if r['answer_text'] is None:
            print('')
            print('      !! the flagged message_uid %s is not in'
                  % r['message_uid'])
            print('         dll_waswa_messages -- the turn was deleted or the')
            print('         uid is wrong. Cannot judge this one from the data.')
        print('      ' + '-' * 84)

    if not rows:
        print('')
        print('   Nothing open. If the queue says otherwise, the five flags')
        print('   were already resolved, or they sit in a status other than')
        print('   %s -- try --status open,in_review.' % args.status)
        return 0

    print('')
    print('  For each one the resolution is one of:')
    print('    correction  Waswa was wrong -> write a curated answer')
    print('    document    the corpus was missing or wrong -> fix a document')
    print('    data_fix    the platform data behind the answer was wrong')
    print('    dismissed   not a valid complaint')
    print('')
    print('  Resolve through POST /assistant/console/feedback/<uid>/resolve')
    print('  (permission gated, writes an audit row). This script only reads.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
