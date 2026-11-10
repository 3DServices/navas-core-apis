#!/usr/bin/env python3
"""
test_product_search_words.py -- the loose product search's word handling.

"My drivers waste a lot of fuel" was searched as service type "Fuel
Telematics", matched nothing in the catalogue, and Waswa told a customer there
was no fuel product. product_search now retries on the individual words; these
check which words it uses and the SQL it builds. No database needed:
search_words and loose_match_sql are compiled out of waswa_products.py.
"""

import ast
import io
import os
import re

_SOURCE = os.path.join(os.path.dirname(__file__), '..', 'endpoints',
                       'waswa_products.py')
_WANT_FUNCS = {'search_words', 'loose_match_sql'}
_WANT_CONSTS = {'_SEARCH_STOPWORDS', '_LOOSE_HAYSTACK', '_PROBLEM_WORDS'}


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
    return ns['search_words'], ns['loose_match_sql']


search_words, loose_match_sql = _load()


def test_the_problem_words_survive_and_the_filler_does_not():
    words = search_words('My drivers waste a lot of fuel', None,
                         'Fuel Telematics', None)
    assert words[:3] == ['driver', 'waste', 'fuel'], words


def test_a_problem_also_searches_for_what_remedies_it():
    words = search_words('Some of my vehicles keep getting stolen')
    assert words[:2] == ['vehicle', 'stolen'], words
    for remedy in ('security', 'alarm', 'immobil', 'recovery', 'camera'):
        assert remedy in words, (remedy, words)


def test_plurals_are_folded_but_short_words_and_ss_are_left():
    assert search_words('vehicles generators gas class') == [
        'vehicle', 'generator', 'gas', 'class']


def test_nothing_distinctive_means_no_loose_search():
    assert search_words('what can help my tracking', None) == []


def test_the_sql_counts_one_point_per_word_with_placeholders_only():
    score, params = loose_match_sql(['fuel', 'driver'])
    assert score.count('::int') == 2
    assert params == ['%fuel%', '%fuel%', '%driver%', '%driver%']
    # Words reach the query only as parameters, never in the SQL text.
    assert 'fuel' not in score and 'driver' not in score


if __name__ == '__main__':
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            passed += 1
            print('  ok  ' + name)
    print(f'{passed}/{passed} passed')
