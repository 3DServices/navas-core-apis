#!/usr/bin/env python3
"""
dashboard_latency_probe.py -- why does the OLIWA dashboard show zeros?

THE OBSERVATION (measured in Chrome against her local backend, 2026-10-09):

The console dashboard renders "0 devices, 0 tokens, 0 transactions" under the
banner "Some figures couldn't be loaded (devices, balance, transactions)",
while Waswa, on the SAME backend and the SAME account, correctly answers
"234 token packs, 120 units, 1 vehicle online".

The dashboard is not getting an error from the backend. Every one of its
calls eventually returned 200:

    POST /devices/configured/all                     200
    GET  /tokens/<account>/balance                   200
    GET  /payments/transactions/<account>/list       200

What it is getting is its own client-side timeout. AegisDashboardPage.tsx:40
aborts at 10s and logs "[Dashboard] devices failed: Error: timeout". The
browser's Resource Timing said why:

    /auth/refresh                        11,798 ms   (and once 503)
    /notifications/<acct>/unread-count    8,911 ms
    /users/<uid>/details                 12,319 ms
    the three dashboard calls            12,608 .. 39,104 ms

So the frontend is innocent and the figures are not wrong -- they never
arrive. The backend answers correctly, 2-4x too late.

WHAT THIS SCRIPT IS FOR. The obvious explanations are both already dead:

  * Not query count. /notifications/<acct>/unread-count runs exactly ONE
    SQL statement and took 16,208 ms when fired completely alone, with no
    other request in flight.
  * Not request concurrency, for the same reason -- that 16s request was
    the only one running. And not the WSGI server: Flask's app.run()
    defaults threaded=True (verified: flask 3.1.3 / werkzeug 3.1.9,
    options.setdefault("threaded", True)).

One SQL statement, alone, 16 seconds. That means the cost is FIXED per
request and sits somewhere other than the query. The candidates, and this
script separates them:

  1. CONNECT. There is no connection pool in this codebase. Every request
     opens one or more fresh psycopg2 connections to a remote Postgres
     (165.232.128.208, previously measured at 282 ms RTT), and the access
     guard's permission loader (globals.py:260) opens another on top of the
     endpoint's own. If connect() is seconds rather than ~1.4s, and several
     happen per request, that is the whole 16 seconds and the fix is
     pooling, not SQL.

  2. THE QUERY ITSELF, over a 282 ms link.

  3. APP TIME outside both -- a guard, an import, a Cassandra attempt.

Phase 2 measures 1 against 1+2+3 directly, per route, by counting and timing
every psycopg2.connect() made while the request runs. Whatever fraction of
the request is inside connect() is the fraction that pooling removes.

THIS IS B7, SURFACING AS A PRODUCT DEFECT. scripts/audit_pg_connections.py
already established the mechanism: "three connections per request, 2.32s each
in the profile", because an endpoint opens one connection and the helpers it
calls each open their own. B7 cut that from three to two -- counted, on both a
successful and a failing request -- but the pool it identified as the fix
("a module-level pool fixes every call site at once with no signature
changes") was never added, and there is still none in the codebase.

So the open half of B7 is what the dashboard is showing the user. What this
script adds to that ticket is the per-connect cost TODAY: the profile behind
B7 measured 2.32s, and the browser timings above imply something closer to
8s. If phase 1 confirms that, the ticket has got worse on its own while
sitting open, which is a fact about the host and belongs in the same report.

Phase 1 characterises the host first, because scripts/audit_db_host_health.py
already found this box misbehaving once: Postgres dropping connections mid
request, Cassandra timing out its handshake, and max_connections reporting
50,000 -- a value that makes a server fail in confusing ways rather than
cleanly refusing. A connect() that is slow because the server is thrashing is
a host ticket, not an application one, and this phase is what tells those
apart.

READ-ONLY. Issues only SELECTs, opens and closes its own connections,
terminates nobody else's, writes no file, and prints no secret: the DSN is
never echoed, only its host and database name.

Phase 2 runs in-process through app.test_client(), the convention these
route checks already use (b2, b3, b3c, b4, b10). That exercises routing,
before_request, the access guard and the JWT decode -- everything the real
request does except the socket to Flask, which the browser timings above
already measured. The patch it installs only counts and times; it returns
the real connection untouched, so no request behaves differently because
the probe is watching.

Usage:
    python scripts/dashboard_latency_probe.py
    python scripts/dashboard_latency_probe.py --account NzQwNTk0NzI2NzA5NTM5NjQz
    python scripts/dashboard_latency_probe.py --phase 1
    python scripts/dashboard_latency_probe.py --connects 5 --rtt 10
"""

