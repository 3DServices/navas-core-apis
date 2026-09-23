"""
waswa_answers.py — corrections, feedback and who may do what (Portal Phase A).

The training loop's rules, in one place, so the chat path and the console
cannot disagree about them:

  * Who the caller is to Waswa. Three permissions (migration 041):
    waswa.staff_knowledge, waswa.review, waswa.approve. Admin roles hold all
    three. The global require_permission decorator lets `customer_tracker`
    through every check; this module deliberately does not, because a fleet
    customer is exactly who must not read internal procedures or approve what
    Waswa tells other customers.

  * Which corrections match a question (`match`). Stricter than document
    search: a correction is given as a verified answer, so a loose match here
    is a confident wrong answer with a staff label on it.

  * The correction lifecycle — draft, pending, approved, rejected, retired —
    and its guards:
      - no currency amounts, ever (the pricing block extends to what staff
        write, not only to what documents say);
      - text about money, approvals or account actions is 'policy' and needs
        two approvers; nobody can lower that;
      - nobody approves their own correction (the database enforces it too);
      - editing an approved correction makes a new version; the old one stays
        live until the new one is approved, then retires.

Every function takes the caller's connection and does not commit. The endpoint
owns the transaction, so a state change and its transparency-log entry land
together or not at all.
"""

import re
import uuid
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

from .globals import _get_user_permissions

PERM_STAFF = 'waswa.staff_knowledge'
PERM_REVIEW = 'waswa.review'
PERM_APPROVE = 'waswa.approve'

_ADMIN_ROLES = {'super_admin', 'system'}
# Internal administrators get the whole console too. 'admin' is also the role
# name a CUSTOMER organisation's own admin carries (account_type 'client'), and
# a customer must never read internal documents or approve what Waswa tells
# other customers — so these roles count only on a non-client account.
_STAFF_ADMIN_ROLES = {'admin', 'sysadmin', 'sys_admin'}
_CUSTOMER_ACCOUNT_TYPES = {'client', 'customer', 'customer_tracker'}

# How long an approved correction stands before someone must confirm it.
DEFAULT_REVIEW_DAYS = 180

# At most this many corrections are offered to the model on one turn.
_MATCH_LIMIT = 3
# Floor on ts_rank_cd for a correction to count as a match at all.
_MATCH_MIN_RANK = 0.05


class RuleError(Exception):
    """A request the rules refuse. The message is shown to the person."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ── Who is asking ──────────────────────────────────────────────────────────

def caller(account_uid):
    """The caller's role and Waswa permissions, or None if not an active user."""
    role, account_type, account_root, permissions = \
        _get_user_permissions(account_uid)
    if role is None:
        return None
    role_name = str(role or '').strip().lower()
    account_kind = str(account_type or '').strip().lower()
    is_admin = (role_name in _ADMIN_ROLES or account_kind == 'system_account'
                or (role_name in _STAFF_ADMIN_ROLES
                    and account_kind not in _CUSTOMER_ACCOUNT_TYPES))
    granted = set(permissions or [])
    if account_kind in _CUSTOMER_ACCOUNT_TYPES:
        # A customer account never holds a Waswa permission, even if someone
        # ticks waswa.* on a role that customer admins share (e.g. 'admin').
        granted = {p for p in granted if not p.startswith('waswa.')}
    if is_admin:
        granted |= {PERM_STAFF, PERM_REVIEW, PERM_APPROVE}
    return {
        'account_uid': str(account_uid),
        'role': role,
        'account_type': account_type,
        'account_root': account_root,
        'is_admin': is_admin,
        'permissions': sorted(p for p in granted if p.startswith('waswa.')),
        '_granted': granted,
    }


def can(who, permission):
    return bool(who) and permission in who['_granted']


def audience_for(who):
    """'staff' if this person may be answered from internal material."""
    if who and (can(who, PERM_STAFF) or can(who, PERM_REVIEW)
                or can(who, PERM_APPROVE)):
        return 'staff'
    return 'everyone'


