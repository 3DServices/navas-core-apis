"""Stop detection over a sequence of position fixes.  (B4)

WHY THIS IS A SEPARATE MODULE AND A SEPARATE ROUTE
--------------------------------------------------
trips/history paginates FIXES: location_store.fixes() stops reading as soon as
it has offset+limit of them.  A stop is not a fix, it is an aggregation over
CONTIGUOUS fixes -- its arrival is the first of a run and its departure the
last -- so a page boundary cuts a run in half and gives the edge fixes a dwell
time that is simply wrong, differing between page 1 and page 2 for the same
stop.  Stop detection therefore cannot run on a paginated slice, and bolting it
onto trips/history would either corrupt the numbers or undo the bounded read
that keeps a 92-day request from loading 1.2 GB.  It lives on its own path,
reads its own window, and paginates stops rather than fixes.

WHY trips/history CANNOT ANSWER DWELL TIME TODAY
-----------------------------------------------
It calls fixes(dedupe_coordinates=True), which keeps ONE fix per distinct
(lon, lat) -- the latest.  Every fix from a vehicle parked in one place
collapses into a single row and the arrival time is discarded before anything
downstream can read it.  Stop detection must read with dedupe OFF.

TIME BASIS -- the one thing to get right
----------------------------------------
A fix carries three time values and only one is safe to subtract:

    at_utc      record_timestamp            a real datetime, UTC   <- use this
    at          parsed from the local pair  a real datetime, EAT (+3)
    timestamp   local_system_timestamp      TEXT, not a datetime
    datestamp   local_system_datestamp      TEXT, 'DD-MM-YYYY'

Mixing at_utc and at in one run shifts part of it by three hours and silently
inflates or erases a dwell.  So this module uses at_utc ONLY, and reports any
fix lacking it as skipped rather than guessing an offset.

Pure: no Flask, no Cassandra, no database, no module state, so
tests/test_stops.py exercises it directly.
"""

from math import asin, cos, radians, sin, sqrt

# A parked vehicle rarely reports a clean zero: GPS jitter puts 1-2 km/h on a
# stationary unit.  Treating only speed == 0 as stopped misses most real stops.
DEFAULT_STATIONARY_SPEED = 2.0

# Shorter than this is a traffic light or a junction, not a stop worth naming.
DEFAULT_MIN_DWELL_SECONDS = 180

# A silence longer than this breaks a run in two: the unit may have been
# powered down, moved, and come back to the same place.  Without this, an
# overnight gap reads as one continuous 14-hour stop.
DEFAULT_MAX_GAP_SECONDS = 900

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lon1, lat1, lon2, lat2):
    """Great-circle distance in kilometres."""
    rlon1, rlat1, rlon2, rlat2 = (radians(v) for v in (lon1, lat1, lon2, lat2))
    dlon = rlon2 - rlon1
    dlat = rlat2 - rlat1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(min(1.0, sqrt(a)))


