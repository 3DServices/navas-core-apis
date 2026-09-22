"""
token_values.py — read the text-typed billing columns safely.

dll_user_token_accounts stores everything as text, and the billing code writes
English sentences into value columns instead of leaving them empty:

    token_hours_left / token_hours_used  'column deprecated use token_units_left column'
    token_units_left / token_used_units  'units_unfined_waiting_for_first_use'

float() on either of those raises, which is why several statistics endpoints
return 500, and catching the error and returning 0 is worse — it reports a
balance the account does not have. This module names the three cases apart so
callers can say which one they are looking at.

A note on units: billing_unit may be hour, unit, event, km, mb, image, command,
report, period or inference. A "unit" is therefore NOT a synonym for an hour,
and code that needs hours must check the token's billing_unit rather than
reading token_units_left and assuming.
"""

import re

# What the billing code writes instead of a number.
AWAITING_FIRST_USE = 'units_unfined_waiting_for_first_use'

_NUMBER = re.compile(r'^-?[0-9][0-9,]*(\.[0-9]+)?$')
_AWAITING = re.compile(r'unfined|undefined|waiting_for_first_use', re.I)
_DEPRECATED = re.compile(r'deprecated', re.I)

# The states a value can be in.
NUMBER = 'number'
AWAITING = 'awaiting_first_use'
DEPRECATED = 'deprecated_column'
EMPTY = 'empty'
UNREADABLE = 'unreadable'


def read(value):
    """Return (number_or_None, state).

    state is one of NUMBER, AWAITING, DEPRECATED, EMPTY, UNREADABLE. Only
    NUMBER comes with a figure; every other state returns None, never 0.
    """
    if value is None:
        return None, EMPTY
    text = str(value).strip()
    if not text:
        return None, EMPTY
    if _NUMBER.match(text):
        try:
            return float(text.replace(',', '')), NUMBER
        except ValueError:
            return None, UNREADABLE
    if _DEPRECATED.search(text):
        return None, DEPRECATED
    if _AWAITING.search(text):
        return None, AWAITING
    return None, UNREADABLE


def number_or(value, default=0):
    """The number, or [default] when there isn't one.

    For callers that must return a number to keep a response shape stable.
    Pair it with state() so the response can also say why the number is a
    fallback — a bare 0 asserts a balance that may not exist.
    """
    parsed, _ = read(value)
    return default if parsed is None else parsed


def state(value):
    """Just the state, for adding a sibling field to an existing response."""
    return read(value)[1]


def describe(state_name):
    """One line a person can read, for admin surfaces and logs."""
    return {
        NUMBER: 'a value was read',
        AWAITING: 'not set until the token pack is first used',
        DEPRECATED: 'this column is deprecated and holds a notice, not a value',
        EMPTY: 'no value stored',
        UNREADABLE: 'the stored value is not a number',
    }.get(state_name, state_name)
