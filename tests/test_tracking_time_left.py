#!/usr/bin/env python3
"""
test_tracking_time_left.py -- how long the token balance lasts, in Waswa's words.

Waswa said it "can't predict when tokens run out" while the dashboard showed
"5 days". tracking_time_left gives the dashboard's figure (1 token = 1 hour,
floor(hours / 24) days), and under a day -- a customer who bought tokens for
a day -- hours and minutes. Compiled out of waswa_context.py, which needs the
database to import.
"""

import ast
import io
import os

_SOURCE = os.path.join(os.path.dirname(__file__), '..', 'endpoints',
                       'waswa_context.py')


def _load():
    tree = ast.parse(io.open(_SOURCE, encoding='utf-8').read())
    body = [n for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == 'tracking_time_left']
    assert body, 'waswa_context.py no longer defines tracking_time_left'
    ns = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), _SOURCE, 'exec'), ns)
    return ns['tracking_time_left']


left = _load()


def test_the_dashboard_figure_for_a_balance_of_days():
    out = left(120)
    assert out['days_left'] == 5           # the dashboard's "5 days"
    assert out['say'] == '5 days (120 hours)'
    assert out['hours_and_minutes_left'] == '120h 00m'


def test_a_day_pack_is_told_in_hours_and_minutes():
    out = left(7.5)
    assert out['days_left'] == 0
    assert out['say'] == '7 hours 30 minutes'
    assert out['hours_and_minutes_left'] == '7h 30m'
    assert left(23.75)['say'] == '23 hours 45 minutes'


def test_singular_words_and_the_edges():
    assert left(24)['say'] == '1 day (24 hours)'
    assert left(1)['say'] == '1 hour'
    assert left(1 / 60)['say'] == '1 minute'
    assert left(0)['say'] == '0 minutes'
    assert left(-3)['hours_left'] == 0       # never a negative balance
    assert left('not a number') is None


if __name__ == '__main__':
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            passed += 1
            print('  ok  ' + name)
    print(f'{passed}/{passed} passed')
