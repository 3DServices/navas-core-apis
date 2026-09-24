"""
waswa_console.py — the endpoints behind the Waswa AI Console (Portal Phase A).

Registered onto assistant_bp by assistant.py, so app.py does not change.

Everyone signed in:
    POST /assistant/feedback                          flag or rate an answer

waswa.review (see and fix):
    GET  /assistant/console/summary                   counts for badges
    GET  /assistant/console/queue                     everything waiting on a person
    GET  /assistant/console/conversations             recent conversations
    GET  /assistant/console/conversations/<uid>       messages, evidence, feedback
    GET  /assistant/console/answers                   corrections, filter by status
    GET  /assistant/console/answers/<uid>
    POST /assistant/console/answers                   draft a correction
    POST /assistant/console/answers/<uid>             edit (an approved one -> new version)
    POST /assistant/console/answers/<uid>/submit      send for approval
    POST /assistant/console/answers/<uid>/retire
    POST /assistant/console/feedback/<uid>/resolve    close a flag
    GET  /assistant/console/sources                   documents and their state
    GET  /assistant/console/sources/<uid>             one document, its passages, versions
    POST /assistant/console/sources/upload            upload a document or a new version (multipart)
    GET  /assistant/console/authority-levels          the levels a document can be filed at
    GET  /assistant/console/match?q=                  which corrections a question hits

waswa.approve (sign off):
    POST /assistant/console/answers/<uid>/decide      approve | reject
    POST /assistant/console/answers/<uid>/confirm     recheck done, still right
    POST /assistant/console/sources/<uid>/review      approve | reject a document
    POST /assistant/console/sources/<uid>/audience    staff | everyone
    POST /assistant/console/sources/<uid>/remove      stop using it (reversible)
    POST /assistant/console/sources/<uid>/restore     undo a removal
    POST /assistant/console/sources/<uid>/details     title, type, authority level, version

Every write runs in one transaction with its transparency-log entry, and is
also written to the hash-chained audit log (domain AI) after it commits.
"""

from functools import wraps

import psycopg2
from flask import request, current_app, g

from . import waswa_answers as wa
from . import waswa_documents as wd
from .globals import reply, _extract_account_uid, log_audit_event


# ── Plumbing ───────────────────────────────────────────────────────────────

def _body():
    payload = request.get_json(silent=True) or {}
    # Accept both {"data": {...}} (the app convention) and a bare object.
    data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
    return data or {}


def _gate(permission=None):
    """Signed in, active, and (if given) holding [permission].

    Not require_permission: that decorator passes customer_tracker through
    every check. Here a permission means the permission.
    """
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            account_uid = _extract_account_uid()
            if not account_uid:
                return reply('error', 401, 'Authentication required.', '')
            try:
                who = wa.caller(account_uid)
            except Exception as error:      # noqa: BLE001
                # Always JSON: an HTML 500 page reaches the CMS as an
                # unreadable "failed to parse response".
                current_app.logger.exception('[waswa] permission lookup failed')
                return reply('error', 503, f'Could not check permissions: {error}', '')
            if not who:
                return reply('error', 401, 'Invalid or inactive account.', '')
            if permission and not wa.can(who, permission):
                held = ', '.join(who['permissions']) or 'none'
                return reply(
                    'error', 403,
                    f"This needs the {permission} permission. You are signed in "
                    f"as role '{who['role']}' (account type '{who['account_type']}') "
                    f"and hold: {held}. Grant it to that role under RBAC, or sign "
                    f"in with an account that has it.", '')
            g.waswa_who = who
            try:
                return func(*args, **kwargs)
            except Exception as error:      # noqa: BLE001
                current_app.logger.exception('[waswa] console endpoint failed')
                return reply('error', 500, f'Waswa console error: {error}', '')
        return wrapped
    return decorator


