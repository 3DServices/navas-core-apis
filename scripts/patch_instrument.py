#!/usr/bin/env python3
"""Stop guessing why no tool is being called. Log the request, and fix my prompt.

The post-patch run, read carefully:

    Q: Why is UBF 364U offline?
    A: "I don't have access to specific vehicle data or live figures FROM YOUR
        SCREEN, so I can't see why UBF 364U is offline."

    Q: How many trips did UBJ 916W make this week?
    A: "I don't have access to specific vehicle data or trip counts FROM YOUR
        SCREEN..."

"from your screen" is my own wording, from the surface message:

    "You do not see what is on their screen; if the question depends on live
     figures from it that you have not been given, say so."

I wrote that to stop Waswa pretending it could read a dashboard. The model has
taken it as a general licence to decline questions about vehicles — the exact
questions unit_find and unit_status exist to answer. My instruction is now
causing the refusal it was meant to prevent, so it is reworded to say plainly
that not seeing the screen is never a reason to refuse something a tool can
retrieve.

Second, and more important: FOUR account-data questions produced ZERO tool
calls. If tool_choice='required' were reaching OpenRouter the model could not
have answered in prose at all — "required" means it must call something. So the
forcing is not in effect, and there are only two candidates: Flask is running
the pre-patch code, or the parameter is not arriving.

I am not going to guess between those twice. This logs, at WARNING so it lands
in the Flask console:

    [waswa] -> model: 24 tools, tool_choice=required (round 0, forced)
    [waswa] <- model: 0 tool call(s), finish_reason=stop

Read it like this:
  * no such line at all        -> Flask is serving the old code; restart it
  * tool_choice=auto on round 0 for a vehicle question -> _needs_lookup said no
  * tool_choice=required and 0 calls -> OpenRouter or the model is ignoring it,
                                        and that is a different fix

Idempotent.
"""
import ast
import io
import sys

ASSIST = 'endpoints/assistant.py'
AUDIT = 'scripts/waswa_audit.py'

OLD_SCREEN = '''        if module and surface in _SCREEN_SURFACES:
            who, app = _SCREEN_SURFACES[surface]
            messages.append({"role": "system", "content": (
                f"The {who} is asking from the {app} \\"{module}\\" screen. "
                "Read short or ambiguous questions in that context. You do not "
                "see what is on their screen; if the question depends on live "
                "figures from it that you have not been given, say so.")})'''

NEW_SCREEN = '''        if module and surface in _SCREEN_SURFACES:
            who, app = _SCREEN_SURFACES[surface]
            # The earlier wording of this ("you do not see what is on their
            # screen ... say so") was being used as a reason to decline
            # questions about their own vehicles, which is the opposite of the
            # point. Not seeing the screen says nothing about what can be
            # looked up.
            messages.append({"role": "system", "content": (
                f"The {who} is asking from the {app} \\"{module}\\" screen. "
                "Read short or ambiguous questions in that context. You cannot "
                "see their screen, but that is NEVER a reason to decline a "
                "question about their vehicles, trips, tokens or charges — "
                "those come from your tools, not from the screen, so call the "
                "tools. Only say you cannot see something when it exists just "
                "on their screen and no tool can fetch it.")})'''

OLD_CALL = '''    if not allow_tools:
        payload["tool_choice"] = "none"
    elif force_tools:
        # "required" = call SOMETHING. Which tool is still the
        # model's choice; answering without looking is not.
        payload["tool_choice"] = "required"
'''

NEW_CALL = '''    if not allow_tools:
        payload["tool_choice"] = "none"
    elif force_tools:
        # "required" = call SOMETHING. Which tool is still the
        # model's choice; answering without looking is not.
        payload["tool_choice"] = "required"

    # What actually goes out. Four account-data questions once produced zero
    # tool calls, and from the outside that is indistinguishable between "the
    # code is not running", "the gate said no" and "the model ignored us".
    # One line removes the guessing.
    _log('-> model: %s tools, tool_choice=%s', len(_TOOL_SPECS),
         payload.get('tool_choice', 'auto (not forced)'))
'''

OLD_RETURN_HOOK = """            assistant_message = outcome['message']
            finish_reason = outcome.get('finish_reason')
            tool_calls = assistant_message.get('tool_calls') or []
"""

NEW_RETURN_HOOK = """            assistant_message = outcome['message']
            finish_reason = outcome.get('finish_reason')
            tool_calls = assistant_message.get('tool_calls') or []
            _log('<- model: %s tool call(s)%s, finish_reason=%s (round %s, '
                 'forced=%s)',
                 len(tool_calls),
                 ': ' + ', '.join(
                     (c.get('function') or {}).get('name', '?')
                     for c in tool_calls) if tool_calls else '',
                 finish_reason, _round, (_round == 0 and must_look_up))
"""


def patch_assistant():
    src = io.open(ASSIST, encoding='utf-8', newline='').read()
    notes = []

    if 'NEVER a reason to decline' in src:
        notes.append('screen message already reworded')
    elif OLD_SCREEN in src:
        src = src.replace(OLD_SCREEN, NEW_SCREEN, 1)
        notes.append('screen message reworded (it was licensing refusals)')
    else:
        notes.append('!! screen message not found verbatim — left alone')

    if '-> model: %s tools' in src:
        notes.append('request logging already present')
    elif OLD_CALL in src:
        src = src.replace(OLD_CALL, NEW_CALL, 1)
        notes.append('logs the outgoing tool_choice')
    else:
        return None, notes + ['!! tool_choice block not found — stopping']

    if '<- model: %s tool call(s)' in src:
        notes.append('response logging already present')
    elif OLD_RETURN_HOOK in src:
        src = src.replace(OLD_RETURN_HOOK, NEW_RETURN_HOOK, 1)
        notes.append('logs the tool calls that came back')
    else:
        return None, notes + ['!! round loop not found — stopping']

    ast.parse(src)
    io.open(ASSIST, 'w', encoding='utf-8', newline='').write(src)
    return src, notes


def patch_audit():
    """The audit prints the stored timestamp raw. It is UTC, and Kampala is
    +3 — which made answers from eight minutes ago look three hours stale and
    cost us a round trip deciding whether the run was new. Label it."""
    src = io.open(AUDIT, encoding='utf-8', newline='').read()
    if 'UTC' in src:
        return 'audit already labels the clock'

    old = "        when_s = str(when)[:16] if when else '?'"
    new = ("        # Stored in UTC. Kampala is +3, so an answer given at 10:02\n"
           "        # local is filed as 07:02 and looks older than it is.\n"
           "        when_s = (str(when)[:16] + ' UTC') if when else '?'")
    if old not in src:
        return '!! timestamp line not found'
    src = src.replace(old, new, 1)

    old_hdr = "    print(f'\\n== Last {len(turns)} answers ' + '=' * 54)"
    new_hdr = ("    print(f'\\n== Last {len(turns)} answers "
               "(times are UTC; local is +3) ' + '=' * 26)")
    if old_hdr in src:
        src = src.replace(old_hdr, new_hdr, 1)

    ast.parse(src)
    io.open(AUDIT, 'w', encoding='utf-8', newline='').write(src)
    return 'audit now says the timestamps are UTC'


def main():
    out, notes = patch_assistant()
    for n in notes:
        print('  ' + n)
    if out is None:
        return 1
    print('  ' + patch_audit())
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
