#!/usr/bin/env python3
"""
waswa_eval_accounts.py -- which account, and which client, was each flagged
answer actually about?

Why
---
"How many tokens do I have?" carries four feedback rows with two flatly
contradictory answers four days apart:

    29 Sep 11:10  "120 token units remaining ... 231 packs not activated"  wrong
    29 Sep 23:21  "doesn't have any token packs yet ... no tokens"         good
    01 Oct 11:21  "doesn't have any token packs yet ... 0 token units"     good
    02 Oct 22:42  "doesn't have any token packs yet."                      unhelpful

Both can be correct if they are different wallets, and both cannot be correct
if they are the same wallet. The eval set has no defined expected answer for
an account question until that is settled, and the user verdicts cannot settle
it -- two people marked "no tokens" good, which is only right if the account
really is empty.

The thing that decides it is NOT account_uid. dll_waswa_feedback stores
account_uid and no client_uid at all, but every figure Waswa reports is read
by client_uid:

    dll_waswa_feedback.account_uid
        -> dll_access_relay.account_root        (that IS the client_uid)
            -> resolve_wallet_owner()           (widens to the account family)
                -> dll_user_token_accounts.client_uid = ANY(family)

So two different account_uids under one company share one wallet and must
give the SAME answer, and endpoints/globals.py:346 documents the bug where
asking with a non-owner account_uid returned an empty wallet -- which is
exactly what "you don't have any token packs yet" looks like.

This script resolves each flagged account through the real production
functions -- it imports resolve_wallet_owner and _token_position rather than
re-implementing them, so what it reports is what Waswa reads -- and prints the
current position. Read-only: SELECTs only.

Usage:
    python scripts/waswa_eval_accounts.py
"""

import sys
import textwrap

sys.path.insert(0, '.')

ROWS = """
SELECT f.feedback_uid, f.verdict, f.status, f.created_at,
       f.account_uid        AS feedback_account_uid,
       f.message_uid,
       c.account_uid        AS conv_account_uid,
       c.client_uid         AS conv_client_uid,
       c.surface            AS conv_surface,
       a.content            AS answer_text,
       a.prompt_version,
       q.content            AS question_text
FROM dll_waswa_feedback f
LEFT JOIN dll_waswa_messages a
       ON a.message_uid = f.message_uid
LEFT JOIN dll_waswa_conversations c
       ON c.conversation_uid = f.conversation_uid
LEFT JOIN LATERAL (
    SELECT m.content
    FROM dll_waswa_messages m
    WHERE m.conversation_uid = f.conversation_uid
      AND m.role = 'user'
      AND m.turn_index < COALESCE(a.turn_index, 2147483647)
    ORDER BY m.turn_index DESC
    LIMIT 1
) q ON TRUE
ORDER BY f.created_at ASC;
"""

RELAY = """
SELECT account_root, account_type, account_clearance, display_name
FROM dll_access_relay WHERE account_uid = %s;
"""


def one_line(text, n=150):
    body = ' '.join(str(text or '').split())
    return body if len(body) <= n else body[:n - 1] + '…'


