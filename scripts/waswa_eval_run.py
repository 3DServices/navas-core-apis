#!/usr/bin/env python3
"""
waswa_eval_run.py -- ask Waswa every question in the eval set and score it.

How it asks
-----------
Through the real route, POST /assistant/chat, with a real Authorization
header. By default it goes via app.test_client(), which is what every other
live route check in this repo uses (b2, b3, b3c, b4, b10). That is NOT the
same as calling the handler directly: Flask still does URL routing, blueprint
dispatch, before_request and the access guard, and _extract_account_uid still
has to find and decode a valid JWT. The only thing skipped is the socket.

Pass --base-url to go over the wire instead, against a deployed server.

Tokens are MINTED, not pasted
-----------------------------
_extract_account_uid accepts a signed JWT and nothing else. Rather than ask
anyone to paste credentials, this mints a short-lived token per account with
the app's own create_access_token, using the role, type and root read from
dll_access_relay -- the same claims /users/auth would issue. Nothing is
stored, nothing is printed, and the token lives only for the run.

Each question gets its own conversation, deliberately
-----------------------------------------------------
_resume_or_open_conversation reuses ANY open conversation for the same
account and surface whose last activity is within 60 minutes. Left alone that
would do two bad things: every eval question would land in ONE conversation,
so question 2 would see question 1 in its history and the set would stop
being fifteen independent questions; and if a real customer had an open
conversation, the eval turns would be appended to THEIRS.

So this script refuses to start if an open conversation already exists for an
account it is about to use, and closes each conversation it creates before
asking the next question. Both writes touch only conversations this run made.

This writes to your database
----------------------------
Every question opens a conversation and records turns, exactly as a real user
would. That is the point -- it is the real path. Every conversation_uid and
message_uid created is written into the run file, so scripts/waswa_eval_cleanup.py
can remove precisely those rows and nothing else.

Start with the pricing rows. They cost nothing.
-----------------------------------------------
_is_pricing_enquiry short-circuits BEFORE the model is called, so ct-001..003
exercise the whole harness -- auth, routing, the guard, conversation records,
the response shape -- without a single model call or a cent of spend:

    python scripts/waswa_eval_run.py --only ct-001,ct-002,ct-003

Then run the rest.

Usage:
    python scripts/waswa_eval_run.py --only ct-001
    python scripts/waswa_eval_run.py --limit 3
    python scripts/waswa_eval_run.py
    python scripts/waswa_eval_run.py --base-url https://api.example.com
"""

import argparse
import datetime
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, '.')

QUESTIONS = os.path.join('tests', 'waswa_eval', 'questions.json')
RUNS_DIR = os.path.join('tests', 'waswa_eval', 'runs')

# Phrases that mean "I will not answer", as opposed to an answer that happens
# to be negative. "You have no token packs" is an answer; "I don't have any
# approved documents" is a refusal.
_REFUSAL = re.compile(
    r"i (don'?t|do not) have (any |the )?(approved |specific )?"
    r"(documents?|information|details|steps|instructions)"
    # The first version missed every "couldn't find" phrasing, and three of
    # the eight knowledge rows refused in exactly those words and were scored
    # as passes. A refusal detector that misses the house style is worse than
    # none, because it reports a clean run.
    r"|i (couldn'?t|could not|can'?t|cannot|was unable to|am unable to)\s+"
    r"(find|locate|see)"
    r"|(couldn'?t|could not) find (any |the |specific |detailed )?"
    r"(information|instructions|details|steps|guidance|documents?)"
    r"|no (specific |detailed )?(information|instructions|steps|guidance) "
    r"(is |was )?(available|found)"
    r"|not covered in the (resources|documents)"
    r"|isn'?t covered"
    r"|i (can'?t|cannot) (help|answer|provide)"
    r"|no approved documents",
    re.I)

# A number in the answer. Money, counts, anything. Deliberately greedy about
# thousands separators and decimals so "1,200.50" is one number, not three.
_NUMBER = re.compile(r'-?\d[\d,]*(?:\.\d+)?')

# A claim that something is live right now.
_LIVE_CLAIM = re.compile(
    r"\b(is |are |currently |actively )?(online|actively reporting|"
    r"reporting now|currently reporting|live now)\b", re.I)

# "last reported 7.3 hours ago", "last seen 2 days ago".
_STATED_AGE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(minute|min|hour|hr|day)s?\s*ago\b", re.I)