def _run(work, audit=None):
    """Run work(cur, who) in a transaction; map rule errors to replies."""
    who = g.waswa_who
    conn = psycopg2.connect(current_app.config['db_link'])
    try:
        with conn:
            with conn.cursor() as cur:
                result = work(cur, who)
    except wa.RuleError as error:
        return reply('error', error.status, str(error), '')
    except psycopg2.Error as error:
        return reply('error', 500, _db_message(error), '')
    finally:
        conn.close()

    if audit:
        action, obj = audit(result) if callable(audit) else audit
        log_audit_event(who['account_uid'], action, obj, 'AI',
                        tenant_id=who.get('account_root'),
                        ip_address=request.remote_addr)
    return reply('success', 200, 'OK', result)


def _read(work):
    who = g.waswa_who
    conn = psycopg2.connect(current_app.config['db_link'])
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            return reply('success', 200, 'OK', work(cur, who))
    except wa.RuleError as error:
        return reply('error', error.status, str(error), '')
    except psycopg2.Error as error:
        current_app.logger.exception('[waswa] console query failed')
        return reply('error', 500, _db_message(error), '')
    finally:
        conn.close()


def _db_message(error):
    """A database error in words someone can act on.

    A missing table or column almost always means a Waswa migration has not
    been run on this database, which is the fix — say so instead of showing
    the raw SQL error.
    """
    detail = (getattr(error, 'pgerror', None) or str(error)).strip().splitlines()[0]
    if getattr(error, 'pgcode', None) in ('42P01', '42703'):
        return ('The database is missing part of the Waswa setup (' + detail +
                '). Run python run_migration_041.py and python '
                'run_migration_042.py on the API server, then restart the API.')
    return f'Database error: {detail}'


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _int_arg(name, default, cap):
    try:
        return max(0, min(int(request.args.get(name, default)), cap))
    except (TypeError, ValueError):
        return default


# ── Handlers ───────────────────────────────────────────────────────────────

@_gate()
def feedback():
    data = _body()
    if not data.get('message_uid'):
        return reply('error', 400, 'message_uid is required.', '')
    return _run(
        lambda cur, who: wa.record_feedback(
            cur, who, data['message_uid'], str(data.get('verdict') or '').lower(),
            data.get('note'), data.get('surface')),
        audit=lambda r: ('FEEDBACK', f"Waswa answer rated {r['verdict']}"))


@_gate(wa.PERM_REVIEW)
def summary():
    def work(cur, who):
        cur.execute("SELECT item_kind, COUNT(*) FROM vw_waswa_review_queue "
                    "GROUP BY item_kind")
        counts = dict(cur.fetchall() if cur.rowcount > 0 else [])
        cur.execute("SELECT status, COUNT(*) FROM dll_waswa_answers GROUP BY status")
        answers = dict(cur.fetchall() if cur.rowcount > 0 else [])
        cur.execute("SELECT verdict, COUNT(*) FROM dll_waswa_feedback "
                    "WHERE created_at > NOW() - INTERVAL '30 days' GROUP BY verdict")
        verdicts = dict(cur.fetchall() if cur.rowcount > 0 else [])
        cur.execute("SELECT COUNT(*) FROM dll_waswa_messages "
                    "WHERE role = 'assistant' "
                    "AND created_at > NOW() - INTERVAL '30 days'")
        answered = cur.fetchone()[0]
        return {
            'queue': {k: counts.get(k, 0)
                      for k in ('flag', 'approval', 'recheck', 'document')},
            'queue_total': sum(counts.values()),
            'corrections': answers,
            'last_30_days': {'answers': answered, 'feedback': verdicts},
            'you': {'permissions': who['permissions']},
        }
    return _read(work)


