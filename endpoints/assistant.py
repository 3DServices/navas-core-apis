"""
assistant.py — Waswa AI Assistant.

Phases 1 and 2 of the Waswa build plan. What changed from the v1 proxy:

  * The account context is assembled server-side from the JWT (waswa_context),
    not taken from the client. A `context` field in the request body is now
    ignored — a client that can assert its own customer class or token balance
    can talk Waswa into saying things the account is not entitled to.
  * Conversations and messages are persisted, so intent, outcomes and the
    transparency log have somewhere to live, and history no longer depends on
    the client sending it back.
  * The runtime system prompt is read from dll_waswa_prompts (versioned), not
    from a constant in this file.
  * Pricing questions never reach a model. Appendix C records that no approved
    price list exists and Odoo is not wired; until it is, a templated hand-off
    is the honest answer and a deterministic one.
  * Product questions are answered from the PPMM tables through tool calls
    (waswa_products), never from the prompt.
  * Every answer records the evidence it was built from.
  * Portal Phase A: approved staff corrections are matched before the model
    is called and put in front of it as verified answers; document search is
    limited to what the caller's audience may read; every reply returns its
    message_uid so the app can flag it. The console endpoints live in
    waswa_console and are registered onto this blueprint.

One connection per request, passed down. Opening a connection per lookup is how
a chat turn quietly becomes a multi-second one.

The OpenRouter API key stays server-side (config.OPENROUTER_API_KEY) and is
never exposed to any client.
"""

import json
import re
import time
import uuid

import psycopg2
import requests
from flask import Blueprint, request, current_app

from . import waswa_answers
from . import waswa_console
from . import waswa_knowledge
from . import waswa_products
from .globals import reply, _extract_account_uid
from .waswa_context import build_context, render_for_prompt
from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_SITE_URL,
    OPENROUTER_SITE_NAME,
)

assistant_bp = Blueprint("Assistant", __name__)
waswa_console.register(assistant_bp)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Turns of stored history replayed to the model, to cap token spend.
_MAX_HISTORY = 10

# A new turn joins the most recent open conversation on the same surface if it
# is this fresh. Keeps multi-turn working for clients that do not yet echo the
# conversation_uid we return.
_CONVERSATION_IDLE_MINUTES = 60

# Model -> tools -> model rounds before we stop. Enough for look up a product,
# check its compatibility, answer; a model looping past that is stuck.
_MAX_TOOL_ROUNDS = 4

# Retries for a dropped connection to OpenRouter, and the pause before each.
_CONNECT_RETRIES = 2
_RETRY_BACKOFF = (0.6, 1.5)

# Product tools (Phase 2) and document retrieval (Phase 3) are one list to the
# model. Order matters a little: the product tools come first so that a question
# naming a product is answered from the approved catalogue rather than from a
# paragraph in a user-story document that happens to mention it.
_TOOL_SPECS = waswa_products.TOOL_SPECS + waswa_knowledge.TOOL_SPECS

# Used only if dll_waswa_prompts is unreachable — migration 030 seeds v1 there.
_FALLBACK_PROMPT = (
    "You are Waswa, the in-app assistant for OLIWA, a fleet-tracking service "
    "powered by the NAVAS IoT engine and used mainly in East Africa. Answer "
    "only from the account context you are given. Never invent numbers, "
    "prices, products or account details. If you do not have something, say "
    "so plainly and say where the user can find it."
)

_PRICING_ROUTED_REPLY = (
    "I'm not able to quote prices. Pricing depends on your country, currency "
    "and account, and it has to come from our sales team rather than from me.\n\n"
    "I can pass your requirement to them with the details you've given me, or "
    "answer anything about how your current tokens and charges work. Which "
    "would you like?"
)


# ── Pricing detection ───────────────────────────────────────────────────────
# Narrow by design. It catches acquisition pricing — what something costs to
# buy, discounts, quotes — and not questions about charges the customer already
# has, which the account context can answer and which the app offers as a quick
# reply ("Explain My Charges").

