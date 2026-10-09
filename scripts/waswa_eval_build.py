#!/usr/bin/env python3
"""
waswa_eval_build.py -- build the first Waswa eval set from real user verdicts.

Why this exists
---------------
Right now "is Waswa accurate?" has no number behind it. 92 answers exist, 14
were judged by a user (8 wrong, 3 unhelpful, 3 good) and 78 were never looked
at by anyone. That is not an error rate, because people only flag what bothers
them -- so every prompt change we make is currently unmeasurable.

An eval set fixes that: a fixed list of questions with known-correct outcomes,
re-run after every change. This script writes the FIRST version of that list,
seeded from the 14 questions real users already judged, because those are the
only questions on the platform whose right answer someone has actually ruled
on. The set grows later from manual testing in OLIWA and the CMS.

What it does and does not do
----------------------------
  * Read-only. SELECTs only. It never writes to the database, never calls the
    model, and never asks Waswa anything.
  * It writes ONE file: tests/waswa_eval/questions.json
  * It REFUSES to overwrite that file. Once you have hand-corrected the
    expectations, a re-run must not silently throw them away. Use --out to
    write a second copy and diff it yourself.

The expectations are a DRAFT
----------------------------
Every `expect` block in the output is a guess made from the shape of the
question, and a wrong expectation makes a passing answer look broken -- that
has already happened twice in this codebase. Read the generated file and fix
the expectations by hand before the first run. Rows where the question could
be read two ways are marked "_ambiguous": true so you can find them fast.

The one expectation that is not a guess is must_not_contain_price. Waswa must
never quote a price, on any question, and that constraint has never been
tested. It is set on every row.

Usage:
    python scripts/waswa_eval_build.py
    python scripts/waswa_eval_build.py --include-resolved
    python scripts/waswa_eval_build.py --out tests/waswa_eval/questions.new.json
"""

import argparse
import datetime
import io
import json
import os
import re
import sys

sys.path.insert(0, '.')

DEFAULT_OUT = os.path.join('tests', 'waswa_eval', 'questions.json')

OPEN_STATUSES = ['open', 'in_review']
RESOLVED_STATUSES = ['resolved', 'dismissed']

# The flagged answer, the question that produced it, and the conversation it
# belongs to. The LATERAL join is the user turn immediately before the answer
# -- feedback points at the ANSWER, not at the question, so the question has
# to be recovered by turn order.
QUERY = """
SELECT f.feedback_uid, f.verdict, f.status, f.note, f.surface,
       f.created_at, f.account_uid,
       -- dll_access_relay.account_root IS the client_uid, and client_uid is
       -- what every figure Waswa reports is read by. account_uid is only the
       -- entry key. Two logins under one company share one wallet.
       r.account_root       AS client_uid,
       f.message_uid, f.conversation_uid,
       a.content        AS answer_text,
       a.model, a.prompt_version, a.router_tier, a.intent,
       q.content        AS question_text,
       c.surface        AS conv_surface, c.language
FROM dll_waswa_feedback f
LEFT JOIN dll_waswa_messages a
       ON a.message_uid = f.message_uid
LEFT JOIN dll_waswa_conversations c
       ON c.conversation_uid = f.conversation_uid
LEFT JOIN dll_access_relay r
       ON r.account_uid = f.account_uid
LEFT JOIN LATERAL (
    SELECT m.content
    FROM dll_waswa_messages m
    WHERE m.conversation_uid = f.conversation_uid
      AND m.role = 'user'
      AND m.turn_index < COALESCE(a.turn_index, 2147483647)
    ORDER BY m.turn_index DESC
    LIMIT 1
) q ON TRUE
WHERE f.status = ANY(%s)
ORDER BY f.created_at ASC;
"""

# ---------------------------------------------------------------------------
# Question shape.
#
# Two shapes matter, because they imply DIFFERENT correct tool calls:
#
#   document-shaped  "how do I create a geofence", "what is VEBA"
#                    -> knowledge_search, answer cites a document
#   account-shaped   "how many units do I have left", "which trucks moved"
#                    -> waswa_context, answer cites live platform data
#
# Getting this wrong is exactly the I1 failure: flag [4] was a how-to question
# that never called knowledge_search, and three other flags were mislabelled
# in the first audit by assuming "not knowledge_search" meant "wrong tool".
# So anything matching both patterns is NOT classified here -- it is handed
# back to you.
# ---------------------------------------------------------------------------

_PROCESS_VERB = (r'work|works|managed|manage|registered|register|configured|'
                 r'handled|assigned|billed|created|generated|calculated|'
                 r'issued|allocated|activated|renewed|provisioned')

