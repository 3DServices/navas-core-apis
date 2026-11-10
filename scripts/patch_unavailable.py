#!/usr/bin/env python3
"""A Cassandra outage must never be reported to a customer as "you have no vehicles".

The probe just failed like this:

    Error connecting to Cassandra: ('Unable to connect to any servers',
      {'165.232.128.208:9042': OperationTimedOut(...)})

and _units_of answers that by returning []. My own docstring said so out loud:
"[] when Cassandra is unreachable." unit_find then reports

    {'found': False, 'reason': 'no units are registered to this account'}

So when the vehicle register is unreachable, Waswa tells a customer who owns
five vehicles that they own none — specifically, confidently, about their own
property. There is no worse failure available to it. An outage is a sentence we
can say; an invented zero is not.

Look back at the audit with this in mind:

    "where is UBK 415T right now?"  -> "your account doesn't have any
                                       subscribed units or active products"

That may well have been this, not an empty account.

And forcing the tool call, which I added an hour ago, makes it fire MORE often:
every vehicle question now reaches unit_find, so every Cassandra blip becomes a
confident denial instead of generic waffle. Shipping that without this would
have made Waswa worse, not better.

The fix separates three states that were collapsed into two:

    units found            -> answer from them
    no units registered    -> say so (true, and useful)
    register unreachable   -> say THAT, and state no number at all

Idempotent.
"""
import ast
import io
import sys

FLEET = 'endpoints/waswa_fleet.py'
ASSIST = 'endpoints/assistant.py'
TESTS = 'tests/test_waswa_fleet.py'

EXC = '''
class FleetUnavailable(Exception):
    """The vehicle register could not be read.

    Raised rather than returned, so that no caller can mistake it for an empty
    fleet by forgetting to check a flag. "I could not look" and "there is
    nothing there" are different answers to a customer, and only one of them is
    safe to guess at.
    """

'''

OLD_UNITS = '''def _units_of(client_uid):
    """Every unit registered to a client. [] when Cassandra is unreachable."""
    session = _cassandra()
    if session is None or not client_uid:
        return []
    try:
        stmt = session.prepare(
            "SELECT device_imei, device_name, device_car_make, device_car_model, "
            "device_vin_number, device_billing_status "
            "FROM dll_device_basic_data WHERE device_client = ? ALLOW FILTERING")
        rows = session.execute(stmt, (str(client_uid),))
    except Exception:
        return []'''

NEW_UNITS = '''def _units_of(client_uid):
    """Every unit registered to a client.

    Raises FleetUnavailable when the register cannot be read. It must not
    return [] for that: an empty list is indistinguishable from "this customer
    owns nothing", and Cassandra timing out is not evidence about what anybody
    owns.
    """
    if not client_uid:
        return []
    try:
        session = _cassandra()
    except Exception as error:      # noqa: BLE001
        raise FleetUnavailable(str(error)) from error
    if session is None:
        raise FleetUnavailable('no Cassandra session')
    try:
        stmt = session.prepare(
            "SELECT device_imei, device_name, device_car_make, device_car_model, "
            "device_vin_number, device_billing_status "
            "FROM dll_device_basic_data WHERE device_client = ? ALLOW FILTERING")
        rows = session.execute(stmt, (str(client_uid),))
    except Exception as error:      # noqa: BLE001
        raise FleetUnavailable(str(error)) from error'''

OLD_CATCH = """    try:
        return func(**arguments, scope=scope)
    except TypeError as error:
        return {'error': f'bad arguments for {tool_name}: {error}'}"""

NEW_CATCH = """    try:
        return func(**arguments, scope=scope)
    except FleetUnavailable as error:
        # Said in the tool result, because that is what the model reads. The
        # instruction is part of the finding: a number here would be a guess.
        _warn('vehicle register unreachable (%s): %s', tool_name, error)
        return {
            'found': False,
            'unavailable': True,
            'reason': ('The vehicle register could not be reached just now. '
                       'This is a fault on our side and says NOTHING about '
                       'what this account owns. Tell the person you cannot '
                       'check their vehicles at the moment and that it should '
                       'be working again shortly. Do NOT say they have no '
                       'vehicles, do not give a count, and do not guess.'),
        }
    except TypeError as error:
        return {'error': f'bad arguments for {tool_name}: {error}'}"""

WARN = '''
def _warn(message, *args):
    """Fleet faults belong in the Flask log, not only in the chat window."""
    try:
        current_app.logger.warning('[waswa.fleet] ' + message, *args)
    except Exception:       # noqa: BLE001 - logging must never break a turn
        pass

'''

PROMPT = '''        # A tool that reports unavailable: true has told us it could not look.
        # Waswa used to turn that into "you have no vehicles", which is the one
        # answer a customer cannot check and must never be guessed.
        messages.append({"role": "system", "content": (
            "If a tool result contains \\"unavailable\\": true, the system could "
            "not read that data. Say you cannot check it right now. Never "
            "convert it into a count, a zero, or \\"you have none\\" — a figure "
            "you did not read is worse than admitting the outage.")})

'''