_PRICING_PATTERNS = (
    r'\bhow much (?:is|are|does|do|would|will|for)\b',
    r'\b(?:price|prices|pricing|price list|rate card|tariff)\b',
    r'\b(?:quote|quotation|pfi|proforma|pro-forma)\b',
    r'\b(?:discount|discounted|cheaper|reduce the price|best price)\b',
    r'\bcost (?:of|for|to buy|per unit|per vehicle)\b',
    r'\bwhat (?:would|will) it cost\b',
    r'\bbei gani\b',            # Swahili: how much
    r'\bgharama\b',             # Swahili: cost
)

_OWN_CHARGES_PATTERNS = (
    r'\bmy (?:charges|charge|bill|billing|invoice|balance|tokens?|account)\b',
    r'\b(?:explain|understand|why) .{0,20}(?:charged|charges|deduction|deducted)\b',
    r'\bwhy (?:is|are) my\b',
)


def _is_pricing_enquiry(text):
    lowered = (text or '').lower()
    for pattern in _OWN_CHARGES_PATTERNS:
        if re.search(pattern, lowered):
            return False
    for pattern in _PRICING_PATTERNS:
        if re.search(pattern, lowered):
            return True
    return False


# ── Persistence helpers ─────────────────────────────────────────────────────
# Each takes the request's connection. All swallow their own errors: a logging
# failure must never cost the user an answer; it costs us a row, and the gap
# shows up in observability.

def _open_connection():
    conn = psycopg2.connect(current_app.config['db_link'])
    # These writes are independent appends; per-statement commit keeps the
    # helpers simple and avoids holding a transaction open across an HTTP call
    # to OpenRouter.
    conn.autocommit = True
    return conn


def _active_prompt(conn):
    """(body, version) of the active runtime prompt, or the fallback."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT body, version FROM dll_waswa_prompts "
                "WHERE prompt_key = 'runtime_system' AND is_active = TRUE "
                "LIMIT 1"
            )
            row = cur.fetchone() if cur.rowcount else None
        if row:
            return row[0], row[1]
    except Exception:       # noqa: BLE001
        pass
    return _FALLBACK_PROMPT, None


def _resume_or_open_conversation(conn, account_uid, scope, surface,
                                 requested_uid):
    """Return a conversation_uid, resuming the caller's recent one if any."""
    try:
        with conn.cursor() as cur:
            if requested_uid:
                cur.execute(
                    "SELECT conversation_uid FROM dll_waswa_conversations "
                    "WHERE conversation_uid = %s AND account_uid = %s",
                    (str(requested_uid), str(account_uid)),
                )
                if cur.rowcount:
                    return cur.fetchone()[0]
                # An unknown or someone else's uid is not honoured; we open a
                # fresh conversation rather than writing into theirs.

            cur.execute(
                "SELECT conversation_uid FROM dll_waswa_conversations "
                "WHERE account_uid = %s AND surface = %s AND status = 'open' "
                "  AND last_activity_at > NOW() - (%s * INTERVAL '1 minute') "
                "ORDER BY last_activity_at DESC LIMIT 1",
                (str(account_uid), str(surface), _CONVERSATION_IDLE_MINUTES),
            )
            if cur.rowcount:
                return cur.fetchone()[0]

            conversation_uid = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO dll_waswa_conversations "
                "(conversation_uid, account_uid, account_root, client_uid, surface) "
                "VALUES (%s, %s, %s, %s, %s)",
                (conversation_uid, str(account_uid), scope.get('account_root'),
                 scope.get('client_uid'), str(surface)),
            )
            return conversation_uid
    except Exception:       # noqa: BLE001
        return None


