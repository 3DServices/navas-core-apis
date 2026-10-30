"""
stop_engine — POST /data-stream/trips/engine-time.

Engine-on time for the stops the app's trip history found (see
engine_time.py for how it is worked out). The app sends the stops' spans
rather than this reading every fix's IO events: a day can hold 13,000 fixes,
each one lookup, while a parked unit sends few.

The access guard has already checked the unit is the caller's.
"""

import logging

from flask import Blueprint, request

from . import engine_time as et
from . import location_store
from .globals import check_device, reply, require_auth

stop_engine_bp = Blueprint('stop_engine', __name__)
log = logging.getLogger('stop_engine')

_UNREACHABLE = ("We couldn't read this vehicle's history right now. "
                "Please try again.")


def _stamp(value):
    return value.strftime('%Y-%m-%d %H:%M:%S')


def _spans_reply(spans, ignition, results=None):
    return {
        'ignition': ignition,
        'spans': [
            {
                'from': _stamp(start),
                'to': _stamp(end),
                'engine_on_seconds': (results[i][0] if results else None),
                'readings': (results[i][1] if results else 0),
            }
            for i, (start, end) in enumerate(spans)
        ],
    }


@stop_engine_bp.route('/data-stream/trips/engine-time', methods=['POST'])
@require_auth
def engine_time_route():
    body = request.get_json(silent=True) or {}
    data = body.get('data') if isinstance(body.get('data'), dict) else body
    imei = str(data.get('device_imei') or '').strip()
    if len(imei) < 5:
        return reply('error', 400, 'Send device_imei.', '')
    spans = et.parse_spans(data.get('spans'))
    if isinstance(spans, str):
        return reply('error', 400, spans, '')

    status = check_device(imei)
    if status == 'blocked':
        return reply('error', 400, 'Device Billing Is Blocked', '')
    if status == 'not-found':
        return reply('error', 404, 'Vehicle not found.', '')
    if status != 'running':
        return reply('error', 503, _UNREACHABLE, '')

    from .alert_engine import attach_ignition, ignition_source
    from .cassandra_store import get_cassandra_session
    from .io_events_store import IoEventsUnavailable

    try:
        session = get_cassandra_session()
        source = ignition_source(session, imei)
        if source is None:
            # Nothing to read ignition from: the app hides engine time.
            return reply('success', 200, 'No ignition input configured',
                         _spans_reply(spans, 'not_configured'))

        first = min(start for start, _ in spans)
        last = max(end for _, end in spans)
        fixes, _ = location_store.fixes(
            session, imei, first.date(), last.date(),
            datetime_from=first, datetime_to=last,
            dedupe_coordinates=False, newest_first=False)

        per_span = [et.in_span(fixes, start, end) for start, end in spans]
        shares = et.share_lookups([len(p) for p in per_span])
        chosen = [et.sample(p, n) for p, n in zip(per_span, shares)]
        attach_ignition(session, [f for c in chosen for f in c], source)
    except (location_store.PositionsUnavailable, IoEventsUnavailable) as error:
        log.warning('engine-time %s: store unavailable: %s', imei, error)
        return reply('error', 503, _UNREACHABLE, '')

    results = [et.engine_on(c, start, end)
               for (start, end), c in zip(spans, chosen)]
    return reply('success', 200, 'Engine time worked out',
                 _spans_reply(spans, 'configured', results))