import argparse
import socket
import statistics
import sys
import time
import urllib.parse

sys.path.insert(0, '.')

# The account the dashboard was showing zeros for, in the browser session
# where this was observed.
DEFAULT_ACCOUNT = 'NzQwNTk0NzI2NzA5NTM5NjQz'

# The frontend's own abort threshold (AegisDashboardPage.tsx:40). Any route
# slower than this cannot reach the dashboard no matter what it returns.
FRONTEND_TIMEOUT_S = 10.0


def heading(text):
    print()
    print(text)
    print('-' * len(text))


def ms(seconds):
    return '%8.0f ms' % (seconds * 1000.0)


# ---------------------------------------------------------------- phase 1

def dsn_parts(link):
    """Host, port and dbname from the DSN. Never returns user or password."""
    try:
        parsed = urllib.parse.urlparse(link)
        if parsed.hostname:
            return parsed.hostname, parsed.port or 5432, parsed.path.lstrip('/')
    except Exception:                                      # noqa: BLE001
        pass
    # key=value DSN form
    fields = {}
    for piece in str(link).split():
        if '=' in piece:
            key, _, value = piece.partition('=')
            fields[key.strip()] = value.strip()
    return (fields.get('host', '?'), int(fields.get('port', 5432) or 5432),
            fields.get('dbname', '?'))


def phase_one(link, connects, rtt_samples):
    import psycopg2

    host, port, dbname = dsn_parts(link)
    heading('PHASE 1  the host: %s:%s db=%s' % (host, port, dbname))

    # DNS. An IP literal costs nothing; a name that resolves slowly would be
    # paid on every single connect, so it is worth ruling out explicitly.
    times = []
    for _ in range(3):
        began = time.perf_counter()
        try:
            socket.getaddrinfo(host, port)
            times.append(time.perf_counter() - began)
        except Exception as error:                         # noqa: BLE001
            print('   DNS resolve FAILED: %s' % error)
            return None
    print('   DNS resolve      x3   median %s' % ms(statistics.median(times)))

    # Raw TCP. This is one round trip plus the handshake: the floor that no
    # application change can go under.
    tcp = []
    for _ in range(min(connects, 5)):
        began = time.perf_counter()
        try:
            socket.create_connection((host, port), timeout=15).close()
            tcp.append(time.perf_counter() - began)
        except Exception as error:                         # noqa: BLE001
            print('   TCP connect FAILED: %s: %s' % (type(error).__name__, error))
            return None
    print('   TCP connect      x%-2d  median %s   min %s   max %s'
          % (len(tcp), ms(statistics.median(tcp)), ms(min(tcp)), ms(max(tcp))))

    # psycopg2 connect: TCP, then the startup packet, authentication and the
    # initial parameter exchange. This is what every request pays, every time,
    # because nothing here is pooled.
    pg = []
    failures = []
    for index in range(connects):
        began = time.perf_counter()
        try:
            conn = psycopg2.connect(link)
            pg.append(time.perf_counter() - began)
            conn.close()
        except Exception as error:                         # noqa: BLE001
            failures.append('%s: %s' % (type(error).__name__, error))
    if pg:
        print('   psycopg2.connect x%-2d  median %s   min %s   max %s'
              % (len(pg), ms(statistics.median(pg)), ms(min(pg)), ms(max(pg))))
        overhead = statistics.median(pg) - statistics.median(tcp)
        print('        of which after TCP:  %s  (startup + auth)' % ms(overhead))
    if failures:
        print('   !! %d of %d connects FAILED -- the host is refusing or '
              'dropping connections:' % (len(failures), connects))
        for text in failures[:3]:
            print('        %s' % text)
    if not pg:
        return None

    # True round-trip time on an already-open connection. Everything slower
    # than this, per statement, is the server doing work.
    conn = psycopg2.connect(link)
    try:
        cur = conn.cursor()
        rtt = []
        for _ in range(rtt_samples):
            began = time.perf_counter()
            cur.execute('SELECT 1')
            cur.fetchone()
            rtt.append(time.perf_counter() - began)
        print('   SELECT 1         x%-2d  median %s   min %s   max %s'
              % (len(rtt), ms(statistics.median(rtt)), ms(min(rtt)), ms(max(rtt))))

        # Host state. Uptime in minutes rather than days means it restarted,
        # which is what "server closed the connection unexpectedly" looks
        # like from the client side.
        cur.execute("SELECT date_trunc('second', now() - "
                    "pg_postmaster_start_time())::text, "
                    "current_setting('max_connections'), "
                    "(SELECT count(*) FROM pg_stat_activity), "
                    "(SELECT count(*) FROM pg_stat_activity "
                    "  WHERE state = 'active')")
        uptime, max_conn, total, active = cur.fetchone()
        print('   postgres uptime      %s' % uptime)
        print('   connections          %s in use (%s active) of '
              'max_connections=%s' % (total, active, max_conn))
        if str(max_conn).isdigit() and int(max_conn) > 500:
            print('        !! max_connections=%s is not a plausible '
                  'deliberate setting. A server sized this way fails in '
                  'confusing ways instead of refusing cleanly.' % max_conn)
        cur.close()
    finally:
        conn.close()

    return {'tcp': statistics.median(tcp), 'connect': statistics.median(pg),
            'rtt': statistics.median(rtt)}


