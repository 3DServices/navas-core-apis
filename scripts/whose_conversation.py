#!/usr/bin/env python3
"""
whose_conversation.py -- identify an open conversation before writing near it.

The eval runner refused to start because an open conversation already exists
for an account it would use. Before deciding what to do about it, the question
is simply: whose is it, and what is in it?

This also settles a timezone question. dll_waswa_conversations.last_activity_at
is TIMESTAMP without time zone and defaults to NOW(). If the database server
runs UTC and you read the value as local time, a conversation from five
minutes ago looks three hours old -- and the 60-minute resume window in
_resume_or_open_conversation compares that column against the database's own
NOW(), so what matters is whether everything writing to it agrees. The report
below prints both so there is nothing to infer.

Read-only.

Usage:
    python scripts/whose_conversation.py 7cf76c67-21d5-46fe-8695-82cc45a5ac80
    python scripts/whose_conversation.py --open-only
"""

import argparse
import sys

sys.path.insert(0, '.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('conversation_uid', nargs='?', default=None)
    ap.add_argument('--open-only', action='store_true',
                    help='list every open conversation instead of one')
    args = ap.parse_args()

    import psycopg2
    from config import DB_LINK

    conn = psycopg2.connect(DB_LINK)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT NOW(), NOW() AT TIME ZONE 'UTC', "
                        "current_setting('TimeZone')")
            now, now_utc, tz = cur.fetchone()
            print('=' * 84)
            print('  database clock')
            print('=' * 84)
            print('  NOW()                %s' % now)
            print('  NOW() at UTC         %s' % now_utc)
            print('  server TimeZone      %s' % tz)
            print('  (your shell said it was just after midnight EAT)')
            print('')

            if args.open_only or not args.conversation_uid:
                cur.execute(
                    "SELECT conversation_uid, account_uid, surface, "
                    "       started_at, last_activity_at, "
                    "       NOW() - last_activity_at AS idle, "
                    "       (SELECT COUNT(*) FROM dll_waswa_messages m "
                    "         WHERE m.conversation_uid = c.conversation_uid) "
                    "FROM dll_waswa_conversations c "
                    "WHERE status = 'open' "
                    "ORDER BY last_activity_at DESC LIMIT 20")
                rows = cur.fetchall()
                print('=' * 84)
                print('  every open conversation (%d)' % len(rows))
                print('=' * 84)
                for uid, acct, surface, started, last, idle, turns in rows:
                    print('  %s' % uid)
                    print('      account %s  surface %s' % (acct, surface))
                    print('      started %s, last %s, idle %s, %d turn(s)'
                          % (started, last, idle, turns))
                if not rows:
                    print('  none.')
                print('')

            if args.conversation_uid:
                uid = args.conversation_uid
                cur.execute(
                    "SELECT account_uid, account_root, client_uid, surface, "
                    "       status, started_at, last_activity_at, "
                    "       NOW() - last_activity_at "
                    "FROM dll_waswa_conversations WHERE conversation_uid = %s",
                    (uid,))
                row = cur.fetchone() if cur.rowcount else None
                print('=' * 84)
                print('  conversation %s' % uid)
                print('=' * 84)
                if not row:
                    print('  no such conversation.')
                    return 0
                acct, root, client, surface, status, started, last, idle = row
                print('  account      %s' % acct)
                print('  client       %s' % client)
                print('  surface      %s' % surface)
                print('  status       %s' % status)
                print('  started      %s' % started)
                print('  last active  %s   (idle %s)' % (last, idle))
                print('')
                cur.execute(
                    "SELECT turn_index, role, LEFT(content, 220), "
                    "       model, prompt_version, created_at "
                    "FROM dll_waswa_messages WHERE conversation_uid = %s "
                    "ORDER BY turn_index", (uid,))
                print('  turns')
                for idx, role, content, model, pv, created in cur.fetchall():
                    print('')
                    print('    [%s] %-9s %s  model=%s prompt=%s'
                          % (idx, role, created, model, pv))
                    print('        %s' % ' '.join(str(content or '').split()))
                print('')
                print('  Is this one of the eval run\'s own conversations?')
                print('  The pricing rows were asked on surface "mobile".')
                print('  A conversation on any other surface was not made by')
                print('  that run.')
    finally:
        conn.close()
    print('')
    print('  Read-only. Nothing was written.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
