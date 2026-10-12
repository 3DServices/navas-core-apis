"""
profile_rules -- what PUT /users/<user_uid>/profile accepts, checked before
anything touches the database.

Editable: display_name, email and date_of_birth. Each is changed only when
its key is in the body, so a client that sends just a date of birth (the app
before this module) changes nothing else.

The username is not editable: it is what the account signs in with.

It is pure, so tests/test_profile_rules.py runs without a server.
"""

import datetime
import re

EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
NAME_MIN, NAME_MAX = 2, 80
EMAIL_MAX = 120

# The only columns update_profile may write; changes_from returns no others.
COLUMNS = ('display_name', 'email', 'date_of_birth')


class ProfileError(ValueError):
    pass


def changes_from(data, today=None):
    """{column: value} for the fields present in `data`. Raises ProfileError
    with a message the user can act on."""
    data = data if isinstance(data, dict) else {}
    today = today or datetime.date.today()
    out = {}

    if 'display_name' in data:
        name = ' '.join(str(data.get('display_name') or '').split())
        if not NAME_MIN <= len(name) <= NAME_MAX:
            raise ProfileError('Your name must be %d to %d characters.'
                               % (NAME_MIN, NAME_MAX))
        out['display_name'] = name

    if 'email' in data:
        email = str(data.get('email') or '').strip().lower()
        if len(email) > EMAIL_MAX or not EMAIL.match(email):
            raise ProfileError("That email address doesn't look right.")
        out['email'] = email

    if 'date_of_birth' in data:
        raw = str(data.get('date_of_birth') or '').strip()
        if not raw:
            out['date_of_birth'] = None
        else:
            try:
                born = datetime.datetime.strptime(raw, '%Y-%m-%d').date()
            except ValueError:
                raise ProfileError('date_of_birth must be YYYY-MM-DD')
            if born > today:
                raise ProfileError('Date of birth cannot be in the future.')
            out['date_of_birth'] = born

    if not out:
        raise ProfileError('Nothing to update.')
    return out
