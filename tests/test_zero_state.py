#!/usr/bin/env python3
"""
test_zero_state.py -- the fb-011 / fb-012 fix.

A customer with two payments recorded against their account, and no token
packs, asked how many tokens they had on 29 September, 1 October and 2
October. Each time Waswa answered "your account doesn't have any token packs
yet" and stopped. Correct, and useless: the reason sat one context slot away.

What these tests hold the note to:

  * it fires when the account holds nothing, and not when it holds something
  * it says payments are on record when they are, with their labels
  * it NEVER interprets a payment status, promises a timeframe, or says a
    payment will complete -- "pending" is the business's word to define
  * it never introduces price language
  * an unresolved slot is not an empty one

No database and no model: the context dict is the input.

Run:
    python tests/test_zero_state.py
"""

import os
import re
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if 'endpoints' not in sys.modules:
    pkg = types.ModuleType('endpoints')
    pkg.__path__ = [os.path.join(ROOT, 'endpoints')]
    sys.modules['endpoints'] = pkg

PASS, FAIL = [], []


def check(name, got, want):
    (PASS if got == want else FAIL).append(
        name if got == want else '%s\n      got  %r\n      want %r'
        % (name, got, want))


def truthy(name, got):
    check(name, bool(got), True)


FULL = {
    'token_balance_and_burn_rate': {'token_packs': 234, 'token_units_left': 120.0},
    'asset_count_and_types': {'subscribed_units': 4},
    'active_products': [{'product_name': 'ivms'}],
    'open_incidents': {'unread_alerts_30d': 0},
}

EMPTY_WITH_PAYMENTS = {
    'token_balance_and_burn_rate': {'token_packs': 0},
    'asset_count_and_types': {'subscribed_units': 0},
    'active_products': 'none (no token packs yet)',
    'open_incidents': {'unread_alerts_30d': 0},
    'payment_standing': {
        'payments_recorded': 2,
        'by_status': {'pending': 2},
        'recent_payments': [
            {'date': '2026-09-18', 'status': 'pending', 'currency': 'UGX'},
            {'date': '2026-09-11', 'status': 'pending', 'currency': 'UGX'},
        ],
    },
}

EMPTY_NO_PAYMENTS = {
    'token_balance_and_burn_rate': {'token_packs': 0},
    'asset_count_and_types': {'subscribed_units': 0},
}


def run():
    import endpoints.assistant as a

    # ---- 1. fires only when something is actually empty -------------------
    check('1a an account that holds things gets no note',
          a._zero_state_note({'known': FULL}), None)
    truthy('1b an empty account gets one',
           a._zero_state_note({'known': EMPTY_WITH_PAYMENTS}))
    check('1c a slot that did not resolve is not an empty one',
          a._zero_state_note({'known': {}, 'unknown': {
              'token_balance_and_burn_rate': 'lookup failed'}}), None)
    check('1d zero open incidents alone is good news, not a dead end',
          a._zero_state_note({'known': {'open_incidents':
                                        {'unread_alerts_30d': 0}}}), None)

    # ---- 2. the payments case --------------------------------------------
    note = a._zero_state_note({'known': EMPTY_WITH_PAYMENTS})
    truthy('2a it names the empty slots', 'token_balance_and_burn_rate' in note)
    truthy('2b it says payments are on record', 'on record' in note.lower())
    truthy('2c it carries the dates', '2026-09-18' in note and '2026-09-11' in note)
    truthy('2d it carries the status label', 'pending' in note)
    truthy('2e it still forbids softening the zero',
           'must not soften' in note.lower() or 'not soften' in note.lower())
    truthy('2f and offers a handoff', 'in touch' in note.lower())

    # ---- 3. what it must never do ----------------------------------------
    low = note.lower()
    truthy('3a it forbids interpreting a status',
           'do not say what a status means' in low)
    truthy('3b it forbids promising a timeframe', 'timeframe' in low)
    truthy('3c it forbids predicting completion',
           'will or will not complete' in low)
    check('3d no price or cost language anywhere in the note',
          bool(re.search(r'\b(price|cost|fee|tariff|charge|discount|quote)\b',
                         low)), False)
    check('3e no currency amounts are passed through',
          bool(re.search(r'\b(ugx|kes|usd)\b', low)), False)

    # ---- 4. the no-payments case -----------------------------------------
    bare = a._zero_state_note({'known': EMPTY_NO_PAYMENTS})
    truthy('4a it says there are no payments either',
           'no payments are on record' in bare.lower())
    truthy('4b it offers who can help', 'who can help' in bare.lower())
    truthy('4c and explicitly bans quoting a price',
           'never quote a price' in bare.lower())

    # ---- 5. the shape detector -------------------------------------------
    for label, value, want in [
            ('all-zero dict', {'token_packs': 0}, True),
            ('non-zero dict', {'token_packs': 234}, False),
            ('mixed dict', {'a': 0, 'b': 3}, False),
            ('"none ..." string', 'none (no token packs yet)', True),
            ('empty list', [], True),
            ('populated list', [{'x': 1}], False),
            ('text-only dict', {'note': 'x'}, False),
            ('missing', None, False)]:
        check('5 %-18s -> %s' % (label, want), a._holds_nothing(value), want)


def main():
    try:
        run()
    except Exception as error:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        FAIL.append('SUITE CRASHED: %s' % error)
    for name in PASS:
        print('  ok   %s' % name)
    for name in FAIL:
        print('  FAIL %s' % name)
    print('')
    print('  %d passed, %d failed' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