# Above this, "actively reporting" is not a defensible description. One hour
# is generous for a tracker that normally reports every few minutes.
STALE_HOURS = 1.0


def stated_age_hours(text):
    """The oldest age the answer states, in hours, or None."""
    worst = None
    for amount, unit in _STATED_AGE.findall(str(text or '')):
        try:
            value = float(amount)
        except ValueError:
            continue
        unit = unit.lower()
        hours = value / 60.0 if unit.startswith('min') else (
            value * 24.0 if unit.startswith('day') else value)
        worst = hours if worst is None else max(worst, hours)
    return worst


# Words that make a reply a handoff rather than a dead end.
_HANDOFF = re.compile(
    r"\b(sales|support|contact|team|representative|get in touch|reach out|"
    r"connect you|put you in touch)\b", re.I)


def norm_number(text):
    """'1,200.0' and '1200' compare equal."""
    try:
        value = float(str(text).replace(',', ''))
    except (TypeError, ValueError):
        return None
    return round(value, 4)


# An identifier is not a figure the answer is claiming. An IMEI and the
# "364" inside the plate "UBF 364U" both got reported as fabricated numbers on
# the first run; neither was.
_IDENTIFIER_DIGITS = 8        # IMEIs, uids, account numbers

# ISO and the DD-MM-YYYY this codebase uses elsewhere. A date is not a
# quantity the answer is claiming.
_DATE_SHAPED = re.compile(r'\b(?:\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4}|'
                          r'\d{4}/\d{2}/\d{2}|\d{2}/\d{2}/\d{4})\b')


def numbers_in(text, claimed_only=True):
    """(kept, skipped) -- always a pair, whatever claimed_only is.

    The first version returned a bare list when claimed_only was False and a
    pair otherwise. That is a function with two shapes, and the very next
    caller unpacked the wrong one and crashed the run. One shape, always.
    """
    body = str(text or '')
    out, skipped = [], []
    # Find dates FIRST and take them out of the text, rather than guessing
    # per character. Two earlier attempts at this read "2026-09-18" as the
    # numbers 2026, -09 and -18; the fix for that then swallowed "10-20
    # units" as well. A date is a shape, so match the shape.
    dates_found = []
    def _blank(match):
        dates_found.append(match.group(0))
        return ' ' * len(match.group(0))
    body = _DATE_SHAPED.sub(_blank, body)
    for value in dates_found:
        skipped.append((value, 'a date'))
    for match in _NUMBER.finditer(body):
        # "[\d,]*" happily eats the comma in "862846042593213, named", which
        # made the reported value look malformed. Numerically harmless, but a
        # figure quoted back to a reader should be the figure.
        raw = match.group(0).rstrip(',')
        if not raw:
            continue
        value = norm_number(raw)
        if value is None:
            continue
        if claimed_only:
            digits = sum(c.isdigit() for c in raw)
            before = body[match.start() - 1] if match.start() else ' '
            after = body[match.end()] if match.end() < len(body) else ' '
            if digits >= _IDENTIFIER_DIGITS:
                skipped.append((raw, 'identifier'))
                continue
            if before.isalpha() or after.isalpha():
                # "UBF 364U", "v2", "Q3" -- part of a name, not a quantity.
                skipped.append((raw, 'inside a name'))
                continue
            if raw in dates_found:
                continue
            if raw.startswith('-') and before.isdigit():
                # "10-20 units" is a range, not ten and minus twenty. Dates
                # are already gone by here, so a hyphen between digits that
                # survived is a range separator.
                raw = raw[1:]
                value = norm_number(raw)
                if value is None:
                    continue
        out.append((raw, value))
    return out, skipped


def numbers_of(value, into=None):
    """Every number anywhere inside a context slot, flattened."""
    into = into if into is not None else set()
    if isinstance(value, bool):
        return into
    if isinstance(value, (int, float)):
        into.add(round(float(value), 4))
    elif isinstance(value, str):
        kept, _ = numbers_in(value, claimed_only=False)
        for _, number in kept:
            into.add(number)
    elif isinstance(value, dict):
        for key, item in value.items():
            # This is the line that crashed: it took the default
            # claimed_only=True and unpacked a pair as if it were a list.
            kept, _ = numbers_in(key, claimed_only=False)
            for _, number in kept:
                into.add(number)
            numbers_of(item, into)
    elif isinstance(value, (list, tuple)):
        for item in value:
            numbers_of(item, into)
    return into


