"""
engine_time — how long the engine ran while a vehicle stood still.

Trip history shows each stop with its engine-on time (Wialon's key icon): an
engine left running at a stop is idling, and idling burns fuel. The app has
already worked out where the stops were; it sends their spans and this works
out, from the ignition reading on the fixes inside each span, how long the
ignition was on.

Pure logic, standard library only, so it is tested with no database. The
route that reads the fixes and their IO events is in stop_engine.py.

Ignition comes from the unit's 'ignition_detection' IO channel (the alert
engine reads the same one). A fix with no reading on that channel says
nothing either way, and a span with no readings at all has an unknown
engine-on time, not zero.
"""

from datetime import datetime, timedelta

MAX_SPANS = 50

# The spans must fall within this many days: the fixes are read for the
# whole range in one go.
MAX_RANGE_DAYS = 3

# An ignition-on reading counts until the next fix, but no longer than this:
# a unit with the engine running reports every few seconds to minutes, so a
# longer silence is a unit that stopped reporting, not proof the engine ran.
MAX_GAP = timedelta(minutes=10)

# The most IO lookups one request makes (one per fix). Past it the fixes in
# each span are sampled evenly; each sampled reading then stands for the time
# to the next sampled fix, still capped by MAX_GAP.
MAX_LOOKUPS = 1500

ON, OFF = 'ON', 'OFF'


def parse_time(value):
    """A naive local datetime from 'YYYY-MM-DD HH:MM[:SS]' or ISO 8601 with a
    'T', or None."""
    text = str(value or '').strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def parse_spans(raw):
    """[(start, end), ...] from the request's spans, or an error message.

    Each span is {"from": ..., "to": ...}; to must not be before from.
    """
    if not isinstance(raw, list) or not raw:
        return 'Send spans: a list of {"from", "to"} local times.'
    if len(raw) > MAX_SPANS:
        return f'Send at most {MAX_SPANS} spans at a time.'
    spans = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return f'Span {i + 1} must be an object with "from" and "to".'
        start, end = parse_time(item.get('from')), parse_time(item.get('to'))
        if start is None or end is None:
            return (f'Span {i + 1}: "from" and "to" must be local times like '
                    f'2026-10-30 12:18:00.')
        if end < start:
            return f'Span {i + 1} ends before it starts.'
        spans.append((start, end))
    first = min(s for s, _ in spans).date()
    last = max(e for _, e in spans).date()
    if (last - first).days >= MAX_RANGE_DAYS:
        return f'The spans must fall within {MAX_RANGE_DAYS} days.'
    return spans


def in_span(fixes, start, end):
    """The fixes timed within [start, end], oldest first."""
    inside = [f for f in fixes
              if f.get('at') is not None and start <= f['at'] <= end]
    return sorted(inside, key=lambda f: f['at'])


def sample(fixes, limit):
    """At most [limit] of [fixes], spread evenly, keeping the first."""
    if limit <= 0:
        return []
    if len(fixes) <= limit:
        return list(fixes)
    step = len(fixes) / limit
    return [fixes[int(i * step)] for i in range(limit)]


def share_lookups(counts, budget=MAX_LOOKUPS):
    """How many fixes of each span to look up, within [budget] in all.

    A span gets all its fixes when everything fits; otherwise the budget is
    shared in proportion, each span keeping at least one lookup.
    """
    total = sum(counts)
    if total <= budget:
        return list(counts)
    return [min(c, max(1, int(budget * c / total))) if c else 0
            for c in counts]


def engine_on(fixes, start, end, max_gap=MAX_GAP):
    """(seconds the ignition was on within [start, end], readings).

    [fixes] are the span's fixes, oldest first, each with 'at' and
    'ignition' (ON, OFF or None). An ON reading counts from its fix to the
    next fix (or the span's end), capped at [max_gap]. Seconds is None when
    no fix had a reading: unknown, not zero.
    """
    readings = sum(1 for f in fixes if f.get('ignition') in (ON, OFF))
    if readings == 0:
        return None, 0
    on = timedelta()
    for i, fix in enumerate(fixes):
        if fix.get('ignition') != ON:
            continue
        begin = max(fix['at'], start)
        until = fixes[i + 1]['at'] if i + 1 < len(fixes) else end
        until = min(until, end, fix['at'] + max_gap)
        if until > begin:
            on += until - begin
    return int(on.total_seconds()), readings