# ---------------------------------------------------------------- phase 2

class ConnectCounter:
    """Counts and times every psycopg2.connect() made while installed.

    It returns the REAL connection object, unwrapped and unmodified. Nothing
    about a request changes because this is watching -- the only cost is a
    perf_counter read on either side of a call the request was making anyway.
    """

    def __init__(self):
        import psycopg2
        self._psycopg2 = psycopg2
        self._original = psycopg2.connect
        self.calls = []
        self.sites = []
        self.failures = []

    def __enter__(self):
        def timed(*args, **kwargs):
            # Name the caller. "3 connections" is a number; "3 connections,
            # and here is the file and line of each" is something you can act
            # on. The frame two below this one is the application code that
            # asked for a connection.
            import traceback
            site = '?'
            for frame in reversed(traceback.extract_stack()[:-1]):
                if 'dashboard_latency_probe' in frame.filename:
                    continue
                name = frame.filename.replace('\\', '/').split('/')[-1]
                site = '%s:%d in %s()' % (name, frame.lineno, frame.name)
                break
            began = time.perf_counter()
            try:
                conn = self._original(*args, **kwargs)
            except Exception as error:                     # noqa: BLE001
                self.failures.append('%s: %s' % (type(error).__name__, error))
                raise
            elapsed = time.perf_counter() - began
            self.calls.append(elapsed)
            self.sites.append((site, elapsed))
            return conn
        self._psycopg2.connect = timed
        return self

    def __exit__(self, *_):
        self._psycopg2.connect = self._original
        return False

    def reset(self):
        self.calls = []
        self.sites = []
        self.failures = []

    @property
    def total(self):
        return sum(self.calls)


def candidate_forms(value):
    """The account identifier as the DB might actually hold it.

    The console puts NzQwNTk0NzI2NzA5NTM5NjQz in its URLs, which is base64 for
    740594726709539643. Which of the two dll_access_relay stores is a question
    about the data, not something to assume: the first run of this probe
    assumed the URL form and reported "no dll_access_relay row", which is a
    lookup that missed, not an account that does not exist.

    So try both and say which one matched. If the URL form is NOT what
    dll_access_relay holds, that is worth knowing on its own -- it means the
    frontend is sending an encoded identifier to routes that compare it
    against unencoded columns.
    """
    import base64
    forms = [('as given', str(value))]
    try:
        decoded = base64.b64decode(str(value), validate=True).decode('ascii')
        if decoded and decoded != str(value):
            forms.append(('base64-decoded', decoded))
    except Exception:                                      # noqa: BLE001
        pass
    try:
        encoded = base64.b64encode(str(value).encode('ascii')).decode('ascii')
        if encoded != str(value):
            forms.append(('base64-encoded', encoded))
    except Exception:                                      # noqa: BLE001
        pass
    return forms