def audiences_visible(audience):
    """The audience values a caller of this audience may read."""
    return ('staff', 'everyone') if audience == 'staff' else ('everyone',)


# ── Content guards ─────────────────────────────────────────────────────────

_AMOUNT = r'(?:\d(?:[\d,]*\d)?(?:\.\d+)?)'
_CURRENCY = re.compile(
    r'\b(?:UGX|KES|Ksh|KSh|USD|EUR|GBP|TZS|RWF|shillings?|dollars?)\s?' + _AMOUNT
    + r'|\$\s?' + _AMOUNT
    + r'|' + _AMOUNT + r'\s?(?:UGX|KES|Ksh|KSh|USD|/=|shillings?)\b',
    re.IGNORECASE)

_POLICY = re.compile(
    r'\b(?:discount\w*|approv\w*|pric\w*|refund\w*|credit\w*|commission\w*|'
    r'suspend\w*|suspension|immobili\w*|contract\w*|legal\w*|insurance|'
    r'penalt\w*|terminat\w*|cancel\w*|billing|invoice\w*|payment\w*|'
    r'threshold\w*)\b',
    re.IGNORECASE)


def _check_content(question, answer):
    for field, text in (('question', question), ('answer', answer)):
        if _CURRENCY.search(text or ''):
            raise RuleError(
                f'The {field} contains a currency amount. Waswa never states '
                f'prices; remove the figure and refer pricing to sales.')


def _sensitivity(requested, question, answer, variants):
    """The sensitivity a correction must carry. Only ever raised."""
    text = ' '.join(filter(None, (question, answer, variants)))
    if requested == 'policy' or _POLICY.search(text):
        return 'policy', 2
    return 'routine', 1


def _clean(value, limit=None):
    text = (value or '').strip() if isinstance(value, str) else value
    if isinstance(text, str) and limit:
        text = text[:limit]
    return text or None


# ── Logging ────────────────────────────────────────────────────────────────

def log(cur, who, entry_type, action, rationale, detail=None,
        conversation_uid=None, message_uid=None):
    """Transparency-log entry in the caller's transaction."""
    cur.execute(
        "INSERT INTO dll_waswa_transparency_log "
        "(entry_uid, account_uid, account_root, conversation_uid, message_uid, "
        " entry_type, action, rationale, approver_account_uid, approved_at, detail) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
        "        CASE WHEN %s THEN NOW() END, %s)",
        (str(uuid.uuid4()), who['account_uid'], who.get('account_root'),
         conversation_uid, message_uid, entry_type, action, rationale,
         who['account_uid'] if entry_type == 'approval' else None,
         entry_type == 'approval',
         psycopg2.extras.Json(detail) if detail else None))


# ── Matching (the chat path) ───────────────────────────────────────────────

_STOP = {
    'the', 'and', 'for', 'are', 'you', 'your', 'our', 'can', 'how', 'what',
    'why', 'who', 'when', 'where', 'with', 'from', 'does', 'did', 'was',
    'were', 'has', 'have', 'had', 'that', 'this', 'there', 'they', 'them',
    'about', 'into', 'will', 'would', 'should', 'could', 'been', 'get', 'tell',
    'need', 'want', 'know', 'any', 'all', 'not', 'but', 'its', 'please',
    'also', 'just', 'like', 'some', 'much', 'very', 'mine', 'i', 'my', 'me',
}


def _terms(text):
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]{2,}", text or '')
    seen, out = set(), []
    for w in words:
        lw = w.lower()
        if lw not in _STOP and lw not in seen:
            seen.add(lw)
            out.append(w)
    return out[:12]


_ANSWER_FIELDS = (
    "answer_uid, question, question_variants, answer, audience, country_scope, "
    "product_uid, sensitivity, approvals_required, status, version, "
    "supersedes_answer_uid, source_feedback_uid, source_message_uid, "
    "based_on_source_uid, based_on_note, authored_by, submitted_at, "
    "approved_at, retired_at, retired_by, retired_reason, review_due, "
    "needs_recheck, recheck_reason, match_count, last_matched_at, created_at, "
    "updated_at")
