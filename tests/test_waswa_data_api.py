"""tests/test_waswa_data_api.py -- the agent reaches data only through the API.

What is checked, and why each one matters:

  1. Tokens. A data token is not a user token and a user token is not a data
     token, in either direction. Tampered, expired, wrong-audience and
     wrong-scope tokens are refused.
  2. The API. No token, or the wrong kind, is a 401 on every route; another
     account's conversation is a 404, and nothing is written.
  3. The agent. AssistantChat and the helpers it calls hold no database
     handle (checked in the source), and a real chat turn still works with
     every direct route to the database made to fail (checked live).

Needs the application's configuration (.env) and its database, unlike the
pure-function tests beside it. Writes one conversation on the surface
'test-data-api' and deletes it again.

Run:  python tests/test_waswa_data_api.py   (or via pytest)
"""

import ast
import io
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import jwt  # noqa: E402

_ASSISTANT = os.path.join(os.path.dirname(__file__), '..', 'endpoints',
                          'assistant.py')
_SURFACE = 'test-data-api'


def _app():
    from app import app
    return app


def _account():
    """A real account with a dll_access_relay row: the eval set's default."""
    import json
    with io.open(os.path.join(os.path.dirname(__file__), 'waswa_eval',
                              'questions.json'), encoding='utf-8') as fh:
        rows = json.load(fh)['questions']
    return next(r['origin']['ask_as_account_uid'] for r in rows
                if r.get('shape') == 'account'
                and r['origin'].get('ask_as_account_uid'))


def _user_token(account_uid):
    import psycopg2
    from config import DB_LINK
    from endpoints.jwt_utils import create_access_token
    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT account_root, account_type, account_clearance "
                        "FROM dll_access_relay WHERE account_uid = %s",
                        (account_uid,))
            root, acct_type, clearance = cur.fetchone()
    finally:
        conn.close()
    return create_access_token(account_uid, clearance, acct_type, root)


def _forge(**overrides):
    """A data token with the right key and some claims changed."""
    from endpoints import waswa_data_auth as auth
    now = datetime.now(timezone.utc)
    claims = {'iss': auth.ISSUER, 'aud': auth.AUDIENCE, 'sub': 'someone',
              'scope': auth.SCOPE, 'iat': now, 'nbf': now,
              'exp': now + timedelta(minutes=5), 'jti': str(uuid.uuid4())}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, auth._signing_key(), algorithm='HS256')


# ── 1. tokens ──────────────────────────────────────────────────────────────

def test_a_data_token_names_its_account():
    from endpoints import waswa_data_auth as auth
    assert auth.verify(auth.mint('acct-1')) == 'acct-1'


def test_a_user_token_is_not_a_data_token():
    _app()
    from endpoints import waswa_data_auth as auth
    from endpoints.jwt_utils import create_access_token
    assert auth.verify(create_access_token('acct-1', 'x', 'y', 'z')) is None


def test_a_data_token_is_not_a_user_token():
    app = _app()
    from endpoints import waswa_data_auth as auth
    from endpoints.jwt_utils import decode_access_token
    with app.app_context():
        assert decode_access_token(auth.mint('acct-1')) is None


def test_bad_data_tokens_are_refused():
    from endpoints import waswa_data_auth as auth
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    assert auth.verify(_forge()) == 'someone'            # the control
    assert auth.verify(_forge(exp=past)) is None          # expired
    assert auth.verify(_forge(aud='someone-else')) is None
    assert auth.verify(_forge(iss='someone-else')) is None
    assert auth.verify(_forge(scope='waswa:everything')) is None
    assert auth.verify(_forge(jti=None)) is None          # claim missing
    good = auth.mint('acct-1')
    assert auth.verify(good[:-2] + ('AA' if good[-2:] != 'AA' else 'BB')) is None
    assert auth.verify('') is None and auth.verify(None) is None


# ── 2. the API ─────────────────────────────────────────────────────────────

