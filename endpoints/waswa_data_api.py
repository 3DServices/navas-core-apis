"""
waswa_data_api.py -- the only way the Waswa agent reaches data.

POST /assistant/chat used to open its own database connection and hand it to
a dozen helpers, and its tools opened more. Now the agent holds no connection
at all: it calls these routes (through waswa_data_client) with a short-lived
token from waswa_data_auth, and everything that touches Postgres or Cassandra
on its behalf happens here.

WHOSE DATA
The account is the token's `sub`, verified on every request. Nothing in a URL
or body can name another account:
  * conversation and message routes check ownership and answer 404 otherwise,
    so a uid belonging to someone else is indistinguishable from none;
  * tool calls build the fleet scope and the document audience here, from the
    account, and strip any scope, client_uid, audience or include_unapproved
    the model put in its arguments (the dispatchers did this already; it is
    still done here so that no future dispatcher can forget).

ERRORS
The old helpers swallowed their errors so that a failed write cost a row and
never an answer. That policy now lives in the client. These routes report
failures honestly, as 4xx/5xx with the reason in the message.

Routes (all under /waswa/data, all need `Authorization: Bearer <data token>`):
  GET  /caller                                    audience for this account
  GET  /context?surface=                          account context, rendered
  GET  /prompt                                    active runtime prompt
  POST /conversations                             resume or open one
  GET  /conversations/<uid>/messages?limit=       history, oldest first
  POST /conversations/<uid>/messages              append a turn
  POST /conversations/<uid>/transparency          transparency log entry
  POST /messages/<uid>/evidence                   evidence rows for a turn
  POST /answers/match                             verified answers for a question
  GET  /knowledge/sources                         documents this account may draw on
  POST /knowledge/search                          a search, as the diagnostic runs it
  POST /tools/<name>                              run a fleet/knowledge/product tool
"""

import json
import uuid

from flask import Blueprint, current_app, g, request

from . import db_pool
from . import waswa_answers
from . import waswa_data_auth
from . import waswa_fleet
from . import waswa_knowledge
from . import waswa_products
from .globals import reply
from .waswa_context import _account, build_context, render_for_prompt

PREFIX = '/waswa/data'

waswa_data_bp = Blueprint('WaswaData', __name__, url_prefix=PREFIX)

# A turn joins the account's most recent open conversation on the same surface
# if it is this fresh (unchanged from when this lived in assistant.py).
_CONVERSATION_IDLE_MINUTES = 60
_MAX_HISTORY = 50

_ROLES = frozenset({'user', 'assistant'})

# Arguments only the server may set. Dropped from whatever the model sent.
_SERVER_ONLY_ARGS = ('scope', 'audience', 'include_unapproved', 'app_guide')


# ── Authentication ─────────────────────────────────────────────────────────

@waswa_data_bp.before_request
def _authenticate():
    """Every route, no exceptions, and whatever AUTH_GATE_MODE says: the
    access guard steps aside for this prefix because this check is stricter."""
    if request.method == 'OPTIONS':
        return None
    header = request.headers.get('Authorization', '')
    token = header[7:].strip() if header.startswith('Bearer ') else ''
    account_uid = waswa_data_auth.verify(token)
    if not account_uid:
        return reply('error', 401, 'A valid Waswa data token is required.', '')
    g.waswa_data_account = account_uid
    return None


def _account_uid():
    return g.waswa_data_account


# ── One connection per request ─────────────────────────────────────────────

def _conn():
    conn = getattr(g, '_waswa_data_conn', None)
    if conn is None:
        # From the pool: the agent now makes several calls per turn where it
        # used to open one connection, and a fresh connection to this
        # database costs about two seconds (see db_pool.py).
        #
        # readonly=True is the pool's name for autocommit, and autocommit is
        # what the chat route always ran these statements under: independent
        # appends and single reads, none needing a transaction across
        # statements. It does not block writes, and the pool turns autocommit
        # back off when the connection is returned.
        conn = db_pool.connect(current_app.config.get('waswa_db_link') or current_app.config['db_link'], readonly=True)
        g._waswa_data_conn = conn
    return conn