_ANSWER_KEYS = [f.strip() for f in _ANSWER_FIELDS.split(',')]


def _answer_dict(row):
    item = dict(zip(_ANSWER_KEYS, row))
    for key in ('submitted_at', 'approved_at', 'retired_at', 'review_due',
                'last_matched_at', 'created_at', 'updated_at'):
        if item.get(key) is not None:
            item[key] = item[key].isoformat()
    return item


def match(cur, question, audience, limit=_MATCH_LIMIT, record=True):
    """Approved corrections that answer [question], best first.

    Tiers, strict to loose, stopping at the first that finds anything:
      phrase   websearch_to_tsquery over the question fields
      words    every meaningful word present
      most     at least 60% of the meaningful words, and never fewer than 2
    Only question and variants are searched — a correction is found by what
    people ask, not by words that happen to appear in its answer.
    """
    question = (question or '').strip()
    if not question:
        return []

    base = (
        f"SELECT {_ANSWER_FIELDS}, ts_rank_cd(qv, q, 32) AS score "
        f"FROM (SELECT a.*, "
        f"        setweight(to_tsvector('english', coalesce(a.question,'')), 'A') || "
        f"        setweight(to_tsvector('english', coalesce(a.question_variants,'')), 'A') AS qv "
        f"      FROM dll_waswa_answers a "
        f"      WHERE a.status = 'approved' AND a.audience = ANY(%(aud)s)) x, "
        f"     {{expr}} AS q "
        f"WHERE qv @@ q AND ts_rank_cd(qv, q, 32) >= %(floor)s {{extra}} "
        f"ORDER BY score DESC, approved_at DESC LIMIT %(limit)s")
    params = {'q': question, 'aud': list(audiences_visible(audience)),
              'floor': _MATCH_MIN_RANK, 'limit': int(limit)}

    attempts = [
        ('phrase', "websearch_to_tsquery('english', %(q)s)", ''),
        ('words', "plainto_tsquery('english', %(q)s)", ''),
    ]
    terms = _terms(question)
    if len(terms) >= 2:
        counters = []
        for i, term in enumerate(terms):
            params[f't{i}'] = term
            counters.append(f"(qv @@ plainto_tsquery('english', %(t{i})s))::int")
        params['need'] = max(2, -(-len(terms) * 6 // 10))     # ceil(60%)
        params['or_terms'] = ' | '.join(
            re.sub(r'[^A-Za-z0-9]', '', t) or 'x' for t in terms)
        attempts.append(('most words', "to_tsquery('english', %(or_terms)s)",
                         f"AND ({' + '.join(counters)}) >= %(need)s"))

    for how, expr, extra in attempts:
        cur.execute(base.format(expr=expr, extra=extra), params)
        rows = cur.fetchall() if cur.rowcount > 0 else []
        if rows:
            found = []
            for row in rows:
                item = _answer_dict(row[:len(_ANSWER_KEYS)])
                item['score'] = round(float(row[len(_ANSWER_KEYS)]), 4)
                item['matched_on'] = how
                found.append(item)
            if record:
                cur.execute(
                    "UPDATE dll_waswa_answers "
                    "SET match_count = match_count + 1, last_matched_at = NOW() "
                    "WHERE answer_uid = ANY(%s)",
                    ([f['answer_uid'] for f in found],))
            return found
    return []


def render_for_prompt(matches):
    """The system message that puts matched corrections in front of the model."""
    lines = [
        'Verified answers — written and approved by NAVAS staff. They outrank '
        'every document and tool result except live account figures.',
        'If one of them answers what the user asked, give that answer '
        'faithfully: you may shorten or rephrase, never change a fact, and '
        'say it is a verified answer. If the user asked something different, '
        'ignore them — a verified answer to a neighbouring question is not an '
        'answer to this one.',
        '',
    ]
    for n, m in enumerate(matches, 1):
        scope = []
        if m.get('country_scope'):
            scope.append(f"applies in {m['country_scope']} only")
        if m.get('audience') == 'staff':
            scope.append('internal — staff only')
        approved = (m.get('approved_at') or '')[:10]
        lines.append(f"[{n}] Question: {m['question']}")
        if m.get('question_variants'):
            lines.append('    Also asked as: '
                         + '; '.join(v.strip() for v in
                                     m['question_variants'].splitlines()
                                     if v.strip()))
        lines.append(f"    Answer: {m['answer']}")
        lines.append(f"    Approved {approved}"
                     + (f" · {' · '.join(scope)}" if scope else ''))
    return '\n'.join(lines)


# ── Corrections: lifecycle ─────────────────────────────────────────────────

def get_answer(cur, answer_uid, lock=False):
    cur.execute(
        f"SELECT {_ANSWER_FIELDS} FROM dll_waswa_answers WHERE answer_uid = %s"
        + (" FOR UPDATE" if lock else ""), (str(answer_uid),))
    row = cur.fetchone() if cur.rowcount else None
    if not row:
        raise RuleError('No such correction.', 404)
    item = _answer_dict(row)
    cur.execute(
        "SELECT approver_account_uid, decision, note, created_at "
        "FROM dll_waswa_answer_approvals WHERE answer_uid = %s ORDER BY created_at",
        (str(answer_uid),))
    item['decisions'] = [
        {'by': r[0], 'decision': r[1], 'note': r[2], 'at': r[3].isoformat()}
        for r in (cur.fetchall() if cur.rowcount > 0 else [])]
    item['approvals'] = sum(1 for d in item['decisions']
                            if d['decision'] == 'approve')
    return item


def list_answers(cur, status=None, q=None, limit=50, offset=0):
    where, params = [], []
    if status:
        where.append("status = ANY(%s)")
        params.append([s.strip() for s in str(status).split(',') if s.strip()])
    if q:
        where.append("search_vector @@ plainto_tsquery('english', %s)")
        params.append(q)
    sql = (f"SELECT {_ANSWER_FIELDS} FROM dll_waswa_answers "
           + (f"WHERE {' AND '.join(where)} " if where else '')
           + "ORDER BY updated_at DESC LIMIT %s OFFSET %s")
    cur.execute(sql, params + [min(int(limit), 200), int(offset)])
    return [_answer_dict(r) for r in (cur.fetchall() if cur.rowcount > 0 else [])]


_EDITABLE = ('question', 'question_variants', 'answer', 'audience',
             'country_scope', 'product_uid', 'based_on_source_uid',
             'based_on_note', 'review_due')


def _normalise(fields):
    out = {k: _clean(fields.get(k)) for k in _EDITABLE if k in fields}
    if 'audience' in out and out['audience'] not in (None, 'staff', 'everyone'):
        raise RuleError("audience must be 'staff' or 'everyone'.")
    if out.get('review_due'):
        try:
            out['review_due'] = date.fromisoformat(str(out['review_due'])[:10])
        except ValueError:
            raise RuleError('review_due must be a date, YYYY-MM-DD.')
    return out


def create_answer(cur, who, fields):
    data = _normalise(fields)
    if not data.get('question') or not data.get('answer'):
        raise RuleError('A correction needs both a question and an answer.')
    _check_content(data['question'], data['answer'])
    sensitivity, required = _sensitivity(
        fields.get('sensitivity'), data['question'], data['answer'],
        data.get('question_variants'))

    feedback_uid = _clean(fields.get('feedback_uid'))
    source_message = _clean(fields.get('source_message_uid'))
    if feedback_uid:
        cur.execute("SELECT message_uid FROM dll_waswa_feedback "
                    "WHERE feedback_uid = %s", (feedback_uid,))
        if not cur.rowcount:
            raise RuleError('No such feedback item.', 404)
        source_message = source_message or cur.fetchone()[0]
        cur.execute("UPDATE dll_waswa_feedback SET status = 'in_review', "
                    "assigned_to = COALESCE(assigned_to, %s), updated_at = NOW() "
                    "WHERE feedback_uid = %s AND status = 'open'",
                    (who['account_uid'], feedback_uid))

    answer_uid = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO dll_waswa_answers "
        "(answer_uid, question, question_variants, answer, audience, "
        " country_scope, product_uid, sensitivity, approvals_required, "
        " source_feedback_uid, source_message_uid, based_on_source_uid, "
        " based_on_note, review_due, authored_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (answer_uid, data['question'], data.get('question_variants'),
         data['answer'], data.get('audience') or 'staff',
         data.get('country_scope'), data.get('product_uid'), sensitivity,
         required, feedback_uid, source_message,
         data.get('based_on_source_uid'), data.get('based_on_note'),
         data.get('review_due'), who['account_uid']))
    log(cur, who, 'knowledge_change', 'correction_drafted',
        f'Drafted correction for: {data["question"][:200]}',
        {'answer_uid': answer_uid, 'sensitivity': sensitivity},
        message_uid=source_message)
    return get_answer(cur, answer_uid)


