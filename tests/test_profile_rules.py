# -*- coding: utf-8 -*-
"""Tests for endpoints/profile_rules.py

profile_rules.py is pure, so it imports directly -- no Flask, no database.

Run:  python tests/test_profile_rules.py
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'endpoints'))

import profile_rules as pr                                # noqa: E402

RESULTS = []
TODAY = datetime.date(2026, 10, 12)


def eq(name, got, want):
    RESULTS.append((name, got == want, 'got %r, want %r' % (got, want)))


def refused(name, data, fragment):
    try:
        got = pr.changes_from(data, TODAY)
    except pr.ProfileError as error:
        RESULTS.append((name, fragment in str(error), 'message %r' % str(error)))
        return
    RESULTS.append((name, False, 'accepted: %r' % got))


# ── only what was sent ────────────────────────────────────────────────────
eq('date of birth alone (the old app)',
   pr.changes_from({'date_of_birth': '1990-05-01'}, TODAY),
   {'date_of_birth': datetime.date(1990, 5, 1)})
eq('empty date of birth clears it', pr.changes_from({'date_of_birth': ''}, TODAY),
   {'date_of_birth': None})
eq('name is tidied', pr.changes_from({'display_name': '  Jane   Achieng '}, TODAY),
   {'display_name': 'Jane Achieng'})
eq('email is lower-cased', pr.changes_from({'email': ' Jane@Example.COM '}, TODAY),
   {'email': 'jane@example.com'})
eq('unknown keys are ignored',
   pr.changes_from({'display_name': 'Jo', 'log_username': 'x', 'account_role': 'admin'},
                   TODAY),
   {'display_name': 'Jo'})
eq('only known columns ever come back',
   set(pr.changes_from({'display_name': 'Jo', 'email': 'a@b.co',
                        'date_of_birth': ''}, TODAY)) <= set(pr.COLUMNS), True)

# ── refused ───────────────────────────────────────────────────────────────
refused('nothing to update', {}, 'Nothing')
refused('only unknown keys', {'username': 'new'}, 'Nothing')
refused('not a dict', 'oops', 'Nothing')
refused('one-letter name', {'display_name': ' J '}, 'name')
refused('blank name', {'display_name': None}, 'name')
refused('overlong name', {'display_name': 'x' * 81}, 'name')
refused('bad email', {'email': 'jane.example.com'}, 'email')
refused('email with a space', {'email': 'jane @example.com'}, 'email')
refused('bad date', {'date_of_birth': '01/05/1990'}, 'YYYY-MM-DD')
refused('future birth date', {'date_of_birth': '2027-01-01'}, 'future')


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