def test_every_route_needs_a_data_token():
    app = _app()
    client = app.test_client()
    account = _account()
    routes = [('GET', '/waswa/data/caller'), ('GET', '/waswa/data/context'),
              ('GET', '/waswa/data/prompt'),
              ('POST', '/waswa/data/conversations'),
              ('POST', '/waswa/data/answers/match'),
              ('POST', '/waswa/data/tools/unit_find'),
              ('GET', '/waswa/data/knowledge/sources'),
              ('POST', '/waswa/data/knowledge/search')]
    user = _user_token(account)
    for method, path in routes:
        for header in ({}, {'Authorization': 'Bearer ' + user},
                       {'Authorization': 'Bearer not-a-token'}):
            status = client.open(path, method=method, json={},
                                 headers=header).status_code
            assert status == 401, (method, path, header and 'with token', status)


def test_a_data_token_is_accepted():
    from endpoints import waswa_data_auth as auth
    client = _app().test_client()
    resp = client.get('/waswa/data/caller', headers={
        'Authorization': 'Bearer ' + auth.mint(_account())})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['data']['audience'] in ('staff', 'everyone')


def test_another_accounts_conversation_is_not_found():
    import psycopg2
    from config import DB_LINK
    from endpoints import waswa_data_auth as auth
    client = _app().test_client()
    # A real conversation, belonging to somebody other than the token's
    # account: a 404, exactly as for a uid that does not exist.
    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT conversation_uid FROM dll_waswa_conversations "
                        "WHERE account_uid <> %s LIMIT 1", (_account(),))
            row = cur.fetchone()
            theirs = row[0] if row else None
            before = None
            if theirs:
                cur.execute("SELECT COUNT(*) FROM dll_waswa_messages "
                            "WHERE conversation_uid = %s", (theirs,))
                before = cur.fetchone()[0]
    finally:
        conn.close()
    header = {'Authorization': 'Bearer ' + auth.mint(_account())}
    for uid in [str(uuid.uuid4())] + ([theirs] if theirs else []):
        base = '/waswa/data/conversations/%s' % uid
        assert client.get(base + '/messages', headers=header).status_code == 404
        assert client.post(base + '/messages', headers=header, json={
            'role': 'user', 'content': 'x'}).status_code == 404
        assert client.post(base + '/transparency', headers=header,
                           json={'entry_type': 'x'}).status_code == 404
    if theirs:
        conn = psycopg2.connect(DB_LINK)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM dll_waswa_messages "
                            "WHERE conversation_uid = %s", (theirs,))
                assert cur.fetchone()[0] == before, 'wrote into theirs'
        finally:
            conn.close()


def test_the_guard_and_the_api_agree_on_the_prefix():
    from endpoints import access_guard, waswa_data_api
    assert access_guard.DATA_API_PREFIX == waswa_data_api.PREFIX


# ── 3. the agent ───────────────────────────────────────────────────────────

# Names that mean "touches a store directly". Any of them inside the chat
# handler or a helper it calls is a regression.
_DIRECT = {'psycopg2', '_open_connection', 'build_context', 'db_pool',
           'get_cassandra_session', 'cursor', 'execute'}
_DIRECT_CALLS = {('waswa_fleet', 'dispatch'), ('waswa_fleet', 'unit_find'),
                 ('waswa_fleet', 'unit_status'), ('waswa_fleet', 'fleet_liveness'),
                 ('waswa_fleet', 'build_scope'),
                 ('waswa_knowledge', 'dispatch'),
                 ('waswa_knowledge', 'knowledge_search'),
                 ('waswa_products', 'dispatch'),
                 ('waswa_answers', 'match'), ('waswa_answers', 'caller')}
_AGENT_FUNCS = ('AssistantChat', '_active_prompt', '_resume_or_open_conversation',
                '_stored_history', '_record_turn', '_record_evidence',
                '_log_transparency', '_prefetch_fleet', '_strict_fleet_read',
                '_fetch_context', 'AssistantContext', 'AssistantKnowledge')


