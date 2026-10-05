#!/usr/bin/env python3
"""
waswa_audience.py — decide which documents a CUSTOMER may be answered from.

The corpus audit found all twelve sources approved and every one of them
audience='staff'. So staff get answers from 2,655 chunks and customers get
nothing — not because retrieval is broken, but because:

    041_waswa_training.sql:
        ALTER TABLE dll_waswa_sources
            ADD COLUMN audience VARCHAR(16) NOT NULL DEFAULT 'staff';

and ingest_waswa_knowledge.py --approve sets review_status and nothing else.
Two switches, and only one of them has a command.

This is that command. It changes who may be answered from a document, so it
shows what it will do and does nothing until you pass --apply.

What it will not do:
  * touch a level-5 document. Those are internal by nature (the view already
    excludes them via may_quote, so this is belt and braces, but the refusal is
    worth being explicit about: 'Operation WOW — Oil & Gas Clients Strategy
    Paper' read aloud to a customer is a leak even unquoted).
  * guess. Every source is named on the command line or by --all, and --all
    still lists what it is about to expose.

Judgement this tool cannot make for you: these documents were written for
staff. Opening the CMS User Manual to customers means Waswa may answer a
customer out of a staff manual — usually fine, occasionally not. Go document by
document the first time.

Usage:
    python scripts/waswa_audience.py                       # show the current state
    python scripts/waswa_audience.py --set token --apply   # one document
    python scripts/waswa_audience.py --set token --set oliwa --apply
    python scripts/waswa_audience.py --all --apply          # every level 1-4
    python scripts/waswa_audience.py --set cms --staff --apply   # put it back
"""

import argparse
import sys

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                        # noqa: E402

INTERNAL_LEVEL = 5


def listing(cur):
    cur.execute("""
        SELECT s.filename, s.title, s.authority_level, s.review_status,
               s.audience, s.chunk_count, a.may_quote
          FROM dll_waswa_sources s
          LEFT JOIN dll_waswa_authority_levels a
                 ON a.authority_level = s.authority_level
         WHERE s.superseded_by IS NULL
         ORDER BY s.authority_level, s.filename""")
    return cur.fetchall()


def show(rows):
    print(f'\n   {"L":<3}{"status":<10}{"audience":<10}{"chunks":>7}  document')
    for fn, title, level, status, audience, chunks, may_quote in rows:
        flag = ''
        if level >= INTERNAL_LEVEL:
            flag = '  [internal — never a customer]'
        elif may_quote is False:
            flag = '  [not quotable at this level]'
        print(f'   {level:<3}{str(status)[:9]:<10}{str(audience)[:9]:<10}'
              f'{chunks or 0:>7}  {str(title)[:44]}{flag}')

    public = sum((r[5] or 0) for r in rows if r[4] == 'everyone')
    staffed = sum((r[5] or 0) for r in rows if r[4] != 'everyone')
    print(f'\n   chunks a customer can be answered from : {public}')
    print(f'   chunks only staff can be answered from : {staffed}')
    if public == 0:
        print('\n   >> No customer can be answered from any document. Every')
        print('      knowledge question from the mobile app or the console will')
        print('      find nothing, however well the forcing works.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', action='append', default=[], metavar='FRAGMENT',
                    help='a distinctive part of the filename (repeatable)')
    ap.add_argument('--all', action='store_true',
                    help='every source below level 5')
    ap.add_argument('--staff', action='store_true',
                    help='set back to staff-only instead of everyone')
    ap.add_argument('--apply', action='store_true',
                    help='actually write the change')
    args = ap.parse_args()

    target_audience = 'staff' if args.staff else 'everyone'

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            rows = listing(cur)
            if not rows:
                print('No sources ingested.')
                return 1
            show(rows)

            if not args.set and not args.all:
                print('\n   Nothing selected. Use --set <fragment> or --all,')
                print('   then add --apply once the list below looks right.')
                return 0

            # Resolve the selection, refusing anything ambiguous rather than
            # picking one: changing the wrong document's audience is the exact
            # mistake worth being slow about.
            chosen = []
            if args.all:
                chosen = [r for r in rows if r[2] < INTERNAL_LEVEL]
            for fragment in args.set:
                hits = [r for r in rows if fragment.lower() in r[0].lower()]
                if not hits:
                    print(f'\n   !! nothing matches {fragment!r}')
                    return 1
                if len(hits) > 1:
                    print(f'\n   !! {fragment!r} matches {len(hits)} documents '
                          f'— be more specific:')
                    for r in hits:
                        print(f'      {r[0]}')
                    return 1
                chosen.append(hits[0])

            refused = [r for r in chosen if r[2] >= INTERNAL_LEVEL]
            chosen = [r for r in chosen if r[2] < INTERNAL_LEVEL]
            for r in refused:
                print(f'\n   refusing {r[1][:50]} — level {r[2]} is internal')

            chosen = [r for r in chosen if r[4] != target_audience]
            if not chosen:
                print(f'\n   Nothing to change; all selected documents are '
                      f'already {target_audience}.')
                return 0

            print(f'\n   Would set audience = {target_audience!r} on:')
            total = 0
            for r in chosen:
                print(f'     - L{r[2]}  {str(r[1])[:52]}  ({r[5] or 0} chunks)')
                total += r[5] or 0
            verb = ('become answerable to customers' if target_audience == 'everyone'
                    else 'stop being answerable to customers')
            print(f'\n   {total} chunks would {verb}.')

            if not args.apply:
                print('\n   Dry run. Add --apply to write it.')
                return 0

            for r in chosen:
                cur.execute(
                    "UPDATE dll_waswa_sources SET audience = %s, "
                    "       updated_at = NOW() "
                    " WHERE filename = %s AND superseded_by IS NULL",
                    (target_audience, r[0]))
            conn.commit()
            print(f'\n   done — {len(chosen)} document(s) updated.')
            print('   Ask Waswa a knowledge question as a CUSTOMER now, then:')
            print('     python scripts/waswa_audit.py --limit 4')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