@waswa_data_bp.teardown_request
def _close(_error=None):
    conn = getattr(g, '_waswa_data_conn', None)
    if conn is not None:
        try:
            conn.close()
        finally:
            g._waswa_data_conn = None


def _plain(value):
    """[value] as the agent has always shown it to the model.

    jsonify would write a datetime as an HTTP date ("Sat, 10 Oct 2026 ...
    GMT"); the agent used json.dumps(default=str) ("2026-10-10 15:04:00"),
    and the prompt tells the model those are LOCAL times. Same format, then.
    """
    return json.loads(json.dumps(value, default=str))


def _body():
    return request.get_json(silent=True) or {}


def _owns_conversation(cur, conversation_uid, resumable=False):
    # resumable: a conversation archived in the console is not reopened;
    # the next message starts a new one instead.
    cur.execute(
        "SELECT 1 FROM dll_waswa_conversations "
        "WHERE conversation_uid = %s AND account_uid = %s "
        + ("AND status <> 'archived'" if resumable else ""),
        (str(conversation_uid), str(_account_uid())))
    return bool(cur.rowcount)


def _not_found():
    return reply('error', 404, 'No such conversation for this account.', '')


# ── Who is asking ──────────────────────────────────────────────────────────

def _audience():
    return waswa_answers.audience_for(waswa_answers.caller(_account_uid()))


def _fleet_scope():
    """Whose fleet the tools may read: this account's client, and any client
    only when the account is staff. Built from the database, never from the
    request."""
    with _conn().cursor() as cur:
        account = _account(cur, _account_uid())
    client_uid = account[0] if account else None
    return waswa_fleet.build_scope(_account_uid(), client_uid,
                                   is_staff=(_audience() == 'staff'))


@waswa_data_bp.route('/caller', methods=['GET'])
def caller():
    return reply('success', 200, 'OK', {'audience': _audience()})


@waswa_data_bp.route('/context', methods=['GET'])
def context():
    """The account context, with everything derived from it rendered here.

    Rendered server-side on purpose: the context holds dates and Decimals,
    and _zero_state_note tests for int/float. A JSON round trip would turn
    those into strings and quietly change which accounts get the note.
    """
    # Imported here: assistant.py is the agent, and it imports the client,
    # not this module, so there is no cycle -- but keep it obviously so.
    from .assistant import _unknown_report, _zero_state_note

    surface = str(request.args.get('surface') or 'mobile').strip().lower()[:20]
    ctx = build_context(_account_uid(), surface=surface, conn=_conn())
    return reply('success', 200, 'OK', {
        'scope': _plain(ctx['scope']),
        # The raw slots, for the /assistant/context diagnostic. The agent
        # itself uses the rendered text below.
        'known': _plain(ctx['known']),
        'rendered': render_for_prompt(ctx),
        'zero_state_note': _zero_state_note(ctx),
        'unknown': _unknown_report(ctx),
    })


@waswa_data_bp.route('/prompt', methods=['GET'])
def prompt():
    with _conn().cursor() as cur:
        cur.execute(
            "SELECT body, version FROM dll_waswa_prompts "
            "WHERE prompt_key = 'runtime_system' AND is_active = TRUE LIMIT 1")
        row = cur.fetchone() if cur.rowcount else None
    if not row:
        return reply('error', 404, 'No active runtime prompt.', '')
    return reply('success', 200, 'OK', {'body': row[0], 'version': row[1]})


# ── Conversations ──────────────────────────────────────────────────────────

@waswa_data_bp.route('/conversations', methods=['POST'])
def open_conversation():
    """Resume the requested conversation if it is this account's, else the
    account's recent open one on this surface, else open a new one."""
    body = _body()
    surface = str(body.get('surface') or 'mobile').strip().lower()[:20]
    requested = body.get('conversation_uid')
    with _conn().cursor() as cur:
        if requested and _owns_conversation(cur, requested, resumable=True):
            return reply('success', 200, 'OK',
                         {'conversation_uid': str(requested), 'resumed': True})
        # An unknown or someone else's uid is not honoured; a fresh
        # conversation is opened rather than writing into theirs.
        cur.execute(
            "SELECT conversation_uid FROM dll_waswa_conversations "
            "WHERE account_uid = %s AND surface = %s AND status = 'open' "
            "  AND last_activity_at > NOW() - (%s * INTERVAL '1 minute') "
            "ORDER BY last_activity_at DESC LIMIT 1",
            (str(_account_uid()), surface, _CONVERSATION_IDLE_MINUTES))
        if cur.rowcount:
            return reply('success', 200, 'OK',
                         {'conversation_uid': cur.fetchone()[0],
                          'resumed': True})

        account = _account(cur, _account_uid())
        root = account[0] if account else None
        conversation_uid = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO dll_waswa_conversations "
            "(conversation_uid, account_uid, account_root, client_uid, surface) "
            "VALUES (%s, %s, %s, %s, %s)",
            (conversation_uid, str(_account_uid()), root, root, surface))
    return reply('success', 201, 'Created',
                 {'conversation_uid': conversation_uid, 'resumed': False})


