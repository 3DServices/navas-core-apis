#!/usr/bin/env python3
"""
patch_b8_distance.py -- B8: Calculate_DistanceX.

The ticket said "2.2s per call". Measurement (scripts/b8_audit.py) put it at
2.76s of a 13.58s request -- 20%. So this is NOT the latency fix for
trips/history; 80% of that request is elsewhere and still unexplained. This
patch is about robustness and waste, and is deliberately not sold as a
speed-up.

Four changes:

1. A TIMEOUT. requests.get had none, so a hung connection to distancematrix.ai
   blocks that worker for ever. Under Gunicorn with N workers, N hung calls is
   a dead service. This is the most dangerous line the audit found and it has
   nothing to do with speed.

2. THE DUPLICATE CALL. find_trips() measures every speed>0 -> speed==0 segment
   to test it against min_trip_distance = 1 km, then appends the trip WITHOUT
   the distance -- and all three callers immediately ask the API again for the
   same two points. Measured: 2 calls, 1 distinct coordinate pair, 1 trip.
   find_trips now carries the number it already has.

3. A CACHE, for the pairs that still repeat (a unit that stops at the same
   depot twice in a window). Only successful lookups are cached: caching a
   CORDS_ERROR would make a transient failure permanent for the process.

4. CONNECTION REUSE, per thread and per process. A requests.Session is not
   documented as thread-safe, and a Session created before fork() holds the
   parent's sockets -- so it is keyed on both, the same pid guard
   cassandra_store uses.

Also fixed, because it sits on the lines being changed: ComputeTrips_EXCELL
and ComputeTrips_PDF did float(distance_data["distance_covered"]) with no
CORDS_ERROR guard, so float('CORDS_ERROR') raised a ValueError and 500'd the
export. trips_history already guarded this; those two did not.

NOT changed, flagged instead:
  - find_trips sets distance = 0 on CORDS_ERROR, and 0 > 1 is false, so a trip
    whose distance could not be measured is silently dropped from the result.
    That is a product decision, not a bug to fix under cover of this patch.
  - float(point["speed_log"]) raises on 'NoData'/''/None, the same hazard
    stops.py handles explicitly.

data.py is CRLF; endings are preserved. Dry run unless --write.
"""

import ast
import io
import sys

TARGET = 'endpoints/data.py'

NEW_HELPERS = '''# B8: distancematrix.ai plumbing.
#
# A Session is not documented as thread-safe, and one built before fork()
# holds the parent's sockets, so it is kept per thread AND per process -- the
# same pid guard cassandra_store.py uses for Cassandra.
_distance_local = threading.local()

# (connect, read). Without this a hung call blocks the worker for ever.
DISTANCE_TIMEOUT = (5, 15)

# Only SUCCESSFUL lookups land here. Caching a CORDS_ERROR would turn one
# transient failure into a permanent wrong answer for the life of the process.
_DISTANCE_CACHE = {}
_DISTANCE_CACHE_MAX = 2048
_distance_cache_lock = threading.Lock()


def _distance_http():
    """A requests.Session for this thread in this process."""
    pid = os.getpid()
    session = getattr(_distance_local, 'session', None)
    if session is None or getattr(_distance_local, 'pid', None) != pid:
        session = requests.Session()
        _distance_local.session = session
        _distance_local.pid = pid
    return session


def _distance_cache_get(key):
    return _DISTANCE_CACHE.get(key)


def _distance_cache_put(key, value):
    with _distance_cache_lock:
        if len(_DISTANCE_CACHE) >= _DISTANCE_CACHE_MAX:
            # Cheap bound. Road distances do not change often enough to earn
            # a full LRU, and an unbounded dict in a long-lived worker does.
            _DISTANCE_CACHE.clear()
        _DISTANCE_CACHE[key] = value


'''

