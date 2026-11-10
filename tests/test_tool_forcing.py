"""tests/test_tool_forcing.py — prove the forcing, don't assume it.

Four account-data questions once produced zero tool calls. From the outside that
is indistinguishable between three causes: the gate decided not to force, the
code never put tool_choice in the payload, or OpenRouter ignored it. Reasoning
about which was happening wasted a round trip, so this settles the first two
here, offline, with no network, no database and no Flask.

What is left over after this passes is exactly one possibility, and the Flask
log answers it: the request went out with tool_choice=required and the model
ignored it.

_call_model is compiled out of assistant.py and run against a fake transport
that records the payload. The real function, the real gate, the real payload —
only the socket is pretend.

Run:  python tests/test_tool_forcing.py   (or via pytest)
"""

from __future__ import annotations

import ast
import io
import os
import re
import time

_SOURCE = os.path.join(os.path.dirname(__file__), '..', 'endpoints', 'assistant.py')

_WANT_FUNCS = ('_call_model', '_needs_lookup', '_plate_or_imei')
_WANT_CONSTS = ('_NO_LOOKUP', '_CONNECT_RETRIES', '_RETRY_BACKOFF',
                '_OPENROUTER_FAILURES', '_FLEET_QUESTION')


class _Response:
    """What a contented OpenRouter looks like."""

    status_code = 200
    text = ''

    def __init__(self, payload=None):
        self._payload = payload or {
            'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}]
        }

    def json(self):
        return self._payload


class _Transport:
    """Stands in for `requests`, and keeps what it was handed."""

    class Timeout(Exception):
        pass

    class RequestException(Exception):
        pass

    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({'url': url, 'headers': headers, 'json': json})
        return _Response()

    @property
    def last(self):
        return self.calls[-1]['json']


def _load():
    tree = ast.parse(io.open(_SOURCE, encoding='utf-8').read())
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _WANT_FUNCS:
            body.append(node)
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(n in _WANT_CONSTS for n in names):
                body.append(node)

    present = {n.name for n in body if isinstance(n, ast.FunctionDef)}
    missing = set(_WANT_FUNCS) - present
    assert not missing, f'assistant.py no longer defines {missing}'

    transport = _Transport()
    ns = {
        're': re, 'time': time, 'requests': transport,
        # Config, stubbed: none of it is secret and none of it is under test.
        'OPENROUTER_URL': 'https://openrouter.test/v1/chat/completions',
        'OPENROUTER_MODEL': 'openai/gpt-4o',
        'OPENROUTER_API_KEY': 'test-key-not-a-real-one',
        'OPENROUTER_SITE_URL': 'https://example.test',
        'OPENROUTER_SITE_NAME': 'test',
        # Two declared tools is enough to prove tools are sent at all.
        '_TOOL_SPECS': [
            {'type': 'function', 'function': {'name': 'unit_find'}},
            {'type': 'function', 'function': {'name': 'knowledge_search'}},
        ],
        '_log': lambda *a, **k: None,
        '_openrouter_error_detail': lambda resp: '',
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), _SOURCE, 'exec'), ns)
    return ns, transport


NS, TRANSPORT = _load()
_call_model = NS['_call_model']
_needs_lookup = NS['_needs_lookup']
_plate_or_imei = NS['_plate_or_imei']
_fleet_question = NS['_FLEET_QUESTION']

MESSAGES = [{'role': 'user', 'content': 'why is UBF 364U offline?'}]


# ── Does the payload carry the forcing? ─────────────────────────────────────

def test_forcing_puts_tool_choice_required_in_the_payload():
    out = _call_model(MESSAGES, force_tools=True)
    assert out['status'] == 'ok', out
    assert TRANSPORT.last['tool_choice'] == 'required', TRANSPORT.last


def test_without_forcing_the_model_is_left_to_choose():
    _call_model(MESSAGES, force_tools=False)
    assert 'tool_choice' not in TRANSPORT.last, (
        "an unforced turn must stay on 'auto' — forcing a tool call on "
        '"thanks" wastes a round and confuses the model')


