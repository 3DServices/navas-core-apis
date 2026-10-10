"""
waswa_v2.py -- the v2 agent: plan, retrieve, verify, answer.

WHY A SECOND AGENT RATHER THAN A PATCH

v1 works. Its context assembly and its evidence trail are the best parts of
the system and v2 reuses both unchanged. What v1 cannot do is recover or
check itself:

  1. WRONG CORPUS. The 54 geofence chunks in the corpus describe the NAVAS
     CMS, not the OLIWA mobile app. Asked "how do I create a geofence?" from
     a phone, v1 can retrieve a CMS procedure and present it as the answer.
     Confidently wrong is worse than the refusal it gives today.
  2. NO RECOVERY. When knowledge_search returns nothing, v1 refuses. It never
     tries different words. Eval row fb-003 reads as a corpus gap; part of it
     may be a query-formulation gap, and nothing in v1 can tell the two apart.
  3. NO SELF-CHECK. Nothing inspects the drafted answer against the evidence
     before it is sent. Every guarantee rests on the model having behaved.

v2 adds a plan step, a retrieval ladder with retries, and a verification gate
that can send one repair round back to the model. It keeps v1's response
contract byte for byte, so the existing eval harness scores it with no
changes -- which is the point: the two can be compared on the same questions.

RUNS BESIDE v1, NEVER INSTEAD OF IT
Selected per request via data.agent_version, falling back to the
WASWA_AGENT_VERSION environment variable, default 'v1'. With no flag, this
module is not imported into the request path at all.

TESTABLE WITHOUT A DATABASE
run_turn() takes `search` and `call_model` as arguments. Every decision below
is a pure function of its inputs. tests/test_waswa_v2.py drives the whole
agent with fakes -- no database, no network, no model.
"""

import re

# ── Which application a question and a document belong to ───────────────────
# The wrong-corpus defect is a scope mismatch, so scope has to be a value the
# code can compare, on both sides.

_MOBILE_SURFACES = frozenset({'mobile', 'app', 'android', 'ios'})
_CONSOLE_SURFACES = frozenset({'console', 'web', 'cms', 'desktop'})


def surface_family(surface):
    """'mobile', 'console', or None when the surface name says neither.

    The eval harness prefixes its surfaces with 'eval-' so its rows can be
    found later, so that prefix is stripped before matching rather than
    enumerated.
    """
    name = str(surface or '').strip().lower()
    if name.startswith('eval-'):
        name = name[5:]
    if name in _MOBILE_SURFACES:
        return 'mobile'
    if name in _CONSOLE_SURFACES:
        return 'console'
    return None


# A chunk carries no scope column -- there is none in dll_waswa_chunks. It is
# inferred from the title, type and category, and left None when none of them
# says. None means UNKNOWN, and unknown is never treated as a match: a
# document that does not say which app it describes cannot be offered as
# instructions for one.
_SCOPE_MARKERS = (
    ('console', re.compile(
        r'\b(cms|console|web\s*app|web\s*portal|admin\s*portal|back\s*office)\b',
        re.I)),
    ('mobile', re.compile(
        r'\b(oliwa\s+mobile|mobile\s+app|mobile\s+application|handset|'
        r'android|ios)\b', re.I)),
)


def document_scope(chunk):
    """'mobile', 'console', or None when the document does not say."""
    if not isinstance(chunk, dict):
        return None
    text = ' '.join(str(chunk.get(key) or '') for key in
                    ('source', 'source_ref', 'document_type', 'category',
                     'heading'))
    for scope, pattern in _SCOPE_MARKERS:
        if pattern.search(text):
            return scope
    return None


# ── Step 1: plan ────────────────────────────────────────────────────────────

_HOW_TO = re.compile(
    r"\b(how\s+(do|can|should|would)\s+(i|we|you)|how\s+to\b|"
    r"where\s+(do|can)\s+i|steps?\s+to\b|walk\s+me\s+through|"
    r"guide\s+me|show\s+me\s+how)", re.I)

# "created" for "how do I created a new geofence" -- eval row fb-010 is
# ungrammatical, and real questions are worse. The pattern above already
# catches it; this note exists so nobody tightens it into correctness.

# Written to match in EITHER order. The first version required the pronoun
# before the noun and so missed "How many tokens do I have?" -- which is eval
# row fb-008, the commonest question there is.
_OWNERSHIP = r"(my|our|\bi\s+have\b|do\s+i\s+have|\bwe\s+have\b|\bi\s+own\b)"
_OWNED = (r"(token|balance|charge|bill|payment|invoice|account|subscription|"
          r"unit|vehicle|device|pack)")
