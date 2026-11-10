#!/usr/bin/env python3
"""Correct an over-labelling in scripts/waswa_audit.py.

The first run labelled 26 answers INVENTED — "answered from training". Some of
those were not. "You have 120 token units remaining across the 3 packs
currently in use" is not something gpt-4o imagined; it is read out of the
standing account block that waswa_context injects into every turn. That block
is real data from the real database.

Calling it invented would send someone hunting a hallucination that is not
there, so it gets its own verdict. It is still not a clean bill of health: the
context block is a snapshot assembled before the question was asked, so an
answer built from it is right only by luck about timing, and "how many
vehicles are online" deserves a live unit_status rather than a figure that was
true when the conversation opened. CONTEXT means "grounded, but not looked
up" — better than INVENTED, worse than GROUNDED.

Idempotent.
"""
import ast
import io
import sys

PATH = 'scripts/waswa_audit.py'

REGEX = '''
# Figures that come from the standing account block (waswa_context) rather than
# from the model's imagination: token packs, payment standing, unit counts.
# An answer stating these without a tool call is reading injected context, not
# inventing — a different fault with a different fix.
_ACCOUNT_FACT = re.compile(
    r"\\d+\\s*(token|unit|pack|payment|vehicle|device)s?\\b"
    r"|\\b(no|zero|0)\\s+(token|unit|pack|subscribed|active)"
    r"|\\bpack(s)? (that )?haven'?t been activated"
    r"|\\brecorded as pending|\\bpayments? recorded"
    r"|\\bdoesn'?t have any (token|subscribed|active)",
    re.I)
'''

OLD_VERDICT = """        if blocked:
            verdict, note = 'BLOCKED  ', f'by rule: {blocked}'
        elif not looked_up and admits:
            verdict, note = 'HONEST   ', 'looked nothing up, and said so'
        elif not looked_up:
            verdict, note = 'INVENTED ', 'NO TOOL CALLED — answered from training'
"""

NEW_VERDICT = """        states_account_fact = bool(_ACCOUNT_FACT.search(answer))
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
"""

OLD_ORDER = ("    for name in ('GROUNDED', 'INVENTED', 'EMPTY', 'HONEST', 'BLOCKED'):")
NEW_ORDER = ("    for name in ('GROUNDED', 'CONTEXT', 'INVENTED', 'EMPTY',\n"
             "                 'HONEST', 'BLOCKED'):")

OLD_TAIL = """    if not invented and not empty:"""
NEW_TAIL = """    context = verdicts.get('CONTEXT', 0)
    if context:
        print(f'   {context} answer(s) quoted the standing account block without a')
        print('   lookup. The figures are real but were assembled before the')
        print('   question; a live unit_status or balance call is the honest source.')
    if not invented and not empty:"""


def patch(src):
    changes = []

    if '_ACCOUNT_FACT' in src:
        changes.append('CONTEXT verdict already present')
        return src, changes

    anchor = '_ADMITS = re.compile('
    at = src.find(anchor)
    if at < 0:
        return None, ['!! _ADMITS not found — stopping']
    end = src.find('\n\n', src.find(')', src.find('re.I)', at)))
    if end < 0:
        return None, ['!! could not find the end of _ADMITS — stopping']
    src = src[:end] + '\n' + REGEX + src[end:]
    changes.append('added _ACCOUNT_FACT')

    for old, new, label in ((OLD_VERDICT, NEW_VERDICT, 'CONTEXT branch'),
                            (OLD_ORDER, NEW_ORDER, 'summary order'),
                            (OLD_TAIL, NEW_TAIL, 'summary advice')):
        if old not in src:
            return None, [f'!! could not find {label} verbatim — stopping']
        src = src.replace(old, new, 1)
        changes.append(f'patched {label}')

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
