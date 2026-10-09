#!/usr/bin/env python3
"""
waswa_eval_cleanup.py -- remove exactly what one eval run created.

The trap this script exists for
-------------------------------
Only dll_waswa_messages has ON DELETE CASCADE from dll_waswa_conversations
(migration 030). These carry conversation_uid or message_uid with NO foreign
key at all:

    dll_waswa_evidence           message_uid
    dll_waswa_offers             conversation_uid, message_uid
    dll_waswa_transparency_log   conversation_uid, message_uid
    dll_waswa_feedback           conversation_uid, message_uid
    dll_waswa_answers            source_message_uid

So deleting conversations first cascades the messages away and leaves every
one of those pointing at rows that no longer exist. Nothing errors. The
damage is silent, and it lands on exactly the statistic this work has been
quoting all day -- "90 of 92 answers record what they were built from" is
computed by joining evidence to messages.

Children first, parents last. Always.

What it will and will not touch
-------------------------------
It deletes only the conversation_uids and message_uids recorded in a run
file. It never deletes by date, by account, or by "everything that looks like
a test". If the run file is missing, it does nothing.

It also refuses to delete a conversation that has grown since the run -- if
someone has since added turns to it, or left feedback on it, that is a real
conversation now and not litter.

Usage:
    python scripts/waswa_eval_cleanup.py tests/waswa_eval/runs/<file>.json
    python scripts/waswa_eval_cleanup.py <file>.json --dry-run
"""

import argparse
import io
import json
import os
import sys

sys.path.insert(0, '.')

# Children first. The order is the whole point of this file.
CHILDREN = [
    ('dll_waswa_evidence',         'message_uid'),
    ('dll_waswa_offers',           'message_uid'),
    ('dll_waswa_offers',           'conversation_uid'),
    ('dll_waswa_transparency_log', 'message_uid'),
    ('dll_waswa_transparency_log', 'conversation_uid'),
    ('dll_waswa_feedback',         'message_uid'),
    ('dll_waswa_feedback',         'conversation_uid'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run_file')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(args.run_file):
        print('no such run file: %s' % args.run_file)
        return 1

    with io.open(args.run_file, encoding='utf-8') as fh:
        run = json.load(fh)

    created = run.get('created') or {}
    convs = sorted(set(created.get('conversations') or []))
    msgs = sorted(set(created.get('messages') or []))

    if not convs and not msgs:
        print('this run created nothing. Nothing to remove.')
        return 0

    import psycopg2
    from config import DB_LINK

    conn = psycopg2.connect(DB_LINK)
    conn.autocommit = False          # one transaction; all or nothing
    try:
        with conn.cursor() as cur:
            print('=' * 80)
            print('  run %s' % run.get('started_at'))
            print('  %d conversation(s), %d message(s) recorded'
                  % (len(convs), len(msgs)))
            print('=' * 80)

            # --- refuse to touch anything that has grown since -----------
            keep = set()
            if convs:
                # The runner closes each conversation after its one question,
                # so a conversation it created holds exactly two turns: the
                # user's and the assistant's. The assistant turn's uid comes
                # back in the response and is in `msgs`; the user turn's does
                # not. Anything beyond that was put there by someone else.
                cur.execute(
                    "SELECT conversation_uid, COUNT(*) "
                    "FROM dll_waswa_messages "
                    "WHERE conversation_uid = ANY(%s) "
                    "GROUP BY conversation_uid", (convs,))
                for conv, turns in cur.fetchall():
                    if turns > 2:
                        keep.add(conv)
                        print('  KEEPING %s -- %d turns, more than the one '
                              'question this run asked' % (conv, turns))
                cur.execute(
                    "SELECT conversation_uid, COUNT(*) FROM dll_waswa_feedback "
                    "WHERE conversation_uid = ANY(%s) GROUP BY conversation_uid",
                    (convs,))
                for conv, votes in cur.fetchall():
                    keep.add(conv)
                    print('  KEEPING %s -- %d feedback row(s) on it'
                          % (conv, votes))

            convs = [c for c in convs if c not in keep]
            if not convs and not msgs:
                print('')
                print('  nothing left to remove.')
                conn.rollback()
                return 0

            # --- children first ------------------------------------------
            removed = []
            for table, column in CHILDREN:
                ids = msgs if column == 'message_uid' else convs
                if not ids:
                    continue
                cur.execute(
                    "DELETE FROM %s WHERE %s = ANY(%%s)" % (table, column),
                    (ids,))
                if cur.rowcount:
                    removed.append((table, column, cur.rowcount))

            # dll_waswa_answers is a CURATED table. Its rows are somebody's
            # work. Only the pointer is cleared, never the answer.
            cur.execute(
                "UPDATE dll_waswa_answers SET source_message_uid = NULL "
                "WHERE source_message_uid = ANY(%s)", (msgs,))
            if cur.rowcount:
                removed.append(('dll_waswa_answers', 'source_message_uid '
                                '(cleared, not deleted)', cur.rowcount))

            # --- then the messages, then the conversations ---------------
            if msgs:
                cur.execute(
                    "DELETE FROM dll_waswa_messages WHERE message_uid = ANY(%s)",
                    (msgs,))
                if cur.rowcount:
                    removed.append(('dll_waswa_messages', 'message_uid',
                                    cur.rowcount))
            if convs:
                cur.execute(
                    "DELETE FROM dll_waswa_conversations "
                    "WHERE conversation_uid = ANY(%s)", (convs,))
                if cur.rowcount:
                    removed.append(('dll_waswa_conversations',
                                    'conversation_uid', cur.rowcount))

            print('')
            for table, column, count in removed:
                print('  %-28s %-34s %d row(s)' % (table, column, count))
            if not removed:
                print('  nothing matched. Already cleaned up?')

            # --- prove no orphan was created -----------------------------
            cur.execute(
                "SELECT COUNT(*) FROM dll_waswa_evidence e "
                "LEFT JOIN dll_waswa_messages m USING (message_uid) "
                "WHERE m.message_uid IS NULL")
            orphans = cur.fetchone()[0]
            print('')
            print('  evidence rows with no message: %d' % orphans)
            if orphans:
                print('  NOT COMMITTING -- this delete would leave orphans,')
                print('  which is the exact failure this script exists to')
                print('  prevent. Rolling back.')
                conn.rollback()
                return 1

            if args.dry_run:
                print('  --dry-run: rolling back.')
                conn.rollback()
                return 0

            conn.commit()
            print('  committed.')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