_ACCOUNT = re.compile(
    r"%s.{0,40}%s|%s.{0,40}%s" % (_OWNERSHIP, _OWNED, _OWNED, _OWNERSHIP),
    re.I)

_FLEET = re.compile(
    r"\b(where\s+is|last\s+seen|online|offline|reporting|trip|route|"
    r"location|moving|parked|idling|speed)\b", re.I)


def plan_turn(question, surface=None, module=None):
    """What kind of question this is, and how to go after it.

    Deterministic on purpose. A planning step that calls the model costs a
    round trip and introduces a second thing that can be wrong; everything
    here is decidable from the words and the surface.
    """
    text = str(question or '')
    kind = 'general'
    if _HOW_TO.search(text):
        kind = 'how_to'
    elif _ACCOUNT.search(text):
        kind = 'account'
    elif _FLEET.search(text):
        kind = 'fleet'

    scope = surface_family(surface)
    return {
        'kind': kind,
        'surface_scope': scope,
        # A how-to answer must come from a document about the app the user is
        # holding. Everything else may draw on any approved document: a
        # policy or a specification is not app-specific.
        'require_scope': scope if kind == 'how_to' else None,
        'needs_documents': kind in ('how_to', 'general'),
        'queries': reformulate(text, module=module),
    }


# ── The retrieval ladder ────────────────────────────────────────────────────
# Deterministic reformulation. No model call, so a retry is free: the only
# cost of trying again is one more database query.

_STOPWORDS = frozenset("""
a an and are as at be been but by can could do does did for from had has have
how i if in into is it its me my of on or our should so some that the their
them then there these they this to us was we were what when where which who
why will with would you your
""".split())

_NOISE = re.compile(r"[^A-Za-z0-9\s/&-]")


def content_words(text):
    """The words that carry the question, in order, duplicates removed."""
    cleaned = _NOISE.sub(' ', str(text or '')).lower()
    seen, out = set(), []
    for word in cleaned.split():
        if word in _STOPWORDS or len(word) < 3 or word in seen:
            continue
        seen.add(word)
        out.append(word)
    return out


def reformulate(question, module=None):
    """Queries to try, in order, best guess first.

    Why this order: the question as asked is the only one that can match a
    phrase, so it goes first. Stripping the question words is what rescues
    "how do I created a new geofence", where the verb tense and the pronouns
    are noise that websearch_to_tsquery weighs equally with "geofence".
    """
    text = str(question or '').strip()
    words = content_words(text)
    candidates = [text]
    if words:
        candidates.append(' '.join(words))
    if module and words:
        candidates.append(' '.join([str(module).strip()] + words[:4]))
    if len(words) > 2:
        # The densest few words. A long question that found nothing often has
        # one specific noun in it doing all the work.
        candidates.append(' '.join(words[:2]))
    out, seen = [], set()
    for candidate in candidates:
        key = candidate.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(candidate.strip())
    return out


def retrieve(plan, search, max_attempts=3):
    """Search, reformulating until something graded comes back.

    Returns {'chunks', 'attempts', 'rejected_for_scope', 'exhausted'}.

    A chunk with authority_level None is not a result -- it is the row the
    dispatcher writes when a search found nothing. v1's eval learned this the
    hard way; here it decides whether to try again.
    """
    attempts, rejected, seen_rejects = [], [], set()
    for query in (plan.get('queries') or [])[:max_attempts]:
        result = search(query) or {}
        chunks = [c for c in (result.get('results') or [])
                  if isinstance(c, dict) and c.get('authority_level') is not None]

        kept = chunks
        require = plan.get('require_scope')
        if require and chunks:
            # THE WRONG-CORPUS GUARD. A document that does not state its scope
            # is dropped too: unknown is not a match. Being unable to answer
            # is a worse outcome than a wrong answer only if you have never
            # handed a phone user a CMS procedure.
            kept = [c for c in chunks if document_scope(c) == require]
            # Count each document once however many attempts surface it. The
            # ladder re-queries, so the same wrong-app manual comes back every
            # time, and a count that grew with the retries would describe the
            # retrying rather than the corpus.
            for chunk in chunks:
                if chunk in kept:
                    continue
                key = chunk.get('chunk_uid') or (
                    chunk.get('source'), chunk.get('heading'))
                if key not in seen_rejects:
                    seen_rejects.add(key)
                    rejected.append(chunk)

        attempts.append({'query': query, 'returned': len(chunks),
                         'kept': len(kept)})
        if kept:
            return {'chunks': kept, 'attempts': attempts,
                    'rejected_for_scope': rejected, 'exhausted': False}

    return {'chunks': [], 'attempts': attempts,
            'rejected_for_scope': rejected, 'exhausted': True}