def mint_token(cur, account_uid):
    """A real token for this account, with the claims /users/auth would set."""
    from endpoints.jwt_utils import create_access_token
    cur.execute(
        "SELECT account_root, account_type, account_clearance "
        "FROM dll_access_relay WHERE account_uid = %s", (str(account_uid),))
    row = cur.fetchone() if cur.rowcount else None
    if not row:
        return None, 'no dll_access_relay row for this account'
    root, acct_type, clearance = row
    return create_access_token(account_uid, clearance, acct_type, root), None


def open_conversations(cur, pairs):
    """Open, recent conversations for the (account, surface) pairs we will
    use. A hit means a real conversation this run must not write into."""
    hits = []
    for account, surface in sorted(pairs):
        cur.execute(
            "SELECT conversation_uid, last_activity_at, "
            "       (SELECT COUNT(*) FROM dll_waswa_messages m "
            "         WHERE m.conversation_uid = c.conversation_uid) "
            "FROM dll_waswa_conversations c "
            "WHERE account_uid = %s AND surface = %s AND status = 'open' "
            "  AND last_activity_at > NOW() - INTERVAL '60 minutes'",
            (str(account), str(surface)))
        for uid, last, turns in cur.fetchall():
            hits.append((account, surface, uid, last, turns))
    return hits


def close_conversation(cur, conversation_uid):
    """Close a conversation this run created, so the next question opens a
    fresh one instead of resuming into this one's history."""
    cur.execute(
        "UPDATE dll_waswa_conversations SET status = 'closed' "
        "WHERE conversation_uid = %s AND status = 'open'",
        (str(conversation_uid),))
    return cur.rowcount


def ask(client, base_url, token, question, surface):
    """One turn. Returns (http_status, payload, seconds)."""
    body = {'data': {'message': question, 'surface': surface or 'mobile'}}
    headers = {'Authorization': 'Bearer %s' % token}
    started = time.time()
    if base_url:
        import requests
        resp = requests.post(base_url.rstrip('/') + '/assistant/chat',
                             json=body, headers=headers, timeout=120)
        elapsed = time.time() - started
        try:
            return resp.status_code, resp.json(), elapsed
        except ValueError:
            return resp.status_code, {'raw': resp.text[:500]}, elapsed
    resp = client.post('/assistant/chat', json=body, headers=headers)
    elapsed = time.time() - started
    try:
        return resp.status_code, resp.get_json(), elapsed
    except Exception:                                   # noqa: BLE001
        return resp.status_code, {'raw': resp.data[:500].decode('utf-8', 'replace')}, elapsed


