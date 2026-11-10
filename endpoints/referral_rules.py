"""
referral_rules -- Refer & Earn, checked before anything touches the database.

The rule: when a customer you referred makes their FIRST PAID top-up, you get
REWARD_HOURS of tracking. One reward per referred customer, ever.

  * codes are made here, never derived from an account uid, so they cannot
    be guessed and two companies never share one
  * a code is entered by the new customer after staff have opened their
    account (there is no self sign-up), and only before their first paid
    top-up -- after that the reward could never be earned
  * a company cannot refer itself, nor a company with the same email
  * at most MONTHLY_CAP rewards are paid per referrer per calendar month;
    the rest are held as 'qualified' for staff to pay or reject

It is pure, so tests/test_referral_rules.py runs without a server.
"""

import re
import secrets

REWARD_HOURS = 24
MONTHLY_CAP = 10
PREFIX = 'OLIWA-'
# No 0/O, 1/I/L: codes are read aloud and typed from SMS.
ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
CODE_LENGTH = 5
CODE = re.compile(r'^OLIWA-[%s]{%d}$' % (ALPHABET, CODE_LENGTH))

# pending    waiting for the referred customer's first paid top-up
# qualified  they paid, but the reward is held (cap reached, or no reward
#            token configured) until staff pay it
# rewarded   the hours are in the referrer's wallet
# rejected   staff turned it down
STATUSES = ('pending', 'qualified', 'rewarded', 'rejected')


class ReferralError(ValueError):
    pass


def make_code(choice=secrets.choice):
    return PREFIX + ''.join(choice(ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(text):
    """'oliwa 7kq4m', ' 7KQ4M ', 'OLIWA-7KQ4M' -> 'OLIWA-7KQ4M'.
    Raises ReferralError if it cannot be a code."""
    raw = re.sub(r'[\s\-_]', '', str(text or '').upper())
    if raw.startswith('OLIWA'):
        raw = raw[len('OLIWA'):]
    code = PREFIX + raw
    if not CODE.match(code):
        raise ReferralError('That is not a referral code. Codes look like OLIWA-7KQ4M.')
    return code


def claim_problem(referee, referrer, referee_email='', referrer_email='',
                  already_referred=False, has_paid_top_up=False):
    """Why `referee` may not use `referrer`'s code, or None when it may.
    `referrer` is None when no company has that code."""
    if referrer is None:
        return 'No account has that referral code. Check it and try again.'
    if already_referred:
        return 'Your account has already used a referral code.'
    if referrer == referee:
        return 'You cannot use your own referral code.'
    a = str(referee_email or '').strip().lower()
    b = str(referrer_email or '').strip().lower()
    if a and a == b:
        return 'You cannot use your own referral code.'
    if has_paid_top_up:
        return ('Referral codes must be entered before your first top-up, '
                'and your account has already topped up.')
    return None


def reward_decision(rewarded_this_month, reward_token_configured,
                    cap=MONTHLY_CAP):
    """('rewarded', None) to pay now, or ('qualified', reason) to hold."""
    if not reward_token_configured:
        return 'qualified', 'The referral reward token is not configured yet.'
    if rewarded_this_month >= cap:
        return 'qualified', 'Monthly referral reward limit reached; held for review.'
    return 'rewarded', None


def masked_name(name):
    """'Kato Logistics Ltd' -> 'Kato L.' -- enough for the referrer to know who
    joined, without showing a full company name to whoever holds a code."""
    words = str(name or '').split()
    if not words:
        return 'A friend'
    if len(words) == 1:
        return words[0][:20]
    return '%s %s.' % (words[0][:20], words[1][0].upper())


def summary(rows):
    """Counts and hours earned for the referrer's screen.
    rows: dicts with at least 'status'."""
    counts = {s: 0 for s in STATUSES}
    for row in rows:
        status = row.get('status')
        if status in counts:
            counts[status] += 1
    return {
        'joined': counts['pending'] + counts['qualified'] + counts['rewarded'],
        'pending': counts['pending'],
        'qualified': counts['qualified'],
        'rewarded': counts['rewarded'],
        'hours_earned': counts['rewarded'] * REWARD_HOURS,
    }


def share_text(code):
    return ('Track your vehicles with OLIWA. When your account is set up, '
            'open Refer & Earn in the app and enter my code %s before your '
            'first top-up.' % code)
