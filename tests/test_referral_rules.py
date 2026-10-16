# -*- coding: utf-8 -*-
"""Tests for endpoints/referral_rules.py

referral_rules.py is pure, so it imports directly -- no Flask, no database.

Run:  python tests/test_referral_rules.py
"""

import itertools
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'endpoints'))

import referral_rules as rr                               # noqa: E402

RESULTS = []


def eq(name, got, want):
    RESULTS.append((name, got == want, 'got %r, want %r' % (got, want)))


def ok(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))


def bad_code(name, text):
    try:
        got = rr.normalize_code(text)
    except rr.ReferralError:
        RESULTS.append((name, True, ''))
        return
    RESULTS.append((name, False, 'accepted: %r' % got))


# ── codes ─────────────────────────────────────────────────────────────────
code = rr.make_code()
ok('made code has the shape', rr.CODE.match(code), code)
ok('made code avoids look-alikes', not set(code[len(rr.PREFIX):]) & set('0O1IL'), code)
cycle = itertools.cycle('AB')
eq('make_code uses the chooser', rr.make_code(lambda alphabet: next(cycle)), 'OLIWA-ABABA')

eq('canonical code', rr.normalize_code('OLIWA-7KQ4M'), 'OLIWA-7KQ4M')
eq('lower case with a space', rr.normalize_code('oliwa 7kq4m'), 'OLIWA-7KQ4M')
eq('without the prefix', rr.normalize_code(' 7kq4m '), 'OLIWA-7KQ4M')
bad_code('empty', '')
bad_code('too short', 'OLIWA-7KQ4')
bad_code('look-alike letter O', 'OLIWA-7KQ4O')
bad_code('old app code (4 chars)', 'OLIWA-AB12')

# ── who may claim ─────────────────────────────────────────────────────────
eq('fine', rr.claim_problem('c2', 'c1', 'b@x.com', 'a@x.com'), None)
ok('unknown code', 'No account' in rr.claim_problem('c2', None))
ok('own company', 'own' in rr.claim_problem('c1', 'c1'))
ok('same email, other company', 'own' in rr.claim_problem('c2', 'c1', 'A@x.com ', 'a@x.com'))
eq('blank emails are not a match', rr.claim_problem('c2', 'c1', '', ''), None)
ok('already referred', 'already' in rr.claim_problem('c2', 'c1', already_referred=True))
ok('already topped up', 'before your first top-up'
   in rr.claim_problem('c2', 'c1', has_paid_top_up=True))

# ── paying the reward ─────────────────────────────────────────────────────
eq('pay when configured and under the cap', rr.reward_decision(0, True), ('rewarded', None))
eq('hold when no reward token', rr.reward_decision(0, False)[0], 'qualified')
eq('hold at the cap', rr.reward_decision(rr.MONTHLY_CAP, True)[0], 'qualified')
eq('one under the cap pays', rr.reward_decision(rr.MONTHLY_CAP - 1, True)[0], 'rewarded')

# ── what the referrer sees ────────────────────────────────────────────────
eq('two words', rr.masked_name('Kato Logistics Ltd'), 'Kato L.')
eq('one word', rr.masked_name('Nakato'), 'Nakato')
eq('no name', rr.masked_name('  '), 'A friend')
eq('summary', rr.summary([{'status': 'pending'}, {'status': 'rewarded'},
                          {'status': 'rewarded'}, {'status': 'qualified'},
                          {'status': 'rejected'}]),
   {'joined': 4, 'pending': 1, 'qualified': 1, 'rewarded': 2,
    'hours_earned': 2 * rr.REWARD_HOURS})
eq('empty summary', rr.summary([])['hours_earned'], 0)
ok('share text carries the code', 'OLIWA-7KQ4M' in rr.share_text('OLIWA-7KQ4M'))


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, passed, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if passed else 'FAIL', name,
                            '' if passed else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
