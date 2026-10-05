#!/usr/bin/env python3
"""
waswa_corpus_audit.py — what Waswa actually knows, and what it is missing.

Waswa draws on two separate stores, and conflating them hides gaps:

  * the DOCUMENT corpus  — dll_waswa_sources / dll_waswa_chunks, reached by
    knowledge_search. Prose: procedures, manuals, strategy, user stories.
  * the PRODUCT catalogue — abi_products_manager and its satellites, reached by
    product_lookup / product_search / product_compare / compatibility_check.
    This is where PPMM lives. It is structured rows, not searchable prose, so
    knowledge_search will never find a product here and product_search will
    never find a procedure there.

A question Waswa answers badly is usually not a prompt failure. It is a
question whose answer is in neither store. This prints both, then probes the
specific questions that have actually been asked, so a gap is named rather than
guessed at.

Read-only.

Usage:
    python scripts/waswa_corpus_audit.py
    python scripts/waswa_corpus_audit.py --probe "fuel monitoring" --probe VEBA
"""

import argparse
import sys

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                        # noqa: E402

PRODUCT_TABLES = (
    ('abi_products_manager', 'the PPMM product register'),
    ('abi_product_aliases', 'the names customers actually use'),
    ('abi_product_capabilities', 'what each product can do'),
    ('abi_product_hardware', 'devices per product'),
    ('abi_product_segments', 'who each product is for'),
    ('abi_official_products', 'the official ID list'),
    ('abi_catalog_objects', 'the NAVAS catalogue'),
)

# Questions that have really been asked of Waswa, plus the ones a selling
# assistant must handle. Each is (label, search terms).
PROBES = (
    ('how tokens work', ('token class', 'billing unit', 'token pack')),
    ('how to buy tokens', ('buy token', 'purchase token', 'top up', 'top-up')),
    ('contact support', ('help desk', 'helpdesk', 'support email',
                         'support line', 'hotline', 'contact us')),
    ('who signs off an installation', ('sign off', 'sign-off', 'acceptance',
                                       'commissioning')),
    ('what a product does, for a customer', ('product description',
                                             'key benefit', 'features and')),
    ('upsell / cross-sell guidance', ('upsell', 'up-sell', 'cross-sell',
                                      'cross sell', 'renewal', 'upgrade path')),
    ('service levels / response times', ('service level', 'response time',
                                         'turnaround', 'SLA')),
    ('coverage / where we operate', ('coverage', 'Uganda and Kenya',
                                     'countries we')),
)


def count(cur, sql, args=()):
    try:
        cur.execute(sql, args)
        row = cur.fetchone()
        return row[0] if row else 0
    except Exception as exc:                        # noqa: BLE001
        cur.connection.rollback()
        return f'!! {str(exc).splitlines()[0][:60]}'


def documents(cur):
    print('\n== The document corpus (knowledge_search) ' + '=' * 34)
    try:
        cur.execute("""
            SELECT s.title, s.document_type, s.authority_level, s.category,
                   s.chunk_count, COUNT(c.chunk_uid),
                   s.review_status, s.audience
              FROM dll_waswa_sources s
              LEFT JOIN dll_waswa_chunks c ON c.source_uid = s.source_uid
             GROUP BY s.title, s.document_type, s.authority_level, s.category,
                      s.chunk_count, s.review_status, s.audience
             ORDER BY s.authority_level, s.title""")
        rows = cur.fetchall()
    except Exception as exc:                        # noqa: BLE001
        cur.connection.rollback()
        print(f'   !! {str(exc).splitlines()[0][:90]}')
        return []

    print(f'   {"L":<3}{"status":<10}{"audience":<10}{"chunks":>7}  title')
    blocked = []
    for title, dtype, level, cat, declared, actual, status, audience in rows:
        print(f'   {level:<3}{str(status)[:9]:<10}{str(audience)[:9]:<10}'
              f'{actual:>7}  {str(title)[:46]}')
        if declared and actual != declared:
            print(f'       !! manifest said {declared} chunks, {actual} present')
        if status != 'approved':
            blocked.append((title, f'not approved ({status})'))
        elif audience != 'everyone' and level <= 4:
            blocked.append((title, 'approved but staff-only'))

    if blocked:
        print('\n   Unreachable by a customer, and why:')
        for title, why in blocked:
            print(f'     - {str(title)[:56]:<58} {why}')
        print('\n   These are loaded. They are not missing. They are gated.')

    # Level 5 is internal-only; it inflates the corpus without being usable in
    # an answer, so it is worth separating.
    quotable = count(cur, """
        SELECT COUNT(*) FROM dll_waswa_chunks
         WHERE authority_level IN (SELECT authority_level
                                     FROM dll_waswa_authority_levels
                                    WHERE may_quote = TRUE)""")
    print(f'\n   chunks Waswa may quote to anyone : {quotable}')
    print(f'   chunks in total                  : '
          f'{count(cur, "SELECT COUNT(*) FROM dll_waswa_chunks")}')

    kinds = {str(r[1] or '').lower() for r in rows}
    cats = {str(r[3] or '').lower() for r in rows}
    marketing = {'brochure', 'website', 'marketing', 'datasheet', 'flyer',
                 'price_list', 'faq', 'sales_collateral'}
    if not (kinds | cats) & marketing:
        print('\n   >> NO customer-facing marketing material is loaded. No')
        print('      brochure, no website content, no product datasheet, no')
        print('      FAQ, no contact sheet. Everything here is a procedure, a')
        print('      manual, a strategy paper or a backlog of user stories —')
        print('      written for staff and for building the system, not for')
        print('      answering a customer or selling to one.')
    return rows