def locate_identifier(link, value):
    """Find which column actually holds the identifier the console sends.

    All three guessed forms missed dll_access_relay.account_uid, so guessing is
    over. This asks the database instead: for every text-shaped column on
    dll_access_relay, does any row equal this value? Then the same question for
    the specific columns the dashboard routes compare it against.

    dll_access_relay is small and this runs once, so a column scan is cheaper
    than another round of assumptions. Password columns are excluded by name
    and never read.

    Returns (relay_hits, route_hits) -- each a list of (table, column, count).
    """
    import psycopg2

    skip = ('password', 'passwd', 'secret', 'token', 'hash')
    relay_hits = []
    route_hits = []

    conn = psycopg2.connect(link)
    try:
        conn.autocommit = True        # one bad column must not abort the rest
        cur = conn.cursor()
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'dll_access_relay' ORDER BY ordinal_position")
        columns = [(name, kind) for name, kind in cur.fetchall()
                   if not any(word in name.lower() for word in skip)]
        print('   dll_access_relay has %d columns (%d searchable)'
              % (len(columns) + 1, len(columns)))

        for name, kind in columns:
            if kind not in ('text', 'character varying', 'character',
                            'bigint', 'integer', 'numeric', 'uuid'):
                continue
            try:
                cur.execute(
                    'SELECT COUNT(*) FROM dll_access_relay '
                    'WHERE %s::text = %%s' % psycopg2.extensions.quote_ident(
                        name, cur), (str(value),))
                count = cur.fetchone()[0]
                if count:
                    relay_hits.append(('dll_access_relay', name, count))
            except Exception:                              # noqa: BLE001
                continue

        # The columns these routes ACTUALLY key on, read from the routes
        # themselves rather than guessed. The first version of this list said
        # dll_payment_logs.payment_owner and reported "0 rows -- this route
        # would answer with nothing even if it were fast". That was a defect
        # in the probe, not in the route: finance.py:332 queries
        # payment_account, and only after resolve_wallet_owner() has widened
        # the identifier to the whole account family. A straight equality test
        # on the wrong column answers a question nobody asked.
        #
        # These three are the right columns, but a direct '= value' here is
        # still only indicative for the two routes that resolve first. The
        # real test is phase 2 calling the route.
        for table, column in (('dll_event_notifications', 'owner_uid'),
                              ('dll_user_token_accounts', 'client_uid'),
                              ('dll_payment_logs', 'payment_account')):
            try:
                cur.execute('SELECT COUNT(*) FROM %s WHERE %s::text = %%s'
                            % (psycopg2.extensions.quote_ident(table, cur),
                               psycopg2.extensions.quote_ident(column, cur)),
                            (str(value),))
                route_hits.append((table, column, cur.fetchone()[0]))
            except Exception as error:                     # noqa: BLE001
                route_hits.append((table, column,
                                   'could not read: %s'
                                   % str(error).strip().splitlines()[0]))
        cur.close()
    finally:
        conn.close()
    return relay_hits, route_hits


def report_identifier(link, account):
    """Say where the console's identifier lives, and what that means."""
    heading('WHERE THE CONSOLE\'S IDENTIFIER ACTUALLY LIVES')
    print('   searching for: %s' % account)
    relay_hits, route_hits = locate_identifier(link, account)

    print()
    if relay_hits:
        for table, column, count in relay_hits:
            print('   FOUND  %s.%s  (%d row(s))' % (table, column, count))
    else:
        print('   NOT FOUND in any searchable dll_access_relay column.')
        print('   So this value is not an account key in the access table at')
        print('   all -- it is something the console derived. Minting a token')
        print('   for it is impossible by definition, which is what the three')
        print('   failed attempts above were really saying.')

    print()
    print('   the columns the dashboard routes compare it against:')
    for table, column, count in route_hits:
        if isinstance(count, str):
            print('      %-28s %-16s %s' % (table, column, count))
        elif count:
            print('      %-28s %-16s %d row(s) MATCH' % (table, column, count))
        else:
            print('      %-28s %-16s 0 rows on a DIRECT match' % (table, column))
            print('      %-28s %-16s (not a verdict: the route resolves the'
                  % ('', ''))
            print('      %-28s %-16s identifier first -- phase 2 decides)'
                  % ('', ''))
    return relay_hits