def test_the_final_answer_round_forbids_tools():
    # When the tool budget runs out the model must answer from what it already
    # fetched, not ask for more.
    _call_model(MESSAGES, allow_tools=False)
    assert TRANSPORT.last['tool_choice'] == 'none'


def test_the_tools_are_actually_declared():
    _call_model(MESSAGES, force_tools=True)
    names = [t['function']['name'] for t in TRANSPORT.last['tools']]
    assert 'unit_find' in names and 'knowledge_search' in names
    # "required" with no tools declared would be a 400 from OpenRouter.
    assert TRANSPORT.last['tools'], 'required with no tools is a hard error'


def test_the_room_to_answer_is_not_600_tokens():
    # A fleet answer naming a unit, its last report and why it is dark does not
    # fit in 600, and a truncated answer reads to a customer as a wrong one.
    _call_model(MESSAGES, force_tools=True)
    assert TRANSPORT.last['max_tokens'] >= 1200


# ── Does the gate fire for the questions that were failing? ─────────────────

# Exactly the four from the run that produced zero tool calls, plus the two the
# gate must leave alone.
FORCED = (
    'How do tracking tokens work?',
    'How do I contact support?',
    'Why is UBF 364U offline?',
    'How many trips did UBJ 916W make this week?',
    'where is UBK 415T right now?',
    'How many tokens do I have?',
    'Explain my charges',
)
LEFT_ALONE = ('hi', 'thanks!', 'ok', 'Good morning', 'yes', 'bye')


def test_every_question_that_failed_now_forces_a_lookup():
    for question in FORCED:
        assert _needs_lookup(question) is True, question


def test_pleasantries_are_not_forced():
    for greeting in LEFT_ALONE:
        assert _needs_lookup(greeting) is False, greeting


def test_the_gate_and_the_payload_agree_end_to_end():
    """The call site is force_tools=(_round == 0 and must_look_up). Compose the
    same expression here, so a gate that says yes provably becomes a payload
    that says required."""
    for question in FORCED:
        for round_index in (0, 1):
            _call_model([{'role': 'user', 'content': question}],
                        force_tools=(round_index == 0
                                     and _needs_lookup(question)))
            sent = TRANSPORT.last.get('tool_choice')
            if round_index == 0:
                assert sent == 'required', (question, sent)
            else:
                # Later rounds must not keep forcing, or the model can never
                # stop calling tools and say the answer.
                assert sent is None, (question, sent)


def test_a_greeting_never_forces_even_on_the_first_round():
    _call_model([{'role': 'user', 'content': 'hello'}],
                force_tools=(0 == 0 and _needs_lookup('hello')))
    assert TRANSPORT.last.get('tool_choice') is None


# ── What gets read before the model is asked ────────────────────────────────

def test_a_named_plate_is_picked_out():
    # These are the real plates on the account that was tested.
    assert _plate_or_imei('Why is UBF 364U offline?') == 'UBF 364U'
    assert _plate_or_imei('trips for UBJ916W this week') == 'UBJ916W'
    assert _plate_or_imei('where is UBK 415T right now?') == 'UBK 415T'


def test_an_imei_is_preferred_over_anything_plate_shaped():
    assert _plate_or_imei('where is 350317173603857') == '350317173603857'


def test_no_vehicle_named_is_not_a_guess():
    assert _plate_or_imei('how many units are online') is None
    assert _plate_or_imei('How many tokens do I have?') is None


def test_only_vehicle_questions_trigger_a_fleet_read():
    for q in ('Why is UBF 364U offline?', 'how many units are online',
              'how many trips this week', 'where is my lorry'):
        assert _fleet_question.search(q), q


def test_balance_and_document_questions_do_not_read_the_fleet():
    # _needs_lookup is true for these — they still need a lookup — but reading
    # the vehicle register for "what is my balance" would be two wasted queries.
    for q in ('How many tokens do I have?', 'Explain my charges',
              'How do I contact support?', 'How do tracking tokens work?'):
        assert _needs_lookup(q) is True, q
        assert not _fleet_question.search(q), q


if __name__ == '__main__':
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            passed += 1
            print('  ok  ' + name)
    print(f'{passed}/{passed} passed')
