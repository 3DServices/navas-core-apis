#!/usr/bin/env python3
"""
waswa_ask.py — ask Waswa questions against your LOCAL Flask, with no browser.

Why this exists: testing the morning's work through the console means a working
vite dev server, and vite is currently dying on the same Windows Application
Control policy that blocked the Cassandra driver. There is no reason to let a
blocked esbuild.exe stand between you and the answer to "does Waswa still
invent things".

This posts straight to /assistant/chat on localhost and prints the reply next
to the evidence trail the route returns, so you can see in one screen whether a
tool was called and which one.

It signs its own access token with the repo's own create_access_token and the
JWT_SECRET from your .env — the documented auth path, exercised locally. It
does NOT invent a role: the role, account type and account_root come from
_get_user_permissions, so the answers you see are the ones that account would
really get. Giving the test staff privileges the customer does not have would
make every result meaningless.

Usage:
    python scripts/waswa_ask.py --account <ACCOUNT_UID>
    python scripts/waswa_ask.py --account <UID> "Why is UBF 364U offline?"
    python scripts/waswa_ask.py                      # replays the last real asker
    python scripts/waswa_ask.py --url http://localhost:5000 --surface console
"""

import argparse
import json
import sys

import psycopg2
import requests

sys.path.insert(0, '.')
from config import DB_LINK                             # noqa: E402
from endpoints.jwt_utils import create_access_token    # noqa: E402
from endpoints.globals import _get_user_permissions    # noqa: E402

# The four that the audit caught being invented or dodged, plus the two the
# live fleet data should now answer. Keep them fixed: the point of a regression
# set is that today's answers are comparable with yesterday's.
DEFAULT_QUESTIONS = (
    'How do tracking tokens work?',
    'How do I contact support?',
    'Why is UBF 364U offline?',
    'How many trips did UBJ 916W make this week?',
)


def last_real_asker(cur):
    """The account that most recently used Waswa, so a default run reproduces a
    real customer's view rather than inventing an account."""
    cur.execute("""
        SELECT c.account_uid
          FROM dll_waswa_conversations c
          JOIN dll_waswa_messages m ON m.conversation_uid = c.conversation_uid
         GROUP BY c.account_uid
         ORDER BY MAX(c.last_activity_at) DESC NULLS LAST
         LIMIT 1""")
    row = cur.fetchone()
    return row[0] if row else None


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


def ask(url, token, question, surface, conversation_uid):
    body = {'data': {'message': question, 'surface': surface}}
    if conversation_uid:
        body['data']['conversation_uid'] = conversation_uid
    try:
        r = requests.post(f'{url.rstrip("/")}/assistant/chat',
                          json=body,
                          headers={'Authorization': f'Bearer {token}'},
                          timeout=120)
    except requests.exceptions.ConnectionError:
        print(f'\n!! Nothing is listening on {url}.')
        print('   Start Flask first:  python app.py   (it serves on :5000)')
        return None
    except requests.exceptions.Timeout:
        print('\n!! No reply within 120s — the model call is probably hanging.')
        return None

    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {'_raw': r.text[:600]}


def show(status, body):
    """The answer, then what it was built from."""
    if status != 200:
        print(f'   HTTP {status}')

    data = body.get('data') if isinstance(body.get('data'), dict) else body
    answer = ''
    for key in ('answer', 'message', 'reply', 'content', 'text'):
        if isinstance(data.get(key), str) and data[key].strip():
            answer = data[key].strip()
            break
    if not answer and isinstance(body.get('message'), str):
        answer = body['message'].strip()

    print(f'   A: {answer or "(no answer field — raw below)"}')
    if not answer:
        print('      ' + json.dumps(body, default=str)[:500])

    evidence = data.get('evidence') or body.get('evidence') or []
    if evidence:
        print('   evidence:')
        for e in evidence:
            if isinstance(e, dict):
                kind = e.get('source_kind') or e.get('kind') or '?'
                ref = e.get('source_ref') or e.get('ref') or ''
                lvl = e.get('authority_level', e.get('authority', ''))
                print(f'      · {kind:<16} L{lvl}  {ref}')
            else:
                print(f'      · {e}')
        looked = [e for e in evidence
                  if (isinstance(e, dict) and
                      (e.get('source_kind') or e.get('kind')) not in
                      (None, '', 'account_context'))]
        print(f'   -> {"GROUNDED — a tool was called" if looked else "NO TOOL CALLED"}')
    else:
        print('   evidence: (none returned)')

    return data.get('conversation_uid') or body.get('conversation_uid')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('questions', nargs='*', help='defaults to the regression set')
    ap.add_argument('--account', help='account_uid to ask as')
    ap.add_argument('--client', help='ask as a login belonging to this client_uid')
    ap.add_argument('--url', default='http://localhost:5000')
    ap.add_argument('--surface', default='mobile',
                    help='mobile | console | cms — picks the audience and prompt')
    ap.add_argument('--fresh', action='store_true',
                    help='a new conversation per question instead of one thread')
    args = ap.parse_args()

    conn = psycopg2.connect(DB_LINK)
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
                          f'asking as {account}')
            account = account or last_real_asker(cur)
            if not account:
                print('No account_uid given and none found in '
                      'dll_waswa_conversations. Pass --account or --client.')
                return 1
    finally:
        conn.close()

    # _get_user_permissions reads current_app.config['db_link'], so it needs an
    # app context even though we are not serving a request. A bare Flask app
    # with the same db_link is all it wants.
    from flask import Flask
    probe = Flask(__name__)
    probe.config['db_link'] = DB_LINK
    with probe.app_context():
        role, acc_type, root, _perms = _get_user_permissions(account)
    if role is None:
        print(f'!! {account} has no permissions record — is that a real login?')
        return 1

    token = create_access_token(account, role, acc_type, root)
    print(f'account : {account}')
    print(f'role    : {role} / {acc_type}   root={root}')
    print(f'surface : {args.surface}        -> {args.url}')
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
        print('      cannot. Use --client to test what a customer really gets.')

    questions = args.questions or list(DEFAULT_QUESTIONS)
    conversation_uid = None
    for n, question in enumerate(questions, 1):
        print('\n' + '-' * 74)
        print(f'[{n}/{len(questions)}] Q: {question}')
        got = ask(args.url, token, question, args.surface,
                  None if args.fresh else conversation_uid)
        if got is None:
            return 1
        status, body = got
        new_uid = show(status, body)
        if not args.fresh and new_uid:
            conversation_uid = new_uid

    print('\n' + '=' * 74)
    print('Now read the stored trail, which is the same thing from the other side:')
    print(f'  python scripts/waswa_audit.py --limit {len(questions) + 1}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
