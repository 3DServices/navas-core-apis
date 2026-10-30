"""
waswa_data_client.py -- how the Waswa agent talks to the data API.

The agent holds a DataClient for one turn, built with the token minted for the
signed-in user. Every call goes through the full Flask stack of
/waswa/data/*: routing, the token check, the route's own ownership checks.

TRANSPORT
WASWA_DATA_API_URL set   -> HTTP to that server (the agent and the data API
                            can then be deployed apart).
unset (the default)      -> in-process, through the app's test client. Same
                            routes, same checks, no socket -- which is also
                            what keeps the eval harness, itself running on
                            app.test_client(), working without a server.

The in-process call runs in an EMPTY contextvars context. Flask reuses the
current app context for a nested request in the same app, and with it `g`,
so without this the data API's request would share the chat request's `g`:
its cached permissions, its pooled connections, and its teardown.

FAILURES
Each method raises DataApiError. The agent decides what a failure costs, and
for the bookkeeping writes it is a lost row, never a lost answer -- the same
policy the old in-process helpers had.
"""

import contextvars
import os

import requests
from flask import current_app

_TIMEOUT_SECONDS = 60


class DataApiError(Exception):
    def __init__(self, status, message):
        super().__init__('%s %s' % (status, message))
        self.status = status
        self.message = message


class DataClient:
    def __init__(self, token, base_url=None, app=None):
        self._token = token
        self._base_url = (base_url if base_url is not None
                          else os.environ.get('WASWA_DATA_API_URL', '')).rstrip('/')
        self._app = app if app is not None else (
            None if self._base_url else current_app._get_current_object())

    # ── transport ───────────────────────────────────────────────────────

    def _call(self, method, path, json=None, params=None):
        headers = {'Authorization': 'Bearer %s' % self._token}
        url_path = '/waswa/data' + path
        if self._base_url:
            try:
                resp = requests.request(
                    method, self._base_url + url_path, json=json,
                    params=params, headers=headers, timeout=_TIMEOUT_SECONDS)
            except requests.RequestException as error:
                raise DataApiError(0, '%s: %s' % (error.__class__.__name__,
                                                  error))
            status = resp.status_code
            try:
                payload = resp.json()
            except ValueError:
                payload = {'message': resp.text[:300]}
        else:
            def _in_process():
                r = self._app.test_client().open(
                    url_path, method=method, json=json,
                    query_string=params, headers=headers)
                return r.status_code, (r.get_json(silent=True) or {})
            status, payload = contextvars.Context().run(_in_process)

        if status >= 400:
            raise DataApiError(status, (payload or {}).get('message') or '')
        return (payload or {}).get('data')

    # ── who and what ───────────────────────────────────────────────────

    def audience(self):
        return self._call('GET', '/caller')['audience']

    def context(self, surface):
        """{'scope', 'rendered', 'zero_state_note', 'unknown'}"""
        return self._call('GET', '/context', params={'surface': surface})

    def prompt(self):
        """(body, version). Raises when there is no active prompt."""
        data = self._call('GET', '/prompt')
        return data['body'], data['version']

    # ── conversation record ───────────────────────────────────────────

    def open_conversation(self, surface, requested_uid=None):
        return self._call('POST', '/conversations', json={
            'surface': surface, 'conversation_uid': requested_uid,
        })['conversation_uid']

    def history(self, conversation_uid, limit):
        return self._call('GET', '/conversations/%s/messages' % conversation_uid,
                          params={'limit': limit})['messages']

    def record_turn(self, conversation_uid, role, content, **fields):
        body = dict(fields, role=role, content=content)
        return self._call('POST', '/conversations/%s/messages' % conversation_uid,
                          json=body)['message_uid']

    def record_evidence(self, message_uid, items):
        self._call('POST', '/messages/%s/evidence' % message_uid,
                   json={'items': [list(item) for item in items]})

    def log_transparency(self, conversation_uid, entry_type, message_uid=None,
                         action=None, rationale=None):
        self._call('POST', '/conversations/%s/transparency' % conversation_uid,
                   json={'entry_type': entry_type, 'message_uid': message_uid,
                         'action': action, 'rationale': rationale})

    # ── knowledge diagnostics ─────────────────────────────────────────

    def knowledge_sources(self):
        return self._call('GET', '/knowledge/sources')

    def knowledge_search(self, query, product=None, document_type=None,
                         limit=None, include_unapproved=False):
        """The API decides whether include_unapproved is honoured."""
        return self._call('POST', '/knowledge/search', json={
            'query': query, 'product': product, 'document_type': document_type,
            'limit': limit, 'include_unapproved': include_unapproved})

    # ── answers and tools ─────────────────────────────────────────────

    def match_answers(self, question):
        """{'verified': [...], 'rendered': str or None}"""
        return self._call('POST', '/answers/match', json={'question': question})

    def tool(self, name, arguments, strict=False):
        """{'owner': 'fleet'|'knowledge'|'products', 'result': ...}.

        strict: a fleet read that could not reach the register raises
        DataApiError with status 503 instead of returning an explanation.
        """
        return self._call('POST', '/tools/%s' % name,
                          json={'arguments': arguments or {}, 'strict': strict})