@_gate(wa.PERM_REVIEW)
def queue():
    kind = request.args.get('kind')
    limit = _int_arg('limit', 50, 200)
    offset = _int_arg('offset', 0, 100000)

    def work(cur, who):
        sql = ("SELECT item_kind, item_uid, badge, title, detail, note, surface, "
               "       status, raised_at, message_uid, conversation_uid "
               "FROM vw_waswa_review_queue ")
        params = []
        if kind:
            sql += "WHERE item_kind = ANY(%s) "
            params.append([k.strip() for k in kind.split(',')])
        sql += "ORDER BY raised_at ASC LIMIT %s OFFSET %s"
        cur.execute(sql, params + [limit, offset])
        rows = cur.fetchall() if cur.rowcount > 0 else []
        items = []
        for r in rows:
            item = dict(zip(('item_kind', 'item_uid', 'badge', 'title', 'detail',
                             'note', 'surface', 'status', 'raised_at',
                             'message_uid', 'conversation_uid'), r))
            item['raised_at'] = _iso(item['raised_at'])
            # The shape WaswaTriagePanel already renders (AiQueueItem):
            # HIC for anything needing two people, HITL for the rest.
            item['card'] = {
                'id': item['item_uid'],
                'badge': 'HIC' if (item['item_kind'] == 'approval'
                                   and str(item['badge']).startswith('policy'))
                         else 'HITL',
                'title': (item['title'] or '')[:120],
                'sub': {'flag': f"Flagged {item['badge']} · {item['surface'] or ''}",
                        'approval': f"Correction awaiting approval · {item['badge']}",
                        'recheck': f"Correction to recheck · {item['badge']}",
                        'document': 'Document awaiting review'}[item['item_kind']],
            }
            items.append(item)
        return {'items': items, 'count': len(items),
                'limit': limit, 'offset': offset}
    return _read(work)


@_gate(wa.PERM_REVIEW)
def conversations():
    surface = request.args.get('surface')
    flagged = str(request.args.get('flagged', '')).lower() in ('1', 'true', 'yes')
    limit = _int_arg('limit', 30, 100)
    offset = _int_arg('offset', 0, 100000)

    def work(cur, who):
        where, params = [], []
        if surface:
            where.append("c.surface = %s")
            params.append(surface)
        if flagged:
            where.append("EXISTS (SELECT 1 FROM dll_waswa_feedback f "
                         "WHERE f.conversation_uid = c.conversation_uid "
                         "AND f.verdict <> 'good')")
        cur.execute(
            "SELECT c.conversation_uid, c.account_uid, c.surface, c.status, "
            "       c.started_at, c.last_activity_at, "
            "       (SELECT COUNT(*) FROM dll_waswa_messages m "
            "         WHERE m.conversation_uid = c.conversation_uid) AS messages, "
            "       (SELECT content FROM dll_waswa_messages m "
            "         WHERE m.conversation_uid = c.conversation_uid AND m.role='user' "
            "         ORDER BY turn_index LIMIT 1) AS first_question, "
            "       (SELECT COUNT(*) FROM dll_waswa_feedback f "
            "         WHERE f.conversation_uid = c.conversation_uid "
            "           AND f.verdict <> 'good') AS flags "
            "FROM dll_waswa_conversations c "
            + (f"WHERE {' AND '.join(where)} " if where else '')
            + "ORDER BY c.last_activity_at DESC LIMIT %s OFFSET %s",
            params + [limit, offset])
        keys = ('conversation_uid', 'account_uid', 'surface', 'status',
                'started_at', 'last_activity_at', 'messages', 'first_question',
                'flags')
        rows = [dict(zip(keys, r)) for r in (cur.fetchall() if cur.rowcount > 0 else [])]
        for r in rows:
            r['started_at'] = _iso(r['started_at'])
            r['last_activity_at'] = _iso(r['last_activity_at'])
        return {'conversations': rows, 'limit': limit, 'offset': offset}
    return _read(work)