def _stored_history(conn, conversation_uid, limit=_MAX_HISTORY):
    """Prior turns as OpenRouter-style role/content dicts, oldest first."""
    if not conversation_uid:
        return []
    try:
        with conn.cursor() as cur:
            # Blocked replies are included on purpose. They are server
            # templates (e.g. the pricing hand-off), never model output, and
            # dropping them left the user's question in history with no
            # answer, so the model answered it again on the next turn.
            cur.execute(
                "SELECT role, content FROM dll_waswa_messages "
                "WHERE conversation_uid = %s "
                "ORDER BY turn_index DESC LIMIT %s",
                (str(conversation_uid), int(limit)),
            )
            rows = cur.fetchall() if cur.rowcount > 0 else []
        return [{'role': r[0], 'content': r[1]} for r in reversed(rows)]
    except Exception:       # noqa: BLE001
        return []


def _record_turn(conn, conversation_uid, role, content, **fields):
    """Append a message. Returns its message_uid, or None if it could not be
    stored (in which case the turn still proceeds)."""
    if not conversation_uid:
        return None
    message_uid = str(uuid.uuid4())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(turn_index), -1) + 1 "
                "FROM dll_waswa_messages WHERE conversation_uid = %s",
                (str(conversation_uid),),
            )
            turn_index = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO dll_waswa_messages "
                "(message_uid, conversation_uid, turn_index, role, content, "
                " intent, router_tier, model, prompt_version, blocked_reason, "
                " latency_ms) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (message_uid, str(conversation_uid), turn_index, role, content,
                 fields.get('intent'), fields.get('router_tier'),
                 fields.get('model'), fields.get('prompt_version'),
                 fields.get('blocked_reason'), fields.get('latency_ms')),
            )
            cur.execute(
                "UPDATE dll_waswa_conversations SET last_activity_at = NOW() "
                "WHERE conversation_uid = %s",
                (str(conversation_uid),),
            )
        return message_uid
    except Exception:       # noqa: BLE001
        return None


def _record_evidence(conn, message_uid, items):
    """items: list of (source_kind, source_ref, authority_level)."""
    if not message_uid or not items:
        return
    try:
        with conn.cursor() as cur:
            for source_kind, source_ref, authority_level in items:
                cur.execute(
                    "INSERT INTO dll_waswa_evidence "
                    "(message_uid, source_kind, source_ref, authority_level) "
                    "VALUES (%s, %s, %s, %s)",
                    (message_uid, source_kind, source_ref, authority_level),
                )
    except Exception:       # noqa: BLE001
        pass


def _log_transparency(conn, entry_type, scope, conversation_uid, message_uid,
                      action=None, rationale=None):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dll_waswa_transparency_log "
                "(entry_uid, account_uid, account_root, client_uid, "
                " conversation_uid, message_uid, entry_type, action, rationale) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (str(uuid.uuid4()), scope.get('account_uid'),
                 scope.get('account_root'), scope.get('client_uid'),
                 conversation_uid, message_uid, entry_type, action, rationale),
            )
    except Exception:       # noqa: BLE001
        pass


# ── Model call ──────────────────────────────────────────────────────────────

# User-facing text per OpenRouter failure. The detail (status, OpenRouter's own
# error message) goes to the server log instead: a customer should not be told
# the account is out of credits, but whoever reads the log must be.
_OPENROUTER_FAILURES = {
    400: (502, 'The assistant could not process that request.'),
    401: (503, 'The assistant is not configured correctly. Please try again later.'),
    402: (503, 'The assistant is temporarily unavailable. Please try again later.'),
    403: (503, 'The assistant is not configured correctly. Please try again later.'),
    408: (504, 'The assistant took too long to respond.'),
    429: (503, 'The assistant is busy right now. Please try again in a moment.'),
}


def _log(message, *args):
    """Waswa's OpenRouter diagnostics, at WARNING so they show in the Flask
    console without any logging configuration."""
    current_app.logger.warning('[waswa] ' + message, *args)