TEST_BLOCK = '''

# ── An outage is not an empty fleet ─────────────────────────────────────────

def test_an_unreachable_register_is_not_reported_as_no_vehicles():
    def tool(**kwargs):
        raise FleetUnavailable('OperationTimedOut')
    NS['_DISPATCH'] = {'unit_find': tool}

    out = dispatch('unit_find', {'query': 'UBK 415K'}, scope=CUSTOMER)
    assert out['unavailable'] is True
    assert out['found'] is False
    # The whole point: nothing in the reason may read as "you own nothing".
    lowered = out['reason'].lower()
    for forbidden in ('no units are registered', 'no vehicles on this account',
                      '0 units', 'zero units'):
        assert forbidden not in lowered, forbidden
    assert 'could not be reached' in lowered


def test_an_outage_is_distinguishable_from_a_genuinely_empty_account():
    def empty(**kwargs):
        return {'found': False, 'reason': 'no units are registered to this account'}
    NS['_DISPATCH'] = {'unit_find': empty}
    out = dispatch('unit_find', {}, scope=CUSTOMER)
    assert not out.get('unavailable'), 'an empty account is not an outage'


def test_an_ordinary_failure_is_still_an_error_not_an_outage():
    def broken(**kwargs):
        raise ValueError('something else entirely')
    NS['_DISPATCH'] = {'unit_find': broken}
    out = dispatch('unit_find', {}, scope=CUSTOMER)
    assert 'error' in out
    assert not out.get('unavailable')
'''


def patch_fleet():
    src = io.open(FLEET, encoding='utf-8', newline='').read()
    notes = []

    if 'class FleetUnavailable' in src:
        notes.append('FleetUnavailable already defined')
    else:
        at = src.find('def _pg():')
        if at < 0:
            return None, ['!! _pg() not found']
        src = src[:at] + EXC.lstrip('\n') + '\n' + WARN.lstrip('\n') + '\n' + src[at:]
        notes.append('added FleetUnavailable and _warn()')

    if 'raise FleetUnavailable' in src:
        notes.append('_units_of already raises')
    elif OLD_UNITS in src:
        src = src.replace(OLD_UNITS, NEW_UNITS, 1)
        notes.append('_units_of raises instead of returning []')
    else:
        return None, ['!! _units_of not found verbatim']

    if 'except FleetUnavailable as error:' in src:
        notes.append('dispatch already handles it')
    elif OLD_CATCH in src:
        src = src.replace(OLD_CATCH, NEW_CATCH, 1)
        notes.append('dispatch returns unavailable:true')
    else:
        return None, ['!! dispatch catch block not found verbatim']

    ast.parse(src)
    io.open(FLEET, 'w', encoding='utf-8', newline='').write(src)
    return src, notes


def patch_assistant():
    src = io.open(ASSIST, encoding='utf-8', newline='').read()
    if 'unavailable\\": true' in src or 'unavailable\\\\": true' in src:
        return 'outage instruction already present'
    anchor = '        if module and surface in _SCREEN_SURFACES:'
    at = src.find(anchor)
    if at < 0:
        return '!! _SCREEN_SURFACES anchor not found'
    src = src[:at] + PROMPT + src[at:]
    ast.parse(src)
    io.open(ASSIST, 'w', encoding='utf-8', newline='').write(src)
    return 'added the outage instruction'


def patch_tests():
    src = io.open(TESTS, encoding='utf-8', newline='').read()
    if 'test_an_unreachable_register_is_not_reported' in src:
        return 'outage tests already present'

    # _load() only lifts functions and consts; the exception is a class.
    if '_WANT_CLASSES' not in src:
        src = src.replace(
            "_WANT_CONSTS = (",
            "_WANT_CLASSES = ('FleetUnavailable',)\n_WANT_CONSTS = (", 1)
        src = src.replace(
            "        if isinstance(node, ast.FunctionDef) and node.name in _WANT_FUNCS:\n"
            "            body.append(node)",
            "        if isinstance(node, ast.FunctionDef) and node.name in _WANT_FUNCS:\n"
            "            body.append(node)\n"
            "        elif isinstance(node, ast.ClassDef) and node.name in _WANT_CLASSES:\n"
            "            body.append(node)", 1)
        src = src.replace("dispatch = NS['dispatch']",
                          "dispatch = NS['dispatch']\n"
                          "FleetUnavailable = NS['FleetUnavailable']", 1)
        # dispatch's handler logs through _warn; the extracted namespace has none.
        src = src.replace("NS = _load()",
                          "NS = _load()\nNS.setdefault('_warn', lambda *a, **k: None)", 1)

    marker = "if __name__ == '__main__':"
    at = src.find(marker)
    if at < 0:
        return '!! test runner block not found'
    src = src[:at] + TEST_BLOCK.strip('\n') + '\n\n\n' + src[at:]
    ast.parse(src)
    io.open(TESTS, 'w', encoding='utf-8', newline='').write(src)
    return 'added 3 outage regression tests'


def main():
    out, notes = patch_fleet()
    for n in notes:
        print('  ' + n)
    if out is None:
        return 1
    print('  ' + patch_assistant())
    print('  ' + patch_tests())
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
