#!/usr/bin/env python3
"""
db_pool.py -- one warm pool of Postgres connections, shared by the whole app.

WHY THIS EXISTS

Every request to this application opens brand-new connections to a Postgres
server that is 282 ms away, and throws them away again. Measured on the
production host:

    TCP connect                284 ms      one round trip
    psycopg2.connect         2,027 ms      TCP + startup + auth
    SELECT 1 (open conn)       282 ms      one round trip

So a connection costs SEVEN TIMES what a query costs. A route that runs one
SQL statement and opens one connection spends 88% of its life connecting.

Measured per route, counting every connect made while the request ran:

    /notifications/<acct>/unread-count    8,517 ms   3 connections
    /tokens/<acct>/balance                8,568 ms   3 connections
    /payments/transactions/<acct>/list    8,555 ms   3 connections
    /devices/configured/all              28,059 ms   7 connections

The OLIWA console aborts a dashboard call at 10 s, so those figures never
arrive and the dashboard renders zeros -- correct data, discarded for being
late. scripts/audit_pg_connections.py named the fix a while ago: "a
module-level pool fixes every call site at once with no signature changes".
This is that pool.

TWO TRAPS, BOTH LOAD-BEARING

1. THIS CODEBASE DOES NOT CLOSE WHAT IT OPENS. 310 call sites look like:

       dbconnect = psycopg2.connect(current_app.config['db_link'])
       with dbconnect:                      # commits or rolls back
           with dbconnect.cursor() as cur:  # and never closes

   psycopg2 is explicit that `with conn:` does NOT close. Today that leaks
   slowly and CPython's refcounting eventually closes the socket. Hand those
   same 310 sites a pooled connection and they leak POOL SLOTS, which nothing
   collects: the pool empties within seconds of real traffic and every later
   request blocks forever on a connection that is never coming back. A pool
   dropped in without handling this turns a slow dashboard into a hung
   application.

   So this module does not rely on callers closing anything. Every connection
   it hands out inside a request is registered on flask.g, and release_all()
   -- wired to teardown_appcontext in app.py -- returns whatever is still out
   when the request ends. Callers that DO close still work: close() is
   idempotent. Nothing at the 310 call sites has to change for them to stop
   leaking.

2. psycopg2's POOL KEEPS ONLY `minconn` CONNECTIONS, NOT `maxconn`. Read
   AbstractConnectionPool._putconn:

       if len(self._pool) < self.minconn and not close:
           ... keep it ...
       else:
           conn.close()                     # <-- discarded outright

   With the tempting-looking minconn=1, maxconn=20, the second concurrent
   request's connection is CLOSED when returned, and the next request pays the
   2,027 ms again. The pool would look installed and do nothing. `minconn` is
   the real pool size here; `maxconn` is only a ceiling on simultaneous
   checkouts.

   But __init__ opens all `minconn` connections synchronously, and at 2 s each
   a warm pool of 8 would stall startup for 16 seconds. So the pool is built
   on a background thread (the same shape as cassandra_store.start_warmup),
   and until it is ready connect() simply opens a direct connection. Nothing
   waits for the pool; the application is merely slow for the first moment,
   exactly as slow as it is today.

WHAT THIS MODULE PROMISES

  * A request never fails because of the pool. Pool exhausted, pool not built
    yet, pool raising -- every one of those falls back to a direct connect,
    which is today's behaviour. The pool can only make things faster or leave
    them as they are.
  * A connection is never handed to another request mid-transaction.
    psycopg2's own _putconn rolls back anything not IDLE, and release_all
    rolls back before returning as well, because a connection carrying a
    failed transaction into the next request would produce wrong answers
    rather than errors -- the worst failure this codebase has.

Read-only outside its own bookkeeping; it holds no application state.

Configuration (environment, all optional):
    DB_POOL_SIZE   connections kept warm      default 8
    DB_POOL_MAX    ceiling on concurrent      default 24
    DB_POOL        'off' disables pooling entirely (direct connects)
"""

import logging
import os
import threading

import psycopg2
import psycopg2.pool
from flask import current_app, g, has_app_context

__all__ = ['connect', 'release_all', 'start_warmup', 'stats', 'shutdown']

_LOG = logging.getLogger(__name__)

# `minconn` is the real pool size -- see trap 2 above.
_POOL_SIZE = int(os.environ.get('DB_POOL_SIZE', '8'))
_POOL_MAX = int(os.environ.get('DB_POOL_MAX', '24'))
_POOL_ENABLED = os.environ.get('DB_POOL', 'on').strip().lower() not in (
    'off', '0', 'false', 'no')

# Where this request's checked-out connections are parked.
_CHECKED_OUT_KEY = '_navas_pooled_connections'

