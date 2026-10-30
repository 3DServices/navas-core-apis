#!/usr/bin/env python3
"""
i1_wallet_check.py -- is flag [3]'s "231 unactivated packs" a wrong number, or
a correctly aggregated one described with the wrong word?

Flag [3] (feedback 295e86ee..., verdict 'wrong', oliwa_console, prompt v9):

    Q: How many tokens do I have?
    A: "You have 120 token units remaining across the packs currently in use.
        Additionally, you hold 231 packs that haven't been activated yet."

231 looked implausible, especially beside flag [6] where a different account
reports no packs at all -- and tests/test_wallet_owner.py exists because
wallet OWNER RESOLUTION has been wrong before. If one account were being shown
another's balance that would be data exposure, not a chatbot bug, so it is the
highest-severity item in I1.

But resolve_wallet_owner() returns (client_uid, owner_uids) BY DESIGN: a
company's tokens live under the company, while some packs are keyed by the
login that bought them, and _token_position() sums across the whole family.
So a company-wide figure shown to a team member is correct behaviour -- and
calling it "you have" is then a wording problem, not a data one.

This separates the two. It prints:

  * what resolve_wallet_owner() returns for the account that complained
  * every owner uid, with the account_root it actually belongs to
  * per-owner pack counts, so the aggregate can be seen being assembled
  * the same totals _token_position() computes
  * THE EXPOSURE CHECK: whether any owner uid resolves to a different
    account_root than the asker's. test_another_company_is_never_pulled_in()
    asserts this cannot happen; this verifies it against live data.

Read-only. SELECTs only.

Usage:
    python scripts/i1_wallet_check.py
    python scripts/i1_wallet_check.py --uid <account_uid>
"""

import argparse
import sys

sys.path.insert(0, '.')

# the account that raised flag [3], and the one from flags [5] and [6]
COMPLAINANT = 'f8e17a96-b5b1-483b-938d-7cf4673692f6'
COMPARISON = '3f20c477-4446-4070-ad96-79aaa6877bd9'


def look(cur, uid, label):
    from endpoints.globals import resolve_wallet_owner

    print('')
    print('=' * 78)
    print('  %s   %s' % (label, uid))
    print('=' * 78)

    cur.execute("SELECT account_root FROM dll_access_relay WHERE account_uid=%s",
                (uid,))
    row = cur.fetchone()
    asker_root = str(row[0]).strip() if row and row[0] else '(none)'
    print('   this login\'s account_root        : %s' % asker_root)

    client_uid, owner_uids = resolve_wallet_owner(cur, uid)
    print('   resolve_wallet_owner -> client   : %s' % client_uid)
    print('   resolve_wallet_owner -> owners   : %d uid(s)' % len(owner_uids))

    # --- THE EXPOSURE CHECK
    cur.execute(
        "SELECT account_uid, account_root FROM dll_access_relay "
        "WHERE account_uid = ANY(%s)", (list(owner_uids),))
    relays = {r[0]: (str(r[1]).strip() if r[1] else '') for r in cur.fetchall()}
    foreign = [(u, r) for u, r in relays.items()
               if r and r != client_uid and u != client_uid]
    print('')
    if foreign:
        print('   !! EXPOSURE: %d owner uid(s) belong to a DIFFERENT client:'
              % len(foreign))
        for u, r in foreign[:8]:
            print('        %s -> root %s' % (u, r))
        print('      This wallet is aggregating across companies. That is a')
        print('      data-exposure bug, not an answer-quality one.')
    else:
        print('   exposure check: every owner uid belongs to this client.')
        print('   No other company is pulled in.')

    # --- per-owner rows, so the aggregate can be watched being built
    cur.execute(
        "SELECT client_uid, COUNT(*) AS packs, "
        "       COUNT(*) FILTER (WHERE LOWER(token_status)='active') AS active, "
        "       COUNT(*) FILTER (WHERE token_units_left ~ '^[0-9]+(\\.[0-9]+)?$') "
        "         AS numeric_rows "
        "FROM dll_user_token_accounts WHERE client_uid = ANY(%s) "
        "GROUP BY 1 ORDER BY packs DESC", (list(owner_uids),))
    rows = cur.fetchall()
    print('')
    print('   packs per owner uid')
    if not rows:
        print('      none -- this family holds no token packs at all')
    total = 0
    for client, packs, active, numeric in rows:
        total += packs
        tag = '  <- the company itself' if client == client_uid else ''
        print('      %-40s %4d pack(s), %d active, %d with a numeric balance%s'
              % (client, packs, active, numeric, tag))
    print('      %-40s %4d total' % ('', total))

    # --- the same totals the assistant reports
    try:
        from endpoints.waswa_context import _token_position
        position, reason = _token_position(cur, uid)
        print('')
        print('   _token_position() -- what Waswa was told')
        if position is None:
            print('      nothing (%s)' % reason)
        else:
            for key in sorted(position):
                print('      %-30s %s' % (key, position[key]))
    except Exception as error:              # noqa: BLE001
        print('   _token_position() raised: %s'
              % str(error).split('\n')[0][:66])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--uid', action='append', default=None)
    args = ap.parse_args()

    import psycopg2
    from config import DB_LINK
    from app import app

    ctx = app.app_context()
    ctx.push()
    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            if args.uid:
                for uid in args.uid:
                    look(cur, uid, 'account')
            else:
                look(cur, COMPLAINANT, 'flag [3] — said 120 units / 231 packs')
                look(cur, COMPARISON, 'flags [5][6] — said no packs at all')
    finally:
        conn.close()

    print('')
    print('  Reading this:')
    print('    exposure flagged          -> a data bug. Stop and fix it.')
    print('    no exposure, 231 matches  -> the number is RIGHT and the word')
    print('                                 "you" is wrong. The answer should')
    print('                                 say whose wallet it is.')
    print('                                 Resolution: `correction`.')
    print('    no exposure, 231 does NOT')
    print('    match the rows            -> `data_fix`: the figure is being')
    print('                                 assembled wrongly.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