def filter_for_scope(result, require):
    """Drop chunks from a knowledge_search result that are about another app.

    Returns (result, dropped). Used in the live tool loop, where retrieval
    comes back through the dispatcher rather than through retrieve() above.

    Filtering the tool RESULT, rather than instructing the model to disregard
    what it was given, is the whole point: a chunk the model never sees cannot
    be paraphrased into an answer. `found` is corrected too, so the rest of
    the turn -- the source line, the evidence authority -- sees the truth
    about what survived.
    """
    if not require or not isinstance(result, dict):
        return result, 0
    chunks = result.get('results')
    if not isinstance(chunks, list) or not chunks:
        return result, 0

    kept = [c for c in chunks if document_scope(c) == require]
    dropped = len(chunks) - len(kept)
    if not dropped:
        return result, 0

    trimmed = dict(result)
    trimmed['results'] = kept
    trimmed['count'] = len(kept)
    trimmed['found'] = bool(kept)
    notes = list(trimmed.get('notes') or [])
    notes.append(
        '%d document(s) were found but describe a different application and '
        'were withheld. Do not describe steps for this one from memory.'
        % dropped)
    trimmed['notes'] = notes
    if not kept:
        trimmed['reason'] = ('no approved document for this application '
                             'covers that')
    return trimmed, dropped


# ── Step 3: verify ──────────────────────────────────────────────────────────
# Checks the DRAFT against what was actually retrieved, before the user sees
# it. Each one states a violation in words the model can act on, because the
# repair round feeds them straight back.

# Is the draft telling the user to DO something, step by step? An answer that
# declines, or that explains a concept, carries none of these. Deliberately
# about instruction verbs rather than about refusal wording: refusals can be
# phrased a thousand ways, while a procedure almost always says tap, click,
# open or go to.
_GIVES_STEPS = re.compile(
    r"\b(tap|click|press|open|select|choose|navigate|go\s+to|head\s+to|"
    r"enter|fill\s+in|toggle|swipe|scroll\s+to)\b|"
    # ^ is multiline for the numbered-step alternative. The flag belongs in
    # the compile call: an inline (?m) mid-pattern is a hard error on Python
    # 3.11 and later ("global flags not at the start of the expression"),
    # while 3.10 accepted it -- so this compiled in the agent sandbox and
    # crashed on import for the person running 3.11.
    r"^\s*\d+[.)]\s+\S", re.I | re.M)

_LIVE_CLAIM = re.compile(
    r"\b(is|are|currently)\s+(online|reporting|live)\b|"
    r"\bactively\s+reporting\b|\blive\s+now\b", re.I)

_NUMBER = re.compile(r'\d[\d,]*(?:\.\d+)?')
_DATE_SHAPED = re.compile(
    r'\b(?:\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4}|\d{2}/\d{2}/\d{4})\b')

# Above this many digits a figure is an identifier -- an IMEI, a uid -- not a
# quantity the answer is claiming.
_IDENTIFIER_DIGITS = 8


def claimed_numbers(text):
    """Figures the answer is asserting, as floats. Dates and ids excluded."""
    body = _DATE_SHAPED.sub(' ', str(text or ''))
    out = []
    for match in _NUMBER.finditer(body):
        raw = match.group(0).rstrip(',')
        if sum(character.isdigit() for character in raw) >= _IDENTIFIER_DIGITS:
            continue
        before = body[match.start() - 1] if match.start() else ' '
        after = body[match.end()] if match.end() < len(body) else ' '
        if before.isalpha() or after.isalpha():
            continue            # "v2", "Q3", part of a name
        try:
            out.append(round(float(raw.replace(',', '')), 4))
        except ValueError:
            continue
    return out