@_gate(wa.PERM_REVIEW)
def conversation(conversation_uid):
    def work(cur, who):
        cur.execute("SELECT conversation_uid, account_uid, surface, status, "
                    "started_at, last_activity_at FROM dll_waswa_conversations "
                    "WHERE conversation_uid = %s", (conversation_uid,))
        row = cur.fetchone() if cur.rowcount else None
        if not row:
            raise wa.RuleError('No such conversation.', 404)
        head = dict(zip(('conversation_uid', 'account_uid', 'surface', 'status',
                         'started_at', 'last_activity_at'), row))
        head['started_at'] = _iso(head['started_at'])
        head['last_activity_at'] = _iso(head['last_activity_at'])

        cur.execute("SELECT message_uid, turn_index, role, content, intent, "
                    "router_tier, model, prompt_version, blocked_reason, "
                    "latency_ms, created_at FROM dll_waswa_messages "
                    "WHERE conversation_uid = %s ORDER BY turn_index",
                    (conversation_uid,))
        keys = ('message_uid', 'turn_index', 'role', 'content', 'intent',
                'router_tier', 'model', 'prompt_version', 'blocked_reason',
                'latency_ms', 'created_at')
        messages = [dict(zip(keys, r)) for r in (cur.fetchall() if cur.rowcount > 0 else [])]
        uids = [m['message_uid'] for m in messages]

        evidence, fb = {}, {}
        if uids:
            cur.execute("SELECT message_uid, source_kind, source_ref, "
                        "authority_level FROM dll_waswa_evidence "
                        "WHERE message_uid = ANY(%s) ORDER BY id", (uids,))
            for m_uid, kind, ref, level in (cur.fetchall() if cur.rowcount > 0 else []):
                evidence.setdefault(m_uid, []).append(
                    {'source_kind': kind, 'source_ref': ref,
                     'authority_level': level})
            cur.execute("SELECT message_uid, feedback_uid, account_uid, verdict, "
                        "note, status, resolution, created_at "
                        "FROM dll_waswa_feedback WHERE message_uid = ANY(%s)",
                        (uids,))
            for r in (cur.fetchall() if cur.rowcount > 0 else []):
                fb.setdefault(r[0], []).append(
                    {'feedback_uid': r[1], 'by': r[2], 'verdict': r[3],
                     'note': r[4], 'status': r[5], 'resolution': r[6],
                     'at': _iso(r[7])})
        for m in messages:
            m['created_at'] = _iso(m['created_at'])
            m['evidence'] = evidence.get(m['message_uid'], [])
            m['feedback'] = fb.get(m['message_uid'], [])
        head['messages'] = messages
        return head
    return _read(work)


@_gate(wa.PERM_REVIEW)
def answers():
    if request.method == 'POST':
        data = _body()
        return _run(lambda cur, who: wa.create_answer(cur, who, data),
                    audit=lambda r: ('CREATE', f"Waswa correction drafted: {r['question'][:80]}"))
    return _read(lambda cur, who: {'answers': wa.list_answers(
        cur, request.args.get('status'), request.args.get('q'),
        _int_arg('limit', 50, 200), _int_arg('offset', 0, 100000))})


@_gate(wa.PERM_REVIEW)
def answer(answer_uid):
    if request.method == 'POST':
        data = _body()
        return _run(lambda cur, who: wa.update_answer(cur, who, answer_uid, data),
                    audit=('UPDATE', f'Waswa correction edited: {answer_uid}'))
    return _read(lambda cur, who: wa.get_answer(cur, answer_uid))


@_gate(wa.PERM_REVIEW)
def answer_submit(answer_uid):
    return _run(lambda cur, who: wa.submit_answer(cur, who, answer_uid),
                audit=('SUBMIT', f'Waswa correction submitted: {answer_uid}'))


@_gate(wa.PERM_REVIEW)
def answer_retire(answer_uid):
    data = _body()
    return _run(lambda cur, who: wa.retire_answer(cur, who, answer_uid,
                                                  data.get('reason')),
                audit=('RETIRE', f'Waswa correction retired: {answer_uid}'))