def score(row, payload, context_numbers):
    """Score what can be scored. Anything needing judgement is NOT scored."""
    data = (payload or {}).get('data') or {}
    answer = str(data.get('reply') or '')
    evidence = data.get('evidence') or []
    refs = [str(e.get('source_ref') or '') for e in evidence]
    kinds = {str(e.get('source_kind') or '') for e in evidence}
    expect = row.get('expect') or {}

    checks = []

    def record(name, ok, detail):
        # ok may be True, False, or None for "cannot be decided from what was
        # recorded". None is not a pass and not a failure.
        checks.append({'check': name, 'result': ok, 'detail': detail})

    # --- tools actually used -------------------------------------------
    # assistant.py records one evidence row per tool call, unconditionally,
    # with source_ref = "tool_name(args)". So this is a real record of what
    # ran, not an inference from the wording of the answer.
    for tool in expect.get('must_call') or []:
        called = any(ref.startswith(tool + '(') for ref in refs)
        record('must_call:%s' % tool, called,
               'tools used: %s' % (', '.join(refs) or 'none'))

    # --- the account's own context was in front of the model -------------
    if expect.get('must_use_account_context'):
        # Seeded by assistant.py before any tool runs, so its absence means
        # context assembly failed, not that the model chose differently.
        record('must_use_account_context', 'account_context' in kinds,
               'account context present' if 'account_context' in kinds
               else 'NO account_context evidence - build_context failed')

    # --- live now, or merely subscribed? ---------------------------------
    if expect.get('must_not_claim_live_when_stale'):
        age = stated_age_hours(answer)
        claims_live = bool(_LIVE_CLAIM.search(answer))
        # Where the claim came from matters as much as whether it is stale.
        # The original fb-009 failure answered a liveness question from a
        # subscription count; fleet_liveness is the only source that reads
        # heartbeats, so its absence behind a liveness claim is the defect
        # even when no age is quoted to contradict.
        from_heartbeats = any(r.startswith('fleet_liveness') for r in refs)
        if claims_live and age is not None and age > STALE_HOURS:
            record('must_not_claim_live_when_stale', False,
                   'calls it live while dating its last report %.1fh ago' % age)
        elif claims_live and not from_heartbeats:
            record('must_not_claim_live_when_stale', False,
                   'claims something is live without reading the heartbeat '
                   'registry - a subscription status is not liveness')
        elif claims_live:
            record('must_not_claim_live_when_stale', True,
                   'liveness claim is backed by fleet_liveness%s'
                   % ('' if age is None else ', newest %.1fh' % age))
        else:
            record('must_not_claim_live_when_stale', True,
                   'no liveness claim to check')

    # --- a document behind the answer -----------------------------------
    if expect.get('must_cite_document'):
        # CAVEAT: kind is set to 'document' whenever the knowledge dispatcher
        # returned anything, including a search that found nothing. Presence
        # proves retrieval ran; it does not prove a document was found. The
        # authority level is reported so a reader can tell.
        auths = [e.get('authority_level') for e in evidence
                 if e.get('source_kind') == 'document']
        # A document-kind row is written whenever the knowledge dispatcher
        # returned ANYTHING, a search that found nothing included -- and such
        # a row carries authority_level None, because there was no chunk to
        # take an authority from. Accepting those passed two rows whose
        # answer was "I couldn't find it in the approved documents".
        graded = [a for a in auths if a is not None]
        if not auths:
            record('must_cite_document', False, 'no document evidence at all')
        elif not graded:
            record('must_cite_document', False,
                   'retrieval ran and returned nothing - %d document row(s), '
                   'every authority_level None' % len(auths))
        else:
            record('must_cite_document', True,
                   'authority levels: %s' % graded)

    # --- refusal ---------------------------------------------------------
    refused = bool(_REFUSAL.search(answer))
    if expect.get('must_not_refuse'):
        record('must_not_refuse', not refused,
               'refusal wording found' if refused else 'no refusal wording')

    # --- the pricing hard block -----------------------------------------
    if expect.get('must_not_contain_price'):
        # The block short-circuits before the model and stamps the turn, so
        # this is a positive confirmation rather than a scan for digits.
        stamped = (data.get('intent') == 'pricing_enquiry'
                   and data.get('router_tier') == 1)
        money = re.search(r'\b(ugx|kes|usd|shs?)\b|\$\s*\d', answer, re.I)
        record('must_not_contain_price', not money,
               'routed to sales before the model' if stamped
               else ('currency mentioned: %s' % money.group(0) if money
                     else 'no currency in the answer'))

    if expect.get('must_redirect_to_human'):
        record('must_redirect_to_human', bool(_HANDOFF.search(answer)),
               'handoff wording present' if _HANDOFF.search(answer)
               else 'no handoff offered')

    # --- figures must be the store's figures -----------------------------
    if expect.get('no_unsourced_numbers') and context_numbers is not None:
        found, skipped = numbers_in(answer)
        unsourced = [raw for raw, value in found if value not in context_numbers]
        # Evidence records that a tool ran, never what it returned. So a
        # figure the model got from a live fleet read has nowhere to be traced
        # to, and calling that fabricated would be a wrong expectation failing
        # a right answer.
        live_tools = [r for r in refs
                      if not r.startswith('waswa_context')
                      and not r.startswith('knowledge_search')]
        note = ''
        if skipped:
            note = ' (ignored %s)' % ', '.join(
                '%s: %s' % (raw, why) for raw, why in skipped)
        if unsourced and live_tools:
            record('no_unsourced_numbers', None,
                   'cannot decide - %s may come from %s%s'
                   % (', '.join(unsourced), ', '.join(live_tools), note))
        else:
            record('no_unsourced_numbers', not unsourced,
                   ('every figure traced to context' + note) if not unsourced
                   else 'not in context: %s%s' % (', '.join(unsourced), note))

    # --- deliberately NOT scored -----------------------------------------
    unscored = []
    if 'must_not_dead_end' in expect:
        unscored.append({
            'check': 'must_not_dead_end',
            'why': 'needs a judgement about whether the answer offers a '
                   'useful next step. No mechanical test for this; a '
                   'reviewer or a model as judge has to read it.',
            'hint_offers_handoff': bool(_HANDOFF.search(answer)),
        })

    return checks, unscored, answer, refs