def update_answer(cur, who, answer_uid, fields):
    current = get_answer(cur, answer_uid, lock=True)
    data = _normalise(fields)

    if current['status'] == 'retired':
        raise RuleError('A retired correction cannot be edited. Write a new one.', 409)

    merged = {k: data.get(k, current.get(k)) for k in _EDITABLE}
    _check_content(merged['question'], merged['answer'])
    # The floor is what the current row already carries: a policy correction
    # stays policy even if the edit removes the words that made it so.
    floor = 'policy' if current['sensitivity'] == 'policy' else fields.get('sensitivity')
    sensitivity, required = _sensitivity(
        floor, merged['question'], merged['answer'], merged['question_variants'])

    if current['status'] == 'approved':
        # An approved correction is live. The edit becomes a new version and
        # the live one keeps answering until that version is approved.
        cur.execute("SELECT 1 FROM dll_waswa_answers "
                    "WHERE supersedes_answer_uid = %s "
                    "AND status IN ('draft', 'pending')", (answer_uid,))
        if cur.rowcount:
            raise RuleError('A revision of this correction is already in '
                            'progress. Edit that one instead.', 409)
        new_uid = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO dll_waswa_answers "
            "(answer_uid, question, question_variants, answer, audience, "
            " country_scope, product_uid, sensitivity, approvals_required, "
            " version, supersedes_answer_uid, source_feedback_uid, "
            " source_message_uid, based_on_source_uid, based_on_note, "
            " review_due, authored_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (new_uid, merged['question'], merged['question_variants'],
             merged['answer'], merged['audience'] or 'staff',
             merged['country_scope'], merged['product_uid'], sensitivity,
             required, current['version'] + 1, answer_uid,
             _clean(fields.get('feedback_uid')) or current['source_feedback_uid'],
             current['source_message_uid'], merged['based_on_source_uid'],
             merged['based_on_note'], None, who['account_uid']))
        log(cur, who, 'knowledge_change', 'correction_revised',
            f'New version {current["version"] + 1} of an approved correction',
            {'answer_uid': new_uid, 'supersedes': answer_uid})
        return get_answer(cur, new_uid)

    if current['authored_by'] != who['account_uid'] and not who['is_admin']:
        raise RuleError('Only the author can edit a draft. Reject it with a '
                        'note, or write your own.', 403)

    cur.execute(
        "UPDATE dll_waswa_answers SET question=%s, question_variants=%s, "
        " answer=%s, audience=%s, country_scope=%s, product_uid=%s, "
        " based_on_source_uid=%s, based_on_note=%s, review_due=%s, "
        " sensitivity=%s, approvals_required=%s, status='draft', "
        " submitted_at=NULL, updated_at=NOW() WHERE answer_uid=%s",
        (merged['question'], merged['question_variants'], merged['answer'],
         merged['audience'] or 'staff', merged['country_scope'],
         merged['product_uid'], merged['based_on_source_uid'],
         merged['based_on_note'], merged['review_due'], sensitivity,
         required, answer_uid))
    # Approvals were given to the old text. They do not carry over.
    cur.execute("DELETE FROM dll_waswa_answer_approvals WHERE answer_uid = %s",
                (answer_uid,))
    log(cur, who, 'knowledge_change', 'correction_edited',
        'Edited; any approvals cleared and returned to draft',
        {'answer_uid': answer_uid, 'previous_status': current['status']})
    return get_answer(cur, answer_uid)