def main():
    import psycopg2
    from config import DB_LINK
    from endpoints.globals import resolve_wallet_owner
    from endpoints.waswa_context import _token_position, _subscribed_units

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            cur.execute(ROWS)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        print('=' * 94)
        print('  every feedback row, with the account and client behind it')
        print('=' * 94)
        print('  %-18s %-10s %-9s %-14s %-14s %s'
              % ('when', 'verdict', 'prompt', 'feedback acct',
                 'conv acct', 'conv client'))
        mismatch = []
        for r in rows:
            fa = str(r['feedback_account_uid'] or '-')
            ca = str(r['conv_account_uid'] or '-')
            cc = str(r['conv_client_uid'] or '-')
            if fa != ca:
                mismatch.append(r['feedback_uid'])
            print('  %-18s %-10s %-9s %-14s %-14s %s'
                  % (str(r['created_at'])[:16], r['verdict'],
                     r['prompt_version'], fa[:14], ca[:14], cc[:20]))

        print('')
        if mismatch:
            print('  NOTE: %d row(s) where the account that GAVE the feedback is'
                  % len(mismatch))
            print('  not the account that asked. For those, the conversation')
            print('  account is the one the answer was about:')
            for uid in mismatch:
                print('      %s' % uid)
        else:
            print('  In every row the account that gave the feedback is the')
            print('  account that asked. feedback.account_uid is safe to use.')
        print('')

        # ---- resolve every distinct account ----
        accounts = []
        for r in rows:
            for uid in (r['feedback_account_uid'], r['conv_account_uid']):
                if uid and uid not in accounts:
                    accounts.append(uid)

        print('=' * 94)
        print('  each account resolved the way Waswa resolves it')
        print('=' * 94)

        resolved = {}
        with conn.cursor() as cur:
            for uid in accounts:
                cur.execute(RELAY, (str(uid),))
                relay = cur.fetchone() if cur.rowcount else None
                client_uid = relay[0] if relay else None
                family = None
                if client_uid:
                    _, family = resolve_wallet_owner(cur, client_uid)
                resolved[uid] = {'relay': relay, 'client_uid': client_uid,
                                 'family': family}

                print('')
                print('  account_uid   %s' % uid)
                if not relay:
                    print('    NO dll_access_relay ROW. Waswa can resolve no')
                    print('    data at all for this account -- every slot would')
                    print('    come back unknown.')
                    continue
                print('    account_root / client_uid   %s' % relay[0])
                print('    account_type                %s' % relay[1])
                print('    clearance                   %s' % relay[2])
                print('    display_name                %s' % relay[3])
                print('    is this the account owner?  %s'
                      % ('yes - account_uid == client_uid'
                         if str(uid) == str(relay[0])
                         else 'NO - a login under the company'))
                print('    wallet owner family         %s' % (family,))

                pos, reason = _token_position(cur, client_uid)
                if pos:
                    print('    TOKENS NOW   packs=%s active=%s units_left=%s '
                          'used=%s'
                          % (pos.get('token_packs'),
                             pos.get('active_token_packs'),
                             pos.get('token_units_left', '(not reported)'),
                             # the key is token_units_USED, not
                             # token_USED_units -- the wrong spelling printed
                             # "(not reported)" over a real figure
                             pos.get('token_units_used', '(not reported)')))
                    extra = {k: v for k, v in pos.items()
                             if k not in ('token_packs', 'active_token_packs',
                                          'token_units_left',
                                          'token_units_used', 'burn_rate')}
                    for k, v in extra.items():
                        print('                 %-24s %s' % (k, v))
                else:
                    print('    TOKENS NOW   none -- %s' % reason)

                units, ureason = _subscribed_units(cur, client_uid)
                print('    UNITS NOW    %s' % (units if units else
                                               'none -- %s' % ureason))

        # ---- the verdict on the contradiction ----
        print('')
        print('=' * 94)
        print('  the contradiction')
        print('=' * 94)
        clients = {}
        for uid, info in resolved.items():
            clients.setdefault(str(info['client_uid']), []).append(str(uid))
        print('  distinct clients behind all flagged accounts: %d'
              % len(clients))
        for cuid, uids in clients.items():
            print('      client %-22s accounts %s' % (cuid, ', '.join(uids)))
        print('')
        if len(clients) == 1:
            print('  SAME CLIENT. Then "120 units / 231 packs" and "no token')
            print('  packs at all" are two answers to ONE wallet, and one of')
            print('  them is wrong. That is a data or scoping defect, not a')
            print('  difference of accounts, and the two "good" verdicts were')
            print('  given to an answer nobody could verify.')
        else:
            print('  DIFFERENT CLIENTS. Then both answers can be correct, the')
            print('  verdict conflict dissolves, and each account question in')
            print('  the eval set must be asked as a named account_uid with')
            print('  its own expected answer. Compare the TOKENS NOW figures')
            print('  above against what each answer claimed.')
        print('')
        print('  Reminder on timing: resolve_wallet_owner landed 2026-09-30')
        print('  (commit 3892ca0). Answers dated 29 Sep predate it; answers')
        print('  dated 01-02 Oct do not. An empty wallet reported BOTH before')
        print('  and after that fix is a real empty wallet, not the bug.')

        print('')
        print('=' * 94)
        print('  the two token answers, verbatim')
        print('=' * 94)
        for r in rows:
            q = ' '.join(str(r['question_text'] or '').split()).lower()
            if 'token' in q and ('how many' in q or 'do i have' in q):
                print('')
                print('  %s  verdict=%-10s acct=%s'
                      % (str(r['created_at'])[:16], r['verdict'],
                         r['conv_account_uid'] or r['feedback_account_uid']))
                print(textwrap.fill(one_line(r['answer_text'], 400),
                                    width=88, initial_indent='      ',
                                    subsequent_indent='      '))
    finally:
        conn.close()
    print('')
    print('  Read-only. Nothing was written.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
