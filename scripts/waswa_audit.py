#!/usr/bin/env python3
"""
waswa_audit.py — why Waswa's last answers were wrong, from the trail it already keeps.

Every Waswa turn already records the evidence it was built from, into
dll_waswa_evidence. Nobody has read it. That table is the difference between
"Waswa is inaccurate" and a list of specific, separately-fixable faults,
because an inaccurate answer is always one of exactly three things:

  1. NO TOOL CALLED   — the model answered from its own general knowledge
                        while a tool could have answered from the account's
                        real data. This is the one that produces confident,
                        plausible, wrong answers.
  2. TOOL FOUND NOTHING — a tool ran and came back empty, so the model either
                        apologised or filled the gap itself. The query is
                        usually at fault, not the data.
  3. DATA WAS THERE   — tools ran and returned figures, and the answer is
                        still wrong. Only then is it a prompt problem.

Fixing 3 before checking 1 is how weeks get spent on prompt wording while the
real fault is an empty knowledge base.

This script is read-only. It writes nothing and costs nothing.

Usage:
    python scripts/waswa_audit.py                 # last 25 answers
    python scripts/waswa_audit.py --limit 60
    python scripts/waswa_audit.py --client CLIENT_UID
    python scripts/waswa_audit.py --full          # show the whole answer text
"""

import argparse
import re
import sys
from collections import Counter

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                        # noqa: E402

# Evidence kinds that are present on EVERY turn and therefore prove nothing
# about whether Waswa looked anything up.
_FREE = {'account_context'}

# Phrases that mean the model knew it was empty-handed. An answer that says
# this is honest; an answer that does NOT say it while no tool ran is the
# dangerous case.
_ADMITS = re.compile(
    r"could not|couldn'?t|unable to|no data|don'?t have|do not have|"
    r"not sure|no record|nothing on file|can'?t see|cannot see|"
    r"which (vehicle|unit|one)|please confirm",
    re.I)

# Figures that come from the standing account block (waswa_context) rather than
# from the model's imagination: token packs, payment standing, unit counts.
# An answer stating these without a tool call is reading injected context, not
# inventing — a different fault with a different fix.
_ACCOUNT_FACT = re.compile(
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*"
    r"(\w+\s+){0,2}"          # "five recorded payments", "3 subscribed units"
    r"(token|unit|pack|payment|vehicle|device)s?\b"
    r"|\b(no|zero|0)\s+(token|unit|pack|subscribed|active)"
    r"|\bpack(s)? (that )?haven'?t been activated"
    r"|\brecorded as pending|\bpayments? recorded"
    r"|\bdoesn'?t have any (token|subscribed|active)",
    re.I)