_pool = None
_pool_lock = threading.Lock()
_pool_state = 'not started'      # not started | building | ready | failed | off
_direct_connects = 0             # connections that bypassed the pool
_pooled_connects = 0             # connections served from the pool


def _dsn(explicit=None):
    """The DSN to use, preferring an explicit one, then the app config."""
    if explicit:
        return explicit
    if has_app_context():
        return current_app.config['db_link']
    raise RuntimeError('db_pool.connect() needs a DSN outside an app context')


# ---------------------------------------------------------------- building

def _build(dsn):
    """Create the pool. Slow (minconn x ~2 s), so never call this inline."""
    global _pool, _pool_state
    try:
        built = psycopg2.pool.ThreadedConnectionPool(
            _POOL_SIZE, max(_POOL_MAX, _POOL_SIZE), dsn)
    except Exception as error:                             # noqa: BLE001
        with _pool_lock:
            _pool_state = 'failed'
        # Not fatal: connect() falls back to direct connections, which is
        # exactly how the application behaved before this module existed.
        _LOG.warning('db_pool: could not build the pool (%s: %s); '
                     'falling back to direct connections',
                     type(error).__name__, error)
        return
    with _pool_lock:
        _pool = built
        _pool_state = 'ready'
    _LOG.info('db_pool: ready, %d connections warm (ceiling %d)',
              _POOL_SIZE, max(_POOL_MAX, _POOL_SIZE))


def start_warmup(dsn=None):
    """Build the pool on a background thread. Never raises, never blocks.

    Call once at startup, and again in each forked worker -- the same shape
    cassandra_store.start_warmup uses, and for the same reason: a pool built
    before fork() is not usable by the children.
    """
    global _pool_state
    if not _POOL_ENABLED:
        with _pool_lock:
            _pool_state = 'off'
        _LOG.info('db_pool: disabled by DB_POOL, using direct connections')
        return
    with _pool_lock:
        if _pool_state in ('building', 'ready'):
            return
        _pool_state = 'building'
    target = dsn
    if target is None:
        try:
            target = current_app.config['db_link']
        except Exception:                                  # noqa: BLE001
            with _pool_lock:
                _pool_state = 'not started'
            return
    thread = threading.Thread(target=_build, args=(target,),
                              name='db-pool-warmup', daemon=True)
    thread.start()


def shutdown():
    """Close every pooled connection. For tests and clean exits."""
    global _pool, _pool_state
    with _pool_lock:
        existing, _pool, _pool_state = _pool, None, 'not started'
    if existing is not None:
        try:
            existing.closeall()
        except Exception:                                  # noqa: BLE001
            pass


# ---------------------------------------------------------------- the proxy

class PooledConnection:
    """A connection that goes back to the pool instead of closing.

    Everything except close() is the real connection's behaviour, including
    `with conn:` -- which still means commit-or-rollback, because __enter__
    and __exit__ are passed straight through. That is what lets the 310
    existing call sites keep their shape.
    """

    __slots__ = ('_conn', '_owner', '_released', '_readonly')

    def __init__(self, conn, owner, readonly=False):
        object.__setattr__(self, '_conn', conn)
        object.__setattr__(self, '_owner', owner)
        object.__setattr__(self, '_released', False)
        object.__setattr__(self, '_readonly', readonly)

    # -- the one changed behaviour ------------------------------------
    def close(self):
        """Return this connection to the pool. Safe to call more than once."""
        if self._released:
            return
        object.__setattr__(self, '_released', True)
        conn, owner = self._conn, self._owner
        try:
            # THE HAZARD THIS WHOLE FEATURE INTRODUCES. A connection handed
            # back with autocommit still on would silently strip transactions
            # from whatever code picks it up next -- a write path would lose
            # its atomicity with no error and no sign. Reset it FIRST, before
            # anything else can fail and skip it.
            if self._readonly and not conn.closed:
                conn.autocommit = False
        except Exception:                                  # noqa: BLE001
            pass
        try:
            # psycopg2's _putconn rolls back anything not IDLE, but say it
            # here too: a connection carrying a failed transaction into
            # another request gives wrong answers rather than errors.
            if not conn.closed:
                conn.rollback()
        except Exception:                                  # noqa: BLE001
            pass
        try:
            owner.putconn(conn)
        except Exception:                                  # noqa: BLE001
            try:
                conn.close()
            except Exception:                              # noqa: BLE001
                pass

    # -- everything else is the real connection ------------------------
    def __getattr__(self, name):
        if self._released:
            if name == 'closed':
                return True
            raise psycopg2.InterfaceError(
                'connection already returned to the pool')
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        if name in PooledConnection.__slots__:
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

    def __enter__(self):
        # On a read-only connection this is deliberately a NO-OP.
        #
        # psycopg2's connection.__enter__ opens a transaction even when
        # autocommit is on -- measured, not assumed: scripts/
        # transaction_cost_probe.py case (d) timed the same SELECT at 614 ms
        # inside `with conn:` against 307 ms outside it, with autocommit on
        # for both. That is the BEGIN, costing its own round trip.
        #
        # So without this, readonly=True buys nothing anywhere the codebase
        # uses `with conn:` -- which is 310 call sites. The first attempt at
        # this fix set autocommit and stopped there; it improved exactly one
        # call site, the only one that happened not to use the idiom.
        #
        # Skipping it is correct, not a trick: with autocommit on, every
        # statement commits itself, so a transaction block has nothing to
        # open and nothing to commit. The call sites keep their `with`
        # blocks and need no edit.
        if not self._readonly:
            self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._readonly:
            return False        # nothing was opened; nothing to commit
        return self._conn.__exit__(exc_type, exc_value, traceback)

    def __repr__(self):
        return '<PooledConnection released=%s %r>' % (self._released,
                                                      self._conn)


