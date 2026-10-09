#!/usr/bin/env python3
"""Two accuracy changes to endpoints/assistant.py, applied in place.

1. max_tokens 600 -> 1200. A fleet answer that lists a unit, its last report
   time and why it is offline does not fit in 600 tokens; it gets cut off
   mid-sentence, and a cut-off answer reads to a customer as a wrong one.

2. tool_choice='required' on the FIRST round when the question is plainly
   about a vehicle. The system prompt already asks the model to call unit_find
   first; asking is not the same as requiring, and gpt-4o with two dozen tools
   declared will sometimes answer from training instead. This removes the
   choice for exactly the questions where answering from training is never
   acceptable, and leaves every other question on 'auto'.

Idempotent: running it twice changes nothing the second time.
"""
import io
import re
import sys

PATH = 'endpoints/assistant.py'

HELPER = '''
# Questions that must never be answered from the model's own training, because
# the answer is a fact about this account that only the database holds. For
# these the first round is forced to call a tool; everything else stays on
# 'auto'. Keep this list tight: forcing a tool call on "hello" wastes a round
# and confuses the model.
_NEEDS_LOOKUP = re.compile(
    r"\\b(unit|units|vehicle|vehicles|truck|lorry|car|bike|boda|fleet|"
    r"trip|trips|route|journey|mileage|odometer|"
    r"offline|online|reporting|disconnected|not showing|last seen|"
    r"moving|parked|idle|stopped|speed|speeding|overspeed|"
    r"where is|where was|location|position|geofence|"
    r"balance|tokens?|charges?|billing|expiry|expire)\\b"
    r"|\\b[A-Z]{3}\\s?\\d{3}[A-Z]?\\b"      # UBK 415K
    r"|\\b\\d{15}\\b",                      # an IMEI
    re.I)


def _needs_lookup(message):
    """True when the question is about this account's own data."""
    return bool(_NEEDS_LOOKUP.search(message or ''))

'''


def patch(src):
    changes = []

    # ── 1. max_tokens ───────────────────────────────────────────────────────
    if '"max_tokens": 600,' in src:
        src = src.replace('"max_tokens": 600,', '"max_tokens": 1200,', 1)
        changes.append('max_tokens 600 -> 1200')
    elif '"max_tokens": 1200,' in src:
        changes.append('max_tokens already 1200')
    else:
        return None, ['!! could not find max_tokens — stopping, nothing written']

    # ── 2a. the helper ──────────────────────────────────────────────────────
    anchor = 'def _call_model(messages, allow_tools=True'
    if '_needs_lookup' not in src:
        at = src.find(anchor)
        if at < 0:
            return None, ['!! could not find _call_model — stopping']
        src = src[:at] + HELPER.lstrip('\n') + '\n' + src[at:]
        changes.append('added _needs_lookup()')
    else:
        changes.append('_needs_lookup already present')

    # ── 2b. the signature ───────────────────────────────────────────────────
    old_sig = 'def _call_model(messages, allow_tools=True):'
    new_sig = 'def _call_model(messages, allow_tools=True, force_tools=False):'
    if old_sig in src:
        src = src.replace(old_sig, new_sig, 1)
        changes.append('_call_model takes force_tools')
    elif new_sig in src:
        changes.append('_call_model already takes force_tools')
    else:
        return None, ['!! could not find _call_model signature — stopping']

    # ── 2c. tool_choice ─────────────────────────────────────────────────────
    old_tc = ('    if not allow_tools:\n'
              '        payload["tool_choice"] = "none"\n')
    new_tc = ('    if not allow_tools:\n'
              '        payload["tool_choice"] = "none"\n'
              '    elif force_tools:\n'
              '        # "required" = call SOMETHING. Which tool is still the\n'
              '        # model\'s choice; answering without looking is not.\n'
              '        payload["tool_choice"] = "required"\n')
    if 'force_tools' not in src.split('def _call_model')[1][:1200] or old_tc in src:
        if old_tc in src:
            src = src.replace(old_tc, new_tc, 1)
            changes.append('tool_choice="required" wired in')
        else:
            changes.append('tool_choice already wired')
    else:
        changes.append('tool_choice already wired')

    # ── 2d. the call site ───────────────────────────────────────────────────
    old_loop = ('        for _ in range(_MAX_TOOL_ROUNDS):\n'
                '            outcome = _call_model(messages)\n')
    new_loop = ('        must_look_up = _needs_lookup(user_message)\n'
                '        for _round in range(_MAX_TOOL_ROUNDS):\n'
                '            outcome = _call_model(\n'
                '                messages,\n'
                '                force_tools=(_round == 0 and must_look_up))\n')
    if old_loop in src:
        src = src.replace(old_loop, new_loop, 1)
        changes.append('first round forced for account-data questions')
    elif 'must_look_up' in src:
        changes.append('call site already patched')
    else:
        return None, ['!! could not find the tool loop — stopping']

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
    io.open(PATH, 'w', encoding='utf-8', newline='').write(out)
    print(f'  written: {PATH}')

    # Prove it still parses before she restarts anything.
    import ast
    ast.parse(out)
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
