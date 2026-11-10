#!/usr/bin/env python3
"""
test_waswa_v2.py -- the v2 agent, driven end to end with fakes.

No database, no network, no model. run_turn() takes `search` and `call_model`
as arguments precisely so this can exist, because the database at
165.232.128.208 is unreachable from the agent sandbox and an improvement
nobody can demonstrate is just an assertion.

The two scenarios that carry the work are 7 and 8: the wrong-corpus case
(eval row fb-010) and the retrieval-recovery case (fb-003). Both are written
so that a v1-shaped agent would FAIL them.

Run:
    python tests/test_waswa_v2.py
"""

import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)



def _load():
    """Load the module by path.

    `from endpoints import waswa_v2` would run endpoints/__init__.py, which
    imports every blueprint and dies on the Cassandra driver. waswa_v2 imports
    nothing but `re`, so it loads standalone -- which is itself worth keeping
    true: an agent whose logic needs a database to import cannot be tested.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'waswa_v2', os.path.join(ROOT, 'endpoints', 'waswa_v2.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v2 = _load()

PASS, FAIL = [], []


def check(name, got, want):
    (PASS if got == want else FAIL).append(
        name if got == want else '%s\n      got  %r\n      want %r'
        % (name, got, want))


def truthy(name, got):
    check(name, bool(got), True)


# ── fakes ──────────────────────────────────────────────────────────────────

CMS_GEOFENCE = {
    'source': 'NAVAS CMS User Manual',
    'document_type': 'user_manual',
    'category': 'geofencing',
    'heading': 'Creating a geofence',
    'text': 'In the CMS, open Administration then Geofences and click New.',
    'authority_level': 2,
}

MOBILE_GEOFENCE = {
    'source': 'OLIWA Mobile App Guide',
    'document_type': 'user_guide',
    'category': 'geofencing',
    'heading': 'New zone',
    'text': 'Open the Dashboard, tap Geofences, tap New.',
    'authority_level': 2,
}

# What the dispatcher returns when a search found nothing: a row, but with no
# authority level, because there was no chunk to take one from.
EMPTY_ROW = {'source': None, 'document_type': None, 'authority_level': None}


def searcher(script):
    """A fake knowledge_search. `script` maps a query substring to results."""
    calls = []

    def search(query):
        calls.append(query)
        for needle, results in script:
            if needle is None or needle.lower() in query.lower():
                return {'found': bool(results), 'results': results}
        return {'found': False, 'results': []}

    search.calls = calls
    return search


def model(*replies):
    """A fake model returning each reply in turn, repeating the last."""
    seen = []

    def call(messages):
        seen.append(messages)
        index = min(len(seen) - 1, len(replies) - 1)
        return replies[index]

    call.seen = seen
    return call


# ── 1-2: scope, on both sides ──────────────────────────────────────────────

def test_scope():
    check('1a mobile surface', v2.surface_family('mobile'), 'mobile')
    check('1b console surface', v2.surface_family('console'), 'console')
    check('1c the eval prefix is stripped, not enumerated',
          v2.surface_family('eval-mobile'), 'mobile')
    check('1d an unknown surface is unknown, not a default',
          v2.surface_family('kiosk'), None)

    check('2a a CMS manual is console scope',
          v2.document_scope(CMS_GEOFENCE), 'console')
    check('2b an OLIWA mobile guide is mobile scope',
          v2.document_scope(MOBILE_GEOFENCE), 'mobile')
    check('2c a document that does not say is None, never a guess',
          v2.document_scope({'source': 'Token Billing Policy'}), None)


# ── 3: planning ────────────────────────────────────────────────────────────

def test_plan():
    plan = v2.plan_turn('how do I created a new geofence', surface='mobile')
    check('3a fb-010 is recognised despite the grammar',
          plan['kind'], 'how_to')
    check('3b and it demands a mobile-scoped document',
          plan['require_scope'], 'mobile')

    plan = v2.plan_turn('How many tokens do I have?', surface='mobile')
    check('3c an account question is not a how-to', plan['kind'], 'account')
    check('3d and carries no scope requirement',
          plan['require_scope'], None)

    plan = v2.plan_turn('Where is UBF 364U right now?', surface='console')
    check('3e a fleet question is classified', plan['kind'], 'fleet')

    plan = v2.plan_turn('How do I add a user?', surface='kiosk')
    check('3f an unknown surface demands no scope it cannot name',
          plan['require_scope'], None)


# ── 4: the reformulation ladder ────────────────────────────────────────────

def test_reformulate():
    queries = v2.reformulate('how do I created a new geofence')
    check('4a the question as asked goes first',
          queries[0], 'how do I created a new geofence')
    truthy('4b a stripped form follows', len(queries) > 1)
    check('4c the stripped form keeps the word doing the work',
          'geofence' in queries[1], True)
    check('4d and drops the question words',
          any(word in queries[1].split() for word in ('how', 'do', 'i')),
          False)
    check('4e no duplicates', len(queries), len(set(queries)))

    check('4f a module is used when given',
          any('Billing' in q for q in
              v2.reformulate('how do I pay', module='Billing')), True)


# ── 5: retrieval with recovery ─────────────────────────────────────────────

def test_retrieve():
    plan = v2.plan_turn('How are devices registered?', surface='console')

    # Nothing on the question as asked; the stripped form finds it. This is
    # the recovery v1 does not have -- it would have refused after attempt 1.
    search = searcher([('How are devices registered?', []),
                       (None, [dict(CMS_GEOFENCE, category='devices')])])
    out = v2.retrieve(plan, search)
    check('5a recovers on the second query', len(out['chunks']), 1)
    check('5b and records both attempts', len(out['attempts']), 2)
    check('5c not exhausted', out['exhausted'], False)

    # An authority_level of None is the dispatcher's "found nothing" row.
    search = searcher([(None, [EMPTY_ROW])])
    out = v2.retrieve(plan, search)
    check('5d an ungraded row is not a result', out['chunks'], [])
    check('5e so the ladder is exhausted', out['exhausted'], True)
    truthy('5f having tried more than once', len(out['attempts']) > 1)

    # Stops as soon as something graded comes back.
    search = searcher([(None, [CMS_GEOFENCE])])
    out = v2.retrieve(plan, search)
    check('5g a first-attempt hit does not retry', len(search.calls), 1)


# ── 6: the wrong-corpus guard ──────────────────────────────────────────────

def test_scope_guard():
    plan = v2.plan_turn('how do I created a new geofence', surface='mobile')
    search = searcher([(None, [CMS_GEOFENCE])])
    out = v2.retrieve(plan, search)
    check('6a a CMS procedure is refused for a mobile how-to',
          out['chunks'], [])
    check('6b and the rejection is counted, not silent',
          len(out['rejected_for_scope']), 1)

    search = searcher([(None, [MOBILE_GEOFENCE])])
    out = v2.retrieve(plan, search)
    check('6c the mobile guide is accepted', len(out['chunks']), 1)

    # Same CMS document, asked from the console: perfectly good answer.
    plan = v2.plan_turn('how do I create a geofence', surface='console')
    search = searcher([(None, [CMS_GEOFENCE])])
    out = v2.retrieve(plan, search)
    check('6d and is accepted from the console, where it belongs',
          len(out['chunks']), 1)

    # A document with no stated scope is not a match either.
    plan = v2.plan_turn('how do I create a geofence', surface='mobile')
    search = searcher([(None, [dict(CMS_GEOFENCE, source='Field Notes',
                                    document_type='notes', category='zones',
                                    heading='Zones')])])
    out = v2.retrieve(plan, search)
    check('6e unknown scope is not treated as a match', out['chunks'], [])


# ── 6b: the same guard, on a live dispatcher result ────────────────────────

def test_filter_for_scope():
    result = {'found': True, 'count': 2, 'results': [CMS_GEOFENCE,
                                                     MOBILE_GEOFENCE]}
    out, dropped = v2.filter_for_scope(result, 'mobile')
    check('6f the wrong-app chunk is withheld from the model', dropped, 1)
    check('6g only the right one survives', out['results'], [MOBILE_GEOFENCE])
    check('6h and the count is corrected', out['count'], 1)

    out, dropped = v2.filter_for_scope(
        {'found': True, 'count': 1, 'results': [CMS_GEOFENCE]}, 'mobile')
    check('6i found becomes False when nothing survives', out['found'], False)
    truthy('6j and a note says why', out.get('notes'))
    truthy('6k with a reason the turn can quote', out.get('reason'))

    original = {'found': True, 'count': 1, 'results': [CMS_GEOFENCE]}
    out, dropped = v2.filter_for_scope(original, None)
    check('6l no scope requirement means no filtering', dropped, 0)
    check('6m and the result is passed through untouched', out, original)
    check('6n the original is never mutated in place',
          original['results'], [CMS_GEOFENCE])


# ── 7: verification ────────────────────────────────────────────────────────

def test_verify():
    plan = v2.plan_turn('how do I created a new geofence', surface='mobile')
    rejected = {'chunks': [], 'attempts': [], 'exhausted': True,
                'rejected_for_scope': [CMS_GEOFENCE]}
    issues = v2.verify('Open Administration then Geofences.', plan, rejected)
    truthy('7a a how-to with only wrong-app documents is rejected', issues)
    check('7b and the violation names the cause',
          'different application' in issues[0], True)

    # The distinction the first version of verify() got wrong: it rejected a
    # correct refusal, so the repair round could never succeed. Giving steps
    # without a document is the violation; declining to is the right answer.
    check('7a2 declining without a document is NOT a violation',
          v2.verify("The steps for this app aren't documented yet. I can "
                    'connect you with someone.', plan, rejected), [])
    truthy('7a3 but giving steps without one is',
           v2.verify('Go to Settings and tap Add.', plan, rejected))
    check('7a4 an explanation that gives no steps also passes',
          v2.verify('A geofence is a boundary that raises an alert.',
                    plan, rejected), [])

    ok = {'chunks': [MOBILE_GEOFENCE], 'attempts': [], 'exhausted': False,
          'rejected_for_scope': []}
    check('7c a scoped document passes',
          v2.verify('Tap Geofences, then New.', plan, ok), [])

    # Liveness.
    fleet = v2.plan_turn('Is UBF 364U online?', surface='console')
    none_found = {'chunks': [], 'attempts': [], 'exhausted': False,
                  'rejected_for_scope': []}
    issues = v2.verify('UBF 364U is online.', fleet, none_found,
                       tool_refs=['unit_status(UBF 364U)'])
    truthy('7d a liveness claim without a heartbeat read is rejected', issues)
    check('7e cleared when fleet_liveness ran',
          v2.verify('UBF 364U is online.', fleet, none_found,
                    tool_refs=['fleet_liveness(all)']), [])

    # Unsourced figures.
    account = v2.plan_turn('How many tokens do I have?', surface='mobile')
    issues = v2.verify('You have 120 units across 3 packs.', account,
                       none_found, context_numbers={120.0, 3.0})
    check('7f figures that trace to context pass', issues, [])
    issues = v2.verify('You have 999 units.', account, none_found,
                       context_numbers={120.0, 3.0})
    truthy('7g a figure in neither context nor a tool is rejected', issues)
    check('7h skipped when a live tool could be the source',
          v2.verify('You have 999 units.', account, none_found,
                    context_numbers={120.0},
                    tool_refs=['unit_find(all)']), [])

    check('7i an IMEI is an identifier, not a claimed figure',
          v2.claimed_numbers('IMEI 862846042593213 reported'), [])
    check('7j a date is not a claimed figure',
          v2.claimed_numbers('on 2026-09-18'), [])


# ── 8: the whole turn ──────────────────────────────────────────────────────

def test_run_turn():
    # fb-010. v1 retrieves the CMS procedure and can present it. v2 must not.
    search = searcher([(None, [CMS_GEOFENCE])])
    call = model('Open Administration then Geofences and click New.',
                 "The steps for the mobile app aren't documented yet. "
                 'I can connect you with someone who can help.')
    out = v2.run_turn('how do I created a new geofence', surface='mobile',
                      search=search, call_model=call)
    check('8a the CMS answer is not what goes out',
          'Administration' in out['reply'], False)
    check('8b one repair round was spent', out['repairs'], 1)
    check('8c the repaired answer passes', out['unresolved'], [])
    check('8d and the scope rejection is on the record',
          out['rejected_for_scope'], 1)

    # fb-003. Nothing on the question as asked; the stripped form finds it.
    search = searcher([('How are devices registered?', []),
                       (None, [dict(CMS_GEOFENCE, category='devices',
                                    text='Register a device in Admin.')])])
    call = model('Devices are registered in Admin.')
    out = v2.run_turn('How are devices registered?', surface='console',
                      search=search, call_model=call)
    check('8e recovery answered what v1 refused',
          out['reply'], 'Devices are registered in Admin.')
    check('8f after two attempts', len(out['retrieval_attempts']), 2)
    check('8g with no repair needed', out['repairs'], 0)

    # A repair that does not fix it is recorded, not hidden.
    search = searcher([(None, [CMS_GEOFENCE])])
    call = model('Open Administration then Geofences.')
    out = v2.run_turn('how do I create a geofence', surface='mobile',
                      search=search, call_model=call)
    truthy('8h an unfixed violation is reported', out['unresolved'])
    check('8i after exactly one repair attempt', out['repairs'], 1)

    # An account question does no document retrieval at all.
    search = searcher([(None, [CMS_GEOFENCE])])
    call = model('You have 120 units across 3 packs.')
    out = v2.run_turn('How many tokens do I have?', surface='mobile',
                      search=search, call_model=call,
                      context_numbers={120.0, 3.0})
    check('8j an account question does not search documents',
          len(search.calls), 0)
    check('8k and passes verification', out['unresolved'], [])
    check('8l the turn is stamped with its version',
          out['agent_version'], 'v2')


# ── 9: it must import on the Python the user actually runs ────────────────

def test_regex_portability():
    """Guard against the bug that shipped: an inline (?m) mid-pattern.

    Python 3.10 accepted a global flag anywhere in a pattern. 3.11 raises
    "global flags not at the start of the expression" -- at import time, so
    the whole application fails to start. The agent sandbox runs 3.10 and
    Agatha runs 3.11, so every test here passed while the module could not be
    imported on her machine.

    The flag belongs in the compile call. This checks the source rather than
    the behaviour, because by the time behaviour could be tested the import
    has already failed.
    """
    import ast
    import re as _re
    source = io.open(os.path.join(ROOT, 'endpoints', 'waswa_v2.py'),
                     encoding='utf-8').read()
    pattern = _re.compile(r'\(\?[aiLmsux]+\)')
    offenders = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Adjacent string literals are one Constant by here, so a flag
            # that looks first in its own fragment is caught in the join.
            offenders += [(node.lineno, m.group(0), m.start())
                          for m in pattern.finditer(node.value)
                          if m.start() != 0]
    check('9a no inline global flag away from position 0', offenders, [])

    # The branch that carried the bug, never asserted until now.
    truthy('9b numbered steps are recognised as steps',
           v2._GIVES_STEPS.search('To do it:\n1. Tap Geofences\n2. Tap New'))
    check('9c prose that gives no steps is not',
          bool(v2._GIVES_STEPS.search('A geofence is a boundary that alerts.')),
          False)
    check('9d and the multiline flag is on the compiled object',
          bool(v2._GIVES_STEPS.flags & __import__('re').M), True)


def main():
    for test in (test_scope, test_plan, test_reformulate, test_retrieve,
                 test_scope_guard, test_filter_for_scope, test_verify,
                 test_run_turn, test_regex_portability):
        test()
    print()
    for line in PASS:
        print('  ok   %s' % line)
    for line in FAIL:
        print('  FAIL %s' % line)
    print('\n  %d passed, %d failed\n' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