def _timestamp_column(cur):
    """dll_waswa_messages may or may not carry a created_at; find out rather
    than assume, so this script works against either schema."""
    cur.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'dll_waswa_messages'
           AND data_type LIKE 'timestamp%'
         ORDER BY CASE column_name
                    WHEN 'created_at' THEN 0 WHEN 'created' THEN 1 ELSE 2 END
         LIMIT 1""")
    row = cur.fetchone()
    return row[0] if row else None


def _count(cur, sql, args=()):
    try:
        cur.execute(sql, args)
        return cur.fetchone()[0]
    except Exception as exc:                        # noqa: BLE001
        cur.connection.rollback()
        return f'!! {str(exc).splitlines()[0][:70]}'


def knowledge_health(cur):
    """What Waswa has to be accurate FROM. An empty base here guarantees that
    every product, policy or billing question is answered by the model's
    imagination, however good the prompt is."""
    print('\n== What Waswa has to draw on ' + '=' * 48)
    rows = [
        ('knowledge chunks (searchable text)',
         "SELECT COUNT(*) FROM dll_waswa_chunks"),
        # The two gates retrieval really applies. `active` is not one of them,
        # and reporting it made an invisible corpus look healthy.
        ('  of those, APPROVED (else unsearchable)',
         "SELECT COUNT(*) FROM vw_waswa_retrievable "
         "WHERE review_status = 'approved'"),
        ('  of those, visible to CUSTOMERS',
         "SELECT COUNT(*) FROM vw_waswa_retrievable "
         "WHERE review_status = 'approved' AND audience = 'everyone'"),
        ('  staff-only (audience = staff)',
         "SELECT COUNT(*) FROM vw_waswa_retrievable WHERE audience = 'staff'"),
        ('knowledge sources registered',
         "SELECT COUNT(*) FROM dll_waswa_sources"),
        ('verified answers (staff corrections)',
         "SELECT COUNT(*) FROM dll_waswa_answers"),
        ('  of those, approved and live',
         "SELECT COUNT(*) FROM dll_waswa_answers WHERE status = 'approved'"),
        ('open feedback awaiting correction',
         "SELECT COUNT(*) FROM dll_waswa_feedback WHERE status = 'open'"),
    ]
    for label, sql in rows:
        print(f'   {label:<44} {_count(cur, sql)}')

    chunks = _count(cur, "SELECT COUNT(*) FROM dll_waswa_chunks")
    if isinstance(chunks, int) and chunks == 0:
        print('\n   >> The knowledge base is EMPTY. Every question that is not')
        print('      about a vehicle is currently answered from gpt-4o\'s own')
        print('      training, which knows nothing about NAVAS or OLIWA.')
        print('      Run: python scripts/ingest_waswa_knowledge.py')
        return

    # Loaded is not reachable. review_status defaults to 'pending' and audience
    # to 'staff', and --approve changes only the first — which is exactly how a
    # corpus answers staff and tells customers it has nothing.
    approved = _count(cur, "SELECT COUNT(*) FROM vw_waswa_retrievable "
                           "WHERE review_status = 'approved'")
    public = _count(cur, "SELECT COUNT(*) FROM vw_waswa_retrievable "
                         "WHERE review_status = 'approved' "
                         "AND audience = 'everyone'")
    if isinstance(approved, int) and approved == 0:
        print('\n   >> NOTHING IS APPROVED, so knowledge_search can never match.')
        print('      The documents are loaded and unreachable.')
        print('      Fix: python scripts/ingest_waswa_knowledge.py --approve-all')
    elif isinstance(public, int) and public == 0:
        print('\n   >> Approved, but NO chunk is visible to a customer.')
        print("      audience defaults to 'staff' and --approve does not change")
        print('      it, so staff get answers and customers get none. Set each')
        print("      customer-facing source's audience to 'everyone' in the CMS;")
        print('      leave the level-5 internal documents on staff.')


def audit(cur, limit, client, show_full):
    ts = _timestamp_column(cur)
    order = f'm.{ts} DESC' if ts else 'c.last_activity_at DESC, m.turn_index DESC'
    select_ts = f'm.{ts}' if ts else 'c.last_activity_at'

    where = ["m.role = 'assistant'"]
    args = []
    if client:
        where.append('c.client_uid = %s')
        args.append(client)

    cur.execute(f"""
        SELECT m.message_uid, m.conversation_uid, m.turn_index, m.content,
               m.intent, m.blocked_reason, m.latency_ms, {select_ts}
          FROM dll_waswa_messages m
          JOIN dll_waswa_conversations c
            ON c.conversation_uid = m.conversation_uid
         WHERE {' AND '.join(where)}
         ORDER BY {order}
         LIMIT %s""", (*args, limit))
    turns = cur.fetchall()

    if not turns:
        print('\n   No assistant turns recorded. Either nobody has asked Waswa')
        print('   anything through this database, or the app is pointed at a')
        print('   different one than this script.')
        return Counter()

    verdicts = Counter()
    print(f'\n== Last {len(turns)} answers (times are UTC; local is +3) ' + '=' * 26)

    for (muid, conv, idx, answer, intent, blocked, latency, when) in turns:
        cur.execute("""
            SELECT source_kind, source_ref, authority_level
              FROM dll_waswa_evidence WHERE message_uid = %s
             ORDER BY authority_level, source_ref""", (muid,))
        ev = cur.fetchall()

        cur.execute("""
            SELECT content FROM dll_waswa_messages
             WHERE conversation_uid = %s AND turn_index < %s AND role = 'user'
             ORDER BY turn_index DESC LIMIT 1""", (conv, idx))
        q = cur.fetchone()
        question = (q[0] if q else '(question not stored)').strip()

        looked_up = [e for e in ev if e[0] not in _FREE]
        answer = (answer or '').strip()
        admits = bool(_ADMITS.search(answer))

        states_account_fact = bool(_ACCOUNT_FACT.search(answer))
        if blocked:
            verdict, note = 'BLOCKED  ', f'by rule: {blocked}'
        elif not looked_up and states_account_fact:
            verdict, note = ('CONTEXT  ',
                             'no tool — read the injected account block '
                             '(real, but a snapshot, not a live lookup)')
        elif not looked_up and admits:
            verdict, note = 'HONEST   ', 'looked nothing up, and said so'
        elif not looked_up:
            verdict, note = 'INVENTED ', 'NO TOOL CALLED — answered from training'
        elif admits:
            verdict, note = 'EMPTY    ', 'tool ran, came back with nothing usable'
        else:
            verdict, note = 'GROUNDED ', 'tools returned data'
        verdicts[verdict.strip()] += 1

        # Stored in UTC. Kampala is +3, so an answer given at 10:02
        # local is filed as 07:02 and looks older than it is.
        when_s = (str(when)[:16] + ' UTC') if when else '?'
        print(f'\n[{verdict}] {when_s}  {latency or "?"}ms  intent={intent or "-"}')
        print(f'   Q: {question[:150]}')
        shown = answer if show_full else answer[:220].replace("\n", " ")
        print(f'   A: {shown}{"" if show_full or len(answer) <= 220 else " …"}')
        print(f'   -> {note}')
        if looked_up:
            for kind, ref, auth in looked_up:
                print(f'      · {kind:<10} L{auth}  {ref}')
        else:
            print('      · (nothing but the standing account context)')

    return verdicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=25)
    ap.add_argument('--client', help='only this client_uid')
    ap.add_argument('--full', action='store_true',
                    help='print answers in full instead of truncating')
    args = ap.parse_args()

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            knowledge_health(cur)
            verdicts = audit(cur, args.limit, args.client, args.full)
    finally:
        conn.close()

    if not verdicts:
        return 1

    total = sum(verdicts.values())
    print('\n== Verdict ' + '=' * 66)
    for name in ('GROUNDED', 'CONTEXT', 'INVENTED', 'EMPTY',
                 'HONEST', 'BLOCKED'):
        n = verdicts.get(name, 0)
        if n:
            print(f'   {name:<10} {n:>4}   {100 * n // total:>3}%')

    invented = verdicts.get('INVENTED', 0)
    empty = verdicts.get('EMPTY', 0)
    print()
    if invented:
        print(f'   {invented} answer(s) were produced with NO lookup at all. These are')
        print('   the ones that read as confident and are wrong. Fix the calling,')
        print('   not the wording: the tools exist and were not used.')
    if empty:
        print(f'   {empty} answer(s) had a tool run and return nothing. Fix the query:')
        print('   run  python scripts/waswa_fleet_check.py --client <UID>')
    context = verdicts.get('CONTEXT', 0)
    if context:
        print(f'   {context} answer(s) quoted the standing account block without a')
        print('   lookup. The figures are real but were assembled before the')
        print('   question; a live unit_status or balance call is the honest source.')
    if not invented and not empty:
        print('   Tools ran and returned data on every turn. If answers are still')
        print('   wrong, the fault is in the prompt or in the data itself — and')
        print('   that is now a much smaller search than where you started.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