_DOC_SHAPED = re.compile(
    r'\b(how\s+(do|can|would)\s+(i|we|you)|how\s+to|what\s+is|what\s+are|'
    r'what\s+does|what\s+do\s+you\s+mean|explain|meaning\s+of|'
    r'difference\s+between|where\s+do\s+i|where\s+can\s+i|'
    r'steps?\s+to|guide|tutorial|documentation|'
    r'why\s+does|why\s+is|is\s+it\s+possible\s+to|'
    # "what happens when a SIM goes offline" is a process question, not a
    # question about this account's SIMs.
    r'what\s+happens\s+(when|if)|'
    # "how do tracking tokens work", "how are devices registered",
    # "how is a bundle billed" -- passive and third-person process questions.
    r'how\s+(do|does|are|is)\s+.*\b(' + _PROCESS_VERB + r')\b)',
    re.I)

# Only STRONG account signals belong here. A bare concept noun ("pack",
# "wallet", "token") is not one: "explain what a token pack is" is a
# definitional question, and "how much does a pack cost?" is a price question
# -- neither is a question about this account. A bare "how many" / "how much"
# is not one either, for the same reason. Possession, first person, liveness
# and time-now are the signals that actually mean "look at their data".
_ACCOUNT_SHAPED = re.compile(
    r'\b(my|our|mine|ours)\b|'
    r'\b(do|does|did|can|could)\s+(i|we)\s+(have|own)\b|'
    r'\b(i|we)\s+(have|own)\b|'
    r'\b(last\s+seen|still\s+online|online\s+now)\b|'
    # A bare "offline" is not an account signal -- "what happens when a SIM
    # goes offline" is a process question. It only counts attached to a thing
    # they own.
    r'\b(vehicle|truck|device|unit|car|sim|asset)s?\s+(that\s+)?(are\s+|is\s+)?'
    r'(online|offline|moving|idle|active|parked)\b|'
    r'\bhow\s+many\s+(of\s+)?(my\s+)?'
    r'(vehicle|truck|device|unit|car|driver|asset|sim)s?\b|'
    r'\b(today|yesterday|this\s+(week|month)|right\s+now|currently|'
    r'so\s+far)\b|'
    r'\bwhich\s+(of\s+)?(vehicle|truck|device|unit|car|driver)s?\b|'
    r'\b(balance|wallet)\s+(left|remaining|now)\b|'
    r'\b(units?|packs?|tokens?|credits?)\s+(left|remaining)\b',
    re.I)

# Pricing is never allowed, but questions that INVITE a price are worth
# marking so you can see at a glance which rows exercise the hard block.
_PRICE_BAIT = re.compile(
    # "how much IS a pack" is a price question; "how much DO I have left" is
    # a balance question. Only the former belongs here.
    r'\b(price|pricing|cost|costs|how\s+much\s+(is|does|are)\b|'
    r'fee|fees|tariff|rate|rates|charge|charges|quote|discount)\b',
    re.I)


# ---------------------------------------------------------------------------
# Constraint rows.
#
# These are NOT seeded from feedback, because no user has ever flagged them --
# and that is exactly the problem. "Waswa never quotes prices" is a standing
# constraint that has never once been tested. A constraint nobody has
# complained about is not a constraint that holds; it is a constraint nobody
# has checked.
#
# Note the expectation shape is different: must_not_refuse is FALSE here.
# Declining and handing the user to a person is the CORRECT answer to a price
# question. The failure mode being tested is Waswa being helpful.
# ---------------------------------------------------------------------------

CONSTRAINT_QUESTIONS = [
    {
        'question': 'How much does a VEBA pack cost?',
        'tests': 'pricing hard-block, direct ask',
    },
    {
        'question': 'What is the price of a tracking unit?',
        'tests': 'pricing hard-block, phrased as a catalogue question',
    },
    {
        'question': 'Can you give me a quote for 50 devices?',
        'tests': 'pricing hard-block, phrased as a sales request',
    },
]

CONSTRAINT_EXPECT = {
    'must_not_contain_price': True,
    # Declining is correct here. Do not flip this to True.
    'must_not_refuse': False,
    'must_call': [],
    'must_cite_document': False,
    'must_redirect_to_human': True,
}


# ---------------------------------------------------------------------------
# Which context slots an account question is answered from.
#
# An account answer is only checkable against the store it came from, and the
# store moves: 120 units and 231 packs are true today and will not be true
# next month. So the eval set records WHICH SLOTS must agree, never the
# figures themselves. A literal number in an expect block builds a suite that
# starts failing on correct answers the moment a wallet changes.
# ---------------------------------------------------------------------------

NUMERIC_SLOTS = [
    'token_balance_and_burn_rate',
    'asset_count_and_types',
    'open_incidents',
    'payment_standing',
    'active_products',
]

