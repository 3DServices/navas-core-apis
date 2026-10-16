#!/usr/bin/env python3
"""
i1_evidence_trail.py -- what was each flagged answer actually built from?

The chain so far, each step refuting the one before it:

  1. "the corpus is missing these documents"  -> wrong, all 12 registered
  2. "the approval gate is hiding them"       -> wrong, all approved + active
  3. "may_quote or the score threshold cuts them" -> wrong, 133 VEBA chunks
     pass every filter with scores up to 0.60 against a threshold of 0.01
  4. "the tsquery tiers lose them"            -> wrong, knowledge_search()
     returns 5 results for all four phrasings, including the typo'd one

So retrieval works. And _needs_lookup() is inverted -- it forces a tool call
for everything except literal pleasantries -- so a lookup WAS forced for
"what is veba?".

But tool_choice="required" means "call SOMETHING", not "call
knowledge_search". The model still chooses. dll_waswa_evidence records what
each answer was grounded in (source_kind: tool | document | account_context,
source_ref: the tool name or document id), so it can say directly whether
knowledge_search was ever called for the flagged turns.

Three outcomes, three different fixes:

  no evidence rows at all      the forced tool call produced nothing usable,
                               or evidence is not being written. Check the
                               writer at assistant.py:297 before blaming the
                               model.
  evidence, but no document    the model called a DIFFERENT tool -- a product
                               or fleet read -- got nothing, and answered "I
                               have no approved documents" from that. The fix
                               is tool selection, not retrieval.
  document evidence present    retrieval ran, returned chunks, and the model
                               still refused. The fix is the prompt.

Read-only.

Usage:
    python scripts/i1_evidence_trail.py
"""

import sys

sys.path.insert(0, '.')

# the six open flags, newest prompt version first
FLAGS = [
    ('d0cba9cf-b76f-44ae-b3fe-6ea6c21560f1', 'what is veba?', 'v9'),
    ('295e86ee-1a5a-472d-aa03-96e9ffb34d65', 'How many tokens do I have?', 'v9'),
    ('01493100-a6a4-4023-b64b-50958cc1c53e', 'create a geofence', 'v9'),
    ('fdd1e811-7a07-4428-adff-6f628f0721cb', 'units in my oliwa account', 'v9'),
    ('b18d367e-01bc-4de4-a09b-9fdf0ba85af8', 'How many tokens do I have?', 'v9'),
    ('bd7a963c-2d96-49eb-8b4c-52e3676ff419', 'What is VEBA escrow?', 'v6'),
]


def main():
    import psycopg2
    import psycopg2.extras
    from config import DB_LINK

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            # is evidence being written at all? a zero here changes everything
            cur.execute("SELECT source_kind, COUNT(*) AS n, "
                        "       COUNT(DISTINCT message_uid) AS msgs "
                        "FROM dll_waswa_evidence GROUP BY 1 ORDER BY 2 DESC")
            rows = cur.fetchall()
            print('dll_waswa_evidence, overall')
            if not rows:
                print('   EMPTY. No answer has ever recorded its grounding, so')
                print('   the absence of rows below says nothing about the')
                print('   model -- it is the writer at assistant.py:297 that')
                print('   needs looking at first.')
            for r in rows:
                print('   %-18s %6d row(s) across %d message(s)'
                      % (r['source_kind'], r['n'], r['msgs']))

            cur.execute("SELECT COUNT(*) AS n FROM dll_waswa_messages "
                        "WHERE role = 'assistant'")
            answers = cur.fetchone()['n']
            cur.execute("SELECT COUNT(DISTINCT message_uid) AS n "
                        "FROM dll_waswa_evidence")
            grounded = cur.fetchone()['n']
            print('')
            print('   %d assistant answer(s), %d with any evidence recorded'
                  ' (%.0f%%)'
                  % (answers, grounded,
                     100.0 * grounded / answers if answers else 0))

            print('')
            print('=' * 80)
            for feedback_uid, label, version in FLAGS:
                cur.execute("""
                    SELECT f.message_uid, m.prompt_version, m.router_tier,
                           m.model
                    FROM dll_waswa_feedback f
                    LEFT JOIN dll_waswa_messages m
                           ON m.message_uid = f.message_uid
                    WHERE f.feedback_uid = %s
                """, (feedback_uid,))
                head = cur.fetchone()
                if head is None:
                    print('  %-34s flag not found' % label)
                    continue

                cur.execute("""
                    SELECT source_kind, source_ref, authority_level
                    FROM dll_waswa_evidence
                    WHERE message_uid = %s
                    ORDER BY source_kind, source_ref
                """, (head['message_uid'],))
                evidence = cur.fetchall()

                print('')
                print('  %-32s  prompt %s, tier %s'
                      % (label, head['prompt_version'], head['router_tier']))
                if not evidence:
                    print('     NO EVIDENCE RECORDED for this answer.')
                else:
                    for e in evidence:
                        print('     %-16s %-44s auth=%s'
                              % (e['source_kind'], str(e['source_ref'])[:44],
                                 e['authority_level']))
                    kinds = {e['source_kind'] for e in evidence}
                    refs = {str(e['source_ref']) for e in evidence}
                    # An account question ("how many tokens do I have?") is
                    # ANSWERED from waswa_context. The first version of this
                    # script called that "the wrong tool" because it was not
                    # knowledge_search, and mislabelled three of six flags.
                    wants_docs = any(w in label.lower() for w in
                                     ('veba', 'escrow', 'geofence', 'how do',
                                      'what is', 'explain'))
                    if 'document' in kinds:
                        auths = {e['authority_level'] for e in evidence
                                 if e['source_kind'] == 'document'}
                        print('     -> documents WERE retrieved (authority %s).'
                              % ', '.join(str(a) for a in sorted(
                                  auths, key=lambda x: (x is None, x))))
                        print('        The model had material and refused:')
                        print('        a PROMPT problem, not retrieval.')
                        if None in auths:
                            print('        NOTE: authority_level is NULL here.'
                                  ' The v6 answer')
                            print('        that DID use its document recorded'
                                  ' auth=3. Worth')
                            print('        checking whether unknown authority'
                                  ' makes a chunk')
                            print('        unquotable downstream.')
                    elif any('knowledge' in r for r in refs):
                        print('     -> knowledge_search ran but returned no'
                              ' document.')
                    elif wants_docs:
                        print('     -> this needed the corpus and'
                              ' knowledge_search was')
                        print('        never called: a TOOL SELECTION problem.')
                    else:
                        print('     -> answered from account context, which is'
                              ' the RIGHT')
                        print('        source for an account question. If the'
                              ' answer was')
                        print('        still wrong, the numbers are wrong:'
                              ' `data_fix`.')
    finally:
        conn.close()

    print('')
    print('  The % of answers with any evidence is the number to read first.')
    print('  If it is low across the board, this is not six bad answers --')
    print('  it is answers not being grounded generally, and the flags are')
    print('  just the ones somebody happened to report.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