def submit_answer(cur, who, answer_uid):
    current = get_answer(cur, answer_uid, lock=True)
    if current['status'] not in ('draft', 'rejected'):
        raise RuleError(f"Only a draft can be submitted; this one is "
                        f"{current['status']}.", 409)
    cur.execute("UPDATE dll_waswa_answers SET status='pending', "
                "submitted_at=NOW(), updated_at=NOW() WHERE answer_uid=%s",
                (answer_uid,))
    log(cur, who, 'knowledge_change', 'correction_submitted',
        f"Submitted for approval ({current['approvals_required']} needed)",
        {'answer_uid': answer_uid})
    return get_answer(cur, answer_uid)


def decide_answer(cur, who, answer_uid, decision, note=None):
    if decision not in ('approve', 'reject'):
        raise RuleError("decision must be 'approve' or 'reject'.")
    current = get_answer(cur, answer_uid, lock=True)
    if current['status'] != 'pending':
        raise RuleError(f"Only a submitted correction can be decided; this "
                        f"one is {current['status']}.", 409)
    if current['authored_by'] == who['account_uid']:
        raise RuleError('You wrote this correction, so someone else has to '
                        'approve it.', 403)
    if decision == 'reject' and not _clean(note):
        raise RuleError('Say why it is rejected, so the author can fix it.')

    try:
        cur.execute(
            "INSERT INTO dll_waswa_answer_approvals "
            "(answer_uid, approver_account_uid, decision, note) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (answer_uid, approver_account_uid) DO UPDATE "
            "SET decision = EXCLUDED.decision, note = EXCLUDED.note, "
            "    created_at = NOW()",
            (answer_uid, who['account_uid'], decision, _clean(note)))
    except psycopg2.errors.CheckViolation:
        raise RuleError('You wrote this correction, so someone else has to '
                        'approve it.', 403)

    log(cur, who, 'approval', f'correction_{decision}',
        _clean(note) or f'{decision}d',
        {'answer_uid': answer_uid, 'sensitivity': current['sensitivity']},
        message_uid=current['source_message_uid'])

    if decision == 'reject':
        cur.execute("UPDATE dll_waswa_answers SET status='rejected', "
                    "updated_at=NOW() WHERE answer_uid=%s", (answer_uid,))
        return get_answer(cur, answer_uid)

    cur.execute("SELECT COUNT(*) FROM dll_waswa_answer_approvals "
                "WHERE answer_uid=%s AND decision='approve'", (answer_uid,))
    approvals = cur.fetchone()[0]
    if approvals < current['approvals_required']:
        return get_answer(cur, answer_uid)

    review_due = current['review_due'] or (
        date.today() + timedelta(days=DEFAULT_REVIEW_DAYS)).isoformat()
    cur.execute("UPDATE dll_waswa_answers SET status='approved', "
                "approved_at=NOW(), review_due=%s, needs_recheck=FALSE, "
                "recheck_reason=NULL, updated_at=NOW() WHERE answer_uid=%s",
                (review_due, answer_uid))

    if current['supersedes_answer_uid']:
        cur.execute("UPDATE dll_waswa_answers SET status='retired', "
                    "retired_at=NOW(), retired_by=%s, "
                    "retired_reason='Replaced by version ' || %s, "
                    "updated_at=NOW() "
                    "WHERE answer_uid=%s AND status='approved'",
                    (who['account_uid'], str(current['version']),
                     current['supersedes_answer_uid']))

    if current['source_feedback_uid']:
        cur.execute("UPDATE dll_waswa_feedback SET status='resolved', "
                    "resolution='correction', answer_uid=%s, resolved_by=%s, "
                    "resolved_at=NOW(), updated_at=NOW() "
                    "WHERE feedback_uid=%s AND status IN ('open','in_review')",
                    (answer_uid, who['account_uid'],
                     current['source_feedback_uid']))

    log(cur, who, 'knowledge_change', 'correction_live',
        'Approved and live on every platform',
        {'answer_uid': answer_uid, 'approvals': approvals})
    return get_answer(cur, answer_uid)