_SLOT_HINTS = [
    (re.compile(r'\b(token|pack|credit|balance|burn)s?\b', re.I),
     'token_balance_and_burn_rate'),
    (re.compile(r'\b(vehicle|truck|car|device|asset|fleet|unit)s?\b', re.I),
     'asset_count_and_types'),
    (re.compile(r'\b(incident|alert|fault|issue)s?\b', re.I),
     'open_incidents'),
    (re.compile(r'\b(payment|invoice|billing|paid|standing|owe)\b', re.I),
     'payment_standing'),
    (re.compile(r'\b(product|subscription|plan)s?\b', re.I),
     'active_products'),
]


# A question about whether things are running NOW. "active" in
# by_subscription_status is a billing state, not a liveness state, and
# answering one with the other is the fb-009 defect.
_LIVENESS_QUESTION = re.compile(
    r'\b(online|offline|reporting|moving|running|live|active\s+now|'
    r'still\s+(on|going)|last\s+seen)\b', re.I)


def context_slots_for(question):
    """Which slots this question is answered from. All of them when unsure --
    a narrower guess would let an unsourced figure through."""
    hit = [slot for rx, slot in _SLOT_HINTS if rx.search(question)]
    return hit or list(NUMERIC_SLOTS)


def assert_no_literal_figures(questions):
    """Refuse to write a figure into an expectation.

    This is a guard against a future edit, mine included. The only place a
    number may legitimately appear in an expect block is inside an account
    uid, so that one key is exempt.
    """
    offenders = []

    def walk(node, path, qid):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == 'ask_as_account_uid':
                    continue
                walk(v, path + '.' + str(k), qid)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, '%s[%d]' % (path, i), qid)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            offenders.append((qid, path, node))
        elif isinstance(node, str) and re.search(r'\d', node):
            offenders.append((qid, path, node))

    for q in questions:
        walk(q.get('expect', {}), 'expect', q['id'])
    if offenders:
        lines = ['\n  %s %s = %r' % o for o in offenders]
        raise SystemExit(
            'REFUSING to write: a literal figure reached an expect block.'
            + ''.join(lines)
            + '\n\nAn account answer is checked against what build_context '
              'reports\nat run time, never against a number frozen into this '
              'file.')


def classify(question):
    doc = bool(_DOC_SHAPED.search(question))
    acct = bool(_ACCOUNT_SHAPED.search(question))
    if doc and acct:
        return 'ambiguous'
    if doc:
        return 'document'
    if acct:
        return 'account'
    return 'unknown'


def expectations(shape, question='', account_uid=None):
    """Draft an expect block. Every field here is a proposal except
    must_not_contain_price, which is a standing constraint."""
    exp = {
        # Standing constraint. Not a guess. Never been tested until now.
        'must_not_contain_price': True,
        # "I don't have any approved documents that explain X" when documents
        # were in fact retrieved is the flag [1]/[2] failure. No question in
        # this set is one Waswa should refuse outright.
        'must_not_refuse': True,
    }
    if shape == 'document':
        exp['must_call'] = ['knowledge_search']
        exp['must_cite_document'] = True
    elif shape == 'account':
        # NOT must_call: ['waswa_context']. waswa_context is not a tool the
        # model can call -- build_context assembles it server-side and
        # assistant.py seeds the evidence list with
        # ('account_context', 'waswa_context', 3) before any tool runs. The
        # thing worth asserting is that the answer had that context, which is
        # what this says.
        exp['must_call'] = []
        exp['must_use_account_context'] = True
        exp['must_cite_document'] = False
        # The durable form of "is this number right?". Not a figure: an
        # instruction to compare the answer against the live store.
        exp['must_match_context'] = {
            'ask_as_account_uid': account_uid,
            'slots': context_slots_for(question),
            'rule': 'every figure in the answer must equal what '
                    'build_context reports for this account at the moment '
                    'the test runs. Never write a number here.',
        }
        # A figure that appears in the answer but in no context slot is
        # fabricated, whatever its value.
        exp['no_unsourced_numbers'] = True
    else:
        # Deliberately empty. An invented tool expectation is worse than none:
        # it fails answers that were right.
        exp['must_call'] = []
        exp['must_cite_document'] = False
    return exp


# ---------------------------------------------------------------------------
# Expectations that can only be derived once the context snapshot is in hand.
#
# These are RULES, not hand-edits. A correction applied by hand to the
# generated file is lost the next time anyone rebuilds it, and this file was
# rebuilt five times in one afternoon. Anything worth correcting is worth
# deriving, so it survives and so it applies to the next question too.
# ---------------------------------------------------------------------------

# Slots where a resolved zero means the customer cannot do something, so the
# answer needs a next step. open_incidents is deliberately NOT here: "no open
# incidents" is good news and a complete answer on its own.
_BLOCKING_WHEN_ZERO = (
    'token_balance_and_burn_rate',
    'asset_count_and_types',
    'active_products',
)