def _openrouter_error_detail(resp):
    """OpenRouter's own error text, for the log — never for the customer."""
    try:
        err = (resp.json() or {}).get('error') or {}
        detail = err.get('message') or str(err)
        meta = err.get('metadata')
        if meta:
            detail = f'{detail} | metadata={meta}'
    except ValueError:
        detail = resp.text
    return (detail or '').strip()[:500]


def _call_model(messages, allow_tools=True):
    """One round trip to OpenRouter.

    With allow_tools=False the tools stay declared (earlier turns in
    `messages` may reference them) but tool_choice='none' makes the model
    answer in text. Used when the tool-round budget runs out.

    Returns {'status': 'ok', 'message': ..., 'finish_reason': ...} or
    {'status': 'error', 'code': ..., 'message': <user-facing text>}.
    Every error is logged with its real cause.
    """
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "tools": _TOOL_SPECS,
        "max_tokens": 600,
        "temperature": 0.3,
    }
    if not allow_tools:
        payload["tool_choice"] = "none"

    # A dropped connection (RemoteDisconnected, SSL EOF, reset) is usually a
    # blip on the network between here and OpenRouter, so it is retried a
    # couple of times before the person sees an error. A timeout is not
    # retried: the model may still be working, and waiting 45s twice is worse
    # than saying so.
    resp = None
    for attempt in range(1 + _CONNECT_RETRIES):
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": OPENROUTER_SITE_URL,
                    "X-Title": OPENROUTER_SITE_NAME,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=45,
            )
            break
        except requests.Timeout:
            _log('OpenRouter timed out after 45s (model=%s)', OPENROUTER_MODEL)
            return {'status': 'error', 'code': 504,
                    'message': 'Waswa took too long to answer. Please try again.'}
        except requests.RequestException as error:
            if attempt < _CONNECT_RETRIES:
                _log('OpenRouter connection dropped (%s), retrying %s/%s',
                     error.__class__.__name__, attempt + 1, _CONNECT_RETRIES)
                time.sleep(_RETRY_BACKOFF[attempt])
                continue
            _log('OpenRouter unreachable after %s attempts: %s: %s',
                 attempt + 1, error.__class__.__name__, error)
            return {'status': 'error', 'code': 502,
                    'message': "Waswa couldn't reach its AI service just now "
                               "(a network drop). Please try again."}

    if resp.status_code != 200:
        _log('OpenRouter HTTP %s (model=%s): %s', resp.status_code,
             OPENROUTER_MODEL, _openrouter_error_detail(resp))
        code, message = _OPENROUTER_FAILURES.get(
            resp.status_code,
            (502, 'The assistant is unavailable right now.'))
        return {'status': 'error', 'code': code, 'message': message}

    try:
        body = resp.json()
    except ValueError:
        _log('OpenRouter returned non-JSON with HTTP 200: %s', resp.text[:300])
        return {'status': 'error', 'code': 502,
                'message': 'The assistant returned an unreadable response.'}

    # OpenRouter can answer 200 with an error object when the upstream
    # provider fails after the request was accepted.
    if body.get('error'):
        _log('OpenRouter error in a 200 body (model=%s): %s',
             OPENROUTER_MODEL, str(body['error'])[:500])
        return {'status': 'error', 'code': 502,
                'message': 'The assistant is unavailable right now.'}

    choices = body.get("choices") or []
    if not choices:
        _log('OpenRouter returned no choices: %s', str(body)[:300])
        return {'status': 'error', 'code': 502,
                'message': 'The assistant returned no response.'}

    return {'status': 'ok',
            'message': choices[0].get("message") or {},
            'finish_reason': choices[0].get("finish_reason")}


def _evidence_arg(arguments):
    """The argument worth recording beside a tool name in the evidence trail."""
    if not arguments:
        return ''
    for key in ('name', 'product_name', 'names', 'capability', 'text',
                'query', 'service_type', 'asset_type', 'document_type'):
        if key in arguments:
            value = arguments[key]
            if isinstance(value, (list, tuple)):
                return ', '.join(str(v) for v in value)[:80]
            return str(value)[:80]
    return ', '.join(f'{k}={v}' for k, v in list(arguments.items())[:2])[:80]