def retire_answer(cur, who, answer_uid, reason):
    current = get_answer(cur, answer_uid, lock=True)
    if current['status'] == 'retired':
        return current
    if not _clean(reason):
        raise RuleError('Say why it is being retired.')
    cur.execute("UPDATE dll_waswa_answers SET status='retired', "
                "retired_at=NOW(), retired_by=%s, retired_reason=%s, "
                "updated_at=NOW() WHERE answer_uid=%s",
                (who['account_uid'], _clean(reason), answer_uid))
    log(cur, who, 'knowledge_change', 'correction_retired', _clean(reason),
        {'answer_uid': answer_uid, 'previous_status': current['status']})
    return get_answer(cur, answer_uid)


def confirm_answer(cur, who, answer_uid, review_due=None, note=None):
    """Recheck done: the approved correction is still right."""
    current = get_answer(cur, answer_uid, lock=True)
    if current['status'] != 'approved':
        raise RuleError('Only a live correction can be confirmed.', 409)
    if current['authored_by'] == who['account_uid'] and current['sensitivity'] == 'policy':
        raise RuleError('A policy correction is confirmed by someone other '
                        'than its author.', 403)
    due = _normalise({'review_due': review_due}).get('review_due') if review_due \
        else date.today() + timedelta(days=DEFAULT_REVIEW_DAYS)
    cur.execute("UPDATE dll_waswa_answers SET needs_recheck=FALSE, "
                "recheck_reason=NULL, review_due=%s, updated_at=NOW() "
                "WHERE answer_uid=%s", (due, answer_uid))
    log(cur, who, 'approval', 'correction_confirmed',
        _clean(note) or 'Confirmed still correct',
        {'answer_uid': answer_uid, 'review_due': str(due)})
    return get_answer(cur, answer_uid)