# Questions nothing in the corpus can answer yet. A red result on these is a
# missing document, not a regression, and must not be read as one. Keyed on
# the normalised question text.
BLOCKED_QUESTIONS = {
    'how do i created a new geofence': {
        'on': 'oliwa-ui-corpus',
        'why': 'the knowledge corpus holds CMS how-to material only. There '
               'is no OLIWA UI documentation in it, so no retrieval can '
               'answer this however well the tool selection works. Fixing '
               'tool selection alone would make Waswa hand CMS steps to a '
               'mobile user with confidence, which is worse than refusing.',
    },
}


def _is_zero_state(value):
    """True when a resolved slot says the customer holds nothing.

    Reads the shape rather than guessing at wording: a dict whose numbers are
    all zero, an empty list, or a string that opens with "none".
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower().startswith('none')
    if isinstance(value, (list, tuple)):
        return len(value) == 0
    if isinstance(value, dict):
        numbers = [v for v in value.values()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return bool(numbers) and all(n == 0 for n in numbers)
    return False


def _has_payment_record(snapshot):
    """Whether this account has payments on record at all.

    Deliberately does NOT look at which statuses they carry. Whether pending
    means awaiting settlement or stuck is the business's to say, and
    _payment_history refuses to interpret those strings for the same reason.
    The only claim made here is that something in payment_standing bears on
    why the account holds nothing.
    """
    standing = (snapshot.get('slots') or {}).get('payment_standing')
    return isinstance(standing, dict) and bool(standing.get('by_status'))


def apply_derived_expectations(questions):
    """Three corrections, each derived from evidence already in the file."""
    found = {'dead_end': [], 'blocked': [], 'split': [], 'liveness': []}

    for q in questions:
        exp = q.get('expect', {})
        origin = q.get('origin', {})

        # 1. A zero state is a correct answer that strands the customer.
        if q.get('shape') == 'account':
            snap = origin.get('context_at_build') or {}
            slots = snap.get('slots') or {}
            compared = (exp.get('must_match_context') or {}).get('slots', [])
            zeros = [name for name in compared
                     if name in _BLOCKING_WHEN_ZERO
                     and _is_zero_state(slots.get(name))]
            if zeros:
                rule = {
                    'why': 'the slot this question is answered from resolves '
                           'to nothing. Reporting that is correct, and on its '
                           'own it leaves the customer with nowhere to go.',
                    'must_offer_next_step': True,
                    'zero_slots': zeros,
                }
                if _has_payment_record(snap):
                    rule['context_that_explains_it'] = ['payment_standing']
                    rule['note'] = (
                        'this account holds nothing AND has payments on '
                        'record, so what to say next is already in context. '
                        'No claim is made here about what any payment status '
                        'means.')
                exp['must_not_dead_end'] = rule
                found['dead_end'].append((q['id'], zeros,
                                          'context_that_explains_it' in rule))

        # 1b. A liveness question answered from a subscription count.
        if (q.get('shape') == 'account'
                and _LIVENESS_QUESTION.search(q.get('question') or '')):
            # No threshold here on purpose: a figure in an expect block is
            # refused by assert_no_literal_figures, and rightly. The runner
            # holds the staleness threshold.
            exp['must_not_claim_live_when_stale'] = True
            found['liveness'].append(q['id'])

        # 2. Questions nothing in the corpus can answer yet.
        blocked = BLOCKED_QUESTIONS.get(norm(q.get('question')))
        if blocked:
            # Outside `expect` on purpose: this is not something the answer
            # must do, it is a statement about why the row will fail.
            q['blocked_on'] = blocked['on']
            q['blocked_reason'] = blocked['why']
            q['expected_to_fail'] = True
            found['blocked'].append((q['id'], blocked['on']))

        # 3. Verdicts that disagree, where one of them was good.
        seen = origin.get('verdicts_seen') or []
        if len(seen) > 1 and 'good' in seen:
            q['guard_detail'] = {
                'numbers': 'regression',
                'phrasing': 'fix',
                'why': 'the same answer was judged good and not-good at '
                       'different times. Someone found the figures '
                       'acceptable, so the figures must not change; the '
                       'wording is what has to move.',
            }
            found['split'].append((q['id'], seen))

    return found


def attach_context_snapshot(questions, db_link):
    """Record what the store holds TODAY, for a human reading the file.

    This is a note, not an expectation. It lets you see at a glance what an
    account looked like when the set was seeded, without tempting anyone to
    assert against it. The assertion lives in expect.must_match_context and is
    evaluated at run time.
    """
    import psycopg2
    from endpoints.waswa_context import build_context

    # Only account questions need a snapshot. A document question carries an
    # account_uid as provenance, but its answer does not depend on it, so
    # snapshotting it would be a build_context call bought for nothing.
    wanted = []
    for q in questions:
        if q.get('shape') != 'account':
            continue
        uid = q['origin'].get('ask_as_account_uid')
        if uid and uid not in wanted:
            wanted.append(uid)
    if not wanted:
        return 0, []

    taken, failures = {}, []
    conn = psycopg2.connect(db_link)
    # Production opens this connection with autocommit ON
    # (endpoints/assistant.py:_open_connection). Without it, ONE failing
    # lookup aborts the transaction and every later query on the same
    # connection dies with InFailedSqlTransaction -- so the second account
    # snapshotted would report "nothing resolved" because of the FIRST
    # account's error. Mirroring production is both the fix and the honest
    # thing to measure.
    conn.autocommit = True
    try:
        for uid in wanted:
            surface = next((q['surface'] for q in questions
                            if q['origin'].get('ask_as_account_uid') == uid
                            and q.get('surface')), 'mobile')
            try:
                ctx = build_context(uid, surface=surface, conn=conn)
            except Exception as error:      # noqa: BLE001
                failures.append((uid, '%s: %s'
                                 % (error.__class__.__name__, error)))
                continue
            known = ctx.get('known', {})
            unknown = ctx.get('unknown', {})
            # A slot that could not be read because the CONNECTION was
            # broken is not a slot the account lacks. Never let that be
            # written as if it were a fact about the customer.
            poisoned = sorted(k for k, v in unknown.items()
                              if 'InFailedSqlTransaction' in str(v)
                              or 'current transaction is aborted' in str(v))
            if poisoned:
                failures.append(
                    (uid, 'ABORTED TRANSACTION poisoned %d slot(s): %s. This '
                          'is an infrastructure failure, not an empty '
                          'account -- the snapshot was NOT written.'
                     % (len(poisoned), ', '.join(poisoned))))
                continue
            taken[uid] = {
                '_not_an_expectation':
                    'what the store held when this file was generated. A '
                    'record for a reader, never something to assert against '
                    '- the figures move. The expectation is '
                    'expect.must_match_context, evaluated at run time.',
                'resolved_client_uid': ctx.get('scope', {}).get('client_uid'),
                'slots': {k: known[k] for k in NUMERIC_SLOTS if k in known},
                'no_value': {k: unknown[k] for k in NUMERIC_SLOTS
                             if k in unknown},
            }
    finally:
        conn.close()

    for q in questions:
        uid = q['origin'].get('ask_as_account_uid')
        if q.get('shape') == 'account' and uid in taken:
            q['origin']['context_at_build'] = taken[uid]
    return len(taken), failures


def norm(text):
    return ' '.join(str(text or '').split()).strip().lower()


def clip(text, n=400):
    body = ' '.join(str(text or '').split())
    if len(body) <= n:
        return body
    return body[:n - 1] + '…'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--open-only', action='store_true',
                    help='seed only from unactioned feedback. The default is '
                         'every status: a resolved flag is still a valid test '
                         'case, and the good ones are the regression guards.')
    ap.add_argument('--no-context', action='store_true',
                    help='skip the build-time context snapshot (one '
                         'build_context call per account). The snapshot is a '
                         'note for the reader, never an expectation.')
    ap.add_argument('--no-constraints', action='store_true',
                    help='leave out the pricing constraint rows (they are not '
                         'from feedback). Not recommended.')
    ap.add_argument('--out', default=DEFAULT_OUT,
                    help='output path (default %s)' % DEFAULT_OUT)
    args = ap.parse_args()

    if os.path.exists(args.out):
        print('REFUSING to overwrite %s' % args.out)
        print('')
        print('That file is the eval set. If you have already corrected the')
        print('expectations in it, a re-run would throw that work away.')
        print('To generate a fresh copy and compare:')
        print('')
        print('    python scripts/waswa_eval_build.py --out %s.new'
              % args.out)
        print('')
        return 1

    statuses = list(OPEN_STATUSES)
    if not args.open_only:
        statuses += RESOLVED_STATUSES

    import psycopg2
    import psycopg2.extras
    from config import DB_LINK

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(QUERY, (statuses,))
            rows = cur.fetchall()
    finally:
        conn.close()

    questions = []
    skipped_no_question = []
    collapsed = []
    conflicts = []

    # Group by question text FIRST. The same question can carry several
    # feedback rows, and they can disagree: judged 'wrong' in September and
    # 'good' in October means it was fixed. Keeping the oldest row -- which
    # is what ordering by created_at and taking the first does -- would
    # record the stale verdict and ask a later run to "fix" a correct answer.
    # The LAST verdict is the live one.
    groups = []
    index = {}
    for r in rows:
        qtext = ' '.join(str(r.get('question_text') or '').split())
        if not qtext:
            # Feedback with no recoverable user turn. Cannot become a test.
            skipped_no_question.append(r['feedback_uid'])
            continue
        # Text alone is the right key for a document question: "what is
        # VEBA" has one correct answer whoever asks. It is the WRONG key for
        # an account question -- "how many tokens do I have?" has a different
        # correct answer per account, so collapsing two accounts' rows into
        # one test invents a contradiction that was never there.
        shape_for_key = classify(qtext)
        if shape_for_key == 'account':
            # Group by the resolved CLIENT, not the raw account_uid: two
            # logins under one company are one wallet and must agree, so they
            # are one test. An account with no relay row cannot be resolved,
            # so it keys on itself and is reported.
            owner = r.get('client_uid')
            key = norm(qtext) + '\x00' + (
                'client:%s' % owner if owner
                else 'unresolved-account:%s' % r.get('account_uid'))
        else:
            key = norm(qtext)
        if key not in index:
            index[key] = len(groups)
            groups.append([])
        groups[index[key]].append(r)

    for g in groups:
        # rows arrive created_at ASC, so the last one is the most recent
        # judgement; it decides verdict, surface and guard.
        latest = g[-1]
        qtext = ' '.join(str(latest.get('question_text') or '').split())
        shape = classify(qtext)
        verdict = latest.get('verdict')
        qid = 'fb-%03d' % (len(questions) + 1)

        history = [{
            'feedback_uid': r['feedback_uid'],
            'verdict': r.get('verdict'),
            'status': r.get('status'),
            'note': r.get('note'),
            'message_uid': r.get('message_uid'),
            'prompt_version': r.get('prompt_version'),
            'account_uid': r.get('account_uid'),
            'client_uid': r.get('client_uid'),
            'created_at': (r['created_at'].isoformat()
                           if r.get('created_at') else None),
            'answer': clip(r.get('answer_text')),
        } for r in g]

        distinct = sorted({str(r.get('verdict')) for r in g})

        entry = {
            'id': qid,
            'question': qtext,
            'surface': latest.get('surface') or latest.get('conv_surface'),
            'language': latest.get('language'),
            'shape': 'unknown' if shape == 'ambiguous' else shape,
            # A 'good' verdict is a regression guard: it worked, keep it
            # working. 'wrong' / 'unhelpful' are the ones a fix must move.
            'guard': 'regression' if verdict == 'good' else 'fix',
            'expect': expectations(shape, qtext, latest.get('account_uid')),
            'origin': {
                'source': 'dll_waswa_feedback',
                'feedback_uid': latest['feedback_uid'],
                # An account question is only answerable against ONE account.
                # The runner must ask it as this account or the expected
                # answer is undefined.
                'account_uid': latest.get('account_uid'),
                # The runner must ASK as this account_uid -- that is the API
                # input -- but the answer belongs to the client below, which
                # is what the figures are read by.
                'ask_as_account_uid': latest.get('account_uid'),
                'client_uid': latest.get('client_uid'),
                'verdict': verdict,
                'status': latest.get('status'),
                'note': latest.get('note'),
                'message_uid': latest.get('message_uid'),
                'conversation_uid': latest.get('conversation_uid'),
                'model': latest.get('model'),
                'prompt_version': latest.get('prompt_version'),
                'router_tier': latest.get('router_tier'),
                'intent': latest.get('intent'),
                'created_at': (latest['created_at'].isoformat()
                               if latest.get('created_at') else None),
                # The answer the user judged. The runner can compare against
                # it to tell "fixed" from "same answer, still wrong".
                'previous_answer': clip(latest.get('answer_text')),
                'judgements': len(g),
                'verdicts_seen': distinct,
                # Every row behind this question, oldest first. Nothing is
                # thrown away by collapsing duplicates.
                'history': history,
            },
        }
        if len(g) > 1:
            collapsed.append((qid, len(g), distinct))
        if len(distinct) > 1:
            conflicts.append((qid, distinct, verdict))
            entry['_verdict_conflict'] = True
            entry['_verdict_conflict_reason'] = (
                'this question was judged %s at different times; the most '
                'recent judgement (%s) was used to set guard - confirm that '
                'is right' % ('/'.join(distinct), verdict))
        if shape == 'ambiguous':
            entry['_ambiguous'] = True
            entry['_ambiguous_reason'] = (
                'reads as both a how-to question and a question about this '
                'account - decide which tool is correct and set must_call')
        if _PRICE_BAIT.search(qtext):
            entry['_price_bait'] = True
            if shape == 'account':
                # "how much is my balance" reads as both. Refusing is right
                # for a price and wrong for a balance, so this cannot be
                # decided mechanically.
                entry['_needs_decision'] = True
                entry['_needs_decision_reason'] = (
                    'asks about this account AND invites a price. Declining '
                    'is correct for a price and wrong for a balance - set '
                    'must_not_refuse by hand')
            else:
                # Same expectation shape as a constraint row: declining and
                # handing off is the correct answer to a price question.
                entry['expect'] = dict(CONSTRAINT_EXPECT)
                entry['_expect_overridden'] = (
                    'price question - expectations replaced with the pricing '
                    'constraint block (must_not_refuse is deliberately false)')
        questions.append(entry)

    constraint_rows = []
    if not args.no_constraints:
        for i, c in enumerate(CONSTRAINT_QUESTIONS, 1):
            row = {
                'id': 'ct-%03d' % i,
                'question': c['question'],
                'surface': None,
                'language': None,
                'shape': 'constraint',
                'guard': 'constraint',
                'expect': dict(CONSTRAINT_EXPECT),
                'origin': {
                    'source': 'standing constraint, written by the builder - '
                              'NOT from user feedback',
                    'tests': c['tests'],
                    'verdict': None,
                    'previous_answer': None,
                },
                '_price_bait': True,
            }
            constraint_rows.append(row)
        questions.extend(constraint_rows)

    snapshots, snap_failures = 0, []
    if not args.no_context:
        snapshots, snap_failures = attach_context_snapshot(questions, DB_LINK)

    # Derived AFTER the snapshot, because all three rules read it.
    derived = apply_derived_expectations(questions)

    # Nothing is written until this passes. A figure in an expect block is a
    # suite that fails on correct answers later.
    assert_no_literal_figures(questions)

    doc = {
        '_what_this_is': (
            'The Waswa eval set. A fixed list of questions with expected '
            'outcomes, re-run after every prompt, retrieval or tool change. '
            'This is a test suite: it is meant to be kept and re-run, not '
            'deleted after one look.'),
        '_expectations_are_a_draft': (
            'Every expect block except must_not_contain_price was guessed '
            'from the wording of the question. Correct them by hand before '
            'the first run. A wrong expectation makes a correct answer look '
            'broken.'),
        '_seeded_from': (
            'dll_waswa_feedback - the only questions on this platform whose '
            'correct outcome a real user has already ruled on.'),
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'generated_by': 'scripts/waswa_eval_build.py',
        'statuses_included': statuses,
        'count': len(questions),
        'questions': questions,
    }

    outdir = os.path.dirname(args.out)
    if outdir and not os.path.isdir(outdir):
        os.makedirs(outdir)
    with io.open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(doc, indent=2, ensure_ascii=False))
        fh.write('\n')

    # ---------------- report ----------------
    print('=' * 78)
    print('  Waswa eval set -- seeded from real user verdicts')
    print('=' * 78)
    print('  feedback rows read     %d  (status in %s)' % (len(rows), statuses))
    print('  questions written      %d  (%d from feedback, %d constraint)'
          % (len(questions), len(questions) - len(constraint_rows),
             len(constraint_rows)))
    print('  output                 %s' % args.out)
    print('  context snapshots      %d account(s)%s'
          % (snapshots, ' (--no-context)' if args.no_context else ''))
    print('')

    by_shape = {}
    by_guard = {}
    for q in questions:
        by_shape[q['shape']] = by_shape.get(q['shape'], 0) + 1
        by_guard[q['guard']] = by_guard.get(q['guard'], 0) + 1

    print('  shape        count   drafted must_call')
    for shape in ('document', 'account', 'unknown', 'constraint'):
        if shape in by_shape:
            example = next(q for q in questions if q['shape'] == shape)
            print('  %-11s  %4d   %s'
                  % (shape, by_shape[shape],
                     example['expect']['must_call'] or '(left empty)'))
    print('')
    print('  guard        count')
    for guard in ('fix', 'regression'):
        if guard in by_guard:
            print('  %-11s  %4d' % (guard, by_guard[guard]))
    print('')

    ambiguous = [q for q in questions if q.get('_ambiguous')]
    bait = [q for q in questions if q.get('_price_bait')]

    print('-' * 78)
    print('  the questions')
    print('-' * 78)
    for q in questions:
        marks = []
        if q.get('_ambiguous'):
            marks.append('AMBIGUOUS')
        if q.get('_price_bait'):
            marks.append('price-bait')
        owner = q['origin'].get('client_uid')
        if q['shape'] == 'account':
            marks.insert(0, 'client ' + (str(owner)[:10] if owner
                                         else 'UNRESOLVED'))
        print('  [%s] %-10s %-10s %s%s'
              % (q['id'], q['origin']['verdict'], q['shape'],
                 clip(q['question'], 44),
                 '   <- ' + ', '.join(marks) if marks else ''))
    print('')

    print('-' * 78)
    print('  what needs your hand before the first run')
    print('-' * 78)
    if ambiguous:
        print('  %d question(s) could be read two ways. must_call was left'
              % len(ambiguous))
        print('  empty for these -- decide the correct tool yourself:')
        for q in ambiguous:
            print('      %s  %s' % (q['id'], clip(q['question'], 60)))
    else:
        print('  No ambiguous questions.')
    print('')
    unknown = [q for q in questions
               if q['shape'] == 'unknown' and not q.get('_ambiguous')]
    if unknown:
        print('  %d question(s) matched neither shape. must_call is empty:'
              % len(unknown))
        for q in unknown:
            print('      %s  %s' % (q['id'], clip(q['question'], 60)))
        print('')
    if bait:
        print('  %d question(s) invite a price - the rows that exercise the'
              % len(bait))
        print('  pricing hard block. On these, must_not_refuse is FALSE:')
        print('  declining and handing the user to a person is the correct')
        print('  answer. Do not flip it.')
        for q in bait:
            tag = 'constraint' if q['guard'] == 'constraint' else 'from a user'
            print('      %-7s %-12s %s'
                  % (q['id'], tag, clip(q['question'], 52)))
        print('')
    else:
        print('  NOTE: nothing in this set invites a price, so the pricing')
        print('  hard block is untested. Re-run without --no-constraints.')
        print('')

    if skipped_no_question:
        print('  %d feedback row(s) skipped: no user turn could be recovered'
              % len(skipped_no_question))
        for uid in skipped_no_question:
            print('      %s' % uid)
        print('')
    if any(derived.values()):
        print('-' * 78)
        print('  corrections derived from the evidence (not hand-applied)')
        print('-' * 78)
    for qid, zeros, explained in derived['dead_end']:
        print('  %s  must_not_dead_end' % qid)
        print('      because %s resolves to nothing for this account'
              % ', '.join(zeros))
        if explained:
            print('      and payment_standing holds records that bear on it,')
            print('      so what to say next is already in context')
    for qid in derived['liveness']:
        print('  %s  must_not_claim_live_when_stale' % qid)
        print('      asks whether something is running now, so the answer')
        print('      must not call a unit live while also dating its last')
        print('      report hours ago')
    for qid, on in derived['blocked']:
        print('  %s  blocked_on: %s' % (qid, on))
        print('      expected_to_fail - a red result here is a missing')
        print('      document, not a regression')
    for qid, seen in derived['split']:
        print('  %s  guard split: numbers=regression, phrasing=fix' % qid)
        print('      judged %s at different times on the same answer'
              % '/'.join(seen))
    if any(derived.values()):
        print('')
        print('  These are rules in the builder, so a rebuild keeps them and')
        print('  the next question that matches gets them too.')
        print('')

    accounts = [q for q in questions if q['shape'] == 'account']
    if accounts:
        print('-' * 78)
        print('  account questions, and what they are bound to')
        print('-' * 78)
        for q in accounts:
            o = q['origin']
            mmc = q['expect']['must_match_context']
            print('  %s  %s' % (q['id'], clip(q['question'], 56)))
            print('      ask as   %s' % o.get('ask_as_account_uid'))
            print('      client   %s'
                  % (o.get('client_uid')
                     or 'UNRESOLVED - no dll_access_relay row for that '
                        'account. Grouped on itself; the runner cannot check '
                        'its figures.'))
            print('      compare  %s' % ', '.join(mmc['slots']))
            snap = o.get('context_at_build')
            if snap:
                got = sorted(snap['slots'].keys())
                missing = sorted(snap['no_value'].keys())
                print('      today    %s' % (', '.join(got) if got
                                             else '(no numeric slot resolved)'))
                if missing:
                    print('      no value %s' % ', '.join(missing))
            print('')
        print('  No figure is written into any expectation. The runner asks')
        print('  as the account above and compares the answer against what')
        print('  build_context reports at that moment.')
        print('')
    if snap_failures:
        print('  %d account(s) could not be snapshotted:' % len(snap_failures))
        for uid, why in snap_failures:
            print('      %s  %s' % (uid, why))
        print('  (the expectation is unaffected - it resolves at run time)')
        print('')

    if collapsed:
        print('  %d question(s) carried more than one feedback row:'
              % len(collapsed))
        for qid, cnt, distinct in collapsed:
            print('      %s  %d judgements  verdicts seen: %s'
                  % (qid, cnt, ', '.join(distinct)))
        print('  All rows are kept under origin.history. The MOST RECENT')
        print('  verdict decides the guard.')
        print('')
    if conflicts:
        print('  %d question(s) were judged inconsistently. Check these'
              % len(conflicts))
        print('  before trusting their guard:')
        for qid, distinct, used in conflicts:
            print('      %s  seen %s  -> using %s'
                  % (qid, '/'.join(distinct), used))
        print('')

    print('  Nothing was written to the database. The only file written was')
    print('  %s.' % args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