def test_the_agent_holds_no_database_handle():
    tree = ast.parse(io.open(_ASSISTANT, encoding='utf-8').read())
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    found = []
    for name in _AGENT_FUNCS:
        assert name in funcs, 'missing ' + name
        for node in ast.walk(funcs[name]):
            if isinstance(node, ast.Name) and node.id in _DIRECT:
                found.append((name, node.id, node.lineno))
            if isinstance(node, ast.Attribute):
                if node.attr in _DIRECT:
                    found.append((name, node.attr, node.lineno))
                if (isinstance(node.value, ast.Name)
                        and (node.value.id, node.attr) in _DIRECT_CALLS):
                    found.append((name, '%s.%s' % (node.value.id, node.attr),
                                  node.lineno))
    assert not found, found


def test_a_chat_turn_works_with_direct_access_cut_off():
    """A pricing question: the whole data path (context, conversation, turns,
    transparency) and no model call, so it costs nothing."""
    import psycopg2
    from config import DB_LINK
    from endpoints import assistant

    app = _app()
    client = app.test_client()
    account = _account()

    # Not patched out: gone. The module has no way left to reach a store.
    for name in ('psycopg2', 'build_context', '_open_connection', 'db_pool'):
        assert not hasattr(assistant, name), 'assistant still has ' + name
    conversation_uid = None
    try:
        resp = client.post('/assistant/chat', headers={
            'Authorization': 'Bearer ' + _user_token(account)},
            json={'data': {'message': 'How much does a VEBA pack cost?',
                           'surface': _SURFACE}})
        body = resp.get_json()
        assert resp.status_code == 200, body
        data = body['data']
        conversation_uid = data['conversation_uid']
        assert conversation_uid and data['message_uid'], data
        assert data['intent'] == 'pricing_enquiry'
        assert isinstance(data['context_unknown'], list)
    finally:
        if conversation_uid:
            conn = psycopg2.connect(DB_LINK)
            conn.autocommit = True
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM dll_waswa_messages "
                                "WHERE conversation_uid = %s", (conversation_uid,))
                    turns = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM dll_waswa_transparency_log "
                                "WHERE conversation_uid = %s", (conversation_uid,))
                    logged = cur.fetchone()[0]
                    for table in ('dll_waswa_transparency_log',
                                  'dll_waswa_messages',
                                  'dll_waswa_conversations'):
                        cur.execute("DELETE FROM %s WHERE conversation_uid = %%s"
                                    % table, (conversation_uid,))
            finally:
                conn.close()
            assert turns == 2, 'user + assistant turns recorded, got %s' % turns
            assert logged == 1, 'transparency entry written, got %s' % logged


def test_the_context_diagnostic_goes_through_the_api():
    client = _app().test_client()
    header = {'Authorization': 'Bearer ' + _user_token(_account())}
    resp = client.get('/assistant/context', headers=header)
    data = resp.get_json()['data']
    assert resp.status_code == 200, resp.get_json()
    assert data['known'].get('surface') == 'diagnostic', data['known']
    assert isinstance(data['unknown'], list) and data['scope'].get('account_uid')
    assert client.get('/assistant/context').status_code == 401


def test_the_knowledge_diagnostic_goes_through_the_api():
    from endpoints import waswa_answers
    app = _app()
    client = app.test_client()
    account = _account()
    header = {'Authorization': 'Bearer ' + _user_token(account)}
    listed = client.get('/assistant/knowledge', headers=header)
    assert listed.status_code == 200, listed.get_json()
    found = client.get('/assistant/knowledge?q=tracking+tokens'
                       '&include_unapproved=true', headers=header)
    body = found.get_json()['data']
    assert found.status_code == 200, found.get_json()
    assert 'found' in body and body['audience'] in ('staff', 'everyone')
    # Asked for, and honoured only for a reviewer -- decided by the API.
    with app.test_request_context():
        reviewer = waswa_answers.can(waswa_answers.caller(account),
                                     waswa_answers.PERM_REVIEW)
    assert body['include_unapproved'] is reviewer, body['include_unapproved']
    assert client.get('/assistant/knowledge').status_code == 401


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith('test_') and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print('  ok    %s' % name)
        except Exception as error:      # noqa: BLE001
            failed += 1
            print('  FAIL  %s: %s: %s' % (name, error.__class__.__name__, error))
    print('\n%d/%d passed' % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