def _unknown_report(context):
    """context_unknown as [{slot, reason}] — the reason is what makes an empty
    slot diagnosable rather than merely absent.

    Nothing is filtered out. An earlier version hid keys beginning with an
    underscore, which is where the assembly error was being stored, so the one
    field that explained a failure was the one field never shown.
    """
    return [
        {'slot': slot, 'reason': reason}
        for slot, reason in sorted(context.get('unknown', {}).items())
    ]


# ── Endpoints ───────────────────────────────────────────────────────────────

@assistant_bp.route("/assistant/context", methods=["GET", "POST"])
def AssistantContext():
    """What Waswa knows about the caller, and what it does not, with reasons.

    Diagnostic: it returns only the caller's own context, resolved from their
    own token, so it exposes nothing they cannot already see. Use it to tell an
    empty account apart from a broken query.

    Read-only, and accepts POST as well as GET purely so that a REST client
    left on POST from /assistant/chat does not answer 405 instead of the
    diagnosis you came for.
    """
    account_uid = _extract_account_uid()
    if not account_uid:
        return reply("error", 401, "Authentication required.", "")

    conn = None
    try:
        conn = _open_connection()
        context = build_context(account_uid, surface='diagnostic', conn=conn)
        return reply("success", 200, "OK", {
            "scope": context['scope'],
            "known": context['known'],
            "unknown": _unknown_report(context),
        })
    except Exception as error:
        return reply("error", 500, str(error), "")
    finally:
        if conn:
            conn.close()


@assistant_bp.route("/assistant/knowledge", methods=["GET", "POST"])
def AssistantKnowledge():
    """Exactly what a knowledge_search tool call would hand the model.

    The counterpart to /assistant/context, and for the same reason: when an
    answer is wrong, this separates "retrieval returned the wrong paragraph"
    from "retrieval was right and the model misread it". Without it the two
    look identical from outside.

    With no q, it lists the documents Waswa can draw on.

        GET /assistant/knowledge
        GET /assistant/knowledge?q=what+is+in+the+add-on+apps+library
        GET /assistant/knowledge?q=fuel&include_unapproved=true

    include_unapproved is why this endpoint is worth having before anything is
    approved: it shows what retrieval WOULD find, so the corpus can be checked
    before it is switched on for customers. It is a diagnostic only — the chat
    path has no way to set it.
    """
    account_uid = _extract_account_uid()
    if not account_uid:
        return reply("error", 401, "Authentication required.", "")

    # Same audience the chat path would use for this person, so the
    # diagnostic shows what Waswa would really see. Looking at unapproved
    # documents is a reviewer's tool, not everyone's.
    who = waswa_answers.caller(account_uid)
    audience = waswa_answers.audience_for(who)

    payload = request.get_json(silent=True) or {}
    query = (request.args.get('q') or payload.get('query') or '').strip()
    if not query:
        return reply("success", 200, "OK",
                     waswa_knowledge.knowledge_sources(audience=audience))

    flag = str(request.args.get('include_unapproved')
               or payload.get('include_unapproved') or '').lower()
    include_unapproved = (flag in ('1', 'true', 'yes')
                          and waswa_answers.can(who, waswa_answers.PERM_REVIEW))
    result = waswa_knowledge.knowledge_search(
        query,
        product=request.args.get('product') or payload.get('product'),
        document_type=(request.args.get('document_type')
                       or payload.get('document_type')),
        limit=request.args.get('limit') or payload.get('limit'),
        include_unapproved=include_unapproved,
        audience=audience,
    )
    result['audience'] = audience
    return reply("success", 200, "OK", result)