@_gate(wa.PERM_APPROVE)
def answer_decide(answer_uid):
    data = _body()
    decision = str(data.get('decision') or '').lower()
    return _run(lambda cur, who: wa.decide_answer(cur, who, answer_uid,
                                                  decision, data.get('note')),
                audit=lambda r: (decision.upper(),
                                 f"Waswa correction {decision}: {answer_uid} "
                                 f"(now {r['status']})"))


@_gate(wa.PERM_APPROVE)
def answer_confirm(answer_uid):
    data = _body()
    return _run(lambda cur, who: wa.confirm_answer(cur, who, answer_uid,
                                                   data.get('review_due'),
                                                   data.get('note')),
                audit=('CONFIRM', f'Waswa correction reconfirmed: {answer_uid}'))


@_gate(wa.PERM_REVIEW)
def feedback_resolve(feedback_uid):
    data = _body()
    return _run(lambda cur, who: wa.resolve_feedback(
        cur, who, feedback_uid, str(data.get('resolution') or '').lower(),
        data.get('note'), data.get('answer_uid')),
        audit=lambda r: ('RESOLVE', f"Waswa flag {feedback_uid}: {r['resolution']}"))


@_gate(wa.PERM_REVIEW)
def sources():
    include_removed = str(request.args.get('include_removed', '')).lower() in ('1', 'true', 'yes')
    include_old = str(request.args.get('include_old', '')).lower() in ('1', 'true', 'yes')

    def work(cur, who):
        where = []
        if not include_removed:
            where.append("active = TRUE")
        if not include_old:
            where.append("superseded_by IS NULL")
        cur.execute("SELECT source_uid, title, document_type, authority_level, "
                    "review_status, audience, chunk_count, reviewed_by, "
                    "reviewed_at, ingested_at, superseded_by, active, "
                    "replaces_source_uid, original_filename, ingested_by, "
                    "version_label, redactions, removed_at, removed_reason "
                    "FROM dll_waswa_sources "
                    + (f"WHERE {' AND '.join(where)} " if where else '')
                    + "ORDER BY active DESC, authority_level, title")
        keys = ('source_uid', 'title', 'document_type', 'authority_level',
                'review_status', 'audience', 'chunk_count', 'reviewed_by',
                'reviewed_at', 'ingested_at', 'superseded_by', 'active',
                'replaces_source_uid', 'original_filename', 'ingested_by',
                'version_label', 'redactions', 'removed_at', 'removed_reason')
        rows = [dict(zip(keys, r)) for r in (cur.fetchall() if cur.rowcount > 0 else [])]
        for r in rows:
            for k in ('reviewed_at', 'ingested_at', 'removed_at'):
                r[k] = _iso(r[k])
        return {'sources': rows, 'document_types': list(wd.DOCUMENT_TYPES),
                'max_upload_mb': wd.MAX_UPLOAD_BYTES // (1024 * 1024),
                'allowed_extensions': sorted(wd.ALLOWED),
                'upload_check': wd.upload_readiness()}
    return _read(work)


@_gate(wa.PERM_REVIEW)
def source_detail(source_uid):
    return _read(lambda cur, who: wd.detail(cur, source_uid))


@_gate(wa.PERM_REVIEW)
def source_upload():
    upload = request.files.get('file')
    if upload is None or not upload.filename:
        return reply('error', 400, 'Choose a file to upload (form field "file").', '')
    data = upload.read(wd.MAX_UPLOAD_BYTES + 1)
    form = request.form.to_dict()
    return _run(lambda cur, who: wd.upload(cur, who, upload.filename, data, form),
                audit=lambda r: ('UPLOAD', f"Waswa document uploaded: {r['title']}"
                                 + (' (new version)' if r.get('replaces_source_uid') else '')))


@_gate(wa.PERM_REVIEW)
def authority_levels():
    return _read(lambda cur, who: {'levels': wd.authority_levels(cur)})