# ---------------------------------------------------------------- handing out

def _remember(proxy):
    """Park a checked-out connection on g so teardown can reclaim it."""
    if not has_app_context():
        return
    try:
        bucket = getattr(g, _CHECKED_OUT_KEY, None)
        if bucket is None:
            bucket = []
            setattr(g, _CHECKED_OUT_KEY, bucket)
        bucket.append(proxy)
    except Exception:                                      # noqa: BLE001
        pass


def connect(dsn=None, readonly=False):
    """A connection, from the pool when there is one.

    Drop-in for psycopg2.connect(current_app.config['db_link']): the object
    returned behaves the same, and close() returns it to the pool instead of
    shutting the socket. Falls back to a direct connection whenever the pool
    cannot serve -- not built yet, exhausted, disabled, or erroring -- so this
    is never worse than the behaviour it replaces.

    readonly=True turns autocommit ON, which means psycopg2 sends no BEGIN.
    That is worth exactly one round trip -- 283 ms against this database,
    measured by scripts/transaction_cost_probe.py, which found a statement
    costs 566 ms as the first in a transaction and 283 ms otherwise.

    USE IT ONLY WHERE EVERY STATEMENT IS A SELECT. Without a transaction
    there is no atomicity and no rollback: two writes could half-apply and
    nothing would say so. It is deliberately not the default, and the
    existing `with conn:` blocks around a read-only connection become
    harmless no-ops rather than erroring, which is convenient and also why
    the flag has to be applied by someone who has checked the call site.
    """
    global _direct_connects, _pooled_connects

    target = _dsn(dsn)
    with _pool_lock:
        pool = _pool if _pool_state == 'ready' else None

    if pool is not None:
        try:
            raw = pool.getconn()
            if readonly:
                # Client-side only: PostgreSQL has no autocommit setting, it
                # is purely whether the driver sends BEGIN. So this costs no
                # round trip, which is the entire point.
                raw.autocommit = True
            proxy = PooledConnection(raw, pool, readonly=readonly)
            _remember(proxy)
            _pooled_connects += 1
            return proxy
        except psycopg2.pool.PoolError as error:
            # Exhausted, or closed under us. A direct connection is slow but
            # correct, and far better than refusing the request.
            _LOG.warning('db_pool: %s; serving a direct connection', error)
        except Exception as error:                         # noqa: BLE001
            _LOG.warning('db_pool: getconn failed (%s: %s); serving a direct '
                         'connection', type(error).__name__, error)

    _direct_connects += 1
    fresh = psycopg2.connect(target)
    if readonly:
        fresh.autocommit = True
    return fresh


def release_all(_exception=None):
    """Return every connection this request still holds. Teardown hook.

    This is what makes the 310 call sites that never close safe to leave
    alone. Registered in app.py with app.teardown_appcontext.
    """
    if not has_app_context():
        return
    try:
        bucket = getattr(g, _CHECKED_OUT_KEY, None)
    except Exception:                                      # noqa: BLE001
        return
    if not bucket:
        return
    for proxy in list(bucket):
        try:
            proxy.close()
        except Exception:                                  # noqa: BLE001
            pass
    try:
        setattr(g, _CHECKED_OUT_KEY, [])
    except Exception:                                      # noqa: BLE001
        pass


def stats():
    """What the pool is doing. For diagnostics and tests."""
    with _pool_lock:
        pool, state = _pool, _pool_state
    out = {
        'state': state,
        'warm_size': _POOL_SIZE,
        'ceiling': max(_POOL_MAX, _POOL_SIZE),
        'pooled_connects': _pooled_connects,
        'direct_connects': _direct_connects,
    }
    if pool is not None:
        try:
            out['idle'] = len(pool._pool)
            out['checked_out'] = len(pool._used)
        except Exception:                                  # noqa: BLE001
            pass
    return out