def verify(draft, plan, retrieval, context_numbers=None, tool_refs=()):
    """Violations found in the draft. Empty list means it may be sent.

    Deliberately conservative: every check here is deterministic and names
    something a record can settle. Nothing in this function asks a model
    whether an answer is good.
    """
    text = str(draft or '')
    violations = []

    # 1 -- a how-to answered without a document about the right app.
    #
    # The first version of this check fired whenever a how-to had no scoped
    # document, whatever the answer said -- so it rejected the very refusal it
    # had just asked the model for, and the repair round could never succeed.
    # The violation is giving STEPS without a document, not failing to give
    # them. Declining is the correct answer here and must pass.
    if (plan.get('kind') == 'how_to' and not retrieval.get('chunks')
            and _GIVES_STEPS.search(text)):
        if retrieval.get('rejected_for_scope'):
            violations.append(
                'This is a how-to question from the %s app, and the only '
                'documents found describe a different application. Say that '
                'the steps for this app are not documented yet and offer to '
                'connect the user with someone, rather than giving the other '
                "application's steps."
                % (plan.get('require_scope') or 'current'))
        else:
            violations.append(
                'No approved document was found for this how-to question. '
                'Say so plainly rather than describing steps from memory.')

    # 2 -- a liveness claim with no heartbeat read behind it. A subscription
    # status is not liveness, which is the defect fb-009 was written for.
    if _LIVE_CLAIM.search(text):
        if not any(str(ref).startswith('fleet_liveness') for ref in tool_refs):
            violations.append(
                'The answer calls a unit live or reporting, but the heartbeat '
                'registry was not read. Either call fleet_liveness or drop '
                'the claim.')

    # 3 -- figures that trace to nothing. Only checked when the context
    # figures were captured AND no live tool ran: a figure from a live fleet
    # read has nowhere to be traced to, and failing it would be a wrong
    # expectation failing a right answer.
    live_tools = [ref for ref in tool_refs
                  if not str(ref).startswith(('waswa_context',
                                              'knowledge_search'))]
    if context_numbers is not None and not live_tools:
        unsourced = [value for value in claimed_numbers(text)
                     if value not in context_numbers]
        if unsourced:
            violations.append(
                'These figures are in the answer but in neither the account '
                'context nor any tool result: %s. Remove them or say where '
                'they come from.'
                % ', '.join('%g' % value for value in unsourced))

    return violations


# ── The turn ────────────────────────────────────────────────────────────────

MAX_REPAIR_ROUNDS = 1


def run_turn(question, *, surface=None, module=None, search=None,
             call_model=None, context_numbers=None, tool_refs=(),
             max_attempts=3):
    """Plan, retrieve, draft, verify, repair once, answer.

    `search(query)` and `call_model(messages)` are injected so this runs
    under test with no database and no network. call_model returns the draft
    text; everything else here is pure.

    Returns a dict carrying the reply and the diagnostics v1 never recorded:
    retrieval attempts, scope rejections, verification result and the repair
    count. Those are the step-efficiency and argument-correctness signals the
    evaluation plan found missing.
    """
    plan = plan_turn(question, surface=surface, module=module)

    retrieval = {'chunks': [], 'attempts': [], 'rejected_for_scope': [],
                 'exhausted': False}
    if plan['needs_documents'] and search is not None:
        retrieval = retrieve(plan, search, max_attempts=max_attempts)

    messages = [{'role': 'user', 'content': str(question or '')}]
    if retrieval['chunks']:
        messages.append({
            'role': 'system',
            'content': 'Approved documents for this question:\n' + '\n'.join(
                '- %s: %s' % (chunk.get('source') or 'untitled',
                              (chunk.get('text') or '')[:600])
                for chunk in retrieval['chunks'])})
    elif plan['kind'] == 'how_to':
        messages.append({
            'role': 'system',
            'content': 'No approved document covers this procedure for this '
                       'application. Do not describe steps from memory.'})

    draft = str(call_model(messages) or '').strip()
    violations = verify(draft, plan, retrieval,
                        context_numbers=context_numbers, tool_refs=tool_refs)

    repairs = 0
    while violations and repairs < MAX_REPAIR_ROUNDS:
        repairs += 1
        messages.append({'role': 'assistant', 'content': draft})
        messages.append({
            'role': 'system',
            'content': 'This draft was rejected before it reached the user. '
                       'Fix every point and answer again:\n' + '\n'.join(
                           '- ' + violation for violation in violations)})
        draft = str(call_model(messages) or '').strip()
        violations = verify(draft, plan, retrieval,
                            context_numbers=context_numbers,
                            tool_refs=tool_refs)

    return {
        'reply': draft,
        'plan': plan,
        'retrieval_attempts': retrieval['attempts'],
        'chunks_used': retrieval['chunks'],
        'rejected_for_scope': len(retrieval['rejected_for_scope']),
        'repairs': repairs,
        # Non-empty means the answer went out with a known problem. It is
        # recorded rather than hidden: a repair round that did not fix the
        # fault is the single most useful thing to see in a bad turn.
        'unresolved': violations,
        'agent_version': 'v2',
    }