NEW_FUNC = '''def Calculate_DistanceX(Origin_Lat, Origin_Long, To_Lat, To_Long):
    """Road distance and duration between two points, as a JSON string.

    Every caller does json.loads() on the result, so every path out of here
    must return JSON — returning a bare word breaks trip history with a
    JSONDecodeError rather than degrading. 'CORDS_ERROR' is the marker the
    callers already understand for "no distance available".

    B8: now cached, connection-reusing, and bounded by a timeout. A network
    failure is reported as CORDS_ERROR like any other failure, and is NOT
    cached.
    """
    # The distancematrix.ai key used to be written into the URL below.
    from config import DISTANCEMATRIX_API_KEY
    if not DISTANCEMATRIX_API_KEY:
        return json.dumps({"distance_covered": 'CORDS_ERROR',
                           "time_covered": "Nothing"})

    cache_key = (str(Origin_Lat), str(Origin_Long), str(To_Lat), str(To_Long))
    cached = _distance_cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        RequestData = _distance_http().get(
            "https://api.distancematrix.ai/maps/api/distancematrix/json",
            params={"origins": f"{Origin_Lat}, {Origin_Long}",
                    "destinations": f"{To_Lat}, {To_Long}",
                    "key": DISTANCEMATRIX_API_KEY},
            timeout=DISTANCE_TIMEOUT)
        api_data = RequestData.json()
    except Exception as error:      # noqa: BLE001 — timeouts, DNS, bad JSON
        # Logged, not returned: the key is in the request and requests puts
        # the URL in its exception text.
        logging.warning('Calculate_DistanceX: %s', type(error).__name__)
        return json.dumps({"distance_covered": 'CORDS_ERROR',
                           "time_covered": "Nothing"})

    try:
        element = api_data['rows'][0]['elements'][0]
    except (KeyError, IndexError, TypeError):
        return json.dumps({"distance_covered": 'CORDS_ERROR',
                           "time_covered": "Nothing"})

    if element.get('status') == 'OK':

        KiloMeters_Covered = re.sub(r'[^\\d.]', '', str(element['distance']['text']))
        TimeCovered = re.sub(r'[^\\d.]', '', str(element['duration']['text']))

        data_xc = {
            "distance_covered": KiloMeters_Covered,
            "time_covered": TimeCovered
        }

        answer = json.dumps(data_xc)
        _distance_cache_put(cache_key, answer)
        return answer

    # Any other status (ZERO_RESULTS, OVER_QUERY_LIMIT, REQUEST_DENIED,
    # NOT_FOUND) used to fall off the end and return None, which json.loads()
    # then choked on. Not cached: OVER_QUERY_LIMIT is transient.
    return json.dumps({"distance_covered": 'CORDS_ERROR',
                       "time_covered": "Nothing"})
'''

# --- find_trips carries the distance it already measured
OLD_APPEND = """                min_trip_distance = 1  # Minimum trip distance in kilometers
                if distance > min_trip_distance:
                    trips.append(current_trip)
"""
NEW_APPEND = """                min_trip_distance = 1  # Minimum trip distance in kilometers
                if distance > min_trip_distance:
                    # B8: carry the number we just paid for. Every caller used
                    # to ask distancematrix.ai again for these same two points.
                    current_trip["distance_km"] = distance
                    trips.append(current_trip)
"""

# --- the two unguarded callers (identical text, excel and pdf)
OLD_EXPORT = """                                    distance_pool_x = Calculate_DistanceX(Starting_Lat, Starting_Long, End_Lat, End_Long)
                                    distance_data = json.loads(distance_pool_x)
                                    distance = float(distance_data["distance_covered"])
"""
NEW_EXPORT = """                                    # B8: find_trips() already measured this pair.
                                    distance = trip.get("distance_km")
                                    if distance is None:
                                        distance_data = json.loads(Calculate_DistanceX(
                                            Starting_Lat, Starting_Long, End_Lat, End_Long))
                                        raw_distance = distance_data["distance_covered"]
                                        # float('CORDS_ERROR') raised a ValueError and
                                        # 500'd the export. trips_history guarded this
                                        # and these two did not.
                                        distance = (float(raw_distance)
                                                    if raw_distance != 'CORDS_ERROR' else 0)
"""

# --- trips_history, which already had the guard
OLD_HISTORY = """                                                distance_pool_x = Calculate_DistanceX(Starting_Lat, Starting_Long, End_Lat, End_Long)
"""
NEW_HISTORY = """                                                # B8: find_trips() already measured this pair;
                                                # only ask the API if it did not.
                                                _carried = trip.get("distance_km")
                                                distance_pool_x = (
                                                    json.dumps({"distance_covered": str(_carried),
                                                                "time_covered": "carried"})
                                                    if _carried is not None else
                                                    Calculate_DistanceX(Starting_Lat, Starting_Long,
                                                                        End_Lat, End_Long))
"""