@_gate(wa.PERM_APPROVE)
def source_review(source_uid):
    data = _body()
    decision = str(data.get('decision') or '').lower()
    return _run(lambda cur, who: wd.review(cur, who, source_uid, decision, data.get('note')),
                audit=lambda r: ('REVIEW', f"Waswa document {r['title']}: {r['review_status']}"))


@_gate(wa.PERM_APPROVE)
def source_remove(source_uid):
    data = _body()
    return _run(lambda cur, who: wd.remove(cur, who, source_uid, data.get('reason')),
                audit=lambda r: ('REMOVE', f"Waswa document removed: {r['title']}"))


@_gate(wa.PERM_APPROVE)
def source_restore(source_uid):
    return _run(lambda cur, who: wd.restore(cur, who, source_uid),
                audit=lambda r: ('RESTORE', f"Waswa document restored: {r['title']}"))


@_gate(wa.PERM_APPROVE)
def source_details(source_uid):
    data = _body()
    return _run(lambda cur, who: wd.update_details(cur, who, source_uid, data),
                audit=lambda r: ('UPDATE', f"Waswa document details changed: {r['title']}"))


@_gate(wa.PERM_APPROVE)
def source_audience(source_uid):
    data = _body()
    return _run(lambda cur, who: wa.set_source_audience(
        cur, who, source_uid, str(data.get('audience') or '').lower()),
        audit=lambda r: ('UPDATE', f"Waswa document {r['title']} visible to {r['audience']}"))


@_gate(wa.PERM_REVIEW)
def match_preview():
    q = (request.args.get('q') or _body().get('q') or '').strip()
    audience = request.args.get('audience') or 'staff'
    if audience not in ('staff', 'everyone'):
        audience = 'staff'
    return _read(lambda cur, who: {
        'query': q, 'audience': audience,
        # record=False: a preview is not a real question and must not
        # inflate match counts.
        'matches': wa.match(cur, q, audience, record=False)})


# ── Registration ───────────────────────────────────────────────────────────

_ROUTES = [
    ('/assistant/feedback', feedback, ['POST']),
    ('/assistant/console/summary', summary, ['GET']),
    ('/assistant/console/queue', queue, ['GET']),
    ('/assistant/console/conversations', conversations, ['GET']),
    ('/assistant/console/conversations/<conversation_uid>', conversation, ['GET']),
    ('/assistant/console/answers', answers, ['GET', 'POST']),
    ('/assistant/console/answers/<answer_uid>', answer, ['GET', 'POST']),
    ('/assistant/console/answers/<answer_uid>/submit', answer_submit, ['POST']),
    ('/assistant/console/answers/<answer_uid>/retire', answer_retire, ['POST']),
    ('/assistant/console/answers/<answer_uid>/decide', answer_decide, ['POST']),
    ('/assistant/console/answers/<answer_uid>/confirm', answer_confirm, ['POST']),
    ('/assistant/console/feedback/<feedback_uid>/resolve', feedback_resolve, ['POST']),
    ('/assistant/console/sources', sources, ['GET']),
    ('/assistant/console/sources/upload', source_upload, ['POST']),
    ('/assistant/console/sources/<source_uid>', source_detail, ['GET']),
    ('/assistant/console/sources/<source_uid>/review', source_review, ['POST']),
    ('/assistant/console/sources/<source_uid>/audience', source_audience, ['POST']),
    ('/assistant/console/sources/<source_uid>/remove', source_remove, ['POST']),
    ('/assistant/console/sources/<source_uid>/restore', source_restore, ['POST']),
    ('/assistant/console/sources/<source_uid>/details', source_details, ['POST']),
    ('/assistant/console/authority-levels', authority_levels, ['GET']),
    ('/assistant/console/match', match_preview, ['GET', 'POST']),
]


def register(blueprint):
    for rule, view, methods in _ROUTES:
        blueprint.add_url_rule(rule, endpoint=f'waswa_console_{view.__name__}',
                               view_func=view, methods=methods)
