#!/usr/bin/env python3
"""
test_eval_runner.py -- the two paths in waswa_eval_run.py that seven live
runs never executed.

  1. --base-url, the HTTP transport. Every run so far used
     app.test_client(), so the requests branch of ask() -- the URL it builds,
     the Authorization header, JSON parsing, a non-JSON body -- has never
     run once.

  2. The crash handler. It was added after a crash stranded rows in the
     database with no run file to find them by, and has not fired since.

Both are exercised here against a stub HTTP server and stub database, so
this needs no droplet, no model and no credentials, and can run on any
machine in under a second.

Run:
    python tests/test_eval_runner.py
"""

import json
import os
import sys
import threading
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS, FAIL = [], []


def check(name, got, want):
    (PASS if got == want else FAIL).append(
        name if got == want else '%s\n      got  %r\n      want %r'
        % (name, got, want))


def truthy(name, got):
    check(name, bool(got), True)


# --------------------------------------------------------------------------
# A stub assistant endpoint. Records what it was sent.
# --------------------------------------------------------------------------

class Stub(object):
    def __init__(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        self.seen = []
        self.mode = 'json'
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):          # silence
                pass

            def do_POST(self):
                length = int(self.headers.get('Content-Length') or 0)
                body = self.rfile.read(length).decode('utf-8')
                outer.seen.append({
                    'path': self.path,
                    'auth': self.headers.get('Authorization'),
                    'body': json.loads(body) if body else None,
                })
                if outer.mode == 'notjson':
                    payload = b'<html>gateway timeout</html>'
                    self.send_response(502)
                else:
                    payload = json.dumps({
                        'status': 'success', 'message': 'OK',
                        'data': {
                            'reply': 'You have no token packs yet.',
                            'conversation_uid': 'conv-%d' % len(outer.seen),
                            'message_uid': 'msg-%d' % len(outer.seen),
                            'evidence': [{'source_kind': 'account_context',
                                          'source_ref': 'waswa_context',
                                          'authority_level': 3}],
                        }}).encode('utf-8')
                    self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    @property
    def url(self):
        return 'http://127.0.0.1:%d' % self.port

    def stop(self):
        self.server.shutdown()


def load_runner():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'waswa_eval_run', os.path.join(ROOT, 'scripts', 'waswa_eval_run.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------

def test_http_transport(m, stub):
    status, payload, seconds = m.ask(
        None, stub.url, 'TOKEN-123', 'How many tokens do I have?', 'mobile')
    sent = stub.seen[-1]
    check('1a posts to the real route', sent['path'], '/assistant/chat')
    check('1b sends the token as a Bearer header',
          sent['auth'], 'Bearer TOKEN-123')
    check('1c wraps the question the way the route expects',
          sent['body'], {'data': {'message': 'How many tokens do I have?',
                                  'surface': 'mobile'}})
    check('1d returns the HTTP status', status, 200)
    check('1e parses the JSON body',
          payload['data']['reply'], 'You have no token packs yet.')
    truthy('1f times the call', seconds >= 0)

    # A gateway that answers HTML must not take the run down.
    stub.mode = 'notjson'
    status, payload, _ = m.ask(None, stub.url, 'T', 'q', 'mobile')
    stub.mode = 'json'
    check('1g a non-JSON body is reported, not raised', status, 502)
    truthy('1h and its text is kept for the record', payload.get('raw'))

    # The surface actually reaches the server, which is what --isolate-surface
    # depends on to keep away from real conversations.
    m.ask(None, stub.url, 'T', 'q', 'eval-oliwa_console')
    check('1i the surface is passed through',
          stub.seen[-1]['body']['data']['surface'], 'eval-oliwa_console')


def test_crash_writes_the_run_file(m, stub, tmp_out):
    """A crash mid-loop must still leave a run file naming every row it
    created, or those rows are unreachable by the cleanup script."""
    calls = {'n': 0}

    def exploding_build_context(uid, surface='mobile', conn=None):
        calls['n'] += 1
        if calls['n'] >= 2:
            raise RuntimeError('boom on the second account row')
        return {'known': {}, 'unknown': {}, 'scope': {}}

    fake_wc = types.ModuleType('endpoints.waswa_context')
    fake_wc.build_context = exploding_build_context
    pkg = types.ModuleType('endpoints'); pkg.__path__ = []
    sys.modules['endpoints'] = pkg
    sys.modules['endpoints.waswa_context'] = fake_wc

    fake_pg = types.ModuleType('psycopg2')

    class Cur(object):
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, q, p=None): self.rows = []
        def fetchall(self): return []
        def fetchone(self): return ('root', 'Customer', 'tracker')
        rowcount = 1

    class Conn(object):
        autocommit = True
        def cursor(self, **k): return Cur()
        def close(self): pass

    fake_pg.connect = lambda *a, **k: Conn()
    sys.modules['psycopg2'] = fake_pg
    cfg = types.ModuleType('config'); cfg.DB_LINK = 'stub'
    sys.modules['config'] = cfg

    jwt = types.ModuleType('endpoints.jwt_utils')
    jwt.create_access_token = lambda *a, **k: 'TOKEN'
    sys.modules['endpoints.jwt_utils'] = jwt

    sys.argv = ['x', '--base-url', stub.url, '--isolate-surface',
                '--only', 'fb-008,fb-009,fb-011', '--out', tmp_out]
    code = m.main()

    check('2a a crashed run exits non-zero', code, 1)
    truthy('2b the run file was written anyway', os.path.exists(tmp_out))
    with open(tmp_out, encoding='utf-8') as fh:
        run = json.load(fh)
    truthy('2c it records that it crashed', run.get('crashed'))
    truthy('2d and names the error',
           'boom on the second account row' in (run.get('crashed') or ''))
    created = run.get('created') or {}
    truthy('2e the rows created before the crash are recorded',
           len(created.get('conversations') or []) >= 1)
    check('2f every created conversation has a uid cleanup can target',
          all(bool(c) for c in created.get('conversations') or []), True)
    truthy('2g the completed row kept its result',
           any(r.get('id') == 'fb-008' for r in run.get('results') or []))


def main():
    m = load_runner()
    stub = Stub()
    tmp_out = os.path.join(ROOT, 'tests', 'waswa_eval', '_crashtest.json')
    try:
        test_http_transport(m, stub)
        test_crash_writes_the_run_file(m, stub, tmp_out)
    except Exception as error:                      # noqa: BLE001
        import traceback
        traceback.print_exc()
        FAIL.append('SUITE CRASHED: %s' % error)
    finally:
        stub.stop()

    for name in PASS:
        print('  ok   %s' % name)
    for name in FAIL:
        print('  FAIL %s' % name)
    print('')
    print('  %d passed, %d failed' % (len(PASS), len(FAIL)))
    if os.path.exists(tmp_out):
        print('  (left %s for inspection)' % tmp_out)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