class QueryCounter:
    """Counts and times every statement, and names the line that ran it.

    Connection setup is solved -- the pool took it to zero. What is left on
    these routes is queries, and the same question applies: not "how long"
    but "how many, and from where". At 282 ms a round trip, a route spending
    4 seconds outside connect() is running roughly fourteen statements, and
    knowing which fourteen is the whole of the next decision.

    The mechanism is psycopg2's documented extension point -- a cursor
    subclass installed as the connection's cursor_factory -- rather than a
    monkeypatch of the C type, which is not possible. A call site that asks
    for its own cursor_factory (RealDictCursor and friends) keeps it and is
    simply not counted; the total says so.

    OPT-IN (--queries), because unlike the connect counter this one does
    change the measured run: it installs a different cursor class. It is also
    wrapped so that if anything about it misbehaves, the run continues
    without query data instead of failing.
    """

    def __init__(self):
        self.rows = []          # (site, seconds)
        self._active = False

    def _cursor_class(self):
        import psycopg2.extensions
        counter = self

        class CountingCursor(psycopg2.extensions.cursor):
            def execute(self, query, vars=None):
                began = time.perf_counter()
                try:
                    return super().execute(query, vars)
                finally:
                    counter._record(time.perf_counter() - began)

            def executemany(self, query, vars_list):
                began = time.perf_counter()
                try:
                    return super().executemany(query, vars_list)
                finally:
                    counter._record(time.perf_counter() - began)

        return CountingCursor

    def _record(self, elapsed):
        if not self._active:
            return
        import traceback
        site = '?'
        for frame in reversed(traceback.extract_stack()[:-2]):
            name = frame.filename.replace('\\', '/').split('/')[-1]
            if name in ('dashboard_latency_probe.py',) or 'psycopg2' in name:
                continue
            site = '%s:%d in %s()' % (name, frame.lineno, frame.name)
            break
        self.rows.append((site, elapsed))

    def arm(self, conn):
        """Install the counting cursor on a connection just handed out."""
        try:
            conn.cursor_factory = self._cursor_class()
        except Exception:                                  # noqa: BLE001
            pass

    def reset(self):
        self.rows = []

    def start(self):
        self._active = True

    def stop(self):
        self._active = False

    @property
    def total(self):
        return sum(t for _, t in self.rows)

    def by_site(self):
        grouped = {}
        for site, took in self.rows:
            count, total = grouped.get(site, (0, 0.0))
            grouped[site] = (count + 1, total + took)
        return sorted(grouped.items(), key=lambda kv: -kv[1][1])