def products(cur):
    print('\n== The PPMM product catalogue (product_search) ' + '=' * 29)
    for table, what in PRODUCT_TABLES:
        n = count(cur, f'SELECT COUNT(*) FROM {table}')
        print(f'   {table:<28} {str(n):>8}   {what}')

    # A product with no alias cannot be found by the name a customer types; one
    # with no capability row cannot answer "does it do X".
    print()
    for label, sql in (
        ('products with no alias',
         "SELECT COUNT(*) FROM abi_products_manager p WHERE NOT EXISTS ("
         "SELECT 1 FROM abi_product_aliases a WHERE a.product_uid = p.product_uid)"),
        ('products with no capability row',
         "SELECT COUNT(*) FROM abi_products_manager p WHERE NOT EXISTS ("
         "SELECT 1 FROM abi_product_capabilities c "
         "WHERE c.product_uid = p.product_uid)"),
        ('products with no segment row',
         "SELECT COUNT(*) FROM abi_products_manager p WHERE NOT EXISTS ("
         "SELECT 1 FROM abi_product_segments s "
         "WHERE s.product_uid = p.product_uid)"),
    ):
        print(f'   {label:<34} {count(cur, sql)}')
    print('\n   A product with no alias is invisible to a customer who types')
    print('   its everyday name; with no capability row, "can it do X" has no')
    print('   answer to give.')


def probe(cur, label, terms):
    """Could anything in either store answer this?"""
    where = ' OR '.join(['body ILIKE %s'] * len(terms))
    doc_hits = count(cur, f'SELECT COUNT(*) FROM dll_waswa_chunks WHERE {where}',
                     [f'%{t}%' for t in terms])
    prod_hits = 0
    for col, table in (('product_name', 'abi_products_manager'),
                       ('alias', 'abi_product_aliases'),
                       ('capability', 'abi_product_capabilities')):
        got = count(cur, f'SELECT COUNT(*) FROM {table} WHERE ' +
                    ' OR '.join([f'{col}::text ILIKE %s'] * len(terms)),
                    [f'%{t}%' for t in terms])
        if isinstance(got, int):
            prod_hits += got

    total = (doc_hits if isinstance(doc_hits, int) else 0) + prod_hits
    mark = 'ok  ' if total else 'GAP '
    print(f'   {mark} {label:<38} docs={doc_hits:<6} catalogue={prod_hits}')
    return bool(total)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe', action='append', default=[],
                    help='extra term to test for coverage (repeatable)')
    args = ap.parse_args()

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            documents(cur)
            products(cur)

            print('\n== Could Waswa answer these at all? ' + '=' * 39)
            gaps = []
            for label, terms in PROBES:
                if not probe(cur, label, terms):
                    gaps.append(label)
            for term in args.probe:
                if not probe(cur, f'(yours) {term}', (term,)):
                    gaps.append(term)

            print()
            if gaps:
                print(f'   {len(gaps)} question(s) have no source in either store:')
                for g in gaps:
                    print(f'     - {g}')
                print('\n   For these, no prompt change and no amount of forcing')
                print('   will help. The tool will run, find nothing, and Waswa')
                print('   will either say so or fill the gap itself. Loading the')
                print('   content is the only fix.')
            else:
                print('   Every probe found something. Where answers are still')
                print('   wrong, the fault is retrieval or prompt, not coverage.')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
