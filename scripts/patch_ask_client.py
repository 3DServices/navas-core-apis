#!/usr/bin/env python3
"""waswa_ask.py asked the right questions as the wrong person.

    account : 1a1db65e-52d5-493b-a1a9-7e495005530a
    role    : super_admin / inhouse   root=engine

That is a 3D Services staff login whose account_root is "engine". It owns no
vehicles, so unit_find correctly found none, and Waswa correctly said so:

    "I can't find any vehicles registered to this account, including UBF 364U."

The answer is right. The test was wrong. UBF 364U belongs to client
NzQwNTk0NzI2NzA5NTM5NjQz, and nothing told anyone that the account being used
was a different tenant — the script picked "whoever asked Waswa last", which
happened to be staff.

Two changes so this cannot mislead again:

  --client <uid>   resolve a real login under that client, via dll_access_relay
                   (account_root = client_uid), and ask as them.

  a pre-flight      count the vehicles the chosen account can actually see, and
                    say so BEFORE the questions run. An empty fleet is then a
                    stated fact about the test rather than a surprise in the
                    answers.

Idempotent.
"""
import ast
import io
import sys

PATH = 'scripts/waswa_ask.py'

RESOLVER = '''
def login_under_client(cur, client_uid):
    """A login that belongs to this client, so the test runs as its customer.

    dll_access_relay.account_root is the client an account hangs off — the same
    join resolve_wallet_owner uses for token balances. Preference goes to an
    account that has a permissions record, because one without cannot sign in
    and would fail at the token step.
    """
    cur.execute("""
        SELECT r.account_uid
          FROM dll_access_relay r
         WHERE r.account_root = %s
         ORDER BY (EXISTS (SELECT 1 FROM dll_access_relay x
                            WHERE x.account_uid = r.account_uid)) DESC,
                  r.account_uid
         LIMIT 5""", (str(client_uid),))
    rows = [r[0] for r in (cur.fetchall() or [])]
    return rows


def fleet_size(account, client_uid=None):
    """How many vehicles the chosen account can see, before anything is asked.

    Printed up front on purpose. "I can't find any vehicles" is a correct answer
    for an account with none, and indistinguishable from a bug unless you knew
    the fleet was empty going in.
    """
    from flask import Flask
    from endpoints import waswa_fleet
    probe = Flask(__name__)
    probe.config['db_link'] = DB_LINK
    try:
        with probe.app_context():
            scope = waswa_fleet.build_scope(account, client_uid, is_staff=False)
            found = waswa_fleet.unit_find(scope=scope)
        return found.get('count') if found.get('found') else 0
    except Exception as error:      # noqa: BLE001
        return f'could not be read ({error.__class__.__name__})'

'''

OLD_ARGS = """    ap.add_argument('--account', help='account_uid to ask as')"""
NEW_ARGS = """    ap.add_argument('--account', help='account_uid to ask as')
    ap.add_argument('--client', help='ask as a login belonging to this client_uid')"""

OLD_PICK = """    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            account = args.account or last_real_asker(cur)
            if not account:
                print('No account_uid given and none found in '
                      'dll_waswa_conversations. Pass --account.')
                return 1
    finally:
        conn.close()"""

NEW_PICK = """    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            account = args.account
            if not account and args.client:
                candidates = login_under_client(cur, args.client)
                if not candidates:
                    print(f'No login hangs off client {args.client} in '
                          f'dll_access_relay. Pass --account instead.')
                    return 1
                account = candidates[0]
                if len(candidates) > 1:
                    print(f'note: {len(candidates)} logins under this client; '
                          f'using {account}')
            account = account or last_real_asker(cur)
            if not account:
                print('No account_uid given and none found in '
                      'dll_waswa_conversations. Pass --account or --client.')
                return 1
    finally:
        conn.close()"""

OLD_BANNER = """    print(f'surface : {args.surface}        -> {args.url}')
    print('(the role is read from the database, not chosen here, so these are '
          'the answers this account really gets)')"""

NEW_BANNER = """    print(f'surface : {args.surface}        -> {args.url}')
    print('(the role is read from the database, not chosen here, so these are '
          'the answers this account really gets)')

    # Said before the questions, not discovered through them.
    units = fleet_size(account, args.client)
    print(f'vehicles this account can see : {units}')
    if units == 0:
        print('   >> This account owns NO vehicles, so "I cannot find any')
        print('      vehicles" is the CORRECT answer to a vehicle question —')
        print('      not a bug. To test the fleet answers, ask as a customer')
        print('      of a client that has units:')
        print('        python scripts/waswa_ask.py --client <CLIENT_UID>')
    if str(acc_type or '').lower() in ('inhouse', 'service_provider', 'ussrx'):
        print(f'   >> note: this is a STAFF account ({acc_type}). Staff see the')
        print('      staff-only corpus and may name any client; a customer')
        print('      cannot. Use --client to test what a customer really gets.')"""


def main():
    src = io.open(PATH, encoding='utf-8', newline='').read()
    notes = []

    if 'def login_under_client(' in src:
        notes.append('resolver already present')
    else:
        at = src.find('def ask(')
        if at < 0:
            print('  !! ask() not found'); return 1
        src = src[:at] + RESOLVER.lstrip('\n') + '\n' + src[at:]
        notes.append('added login_under_client() and fleet_size()')

    for old, new, note in ((OLD_ARGS, NEW_ARGS, 'added --client'),
                           (OLD_PICK, NEW_PICK, 'resolves a login under a client'),
                           (OLD_BANNER, NEW_BANNER, 'states the fleet size up front')):
        if new.strip().splitlines()[-1] in src:
            notes.append(note + ' (already)')
            continue
        if old not in src:
            print(f'  !! could not find the block for: {note}')
            return 1
        src = src.replace(old, new, 1)
        notes.append(note)

    ast.parse(src)
    io.open(PATH, 'w', encoding='utf-8', newline='').write(src)
    for n in notes:
        print('  ' + n)
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