def mint_token(link, account_uid):
    """A real access token for this account, claims as /users/auth sets them.

    Returns (token, account_uid_that_matched, how_it_matched, problem).
    """
    import psycopg2
    from endpoints.jwt_utils import create_access_token
    conn = psycopg2.connect(link)
    tried = []
    try:
        cur = conn.cursor()
        for how, form in candidate_forms(account_uid):
            cur.execute(
                'SELECT account_root, account_type, account_clearance '
                'FROM dll_access_relay WHERE account_uid = %s', (form,))
            row = cur.fetchone()
            tried.append((how, form, bool(row)))
            if row:
                cur.close()
                root, acct_type, clearance = row
                return (create_access_token(form, clearance, acct_type, root),
                        form, how, None)
        # The console does not send an account_uid at all. It sends the
        # ACCOUNT ROOT -- dll_access_relay.account_root, which is the
        # client_uid, the thing that actually owns the data. That is the
        # correct identifier for these routes, not a bug: /tokens/.../balance
        # and /payments/transactions/.../list both widen it with
        # resolve_wallet_owner() before they query anything.
        #
        # So to authenticate we need any one login under that root.
        for how, form in candidate_forms(account_uid):
            # access_status matters: the guard's permission loader selects
            # "WHERE account_uid = %s AND access_status = 'active'", and an
            # inactive login makes every route answer 401 before it does any
            # work. The first version of this picked an arbitrary login and
            # measured two 401s as if they were real route timings.
            cur.execute(
                'SELECT account_uid, account_type, account_clearance '
                'FROM dll_access_relay WHERE account_root = %s '
                "  AND access_status = 'active' "
                'ORDER BY account_uid LIMIT 1', (form,))
            row = cur.fetchone()
            if row:
                uid, acct_type, clearance = row
                cur.close()
                return (create_access_token(uid, clearance, acct_type, form),
                        uid, 'account_root (%s) -- authenticating as one of '
                        'its logins' % how, None)
        cur.close()
    finally:
        conn.close()
    detail = '; '.join('%s (%s): no row' % (h, f) for h, f, _ in tried)
    return None, None, None, ('not an account_uid and not an account_root -- '
                              'tried %s' % detail)