def fail(message):
    sys.stderr.write('REFUSED: %s\n' % message)
    raise SystemExit(2)


def main():
    write = '--write' in sys.argv

    with io.open(TARGET, 'r', newline='', encoding='utf-8') as handle:
        src = handle.read()
    if '\r\n' not in src:
        fail('%s is not CRLF' % TARGET)
    nl = '\r\n'

    flat = src.replace('\r\n', '\n')
    tree = ast.parse(flat)
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'Calculate_DistanceX':
            fn = node
            break
    if fn is None:
        fail('Calculate_DistanceX not found')
    if 'timeout' in '\n'.join(flat.splitlines()[fn.lineno - 1:fn.end_lineno]):
        fail('Calculate_DistanceX already has a timeout — already patched?')

    lines = src.splitlines(keepends=True)

    # `threading` is the one name the new helpers need that data.py does not
    # already import. The verification below refused the patch without it,
    # which is what that check is for. Anchored on the first import rather
    # than a line number.
    needs_threading = not any(
        isinstance(n, ast.Import) and any(a.name == 'threading' for a in n.names)
        for n in tree.body)
    import_at = min(n.lineno for n in tree.body
                    if isinstance(n, (ast.Import, ast.ImportFrom)))

    replacement = [l + nl for l in (NEW_HELPERS + NEW_FUNC).split('\n')]
    if replacement and replacement[-1].strip() == '':
        replacement.pop()
    out_lines = lines[:fn.lineno - 1] + replacement + lines[fn.end_lineno:]
    if needs_threading:
        out_lines.insert(import_at - 1, 'import threading' + nl)
    out = ''.join(out_lines)

    for label, old, new, expect in (
            ('find_trips carries the distance', OLD_APPEND, NEW_APPEND, 1),
            ('excel + pdf callers', OLD_EXPORT, NEW_EXPORT, 2),
            ('trips_history caller', OLD_HISTORY, NEW_HISTORY, 1)):
        old_c = old.replace('\n', nl)
        new_c = new.replace('\n', nl)
        found = out.count(old_c)
        if found != expect:
            fail('%s: matched %d times, expected %d' % (label, found, expect))
        out = out.replace(old_c, new_c)

    # ---- verification
    flat_out = out.replace('\r\n', '\n')
    compile(flat_out, TARGET, 'exec')
    new_tree = ast.parse(flat_out)

    for module in ('os', 'threading', 'logging', 'requests', 're', 'json'):
        if not any(isinstance(n, ast.Import) and any(a.name == module for a in n.names)
                   for n in new_tree.body):
            fail('%s does not import %s at module level' % (TARGET, module))

    calls = [n for n in ast.walk(new_tree) if isinstance(n, ast.Call)
             and getattr(n.func, 'id', None) == 'Calculate_DistanceX']
    guarded = sum(1 for n in ast.walk(new_tree) if isinstance(n, ast.Call)
                  and getattr(n.func, 'attr', None) == 'get'
                  and n.args and isinstance(n.args[0], ast.Constant)
                  and n.args[0].value == 'distance_km')
    if guarded != 3:
        fail('expected 3 `trip.get("distance_km")` guards, found %d' % guarded)

    if out.count('\r\n') != out.count('\n'):
        fail('line endings are no longer uniformly CRLF')

    print('  %-46s %s' % ('requests.get timeout', 'DISTANCE_TIMEOUT (5, 15)'))
    print('  %-46s %s' % ('connection reuse', 'Session per thread + pid guard'))
    print('  %-46s %s' % ('cache', 'successes only, bounded at 2048'))
    print('  %-46s %s' % ('network failure', 'caught -> CORDS_ERROR, not cached'))
    print('  %-46s %d (was 4)' % ('Calculate_DistanceX call sites', len(calls)))
    print('  %-46s %d' % ('callers that reuse find_trips\' number', guarded))
    print('  %-46s %s' % ('excel/pdf CORDS_ERROR ValueError', 'guarded'))
    print('  %-46s %d -> %d lines' % (TARGET, len(lines), len(out.splitlines())))
    print('  %-46s %s' % ('line endings', 'CRLF preserved'))

    if not write:
        print('')
        print('dry run -- nothing written. Re-run with --write to apply.')
        return 0

    with io.open(TARGET, 'w', newline='', encoding='utf-8') as handle:
        handle.write(out)
    print('')
    print('written.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