def traced_slots(row):
    """Which context slots a row's figures may legitimately come from.

    A zero-state row is told to explain itself from another slot -- payments,
    usually. Tracing only the first slot reported the payment dates Waswa had
    just been instructed to quote as fabricated figures.
    """
    expect = row.get('expect') or {}
    slots = list((expect.get('must_match_context') or {}).get('slots', []))
    slots += [s for s in
              (expect.get('must_not_dead_end') or {}).get(
                  'context_that_explains_it', [])
              if s not in slots]
    return slots


def checks_fingerprint():
    """A short hash of the scoring rules.

    The 00:55 run was scored by a refusal pattern that missed "I couldn't
    find", and the 01:05 run was not. Comparing them row by row makes a fixed
    harness look like a flaky system. Runs carry this so the report can refuse
    to compare across a change in the rules.
    """
    import hashlib
    import inspect
    # Every function and pattern that can change a verdict. The first
    # version hashed score() and a few regexes, and missed numbers_in and
    # the date matcher -- so a change that flipped a row from FAIL to pass
    # left the fingerprint identical, and the replay announced "same rules,
    # nothing should move" immediately before a row moved. A guard that
    # under-reports a change is worse than no guard.
    material = ''.join([
        inspect.getsource(score),
        inspect.getsource(numbers_in),
        inspect.getsource(numbers_of),
        inspect.getsource(stated_age_hours),
        inspect.getsource(traced_slots),
        _REFUSAL.pattern, _LIVE_CLAIM.pattern, _STATED_AGE.pattern,
        _HANDOFF.pattern, _NUMBER.pattern, _DATE_SHAPED.pattern,
        str(STALE_HOURS), str(_IDENTIFIER_DIGITS),
    ])
    return hashlib.sha1(material.encode('utf-8')).hexdigest()[:12]


def rebuild_evidence(result):
    """Evidence rows for a run recorded before they were stored whole.

    Not guesswork. assistant.py seeds ('account_context', 'waswa_context', 3)
    before any tool runs, and writes one row per tool call with
    source_ref = "tool_name(args)". The knowledge dispatcher is what makes a
    row document-kind, and knowledge_search is its tool. The authority levels
    were recorded separately in cited_authorities, in the same order.

    Returns (evidence, note) or (None, reason).
    """
    refs = result.get('tools_used')
    auths = result.get('cited_authorities')
    if refs is None or auths is None:
        return None, 'recorded before evidence or authorities were stored'
    evidence, remaining = [], list(auths)
    for ref in refs:
        if ref == 'waswa_context':
            evidence.append({'source_kind': 'account_context',
                             'source_ref': ref, 'authority_level': 3})
        elif ref.startswith('knowledge_search('):
            level = remaining.pop(0) if remaining else None
            evidence.append({'source_kind': 'document',
                             'source_ref': ref, 'authority_level': level})
        else:
            evidence.append({'source_kind': 'tool',
                             'source_ref': ref, 'authority_level': 1})
    return evidence, 'rebuilt from tools_used + cited_authorities'