def phase_two(link, account, baseline=None, warm=True,
              count_queries=False):
    heading('PHASE 2  where the time goes, per route')

    from app import app
    from endpoints import db_pool

    if warm:
        # Measure a WARM pool, which is the steady state the application runs
        # in. Measuring while it is still building would time direct
        # connections and report that the pool does nothing.
        print('   warming the pool ...', end=' ', flush=True)
        began = time.perf_counter()
        db_pool.start_warmup(link)
        deadline = began + 90
        while time.perf_counter() < deadline:
            if db_pool.stats()['state'] in ('ready', 'failed', 'off'):
                break
            time.sleep(0.25)
        state = db_pool.stats()
        print('%s after %.1fs (%d warm, ceiling %d)'
              % (state['state'], time.perf_counter() - began,
                 state['warm_size'], state['ceiling']))
        if state['state'] != 'ready':
            print('        !! the pool is %s, so the figures below are'
                  % state['state'])
            print('           direct connections -- i.e. the OLD behaviour.')
    else:
        print('   pool: %s (not warmed by this run)'
              % db_pool.stats()['state'])

    before_stats = db_pool.stats()

    token, matched, how, problem = mint_token(link, account)
    if problem:
        print('   cannot mint a token: %s' % problem)
        report_identifier(link, account)
        print()
        print('   Phase 2 needs a real account to authenticate as. Re-run with')
        print('   --account <the account_uid from dll_access_relay> once the')
        print('   lines above say which value that is.')
        return
    print('   dll_access_relay holds the account as: %s' % how)
    if 'account_root' in str(how):
        print('        The console sends the ACCOUNT ROOT -- the client_uid,')
        print('        which is what owns the data. That is the right')
        print('        identifier, not a bug: /tokens/.../balance and')
        print('        /payments/.../list both widen it with')
        print('        resolve_wallet_owner() before querying. A token just')
        print('        has to be minted for a login underneath it.')
    print('   paths below use the console\'s own form, as the browser sends it')
    headers = {'Authorization': 'Bearer %s' % token}
    client = app.test_client()

    # The four calls the console fires on load. The first is not a dashboard
    # figure but it is on the same path and the browser timed it at 8.9s, so
    # it is the cheapest possible control: one SQL statement, no Cassandra.
    routes = [
        ('GET',  '/notifications/%s/unread-count' % account, None,
         'control: 1 SQL statement'),
        ('GET',  '/tokens/%s/balance' % account, None,
         'dashboard: tokens'),
        ('GET',  '/payments/transactions/%s/list' % account, None,
         'dashboard: transactions'),
        ('POST', '/devices/configured/all',
         {'data': {'data_level': 'client', 'account_uid': account}},
         'dashboard: devices (also reads Cassandra)'),
    ]

    print('   %-46s %10s %10s %10s  %5s' %
          ('route', 'total', 'in connect', 'elsewhere', 'conn'))
    print('   %s' % ('-' * 86))

    rows = []
    counter = ConnectCounter()
    queries = QueryCounter() if count_queries else None
    if queries is not None:
        # Wrap db_pool.connect as well: with the pool warm, almost nothing
        # reaches psycopg2.connect any more, so arming only there would see
        # no queries at all.
        _pool_connect = db_pool.connect

        def _armed(*a, **kw):
            conn = _pool_connect(*a, **kw)
            queries.arm(conn)
            return conn
        db_pool.connect = _armed

    with counter:
        for method, path, payload, note in routes:
            counter.reset()
            if queries is not None:
                queries.reset()
                queries.start()
            began = time.perf_counter()
            try:
                if method == 'POST':
                    res = client.post(path, json=payload, headers=headers)
                else:
                    res = client.get(path, headers=headers)
                status = res.status_code
            except Exception as error:                     # noqa: BLE001
                status = 'EXC %s' % type(error).__name__
            elapsed = time.perf_counter() - began
            if queries is not None:
                queries.stop()
            connect_time = counter.total
            query_rows = queries.by_site() if queries is not None else []
            query_total = queries.total if queries is not None else 0.0
            query_count = len(queries.rows) if queries is not None else 0
            rows.append((path, note, status, elapsed, connect_time,
                         len(counter.calls), list(counter.failures),
                         list(counter.sites),
                         (query_count, query_total, query_rows)))
            label = path if len(path) <= 46 else path[:43] + '...'
            print('   %-46s %8.0f ms %8.0f ms %8.0f ms  %5d'
                  % (label, elapsed * 1000, connect_time * 1000,
                     (elapsed - connect_time) * 1000, len(counter.calls)))
            if baseline and baseline.get('connect'):
                print('   %-46s   = %.2f x the %.0f ms cost of one connect'
                      % ('', elapsed / baseline['connect'],
                         baseline['connect'] * 1000))
            if counter.failures:
                for text in counter.failures[:2]:
                    print('        !! connect failed mid-request: %s' % text)

    heading('WHAT THAT MEANS')
    for path, note, status, elapsed, connect_time, count, failures, sites, \
            qinfo in rows:
        # The console fires each of these twice on mount, and the browser
        # measured roughly double these figures. So "under 10s here" does not
        # mean "arrives in the browser" -- it means it has headroom only if
        # the duplicate call goes away.
        if elapsed >= FRONTEND_TIMEOUT_S:
            verdict = 'TIMES OUT at %.0fs even measured once' % FRONTEND_TIMEOUT_S
        elif elapsed * 2 >= FRONTEND_TIMEOUT_S:
            verdict = ('under %.0fs measured once, but the console fires it '
                       'twice -- it timed out in the browser'
                       % FRONTEND_TIMEOUT_S)
        else:
            verdict = 'has headroom even fired twice'
        share = (connect_time / elapsed * 100) if elapsed else 0
        print()
        print('   %s' % path)
        print('        %s, HTTP %s' % (note, status))
        if status in (401, 403):
            print('        !! BLOCKED BEFORE THE ROUTE RAN. This time is the')
            print('           guard only, so the real cost is HIGHER than')
            print('           shown. Re-run once the token is for an active')
            print('           login with the permission this route needs.')
        print('        %.1fs total, %d connection(s) opened, %.0f%% of the '
              'time inside connect()' % (elapsed, count, share))
        print('        %s' % verdict)
        qcount, qtotal, qrows = qinfo
        if qcount:
            print('        %d statement(s), %.1fs of the %.1fs -- where:'
                  % (qcount, qtotal, elapsed))
            for site, (n, took) in qrows[:8]:
                print('           %4dx %7.0f ms  %s' % (n, took * 1000, site))
            unexplained = elapsed - connect_time - qtotal
            print('        %.1fs is neither connecting nor querying (app code,'
                  % unexplained)
            print('        Cassandra, or statements on a cursor this could not')
            print('        count).')
        if sites:
            print('        every connect, and who asked for it:')
            for site, took in sites:
                print('           %7.0f ms  %s' % (took * 1000, site))
            print('        Pooling removes every one of these.')

    if queries is not None:
        db_pool.connect = _pool_connect

    after_stats = db_pool.stats()
    served_pooled = (after_stats['pooled_connects']
                     - before_stats['pooled_connects'])
    served_direct = (after_stats['direct_connects']
                     - before_stats['direct_connects'])
    heading('WHAT THE POOL SERVED')
    print('   pool state        %s' % after_stats['state'])
    print('   from the pool     %d' % served_pooled)
    print('   direct (fallback) %d' % served_direct)
    if 'idle' in after_stats:
        print('   idle / checked out  %s / %s'
              % (after_stats.get('idle'), after_stats.get('checked_out')))
    if served_direct and after_stats['state'] == 'ready':
        print('        !! a ready pool still served %d direct connection(s).'
              % served_direct)
        print('           That is the exhaustion fallback. Raise DB_POOL_SIZE')
        print('           or look for connections never being returned.')
    if after_stats.get('checked_out'):
        print('        !! %s connection(s) are still checked out after the'
              % after_stats['checked_out'])
        print('           requests finished. teardown_appcontext should have')
        print('           returned every one -- this is the leak the pool')
        print('           cannot survive. Investigate before deploying.')

    total = sum(r[3] for r in rows)
    in_connect = sum(r[4] for r in rows)
    opened = sum(r[5] for r in rows)
    print()
    print('   ACROSS ALL FOUR: %.1fs, %d connections, %.1fs (%.0f%%) of it '
          'inside connect().' % (total, opened, in_connect,
                                 (in_connect / total * 100) if total else 0))
    if total and opened == 0:
        # Not "pooling will not help" -- pooling has already taken all of it.
        print('   NOTHING was spent opening connections: every one came from')
        print('   the pool. Connection setup is finished as a problem on')
        print('   these routes, and the %.1fs that remains is queries and app'
              % total)
        print('   code. Whatever is still over budget needs fewer or faster')
        print('   queries, not more pooling.')
    elif total and in_connect / total > 0.5:
        print('   Most of the wait is connection setup, not SQL. A pool is the')
        print('   fix, and it is a backend change -- raising the frontend\'s')
        print('   10s timeout would only make the user wait longer for the')
        print('   same figures.')
    elif total:
        print('   Connection setup is not the bulk of what is LEFT, but %d'
              % opened)
        print('   connection(s) were still opened -- so some call sites on')
        print('   these routes are not pooled yet. Convert those before')
        print('   concluding anything about the queries.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--account', default=DEFAULT_ACCOUNT)
    parser.add_argument('--phase', type=int, choices=(1, 2), default=None,
                        help='run only this phase (default: both)')
    parser.add_argument('--connects', type=int, default=8,
                        help='how many psycopg2 connects to time in phase 1')
    parser.add_argument('--rtt', type=int, default=10,
                        help='how many SELECT 1 round trips to time')
    parser.add_argument('--queries', action='store_true',
                        help='also count and time every SQL statement, and '
                             'name the line that ran it. Opt-in: it installs '
                             'a counting cursor, so it changes the measured '
                             'run.')
    parser.add_argument('--no-warm', action='store_true',
                        help='do not warm the pool first (measures the cold '
                             'path, i.e. the behaviour before the pool)')
    args = parser.parse_args()

    from config import DB_LINK

    print('dashboard_latency_probe -- read-only')
    print('account under test: %s' % args.account)

    baseline = None
    if args.phase in (None, 1):
        baseline = phase_one(DB_LINK, args.connects, args.rtt)
        if baseline is None and args.phase != 1:
            print()
            print('Phase 1 could not reach the database, so phase 2 would only')
            print('time the same failure. Stopping here.')
            return 1
        if baseline:
            print()
            print('   So one connection costs %.0f ms and one statement on an'
                  % (baseline['connect'] * 1000))
            print('   already-open connection costs %.0f ms. A route that takes'
                  % (baseline['rtt'] * 1000))
            print('   N seconds is therefore mostly reporting how many times it')
            print('   reconnected -- which is what phase 2 counts.')
    if args.phase in (None, 2):
        phase_two(DB_LINK, args.account, baseline,
                  warm=not args.no_warm, count_queries=args.queries)
    return 0


if __name__ == '__main__':
    sys.exit(main())