# ── Feedback ───────────────────────────────────────────────────────────────

def record_feedback(cur, who, message_uid, verdict, note=None, surface=None):
    """A verdict on an assistant answer, from its owner or a reviewer."""
    if verdict not in ('wrong', 'unhelpful', 'good'):
        raise RuleError("verdict must be 'wrong', 'unhelpful' or 'good'.")
    cur.execute(
        "SELECT m.conversation_uid, m.role, c.account_uid, c.surface "
        "FROM dll_waswa_messages m "
        "JOIN dll_waswa_conversations c ON c.conversation_uid = m.conversation_uid "
        "WHERE m.message_uid = %s", (str(message_uid),))
    row = cur.fetchone() if cur.rowcount else None
    if not row:
        raise RuleError('No such answer.', 404)
    conversation_uid, role, owner, conv_surface = row
    if role != 'assistant':
        raise RuleError('Feedback is given on Waswa\'s answers, not on questions.')
    if owner != who['account_uid'] and not can(who, PERM_REVIEW):
        # Same response as a missing message: do not confirm that someone
        # else's conversation exists.
        raise RuleError('No such answer.', 404)

    status = 'resolved' if verdict == 'good' else 'open'
    resolution = 'dismissed' if verdict == 'good' else None
    feedback_uid = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO dll_waswa_feedback "
        "(feedback_uid, message_uid, conversation_uid, account_uid, surface, "
        " verdict, note, status, resolution) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (message_uid, account_uid) DO UPDATE SET "
        "  verdict = EXCLUDED.verdict, note = EXCLUDED.note, "
        "  status = CASE WHEN dll_waswa_feedback.status IN ('resolved','dismissed') "
        "                 AND EXCLUDED.verdict <> 'good' THEN 'open' "
        "                ELSE EXCLUDED.status END, "
        "  resolution = CASE WHEN EXCLUDED.verdict = 'good' THEN 'dismissed' "
        "                    ELSE dll_waswa_feedback.resolution END, "
        "  updated_at = NOW() "
        "RETURNING feedback_uid, status",
        (feedback_uid, str(message_uid), conversation_uid, who['account_uid'],
         _clean(surface) or conv_surface, verdict, _clean(note, 2000),
         status, resolution))
    feedback_uid, status = cur.fetchone()
    log(cur, who, 'feedback', f'feedback_{verdict}',
        _clean(note, 500) or verdict, {'feedback_uid': feedback_uid},
        conversation_uid=conversation_uid, message_uid=str(message_uid))
    return {'feedback_uid': feedback_uid, 'status': status, 'verdict': verdict}


