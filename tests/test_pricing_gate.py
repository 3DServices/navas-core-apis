#!/usr/bin/env python3
"""
test_pricing_gate.py -- what the pricing check in assistant.py lets through.

The check sends pricing questions to a canned reply before any model sees
them. It used to catch every mention of "discount", so a staff member asking
how discounts are approved -- which the Sales Procedures answer: no discount
without SMU/KCM approval -- got "I'm not able to quote prices". Staff may now
ask about the discount process; customers still get the canned reply for any
discount question, and nobody gets a price.

_is_pricing_enquiry and its pattern tables are compiled out of assistant.py,
as test_tool_forcing.py does, because importing the module needs the database.
"""

import ast
import io
import os
import re

_SOURCE = os.path.join(os.path.dirname(__file__), '..', 'endpoints', 'assistant.py')
_WANT_FUNCS = {'_is_pricing_enquiry'}
_WANT_CONSTS = {'_PRICING_PATTERNS', '_OWN_CHARGES_PATTERNS',
                '_DISCOUNT_POLICY_PATTERNS', '_PRICE_AMOUNT_PATTERNS'}


def _load():
    tree = ast.parse(io.open(_SOURCE, encoding='utf-8').read())
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _WANT_FUNCS:
            body.append(node)
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(n in _WANT_CONSTS for n in names):
                body.append(node)
    ns = {'re': re}
    exec(compile(ast.Module(body=body, type_ignores=[]), _SOURCE, 'exec'), ns)
    return ns['_is_pricing_enquiry']


is_pricing = _load()

DISCOUNT_PROCESS = (
    'What is the maximum discount a salesperson can give without approval?',
    'Who approves a discount?',
    'What is the discount approval process?',
    'What is the discount policy?',
)


def test_staff_may_ask_how_discounts_are_approved():
    for q in DISCOUNT_PROCESS:
        assert is_pricing(q, 'staff') is False, q


def test_customers_are_still_routed_to_sales_for_any_discount_question():
    for q in DISCOUNT_PROCESS + ('Can I get a discount?',):
        assert is_pricing(q, 'everyone') is True, q
        assert is_pricing(q) is True, q


def test_nobody_gets_a_price():
    for q in ('How much does a VEBA pack cost?',
              'What is the price of a tracking unit?',
              'Can you give me a quote for 50 devices?',
              'What discount price is approved for 50 units?',
              'Who approves the price list?'):
        assert is_pricing(q, 'staff') is True, q
        assert is_pricing(q, 'everyone') is True, q


def test_questions_about_your_own_charges_are_not_pricing():
    for q in ('Explain my charges', 'Why is my balance lower?'):
        assert is_pricing(q, 'everyone') is False, q


if __name__ == '__main__':
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            passed += 1
            print('  ok  ' + name)
    print(f'{passed}/{passed} passed')