def replay(run_path, questions_path):
    """Re-score a recorded run with the CURRENT checks. No model, no
    database, no writes -- it answers "would this change of expectation have
    scored differently?" in under a second.

    Seven runs of recorded answers are a regression corpus for the harness
    itself: change a check, replay them all, see exactly what moves.
    """
    if not os.path.exists(run_path):
        print('no such run file: %s' % run_path)
        return 1
    with io.open(run_path, encoding='utf-8') as fh:
        run = json.load(fh)
    with io.open(questions_path, encoding='utf-8') as fh:
        rows = {q['id']: q for q in json.load(fh)['questions']}

    print('=' * 86)
    print('  replay of %s' % os.path.basename(run_path))
    print('  scored when: %s' % (run.get('checks_fingerprint') or 'unversioned'))
    print('  scored now : %s' % checks_fingerprint())
    print('=' * 86)
    if (run.get('checks_fingerprint') or 'unversioned') == checks_fingerprint():
        print('  Same rules as the recorded run, so nothing should move.')
    print('')

    moved, missing, skipped = [], [], []
    not_replayable = {}
    rebuilt_rows = 0
    for result in run.get('results') or []:
        rid = result.get('id')
        row = rows.get(rid)
        if row is None:
            missing.append(rid)
            continue
        evidence = result.get('evidence')
        rebuilt = None
        if evidence is None:
            evidence, rebuilt = rebuild_evidence(result)
            if evidence is None:
                skipped.append((rid, rebuilt))
                continue
        context_numbers = result.get('context_numbers')
        if context_numbers is not None:
            context_numbers = set(context_numbers)
        else:
            # Without the figures the store held at the time, this one check
            # cannot be re-scored. Drop it rather than re-score it against
            # today's store and call the difference a change in the checks.
            not_replayable.setdefault('no_unsourced_numbers', []).append(rid)
        checks, unscored, answer, refs = score(
            row, {'data': {'reply': result.get('answer'),
                           'evidence': evidence,
                           'intent': result.get('intent'),
                           'router_tier': result.get('router_tier')}},
            context_numbers)

        was = {c['check']: c['result'] for c in result.get('checks') or []}
        now = {c['check']: c['result'] for c in checks}
        if result.get('context_numbers') is None:
            was.pop('no_unsourced_numbers', None)
            now.pop('no_unsourced_numbers', None)
        label = {True: 'pass', False: 'FAIL', None: '????'}
        changes = []
        for name in sorted(set(was) | set(now)):
            before, after = was.get(name, 'absent'), now.get(name, 'absent')
            if before != after:
                changes.append('%s: %s -> %s'
                               % (name,
                                  label.get(before, before),
                                  label.get(after, after)))
        if rebuilt:
            rebuilt_rows += 1
        if changes:
            moved.append((rid, changes))
            print('  %-7s %s' % (rid, row['question'][:56]))
            for change in changes:
                print('        %s' % change)

    print('')
    print('-' * 86)
    if not moved:
        print('  No row scored differently.')
    else:
        print('  %d row(s) scored differently under the current checks.'
              % len(moved))
    if rebuilt_rows:
        print('  %d row(s) had their evidence rebuilt from the recorded tool '
              'names' % rebuilt_rows)
        print('  and authority levels -- faithful, but not the original rows.')
    for check, ids in sorted(not_replayable.items()):
        print('  %s was skipped on %d row(s): the context figures of the '
              'time' % (check, len(ids)))
        print('  were not recorded, and re-scoring against today\'s store '
              'would')
        print('  report a moving database as a change in the checks.')
    if skipped:
        print('  %d row(s) could not be replayed at all:' % len(skipped))
        for rid, why in skipped:
            print('      %-7s %s' % (rid, why))
    if missing:
        print('  %d row(s) are no longer in the question set: %s'
              % (len(missing), ', '.join(missing)))
    print('')
    print('  Nothing was called and nothing was written.')
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--questions', default=QUESTIONS)
    ap.add_argument('--only', default=None,
                    help='comma-separated row ids, e.g. ct-001,fb-008')
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--base-url', default=None,
                    help='hit a deployed server instead of app.test_client()')
    ap.add_argument('--as-account', default=None,
                    help='account to ask non-account questions as. Defaults '
                         'to the first account question in the set.')
    ap.add_argument('--isolate-surface', action='store_true',
                    help="ask on a surface of this run's own, so no real "
                         "conversation can be resumed. Surface does not "
                         "affect which documents are visible (audience comes "
                         "from the account, not the surface), but it is "
                         "recorded on the conversation, so the default is to "
                         "keep the real one.")
    ap.add_argument('--replay', default=None, metavar='RUNFILE',
                    help='re-score a recorded run with the current checks. '
                         'No model calls, no database, no writes.')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    if args.replay:
        return replay(args.replay, args.questions)

    if not os.path.exists(args.questions):
        print('no eval set at %s -- run scripts/waswa_eval_build.py first'
              % args.questions)
        return 1

    with io.open(args.questions, encoding='utf-8') as fh:
        doc = json.load(fh)
    rows = doc['questions']

    if args.only:
        wanted = {r.strip() for r in args.only.split(',') if r.strip()}
        rows = [r for r in rows if r['id'] in wanted]
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        print('no rows selected')
        return 1

    import psycopg2
    from config import DB_LINK
    from endpoints.waswa_context import build_context

    default_account = args.as_account
    if not default_account:
        default_account = next(
            (r['origin'].get('ask_as_account_uid') for r in doc['questions']
             if r.get('shape') == 'account'
             and r['origin'].get('ask_as_account_uid')), None)
    if not default_account:
        print('no account to ask as. Pass --as-account.')
        return 1

    client = None
    if not args.base_url:
        from app import app
        client = app.test_client()

    conn = psycopg2.connect(DB_LINK)
    conn.autocommit = True

    # Refuse to write into a conversation somebody else is having.
    pairs = {((r['origin'].get('ask_as_account_uid') or default_account),
              (('eval-' + (r.get('surface') or 'mobile'))[:20]
               if args.isolate_surface else (r.get('surface') or 'mobile')))
             for r in rows}
    with conn.cursor() as cur:
        existing = open_conversations(cur, pairs)
    # A conversation on an "eval-" surface can only have been made by this
    # runner -- nothing else uses those surfaces. A crashed run leaves one
    # open, and refusing to start because of our own litter helps nobody.
    ours = [e for e in existing if str(e[1]).startswith('eval-')]
    if ours:
        with conn.cursor() as cur:
            for account, surface, uid, last, turns in ours:
                closed = close_conversation(cur, uid)
                if closed:
                    print('  closing %s on %s -- left open by an earlier eval '
                          'run' % (uid, surface))
        existing = [e for e in existing if e not in ours]

    if existing:
        print('REFUSING to start. An open conversation already exists for an')
        print('account this run would use, and Waswa resumes any open')
        print('conversation within 60 minutes -- so these questions would be')
        print('appended to it:')
        print('')
        for account, surface, uid, last, turns in existing:
            print('    %s  surface=%-14s %d turn(s), last active %s'
                  % (uid, surface, turns, last))
        print('')
        print('Either wait for it to go idle, or close it, or re-run with')
        print('--isolate-surface to ask on a surface of this run\'s own.')
        conn.close()
        return 1

    results = []
    crashed = None
    created = {'conversations': [], 'messages': []}
    started_at = datetime.datetime.now()

    print('=' * 86)
    print('  Waswa eval run  --  %d row(s)  --  %s'
          % (len(rows), 'HTTP %s' % args.base_url if args.base_url
             else 'app.test_client()'))
    print('=' * 86)

    try:
        for row in rows:
            account = (row['origin'].get('ask_as_account_uid')
                       or default_account)
            with conn.cursor() as cur:
                token, why = mint_token(cur, account)
            if not token:
                print('  %-7s SKIPPED -- %s' % (row['id'], why))
                results.append({'id': row['id'], 'error': why})
                continue

            surface = row.get('surface') or 'mobile'
            if args.isolate_surface:
                surface = ('eval-' + surface)[:20]
            status, payload, elapsed = ask(
                client, args.base_url, token, row['question'], surface)

            data = (payload or {}).get('data') or {}
            if data.get('conversation_uid'):
                created['conversations'].append(data['conversation_uid'])
            if data.get('message_uid'):
                created['messages'].append(data['message_uid'])

            context_numbers = None
            if row.get('shape') == 'account':
                ctx = build_context(account, surface=row.get('surface')
                                    or 'mobile', conn=conn)
                slots = traced_slots(row)
                context_numbers = set()
                for slot in slots:
                    numbers_of(ctx.get('known', {}).get(slot), context_numbers)

            checks, unscored, answer, refs = score(row, payload,
                                                   context_numbers)
            # None is "cannot be decided", which is neither a pass nor a
            # failure. `not c['result']` would have counted it as a failure.
            failed = [c for c in checks if c['result'] is False]
            undecided = [c for c in checks if c['result'] is None]

            results.append({
                'id': row['id'], 'question': row['question'],
                'shape': row.get('shape'), 'guard': row.get('guard'),
                'blocked_on': row.get('blocked_on'),
                'asked_as': account, 'http_status': status,
                'seconds': round(elapsed, 2),
                'answer': answer,
                'tools_used': refs,
                # Recorded so a run can be re-scored offline later. Replay
                # needs the evidence rows as they were, not an inference
                # from the tool names, and the context figures as they were
                # at the time -- the store moves.
                'evidence': data.get('evidence') or [],
                'context_numbers': (sorted(context_numbers)
                                    if context_numbers is not None else None),
                # Which sources backed the answer, so a run that cites a
                # different document for the same question is visible. The
                # authority level is the only identifier the response
                # carries; the document title is in the answer text.
                'cited_authorities': sorted(
                    [e.get('authority_level') for e in
                     ((payload or {}).get('data') or {}).get('evidence') or []
                     if e.get('source_kind') == 'document'],
                    key=lambda v: (v is None, v)),
                'intent': data.get('intent'),
                'router_tier': data.get('router_tier'),
                'prompt_version': data.get('prompt_version'),
                'conversation_uid': data.get('conversation_uid'),
                'message_uid': data.get('message_uid'),
                'checks': checks, 'not_scored': unscored,
                'passed': not failed,
                'undecided': len(undecided),
            })

            # Close it so the next question is asked fresh rather than
            # resuming into this one's history.
            if data.get('conversation_uid'):
                with conn.cursor() as cur:
                    close_conversation(cur, data['conversation_uid'])

            mark = 'PASS' if not failed else 'FAIL'
            if row.get('blocked_on') and failed:
                mark = 'BLOCKED'
            print('')
            print('  [%s] %-7s %s' % (mark, row['id'],
                                      row['question'][:56]))
            print('          http %s in %.1fs, tools: %s'
                  % (status, elapsed, ', '.join(refs) or 'none'))
            for check in checks:
                mark = {True: 'ok', False: 'FAIL', None: '????'}[check['result']]
                print('          %-4s %-28s %s'
                      % (mark, check['check'], check['detail'][:62]))
            for item in unscored:
                print('          --   %-28s not scored' % item['check'])
    except Exception as error:      # noqa: BLE001
        # The run file is how cleanup finds what was created. If the loop
        # dies, the rows are already in the database and would otherwise be
        # unreachable, so the file is written either way and the error is
        # re-raised afterwards.
        import traceback
        crashed = '%s: %s' % (error.__class__.__name__, error)
        print('')
        traceback.print_exc()
        print('')
        print('  RUN CRASHED -- %s' % crashed)
        print('  the rows created so far are still recorded below, so')
        print('  cleanup can still find them.')
    finally:
        conn.close()

    out = args.out or os.path.join(
        RUNS_DIR, started_at.strftime('%Y%m%d-%H%M%S') + '.json')
    if not os.path.isdir(os.path.dirname(out)):
        os.makedirs(os.path.dirname(out))
    with io.open(out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps({
            '_what_this_is': 'one run of the Waswa eval set. The ids under '
                             '"created" are the rows this run added to your '
                             'database; scripts/waswa_eval_cleanup.py removes '
                             'exactly those and nothing else.',
            'started_at': started_at.isoformat(timespec='seconds'),
            'transport': args.base_url or 'app.test_client()',
            'checks_fingerprint': checks_fingerprint(),
            'crashed': crashed,
            'rows': len(rows),
            'created': created,
            'results': results,
        }, indent=2, ensure_ascii=False))
        fh.write('\n')

    scored = [r for r in results if 'checks' in r]
    passed = [r for r in scored if r['passed']]
    blocked = [r for r in scored if r.get('blocked_on') and not r['passed']]
    print('')
    print('=' * 86)
    print('  %d of %d rows passed every check they could be scored on'
          % (len(passed), len(scored)))
    undecided = sum(r.get('undecided') or 0 for r in scored)
    if undecided:
        print('  %d check(s) could not be decided from what was recorded '
              '(????)' % undecided)
    if blocked:
        print('  %d of the failures are BLOCKED rows -- a missing document, '
              'not a regression' % len(blocked))
    pending = sum(len(r.get('not_scored') or []) for r in scored)
    if pending:
        print('  %d check(s) need a human: must_not_dead_end cannot be '
              'scored mechanically' % pending)
    print('')
    print('  run written to %s' % out)
    print('  it created %d conversation(s) and %d message(s) in your database.'
          % (len(created['conversations']), len(created['messages'])))
    print('  remove them with:')
    print('      python scripts/waswa_eval_cleanup.py %s' % out)
    return 1 if crashed else 0


if __name__ == '__main__':
    sys.exit(main())