def resolve_feedback(cur, who, feedback_uid, resolution, note=None,
                     answer_uid=None):
    if resolution not in ('correction', 'document', 'data_fix', 'dismissed'):
        raise RuleError("resolution must be correction, document, data_fix "
                        "or dismissed.")
    if resolution == 'dismissed' and not _clean(note):
        raise RuleError('Say why the answer was fine, so the pattern is visible.')
    if resolution == 'correction' and not answer_uid:
        raise RuleError('Link the correction that resolves it. A correction '
                        'resolves its flag automatically when approved.')
    cur.execute("SELECT status FROM dll_waswa_feedback WHERE feedback_uid=%s "
                "FOR UPDATE", (str(feedback_uid),))
    if not cur.rowcount:
        raise RuleError('No such feedback item.', 404)
    cur.execute(
        "UPDATE dll_waswa_feedback SET status=%s, resolution=%s, "
        " resolution_note=%s, answer_uid=COALESCE(%s, answer_uid), "
        " resolved_by=%s, resolved_at=NOW(), updated_at=NOW() "
        "WHERE feedback_uid=%s",
        ('dismissed' if resolution == 'dismissed' else 'resolved', resolution,
         _clean(note), _clean(answer_uid), who['account_uid'],
         str(feedback_uid)))
    log(cur, who, 'override' if resolution == 'dismissed' else 'knowledge_change',
        f'feedback_{resolution}', _clean(note) or resolution,
        {'feedback_uid': str(feedback_uid)})
    return {'feedback_uid': str(feedback_uid), 'resolution': resolution}


# ── Documents ──────────────────────────────────────────────────────────────

def review_source(cur, who, source_uid, decision, note=None):
    if decision not in ('approved', 'rejected', 'pending'):
        raise RuleError("decision must be approved, rejected or pending.")
    cur.execute("UPDATE dll_waswa_sources SET review_status=%s, reviewed_by=%s, "
                "reviewed_at=NOW(), updated_at=NOW() WHERE source_uid=%s "
                "RETURNING title", (decision, who['account_uid'], str(source_uid)))
    if not cur.rowcount:
        raise RuleError('No such document.', 404)
    title = cur.fetchone()[0]
    log(cur, who, 'approval', f'document_{decision}',
        _clean(note) or f'{title}: {decision}', {'source_uid': str(source_uid)})
    return {'source_uid': str(source_uid), 'title': title,
            'review_status': decision}


def set_source_audience(cur, who, source_uid, audience):
    if audience not in ('staff', 'everyone'):
        raise RuleError("audience must be 'staff' or 'everyone'.")
    cur.execute("UPDATE dll_waswa_sources SET audience=%s, updated_at=NOW() "
                "WHERE source_uid=%s RETURNING title",
                (audience, str(source_uid)))
    if not cur.rowcount:
        raise RuleError('No such document.', 404)
    title = cur.fetchone()[0]
    log(cur, who, 'approval', 'document_audience',
        f'{title}: now visible to {audience}',
        {'source_uid': str(source_uid), 'audience': audience})
    return {'source_uid': str(source_uid), 'title': title, 'audience': audience}
