#!/usr/bin/env python3
"""Accuracy round 2 for endpoints/assistant.py, from the audit's own numbers.

The audit of the first 40 real questions: 26 answered with no lookup at all,
1 grounded. Among the 26 were invented support contact methods, invented
instructions for buying tokens, a textbook essay on why vehicles go offline
while a tool could have named the actual vehicle, and "I have data and
training up to October 2023" — gpt-4o introducing itself to a NAVAS customer.

The knowledge base is NOT the problem: 2,679 chunks across 12 sources are
loaded, and the one question that did reach knowledge_search got a correct,
specific answer. The tools were declared, described in the system prompt, and
ignored.

So this stops asking the model to look things up and starts requiring it.

  1. _needs_lookup is INVERTED. Every turn forces a tool call except pure
     pleasantries. A missed lookup yields a fluent invented answer the
     customer cannot distinguish from a correct one; a needless lookup costs
     one round trip and returns "found: false". Those mistakes are not
     symmetrical, so the default flips to looking.

  2. An instruction to search the documents. There was one telling the model
     to call unit_find for vehicles, and nothing at all about the 2,679
     chunks, which is why they went unread.

  3. An identity instruction, so Waswa stops citing its training.

Idempotent.
"""
import ast
import io
import sys

PATH = 'endpoints/assistant.py'

NEW_BLOCK = '''# Waswa answered 26 of its first 40 real questions with no lookup at all:
# confident prose about token packs, support contacts and offline vehicles,
# none of it read from NAVAS. The cause was not the wording of the prompt —
# the tools were declared, described and ignored. So the question is no longer
# "does this turn need a lookup?" but "is there any reason NOT to look?".
#
# Hence the inversion: everything forces a tool call except social turns,
# which have nothing to look up. Keep this list short and literal. A missed
# lookup produces an invented answer a customer cannot tell from a correct
# one; a needless lookup costs one round trip and returns "found: false".
# Those are not symmetrical mistakes.
_NO_LOOKUP = re.compile(
    r"^\\s*(hi|hey|hello|yo|good\\s+(morning|afternoon|evening|day)|"
    r"thanks?|thank\\s+you|thx|cheers|ok(ay)?|alright|got\\s+it|understood|"
    r"sure|fine|great|nice|cool|perfect|lovely|"
    r"yes|yeah|yep|yup|no|nope|"
    r"bye|goodbye|see\\s+you|later|good\\s?night)"
    r"[\\s!.,:;)\\u2019']*$", re.I)


def _needs_lookup(message):
    """True unless the turn is pure pleasantry.

    Inverted on purpose: see the comment above. When in doubt, look it up.
    """
    text = (message or '').strip()
    if not text:
        return False
    return not _NO_LOOKUP.match(text)

'''

SEARCH_INSTRUCTION = '''        # 2,679 knowledge chunks sat unread because nothing told the model
        # they existed. The vehicle instruction above had a counterpart for
        # documents only in spirit; now it has one in the prompt.
        messages.append({"role": "system", "content": (
            "You also have the approved NAVAS and OLIWA documents, through "
            "knowledge_search. For anything about how the platform works, what "
            "a term means, a policy, a procedure, a product, billing, tokens, "
            "support or who to contact, search them FIRST and answer from what "
            "comes back. Do not answer such a question from general knowledge "
            "about telematics: a plausible answer that is not what NAVAS "
            "actually does is worse for the customer than no answer. If the "
            "search returns nothing, say you could not find it and offer to "
            "put them in touch with someone who can help.")})

        # "I have data and training up to October 2023" was a real answer to a
        # real customer. Waswa is a NAVAS assistant, not a chatbot discussing
        # its own construction.
        messages.append({"role": "system", "content": (
            "You are Waswa, the assistant for the NAVAS platform and the OLIWA "
            "apps. Never mention your training data, a knowledge cut-off date, "
            "any model name, or who built you; you have no useful knowledge of "
            "those and they are not what was asked. When you do not know "
            "something, say you could not find it in NAVAS, and stop there.")})

'''

ANCHOR = '        if module and surface in _SCREEN_SURFACES:'


def patch(src):
    changes = []

    # ── 1. invert _needs_lookup ─────────────────────────────────────────────
    if '_NO_LOOKUP' in src:
        changes.append('_needs_lookup already inverted')
    else:
        start = src.find('# Questions that must never be answered')
        if start < 0:
            return None, ['!! round-1 _NEEDS_LOOKUP block not found — stopping']
        end_marker = "return bool(_NEEDS_LOOKUP.search(message or ''))\n"
        end = src.find(end_marker, start)
        if end < 0:
            return None, ['!! end of _needs_lookup not found — stopping']
        end += len(end_marker)
        while src[end:end + 1] == '\n':
            end += 1
        src = src[:start] + NEW_BLOCK + src[end:]
        changes.append('_needs_lookup INVERTED (forces a tool call by default)')

    # ── 2 + 3. the two new instructions ─────────────────────────────────────
    if 'knowledge_search. For anything about how the platform works' in src:
        changes.append('document + identity instructions already present')
    else:
        at = src.find(ANCHOR)
        if at < 0:
            return None, ['!! _SCREEN_SURFACES anchor not found — stopping']
        src = src[:at] + SEARCH_INSTRUCTION + src[at:]
        changes.append('added document-search instruction')
        changes.append('added identity instruction (no more "training data")')

    return src, changes


def main():
    src = io.open(PATH, encoding='utf-8', newline='').read()
    out, changes = patch(src)
    for c in changes:
        print('  ' + c)
    if out is None:
        return 1
    if out == src:
        print('  (nothing to write)')
        return 0
    ast.parse(out)
    io.open(PATH, 'w', encoding='utf-8', newline='').write(out)
    print(f'  written: {PATH}')
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