@waswa_data_bp.route('/conversations/<conversation_uid>/messages',
                     methods=['GET'])
def history(conversation_uid):
    try:
        limit = max(1, min(int(request.args.get('limit') or 10), _MAX_HISTORY))
    except ValueError:
        limit = 10
    with _conn().cursor() as cur:
        if not _owns_conversation(cur, conversation_uid):
            return _not_found()
        # Blocked replies are included on purpose: they are server templates,
        # and dropping them left a question with no answer in the history.
        cur.execute(
            "SELECT role, content FROM dll_waswa_messages "
            "WHERE conversation_uid = %s ORDER BY turn_index DESC LIMIT %s",
            (str(conversation_uid), limit))
        rows = cur.fetchall() if cur.rowcount > 0 else []
    return reply('success', 200, 'OK', {
        'messages': [{'role': r[0], 'content': r[1]} for r in reversed(rows)]})


@waswa_data_bp.route('/conversations/<conversation_uid>/messages',
                     methods=['POST'])
def record_turn(conversation_uid):
    body = _body()
    role = body.get('role')
    content = body.get('content')
    if role not in _ROLES or not isinstance(content, str):
        return reply('error', 400, 'role must be user or assistant, and '
                     'content a string.', '')
    message_uid = str(uuid.uuid4())
    with _conn().cursor() as cur:
        if not _owns_conversation(cur, conversation_uid):
            return _not_found()
        cur.execute(
            "SELECT COALESCE(MAX(turn_index), -1) + 1 "
            "FROM dll_waswa_messages WHERE conversation_uid = %s",
            (str(conversation_uid),))
        turn_index = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO dll_waswa_messages "
            "(message_uid, conversation_uid, turn_index, role, content, "
            " intent, router_tier, model, prompt_version, blocked_reason, "
            " latency_ms) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (message_uid, str(conversation_uid), turn_index, role, content,
             body.get('intent'), body.get('router_tier'), body.get('model'),
             body.get('prompt_version'), body.get('blocked_reason'),
             body.get('latency_ms')))
        cur.execute(
            "UPDATE dll_waswa_conversations SET last_activity_at = NOW() "
            "WHERE conversation_uid = %s", (str(conversation_uid),))
    return reply('success', 201, 'Created', {'message_uid': message_uid})


@waswa_data_bp.route('/conversations/<conversation_uid>/transparency',
                     methods=['POST'])
def log_transparency(conversation_uid):
    body = _body()
    with _conn().cursor() as cur:
        if not _owns_conversation(cur, conversation_uid):
            return _not_found()
        account = _account(cur, _account_uid())
        root = account[0] if account else None
        cur.execute(
            "INSERT INTO dll_waswa_transparency_log "
            "(entry_uid, account_uid, account_root, client_uid, "
            " conversation_uid, message_uid, entry_type, action, rationale) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (str(uuid.uuid4()), str(_account_uid()), root, root,
             str(conversation_uid), body.get('message_uid'),
             body.get('entry_type'), body.get('action'), body.get('rationale')))
    return reply('success', 201, 'Created', '')


