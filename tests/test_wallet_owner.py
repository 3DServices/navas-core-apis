"""tests/test_wallet_owner.py — resolve_wallet_owner(), without a database.

The function decides which account a token balance is read for. Getting it
wrong is not a crash, it is a wrong number on a customer's screen, so it is
worth a test that runs anywhere.

globals.py imports Flask and psycopg2, which a bare checkout may not have, so
the one function under test is compiled out of the source file rather than
imported. Run:  python tests/test_wallet_owner.py   (or via pytest)
"""

from __future__ import annotations

import ast
import io
import os

_SOURCE = os.path.join(os.path.dirname(__file__), '..', 'endpoints', 'globals.py')


_WANTED = ('resolve_wallet_owner', 'resolve_client_account')


def _load():
    tree = ast.parse(io.open(_SOURCE, encoding='utf-8').read())
    wanted = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name in _WANTED]
    assert len(wanted) == len(_WANTED), 'globals.py no longer defines both'
    namespace: dict = {}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), _SOURCE, 'exec'), namespace)
    return namespace


_NS = _load()
resolve_wallet_owner = _NS['resolve_wallet_owner']
resolve_client_account = _NS['resolve_client_account']


class FakeCursor:
    """Answers the queries these functions make, from an in-memory database."""

    def __init__(self, relay, clients=None):
        # relay:   {account_uid: account_root}  (dll_access_relay)
        # clients: {client_uid}                 (dll_client_accounts)
        self.relay = relay
        self.clients = set(CLIENTS if clients is None else clients)
        self._rows = []
        self.queries = []

    def execute(self, sql, params):
        self.queries.append(sql)
        value = str(params[0])
        if 'SELECT account_root' in sql:
            root = self.relay.get(value)
            self._rows = [(root,)] if root is not None else []
        elif 'SELECT account_uid' in sql:
            self._rows = [(uid,) for uid, root in sorted(self.relay.items())
                          if root == value]
        elif 'dll_client_accounts' in sql:
            self._rows = [(value,)] if value in self.clients else []
        else:                                    # pragma: no cover
            raise AssertionError('unexpected query: ' + sql)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


# One company: CLIENT-1 is the owner login (its own root), USER-2 and USER-3
# are team members. CLIENT-9 is a different company entirely.
RELAY = {
    'CLIENT-1': 'CLIENT-1',
    'USER-2': 'CLIENT-1',
    'USER-3': 'CLIENT-1',
    'CLIENT-9': 'CLIENT-9',
    # A member of 3D Services staff. Their root is the staff org, which is not
    # a customer and therefore owns no wallet.
    'STAFF-7': 'THREED-STAFF',
}

# Companies that exist in dll_client_accounts.
CLIENTS = {'CLIENT-1', 'CLIENT-9'}


def test_team_member_resolves_to_the_company():
    client, owners = resolve_wallet_owner(FakeCursor(RELAY), 'USER-2')
    assert client == 'CLIENT-1'
    assert owners == ['CLIENT-1', 'USER-2', 'USER-3']


def test_owner_login_is_unchanged():
    client, owners = resolve_wallet_owner(FakeCursor(RELAY), 'CLIENT-1')
    assert client == 'CLIENT-1'
    assert owners == ['CLIENT-1', 'USER-2', 'USER-3']


def test_every_team_member_sees_the_same_wallet():
    seen = set()
    for uid in ('CLIENT-1', 'USER-2', 'USER-3'):
        client, owners = resolve_wallet_owner(FakeCursor(RELAY), uid)
        seen.add((client, tuple(owners)))
    assert len(seen) == 1


def test_another_company_is_never_pulled_in():
    _, owners = resolve_wallet_owner(FakeCursor(RELAY), 'USER-2')
    assert 'CLIENT-9' not in owners


def test_client_uid_with_no_login_row_still_resolves_to_itself():
    # A client account that nobody signs in as: no dll_access_relay row keyed
    # by it, but team members point at it.
    relay = {'USER-2': 'CLIENT-1', 'USER-3': 'CLIENT-1'}
    client, owners = resolve_wallet_owner(FakeCursor(relay), 'CLIENT-1')
    assert client == 'CLIENT-1'
    assert owners == ['CLIENT-1', 'USER-2', 'USER-3']


def test_unknown_uid_resolves_to_itself_alone():
    client, owners = resolve_wallet_owner(FakeCursor(RELAY), 'NOBODY')
    assert client == 'NOBODY'
    assert owners == ['NOBODY']


def test_blank_and_none_do_not_crash():
    for value in ('', None, '   '):
        client, owners = resolve_wallet_owner(FakeCursor(RELAY), value)
        assert client == ''
        assert owners == []          # nothing to query; the route answers 404


def test_null_account_root_falls_back_to_the_uid():
    client, owners = resolve_wallet_owner(FakeCursor({'USER-2': None}), 'USER-2')
    assert client == 'USER-2'
    assert owners == ['USER-2']


def test_owners_are_unique_and_sorted():
    _, owners = resolve_wallet_owner(FakeCursor(RELAY), 'USER-3')
    assert owners == sorted(set(owners))


# ── resolve_client_account: nothing is credited unless it lands on a company ──

def test_a_customer_login_resolves_to_its_company():
    assert resolve_client_account(FakeCursor(RELAY), 'USER-2') == 'CLIENT-1'


def test_a_company_uid_resolves_to_itself():
    assert resolve_client_account(FakeCursor(RELAY), 'CLIENT-9') == 'CLIENT-9'


def test_staff_buying_for_a_client_lands_on_that_client():
    # The top-up and instant-buy screens send the client the staff member
    # picked, not the staff member.
    assert resolve_client_account(FakeCursor(RELAY), 'CLIENT-1') == 'CLIENT-1'


def test_a_staff_login_is_not_a_wallet():
    # A staff member's own login has no company behind it: refuse, rather than
    # opening a wallet on the staff org that no balance screen would ever read.
    assert resolve_client_account(FakeCursor(RELAY), 'STAFF-7') is None


def test_a_uid_nobody_recognises_is_refused():
    assert resolve_client_account(FakeCursor(RELAY), 'TYPO-XYZ') is None


def test_a_deleted_company_is_refused():
    assert resolve_client_account(FakeCursor(RELAY, clients=set()), 'USER-2') is None


def test_blank_is_refused():
    for value in ('', None, '   '):
        assert resolve_client_account(FakeCursor(RELAY), value) is None


if __name__ == '__main__':
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            passed += 1
            print('  ok  ' + name)
    print(f'{passed}/{passed} passed')
