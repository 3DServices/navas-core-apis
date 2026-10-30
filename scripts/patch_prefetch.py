#!/usr/bin/env python3
"""Don't ask the model to look things up. Look them up, then ask the model.

tool_choice='required' is a request to OpenRouter that the model call something.
The audit showed four vehicle questions answered in prose with no call at all,
and the test suite proves the parameter leaves this codebase correctly — so the
failure is downstream, at the provider or in the model. That distinction matters
for a bug report and not at all to a customer whose question went unanswered.

So for the one class of question where guessing is never acceptable — what this
account's own vehicles are doing — the server looks FIRST and hands the result
over as context. The model is no longer asked to decide whether to check; the
check has already happened and the figures are in front of it. Tools stay
available for everything beyond the first lookup (trips over a range, route
probes, a second vehicle), and tool_choice stays as a belt to this braces.

This is also why the "from your screen" refusals can't come back for these
questions: there is no gap left to decline into.

Adds:
  _FLEET_QUESTION   — does this turn concern vehicles at all
  _plate_or_imei    — the vehicle the person named, if they named one
  _prefetch_fleet   — one or two reads, before the first model call

Idempotent.
"""
import ast
import io
import sys

PATH = 'endpoints/assistant.py'

HELPERS = '''
# Vehicle-shaped questions. Narrower than _needs_lookup on purpose: that gate
# also fires for tokens and charges, which waswa_context already carries, and a
# fleet read for "what is my balance" would be two wasted queries.
_FLEET_QUESTION = re.compile(
    r"\\b(unit|units|vehicle|vehicles|truck|lorry|car|bike|boda|fleet|"
    r"trip|trips|route|journey|mileage|odometer|driver|"
    r"offline|online|reporting|disconnected|not showing|last seen|"
    r"moving|parked|idle|stopped|speed|speeding|overspeed|"
    r"where is|where was|location|position|geofence)\\b", re.I)


def _plate_or_imei(message):
    """The vehicle the person named, or None.

    Plates here look like UBF 364U or UBJ916W; an IMEI is fifteen digits. Both
    are passed to unit_find as a query, which matches on name, plate, VIN,
    make, model and IMEI, so a near miss still finds the unit.
    """
    text = str(message or '')
    imei = re.search(r"\\b\\d{15}\\b", text)
    if imei:
        return imei.group(0)
    plate = re.search(r"\\b[A-Z]{2,3}\\s?\\d{3}\\s?[A-Z]?\\b", text)
    return plate.group(0).strip() if plate else None


def _prefetch_fleet(message, fleet_scope):
    """Read the account's fleet before the model is asked anything.

    Returns (notes, evidence) — notes are system messages to append, evidence
    are rows for the trail so the audit shows a real lookup rather than "nothing
    but the standing account context".

    At most two reads: which vehicles exist, and if the person named exactly one,
    how it is doing. Everything else stays a tool call, because a range of trips
    or a route probe is too expensive to do speculatively.
    """
    notes, evidence = [], []
    if not _FLEET_QUESTION.search(str(message or '')):
        return notes, evidence

    named = _plate_or_imei(message)
    try:
        found = (waswa_fleet.unit_find(query=named, scope=fleet_scope) if named
                 else waswa_fleet.unit_find(scope=fleet_scope))
    except waswa_fleet.FleetUnavailable as error:
        _log('fleet prefetch: register unreachable (%s)', error)
        notes.append(
            "The vehicle register could not be read just now. This is a fault "
            "on our side and says NOTHING about what this account owns. Tell "
            "the person you cannot check their vehicles at the moment. Do not "
            "say they have none and do not give a count.")
        evidence.append(('fleet', 'unit_find(unavailable)', 1))
        return notes, evidence
    except Exception as error:      # noqa: BLE001 - never break the turn
        _log('fleet prefetch failed: %s: %s', error.__class__.__name__, error)
        return notes, evidence

    evidence.append(('fleet', f'unit_find({named or "all"}, prefetched)', 1))
    notes.append(
        "This account's own vehicles, read from the database just now — not "
        "from the screen, and not from your training. Answer from these "
        "figures:\\n" + json.dumps(found, default=str))

    # One named vehicle, unambiguous: fetch how it is doing too, since that is
    # what "why is it offline" and "where is it" both need.
    units = found.get('units') or []
    if named and found.get('found') and len(units) == 1:
        imei = units[0].get('imei')
        if imei:
            try:
                status = waswa_fleet.unit_status(imei=imei, scope=fleet_scope)
            except waswa_fleet.FleetUnavailable as error:
                _log('status prefetch: unreachable (%s)', error)
                status = None
            except Exception as error:      # noqa: BLE001
                _log('status prefetch failed: %s', error)
                status = None
            if status:
                evidence.append(('fleet', f'unit_status({imei}, prefetched)', 1))
                notes.append(
                    "Its current state, measured just now. last_reported_at and "
                    "last_position.at are LOCAL times. State these figures; if a "
                    "field is null say it could not be read rather than filling "
                    "the gap:\\n" + json.dumps(status, default=str))
    elif len(units) > 1:
        notes.append(
            "More than one vehicle matches what they said. Ask which one, "
            "naming the candidates above, and stop there.")

    return notes, evidence

'''

OLD = """        must_look_up = _needs_lookup(user_message)
        for _round in range(_MAX_TOOL_ROUNDS):"""

NEW = """        must_look_up = _needs_lookup(user_message)

        # Looked up here rather than left to the model. See _prefetch_fleet:
        # asking the model to call a tool is a request that can be declined
        # somewhere between here and the provider; reading the data first is
        # not. Tools remain available for everything past the first lookup.
        if must_look_up:
            fleet_notes, fleet_evidence = _prefetch_fleet(
                user_message, fleet_scope)
            for note in fleet_notes:
                messages.append({"role": "system", "content": note})
            evidence.extend(fleet_evidence)

        for _round in range(_MAX_TOOL_ROUNDS):"""


def main():
    src = io.open(PATH, encoding='utf-8', newline='').read()

    if '_prefetch_fleet' in src:
        print('  prefetch already in place')
        return 0

    at = src.find('def _needs_lookup(message):')
    if at < 0:
        print('  !! _needs_lookup not found — stopping')
        return 1
    # Insert the helpers after _needs_lookup's own block, before _call_model.
    anchor = src.find('def _call_model(', at)
    if anchor < 0:
        print('  !! _call_model not found — stopping')
        return 1
    src = src[:anchor] + HELPERS.lstrip('\n') + '\n' + src[anchor:]
    print('  added _FLEET_QUESTION, _plate_or_imei, _prefetch_fleet')

    if OLD not in src:
        print('  !! the round loop was not found verbatim — stopping')
        return 1
    src = src.replace(OLD, NEW, 1)
    print('  the fleet is read before the first model call')

    ast.parse(src)
    io.open(PATH, 'w', encoding='utf-8', newline='').write(src)
    print(f'  written: {PATH}')
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