@waswa_data_bp.route('/messages/<message_uid>/evidence', methods=['POST'])
def record_evidence(message_uid):
    items = _body().get('items') or []
    if not isinstance(items, list):
        return reply('error', 400, 'items must be a list.', '')
    with _conn().cursor() as cur:
        cur.execute(
            "SELECT 1 FROM dll_waswa_messages m "
            "JOIN dll_waswa_conversations c USING (conversation_uid) "
            "WHERE m.message_uid = %s AND c.account_uid = %s",
            (str(message_uid), str(_account_uid())))
        if not cur.rowcount:
            return reply('error', 404, 'No such message for this account.', '')
        for item in items:
            source_kind, source_ref, authority_level = (list(item) + [None] * 3)[:3]
            cur.execute(
                "INSERT INTO dll_waswa_evidence "
                "(message_uid, source_kind, source_ref, authority_level) "
                "VALUES (%s, %s, %s, %s)",
                (str(message_uid), source_kind, source_ref, authority_level))
    return reply('success', 201, 'Created', {'recorded': len(items)})


# ── Verified answers ───────────────────────────────────────────────────────

@waswa_data_bp.route('/answers/match', methods=['POST'])
def match_answers():
    question = str(_body().get('question') or '')
    with _conn().cursor() as cur:
        verified = waswa_answers.match(cur, question, _audience())
    return reply('success', 200, 'OK', {
        'verified': _plain(verified),
        'rendered': (waswa_answers.render_for_prompt(verified)
                     if verified else None)})


# ── Knowledge diagnostics ──────────────────────────────────────────────────
# For GET /assistant/knowledge, which shows exactly what retrieval returns.
# Unlike /tools/knowledge_search -- which the model drives, and which always
# drops include_unapproved -- this honours it, but only for an account that
# holds the reviewer permission, decided here from the token's account.

@waswa_data_bp.route('/knowledge/sources', methods=['GET'])
def knowledge_sources():
    return reply('success', 200, 'OK', _plain(
        waswa_knowledge.knowledge_sources(audience=_audience())))


@waswa_data_bp.route('/knowledge/search', methods=['POST'])
def knowledge_search():
    body = _body()
    query = str(body.get('query') or '').strip()
    if not query:
        return reply('error', 400, 'query is required.', '')
    who = waswa_answers.caller(_account_uid())
    audience = waswa_answers.audience_for(who)
    include_unapproved = (bool(body.get('include_unapproved'))
                          and waswa_answers.can(who, waswa_answers.PERM_REVIEW))
    result = waswa_knowledge.knowledge_search(
        query, product=body.get('product'),
        document_type=body.get('document_type'), limit=body.get('limit'),
        include_unapproved=include_unapproved, audience=audience)
    result['audience'] = audience
    result['include_unapproved'] = include_unapproved
    return reply('success', 200, 'OK', _plain(result))


# ── Tools ──────────────────────────────────────────────────────────────────

@waswa_data_bp.route('/tools/<name>', methods=['POST'])
def run_tool(name):
    """Run one tool for this account.

    strict=true is for the agent's own prefetch, which must tell "could not
    read the register" apart from "there is nothing there": the fleet
    function's FleetUnavailable becomes a 503 rather than the explanatory
    result the model is given.
    """
    body = _body()
    arguments = {k: v for k, v in dict(body.get('arguments') or {}).items()
                 if k not in _SERVER_ONLY_ARGS}

    if name in waswa_fleet._DISPATCH:
        scope = _fleet_scope()
        if not scope.get('is_staff'):
            arguments.pop('client_uid', None)
        if body.get('strict'):
            try:
                result = waswa_fleet._DISPATCH[name](**arguments, scope=scope)
            except waswa_fleet.FleetUnavailable as error:
                return reply('error', 503, 'fleet_unavailable: %s' % error, '')
        else:
            result = waswa_fleet.dispatch(name, arguments, scope=scope)
        return reply('success', 200, 'OK', {'owner': 'fleet',
                                               'result': _plain(result)})

    knowledge = waswa_knowledge.dispatch(name, arguments, audience=_audience())
    if knowledge is not None:
        return reply('success', 200, 'OK',
                     {'owner': 'knowledge', 'result': _plain(knowledge),
                      'authority': waswa_knowledge.authority_of(knowledge)})

    # Unknown names land here too, and get the product dispatcher's readable
    # "no such tool" answer for the model.
    return reply('success', 200, 'OK',
                 {'owner': 'products',
                  'result': _plain(waswa_products.dispatch(name, arguments))})