@assistant_bp.route("/assistant/chat", methods=["POST"])
def AssistantChat():
    conn = None
    try:
        account_uid = _extract_account_uid()
        if not account_uid:
            return reply("error", 401, "Authentication required.", "")

        payload = request.get_json(silent=True) or {}
        data = payload.get("data") or {}

        user_message = str(data.get("message", "")).strip()
        if not user_message:
            return reply("error", 400, "A message is required.", "")

        surface = str(data.get("surface") or "mobile").strip().lower()[:20]
        # The CMS screen a staff question came from ("Billing", "SIM Cards"),
        # so a short question is read in that context. Context only: it grants
        # nothing and is never trusted for access. Letters, digits, spaces and
        # a little punctuation, 60 characters at most.
        module = re.sub(r"[^A-Za-z0-9 &/+.\-]", "", str(data.get("module") or ""))[:60].strip()
        requested_conversation = data.get("conversation_uid")
        # data.get("context") and data.get("history") are accepted for
        # backward compatibility and deliberately ignored — see the module
        # docstring. Both are resolved server-side.

        conn = _open_connection()

        context = build_context(account_uid, surface=surface, conn=conn)
        scope = context['scope']

        conversation_uid = _resume_or_open_conversation(
            conn, account_uid, scope, surface, requested_conversation)

        # Read prior turns BEFORE recording this one, or the new message would
        # appear twice in what we send the model.
        history = _stored_history(conn, conversation_uid)

        _record_turn(conn, conversation_uid, 'user', user_message)

        # Pricing never reaches a model.
        if _is_pricing_enquiry(user_message):
            message_uid = _record_turn(
                conn, conversation_uid, 'assistant', _PRICING_ROUTED_REPLY,
                intent='pricing_enquiry', router_tier=1,
                blocked_reason='pricing_not_available')
            _log_transparency(
                conn, 'blocked_action', scope, conversation_uid, message_uid,
                action='state_price',
                rationale='No approved price book; Odoo pricing not wired. '
                          'Routed to sales per the master prompt (Appendix C).')
            return reply("success", 200, "OK", {
                "reply": _PRICING_ROUTED_REPLY,
                "model": None,
                "conversation_uid": conversation_uid,
                "message_uid": message_uid,
                "verified_answers": [],
                "intent": "pricing_enquiry",
                "router_tier": 1,
                "evidence": [],
                "context_unknown": _unknown_report(context),
            })

        if not OPENROUTER_API_KEY:
            return reply(
                "error", 503,
                "The assistant is not configured yet. Please try again later.",
                "",
            )

        prompt_body, prompt_version = _active_prompt(conn)

        # Who this is decides what Waswa may read to them: staff-only
        # documents and corrections reach staff, never a fleet customer.
        who = waswa_answers.caller(account_uid)
        audience = waswa_answers.audience_for(who)

        # Corrections first. Matched here, before the model, rather than
        # offered as a tool: a correction exists because the model got this
        # wrong once, so it is not left to the model to remember to look.
        verified = []
        try:
            with conn.cursor() as cur:
                verified = waswa_answers.match(cur, user_message, audience)
        except Exception:       # noqa: BLE001
            # A lookup failure costs the verified answer, never the reply.
            current_app.logger.exception(
                '[waswa] verified-answer lookup failed (conversation=%s)',
                conversation_uid)
            verified = []

        messages = [{"role": "system", "content": prompt_body}]
        messages.append({"role": "system", "content": render_for_prompt(context)})
        if verified:
            messages.append({"role": "system",
                             "content": waswa_answers.render_for_prompt(verified)})
        if module and surface == "cms":
            messages.append({"role": "system", "content": (
                f"The staff member is asking from the CMS \"{module}\" screen. "
                "Read short or ambiguous questions in that context. You do not "
                "see what is on their screen; if the question depends on live "
                "figures from it that you have not been given, say so.")})
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        evidence = [('account_context', 'waswa_context', 3)]
        for item in verified:
            evidence.append(('verified_answer',
                             f"answer:{item['answer_uid']} v{item['version']}", 1))

        started = time.time()
        text = None
        finish_reason = None
        answered = False
        for _ in range(_MAX_TOOL_ROUNDS):
            outcome = _call_model(messages)
            if outcome['status'] != 'ok':
                return reply("error", outcome['code'], outcome['message'], "")

            assistant_message = outcome['message']
            finish_reason = outcome.get('finish_reason')
            tool_calls = assistant_message.get('tool_calls') or []

            if not tool_calls:
                text = (assistant_message.get('content') or '').strip()
                answered = True
                break

            messages.append(assistant_message)
            for call in tool_calls:
                function = call.get('function') or {}
                tool_name = function.get('name', '')
                try:
                    arguments = json.loads(function.get('arguments') or '{}')
                except ValueError:
                    arguments = {}

                # Knowledge tools first: dispatch returns None for a name it
                # does not own, so an unknown tool still reaches the product
                # dispatcher and gets its readable "no such tool" answer rather
                # than being swallowed here.
                result = waswa_knowledge.dispatch(tool_name, arguments,
                                                  audience=audience)
                if result is None:
                    result = waswa_products.dispatch(tool_name, arguments)
                    authority = 1          # PPMM tables are level 1 by definition
                    kind = 'tool'
                else:
                    # A document answer is only as authoritative as the weakest
                    # chunk it was built from, and that varies per search.
                    authority = waswa_knowledge.authority_of(result)
                    kind = 'document'
                evidence.append((
                    kind, f'{tool_name}({_evidence_arg(arguments)})', authority))
                messages.append({
                    'role': 'tool',
                    'tool_call_id': call.get('id'),
                    'name': tool_name,
                    'content': json.dumps(result, default=str),
                })

        if not answered:
            # Every round asked for more tools. The data it fetched is already
            # in `messages`; make the model answer from it instead of failing.
            _log('tool budget (%s rounds) exhausted; forcing a final answer '
                 '(conversation=%s)', _MAX_TOOL_ROUNDS, conversation_uid)
            outcome = _call_model(messages, allow_tools=False)
            if outcome['status'] != 'ok':
                return reply("error", outcome['code'], outcome['message'], "")
            finish_reason = outcome.get('finish_reason')
            text = (outcome['message'].get('content') or '').strip()

        latency_ms = int((time.time() - started) * 1000)

        truncated = finish_reason == 'length'
        if truncated:
            _log('reply hit max_tokens and was cut off (conversation=%s)',
                 conversation_uid)

        if not text:
            _log('model returned empty content (finish_reason=%s, '
                 'conversation=%s)', finish_reason, conversation_uid)
            return reply("error", 502, "The assistant returned no response.", "")

        message_uid = _record_turn(
            conn, conversation_uid, 'assistant', text,
            router_tier=3, model=OPENROUTER_MODEL,
            prompt_version=prompt_version, latency_ms=latency_ms)

        _record_evidence(conn, message_uid, evidence)

        return reply("success", 200, "OK", {
            "reply": text,
            "model": OPENROUTER_MODEL,
            "conversation_uid": conversation_uid,
            # The id the app sends back to POST /assistant/feedback.
            "message_uid": message_uid,
            # Corrections put in front of the model this turn. Whether it
            # used them is in the reply; that they were offered is here.
            "verified_answers": [
                {"answer_uid": v['answer_uid'], "question": v['question'],
                 "approved_at": v['approved_at'], "matched_on": v['matched_on']}
                for v in verified
            ],
            "audience": audience,
            "prompt_version": prompt_version,
            "router_tier": 3,
            "latency_ms": latency_ms,
            "truncated": truncated,
            "evidence": [
                {"source_kind": e[0], "source_ref": e[1], "authority_level": e[2]}
                for e in evidence
            ],
            "context_unknown": _unknown_report(context),
        })

    except Exception as error:
        current_app.logger.exception('[waswa] /assistant/chat failed')
        return reply("error", 500, str(error), "")
    finally:
        if conn:
            conn.close()
