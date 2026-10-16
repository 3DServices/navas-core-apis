#!/usr/bin/env python3
"""
test_waswa_ivms_lookup.py -- "What is the Ivms Product?" must reach iVMS.

Waswa answered that question about "Ivms Sdk" and said it could not describe
it, while the approved CMS User Manual covers iVMS at length. Two things went
wrong, both checked here:

  1. product_lookup("Ivms Product") fuzzy-matched "ivms sdk" (0.60) because the
     filler word dragged the real name "ivms" (0.50) under the cutoff. Filler
     words are now dropped before guessing by spelling.
  2. knowledge_search("ivms", product="Ivms") narrowed to chunks filed under
     that product -- and no iVMS chunk is filed under one -- so it found
     nothing. A product filter that empties the search is now widened once.

The real functions are compiled out of the endpoint modules and run against
fakes. No database, no Flask.
"""

import ast
import difflib
import io
import os
import re

_HERE = os.path.dirname(__file__)
_PRODUCTS = os.path.join(_HERE, '..', 'endpoints', 'waswa_products.py')
_KNOWLEDGE = os.path.join(_HERE, '..', 'endpoints', 'waswa_knowledge.py')


def _compile(source, funcs, consts, ns):
    tree = ast.parse(io.open(source, encoding='utf-8').read())
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in funcs:
            body.append(node)
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(n in consts for n in names):
                body.append(node)
    exec(compile(ast.Module(body=body, type_ignores=[]), source, 'exec'), ns)
    return ns


class _Psycopg2:
    class Error(Exception):
        pass


class _Conn:
    """A connection whose cursor answers the knowledge_search product query."""

    def __init__(self, cursor=None):
        self._cursor = cursor or _Cursor()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self._cursor

    def close(self):
        pass


class _Cursor:
    rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return ('u-ivms',)


# ── product_lookup ──────────────────────────────────────────────────────────

# The live catalogue's three IVMS rows, plus one name for near-spelling.
_CATALOGUE = {'ivms': ['u-ivms'], 'ivms+': ['u-ivms-plus'],
              'ivms sdk': ['u-ivms-sdk'], 'oliwa': ['u-oliwa']}
_NAMES = {uid[0]: name for name, uid in _CATALOGUE.items()}


def _products_ns():
    ns = {
        'difflib': difflib, 're': re, 'psycopg2': _Psycopg2,
        '_connect': _Conn,
        '_all_names': lambda cur: _CATALOGUE,
        '_preferred': lambda cur, uids: (uids[0], []),
        '_fetch_by_uid': lambda cur, uid: {
            'product_uid': uid, 'product_name': _NAMES[uid],
            'product_code': '3D-PRD-008', 'service_type': 'Vehicle Telematics',
            'attributes_loaded': False},
        '_capabilities': lambda cur, uid: [],
        '_hardware': lambda cur, uid: [],
        '_segments': lambda cur, uid: [],
    }
    return _compile(_PRODUCTS, {'product_lookup', '_key'},
                    {'_FUZZY_CUTOFF', '_MAX_CANDIDATES', '_SEARCH_STOPWORDS'}, ns)


product_lookup = _products_ns()['product_lookup']


def _uid(name):
    result = product_lookup(name)
    assert result['found'], result
    return result['product']['product_uid']


def test_ivms_product_is_ivms_not_the_sdk():
    assert _uid('Ivms Product') == 'u-ivms'


def test_filler_words_anywhere_are_ignored():
    assert _uid('the ivms product') == 'u-ivms'
    assert _uid('IVMS service') == 'u-ivms'


def test_the_real_names_still_match_exactly():
    assert _uid('ivms') == 'u-ivms'
    assert _uid('Ivms Sdk') == 'u-ivms-sdk'
    assert _uid('ivms+') == 'u-ivms-plus'


def test_near_spelling_still_resolves():
    result = product_lookup('olwa')
    assert result['found'] and result['matched_via'] == 'fuzzy', result
    assert result['product']['product_uid'] == 'u-oliwa'


def test_missing_detail_sends_waswa_to_the_documents():
    notes = ' '.join(product_lookup('Ivms Product').get('notes', []))
    assert 'knowledge_search' in notes, notes


# ── knowledge_search ────────────────────────────────────────────────────────

def _knowledge_ns(searches):
    """searches records each _search call's filters; rows come back only when
    no product filter is applied, like the real iVMS chunks."""

    def fake_search(cur, query, filters, limit, include_unapproved, audience):
        searches.append(dict(filters))
        if filters.get('product_uid'):
            return [], 'phrase'
        return [('chunk-1',)], 'phrase'

    ns = {
        're': re, 'psycopg2': _Psycopg2,
        '_connect': _Conn,
        '_search': fake_search,
        '_corpus_state': lambda cur, audience='everyone': (49, 49, 49),
        '_row': lambda record: {
            'text': 'Vehicle Telematics (OLIWA, iVMS, iVMS-PLUS) ...',
            'authority_level': 2, 'source': 'NAVAS CMS User Manual'},
    }
    return _compile(_KNOWLEDGE, {'knowledge_search'},
                    {'_DEFAULT_LIMIT', '_MAX_LIMIT', '_MAX_TOTAL_CHARS'}, ns)


def test_a_product_filter_that_finds_nothing_is_widened():
    searches = []
    knowledge_search = _knowledge_ns(searches)['knowledge_search']
    result = knowledge_search('ivms', product='Ivms')
    assert result['found'] and result['count'] == 1, result
    assert searches[0].get('product_uid') == 'u-ivms'
    assert not searches[-1].get('product_uid'), searches
    assert any("no document is filed under 'Ivms'" in n
               for n in result['notes']), result['notes']


def test_without_a_product_there_is_one_search():
    searches = []
    knowledge_search = _knowledge_ns(searches)['knowledge_search']
    assert knowledge_search('ivms')['found']
    assert len(searches) == 1, searches


if __name__ == '__main__':
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            passed += 1
            print('  ok  ' + name)
    print(f'{passed}/{passed} passed')