def _speed_of(row):
    """speed_log as a number, or None when it is absent or unparseable.

    None is NOT treated as zero.  A missing speed is not evidence the vehicle
    was stationary, and counting it as a stop would invent dwell time.
    """
    try:
        return float(str(row.get('speed')).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _ordered(rows):
    """Fixes oldest-first, keeping only those that can be placed in time.

    fixes() returns newest-first by default, and a run has to be walked
    forwards, so this does not rely on the caller's ordering.
    """
    usable = [r for r in rows if r.get('at_utc') is not None]
    usable.sort(key=lambda r: r['at_utc'])
    return usable, len(rows) - len(usable)


def _seconds(later, earlier):
    return (later - earlier).total_seconds()


def human_duration(seconds):
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return '%dh %dm' % (hours, minutes)
    if minutes:
        return '%dm %ds' % (minutes, secs)
    return '%ds' % secs


# Integration is only trustworthy on densely sampled fixes.  With fixes an hour
# apart, a trapezoid between two zero-speed endpoints integrates to zero even
# if the vehicle drove 50 km in between, which would flag a perfectly ordinary
# day as impossible.  Above this median gap, fall back to the looser bound.
DENSE_SAMPLING_SECONDS = 120

# Fraction of intervals that must carry a speed at both ends before the
# integral is used at all.
MIN_SPEED_COVERAGE = 0.8


def _median(values):
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def speed_is_plausible(rows, travelled_km=None):
    """Could the speeds on these fixes have produced the distance covered?

    TWO BOUNDS, and the sampling density decides which is used.

    The integrated bound is the real test.  Summing speed over time -- a
    trapezoid per interval -- says how far the speed log CLAIMS the vehicle
    went.  Compare that with the haversine distance between the fixes and a
    speed field that is not describing the movement shows up immediately.

    The max-speed bound (max_speed x elapsed) is the fallback, and it is very
    weak: it assumes the vehicle held its peak speed for the entire window,
    including every hour it sat parked.  On a real day with 25 stops it passes
    almost anything -- 783 km against a 38 km/h ceiling "fits" only because it
    pretends to 20.6 hours of unbroken driving at full speed.  It is kept only
    for sparsely sampled data, where integration would produce false alarms.

    Haversine between consecutive fixes is a straight line, so travelled_km
    understates a winding route.  That makes both comparisons conservative in
    the right direction: they under-report distance and so under-report
    implausibility.  The slack on top is therefore generous, not tight.

    Returns (plausible, detail).  detail always names which bound was used and
    shows the arithmetic, so a caller never has to trust the verdict blind.
    """
    ordered, _skipped = _ordered(rows)

    if len(ordered) < 2:
        return True, {'reason': 'fewer than two placeable fixes',
                      'basis': 'none'}

    if travelled_km is None:
        travelled_km = 0.0
        for before, after in zip(ordered, ordered[1:]):
            travelled_km += haversine_km(before['lon'], before['lat'],
                                         after['lon'], after['lat'])

    elapsed_h = _seconds(ordered[-1]['at_utc'], ordered[0]['at_utc']) / 3600.0
    speeds = [s for s in (_speed_of(r) for r in ordered) if s is not None]

    if not speeds or elapsed_h <= 0:
        # Its own basis, not 'none'.  'none' means "not enough fixes to form
        # an opinion", which is benign; this means the device reported no
        # usable speed at all, which is a finding in its own right and must
        # not be filed under "too few fixes" by a caller classifying these.
        return False, {'reason': 'no usable speeds or no elapsed time',
                       'basis': 'no speed data',
                       'travelled_km': round(travelled_km, 2)}

    gaps = []
    integrated_km = 0.0
    with_speed = 0

    for before, after in zip(ordered, ordered[1:]):
        gap_s = _seconds(after['at_utc'], before['at_utc'])
        gaps.append(gap_s)
        s1, s2 = _speed_of(before), _speed_of(after)
        if s1 is not None and s2 is not None:
            integrated_km += ((s1 + s2) / 2.0) * (gap_s / 3600.0)
            with_speed += 1

    coverage = (with_speed / float(len(gaps))) if gaps else 0.0
    median_gap = _median(gaps) or 0.0
    top = max(speeds)

    detail = {
        'travelled_km': round(travelled_km, 2),
        'max_speed_reported': top,
        'elapsed_hours': round(elapsed_h, 2),
        'reachable_km_at_max_speed': round(top * elapsed_h, 2),
        'integrated_km': round(integrated_km, 2),
        'median_gap_seconds': round(median_gap, 1),
        'speed_coverage': round(coverage, 3),
    }

    if travelled_km <= 0.001:
        detail['basis'] = 'no distance to explain'
        return True, detail

    if median_gap <= DENSE_SAMPLING_SECONDS and coverage >= MIN_SPEED_COVERAGE:
        detail['basis'] = 'integrated'
        # 25% slack: instantaneous speeds sampled at intervals do not
        # integrate exactly, and haversine already understates the route.
        limit = integrated_km * 1.25
        detail['allowed_km'] = round(limit, 2)
        if travelled_km > limit:
            detail['reason'] = ('the distance between fixes is further than '
                                'the reported speeds could have carried it; '
                                'speed_log is unreliable on this device')
            return False, detail
        return True, detail

    detail['basis'] = 'max_speed (fixes too sparse to integrate)'
    limit = top * elapsed_h * 1.1
    detail['allowed_km'] = round(limit, 2)
    if travelled_km > limit:
        detail['reason'] = ('reported speeds cannot account for the distance '
                            'covered; speed_log is unreliable on this device')
        return False, detail

    return True, detail


def detect(rows,
           stationary_speed=DEFAULT_STATIONARY_SPEED,
           min_dwell_seconds=DEFAULT_MIN_DWELL_SECONDS,
           max_gap_seconds=DEFAULT_MAX_GAP_SECONDS):
    """Collapse runs of stationary fixes into stops.

    Returns a dict:
        stops        list, oldest first, each with arrival / departure / dwell
        fix_count    fixes considered
        skipped      fixes with no record_timestamp, so unplaceable in time
        speed_trustworthy  bool -- see speed_is_plausible()
        speed_detail       the arithmetic behind that verdict

    Every stop carries fix_count and drift_m so a caller can see how much
    evidence it rests on.  A one-fix "stop" has no duration and is dropped by
    min_dwell_seconds, which is deliberate: a single stationary fix proves the
    vehicle was slow once, not that it stopped.
    """
    ordered, skipped = _ordered(rows)
    trustworthy, detail = speed_is_plausible(ordered)

    runs = []
    current = []

    for row in ordered:
        speed = _speed_of(row)
        stationary = (speed is not None and speed <= stationary_speed)

        if not stationary:
            if current:
                runs.append(current)
                current = []
            continue

        if current and _seconds(row['at_utc'],
                                current[-1]['at_utc']) > max_gap_seconds:
            # silence long enough that we cannot claim it stood still through it
            runs.append(current)
            current = [row]
            continue

        current.append(row)

    if current:
        runs.append(current)

    stops = []
    for run in runs:
        arrival = run[0]['at_utc']
        departure = run[-1]['at_utc']
        dwell = _seconds(departure, arrival)

        if dwell < min_dwell_seconds:
            continue

        drift_m = 0.0
        for other in run[1:]:
            drift_m = max(drift_m, haversine_km(run[0]['lon'], run[0]['lat'],
                                                other['lon'], other['lat']) * 1000)

        stops.append({
            'lon': run[0]['lon'],
            'lat': run[0]['lat'],
            'place': run[0].get('place'),
            'arrival': arrival.isoformat(),
            'departure': departure.isoformat(),
            'dwell_seconds': int(dwell),
            'dwell': human_duration(dwell),
            'fix_count': len(run),
            'drift_m': round(drift_m, 1),
        })

    return {
        'stops': stops,
        'fix_count': len(ordered),
        'skipped_no_timestamp': skipped,
        'speed_trustworthy': trustworthy,
        'speed_detail': detail,
        'settings': {
            'stationary_speed': stationary_speed,
            'min_dwell_seconds': min_dwell_seconds,
            'max_gap_seconds': max_gap_seconds,
        },
    }
