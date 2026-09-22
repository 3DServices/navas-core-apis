"""
geozone_shapes.py — the three geofence shapes customers can draw.

    polygon  at least 4 corners, each a latitude/longitude
    circle   a centre and a radius in metres
    line     a route of at least 2 points and a thickness in metres
             (a corridor: "stay on this road")

Everything that decides whether a vehicle is inside a zone — the live
monitoring screen and the stream that writes enter/exit events — reads
dll_geozones.geozone_points as a polygon ring of [lng, lat] pairs. So every
shape is ALSO stored as that ring: a circle as a 64-sided polygon, a line as
the corridor around it. Those readers keep working unchanged, and the shape
itself (centre, radius, route, thickness) is kept beside it in
geozone_shape / geozone_shape_params so the map can draw and edit it exactly.

The ring is computed here, on the server, from the shape — never taken from
the client for a circle or a line — so every app stores the same geometry.
The OLIWA console computes the same ring for its preview
(src/utils/geofenceShapes.ts); keep the two in step.
"""

import json
import math

SHAPES = ('polygon', 'circle', 'line')

MIN_POLYGON_POINTS = 4
MIN_LINE_POINTS = 2
MAX_POINTS = 500

CIRCLE_RADIUS_M = (10, 100_000)          # 10 m to 100 km
LINE_WIDTH_M = (5, 5_000)                # corridor 5 m to 5 km wide
CIRCLE_SEGMENTS = 64

_EARTH_M = 6_371_008.8


class ShapeError(ValueError):
    """A shape the customer should be told how to fix."""


# ── Validation ──────────────────────────────────────────────────────────────

def _point(value, label):
    """{'lat': .., 'lng': ..} -> (lat, lng), checked."""
    try:
        lat = float(value['lat'])
        lng = float(value['lng'])
    except (KeyError, TypeError, ValueError):
        raise ShapeError(f'{label} needs a latitude and a longitude.')
    if not (math.isfinite(lat) and math.isfinite(lng)):
        raise ShapeError(f'{label} has an invalid coordinate.')
    if not -90 <= lat <= 90:
        raise ShapeError(f'{label}: latitude must be between -90 and 90.')
    if not -180 <= lng <= 180:
        raise ShapeError(f'{label}: longitude must be between -180 and 180.')
    return lat, lng


def _points(values, minimum, what):
    if not isinstance(values, list):
        raise ShapeError(f'A {what} needs a list of points.')
    if len(values) < minimum:
        raise ShapeError(f'A {what} needs at least {minimum} points.')
    if len(values) > MAX_POINTS:
        raise ShapeError(f'A {what} can have at most {MAX_POINTS} points.')
    pts = [_point(v, f'Point {i + 1}') for i, v in enumerate(values)]
    distinct = {(round(a, 7), round(b, 7)) for a, b in pts}
    if len(distinct) < minimum:
        raise ShapeError(f'A {what} needs at least {minimum} different points.')
    return pts


def _number(value, bounds, label):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ShapeError(f'{label} must be a number of metres.')
    low, high = bounds
    if not (math.isfinite(number) and low <= number <= high):
        raise ShapeError(f'{label} must be between {low:,} and {high:,} metres.')
    return number


def normalise(shape, params):
    """Check a shape and return (shape, clean_params) ready to store.

    params: polygon {'points': [{lat,lng}...]}
            circle  {'center': {lat,lng}, 'radius_m': n}
            line    {'points': [{lat,lng}...], 'width_m': n}
    """
    shape = str(shape or 'polygon').strip().lower()
    if shape not in SHAPES:
        raise ShapeError('Shape must be polygon, circle or line.')
    if isinstance(params, str):
        try:
            params = json.loads(params) if params.strip() else {}
        except ValueError:
            raise ShapeError('Shape details are not valid JSON.')
    if not isinstance(params, dict):
        raise ShapeError('Shape details are missing.')

    if shape == 'polygon':
        pts = _points(params.get('points'), MIN_POLYGON_POINTS, 'polygon')
        if _ring_area_m2(pts) < 1:
            raise ShapeError('The polygon has no area — its points are in a line.')
        return shape, {'points': [{'lat': a, 'lng': b} for a, b in pts]}

    if shape == 'circle':
        lat, lng = _point(params.get('center') or {}, 'The centre')
        radius = _number(params.get('radius_m'), CIRCLE_RADIUS_M, 'The radius')
        return shape, {'center': {'lat': lat, 'lng': lng}, 'radius_m': radius}

    pts = _points(params.get('points'), MIN_LINE_POINTS, 'line')
    width = _number(params.get('width_m'), LINE_WIDTH_M, 'The thickness')
    return shape, {'points': [{'lat': a, 'lng': b} for a, b in pts],
                   'width_m': width}


# ── Geometry ────────────────────────────────────────────────────────────────
# Distances are small next to the Earth, so shapes are built in a local flat
# projection (metres east / north of a reference point) and projected back.

def _to_xy(lat, lng, lat0, lng0):
    k = math.cos(math.radians(lat0))
    return (math.radians(lng - lng0) * _EARTH_M * k,
            math.radians(lat - lat0) * _EARTH_M)


def _to_latlng(x, y, lat0, lng0):
    k = math.cos(math.radians(lat0)) or 1e-12
    return (lat0 + math.degrees(y / _EARTH_M),
            lng0 + math.degrees(x / (_EARTH_M * k)))


def _ring_area_m2(pts):
    lat0 = sum(p[0] for p in pts) / len(pts)
    lng0 = sum(p[1] for p in pts) / len(pts)
    xy = [_to_xy(a, b, lat0, lng0) for a, b in pts]
    s = 0.0
    for i in range(len(xy)):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % len(xy)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def circle_ring(lat, lng, radius_m, segments=CIRCLE_SEGMENTS):
    """[(lat, lng)] around a centre (destination-point formula)."""
    d = radius_m / _EARTH_M
    phi1, lam1 = math.radians(lat), math.radians(lng)
    ring = []
    for i in range(segments):
        theta = 2 * math.pi * i / segments
        phi2 = math.asin(math.sin(phi1) * math.cos(d)
                         + math.cos(phi1) * math.sin(d) * math.cos(theta))
        lam2 = lam1 + math.atan2(math.sin(theta) * math.sin(d) * math.cos(phi1),
                                 math.cos(d) - math.sin(phi1) * math.sin(phi2))
        ring.append((math.degrees(phi2),
                     (math.degrees(lam2) + 540) % 360 - 180))
    return ring


def _offset_side(xy, half, side):
    """Points offset `half` metres to one side (+1 left, -1 right) of a
    polyline, mitred at the corners, the mitre capped at 3x the offset so a
    hairpin does not throw a spike across the map."""
    out = []
    n = len(xy)
    for i in range(n):
        if i == 0:
            dx, dy = xy[1][0] - xy[0][0], xy[1][1] - xy[0][1]
            normals = [(dx, dy)]
        elif i == n - 1:
            dx, dy = xy[i][0] - xy[i - 1][0], xy[i][1] - xy[i - 1][1]
            normals = [(dx, dy)]
        else:
            normals = [(xy[i][0] - xy[i - 1][0], xy[i][1] - xy[i - 1][1]),
                       (xy[i + 1][0] - xy[i][0], xy[i + 1][1] - xy[i][1])]
        units = []
        for dx, dy in normals:
            length = math.hypot(dx, dy) or 1e-9
            units.append((-dy / length * side, dx / length * side))
        nx = sum(u[0] for u in units) / len(units)
        ny = sum(u[1] for u in units) / len(units)
        norm = math.hypot(nx, ny)
        if norm < 1e-9:                      # a full reversal: use one normal
            nx, ny, norm = units[0][0], units[0][1], 1.0
        # Mitre: the averaged normal is shorter than 1 at a corner; scale it
        # so the offset edges stay `half` away from both segments.
        scale = min(1 / norm, 3.0) if len(units) == 2 else 1.0
        nx, ny = nx / norm * scale, ny / norm * scale
        out.append((xy[i][0] + nx * half, xy[i][1] + ny * half))
    return out


def _cap(center, direction, half, steps=8):
    """Half-circle cap round the end of a route heading in `direction`: from
    its left side, through the point ahead, to its right side."""
    dx, dy = direction
    length = math.hypot(dx, dy) or 1e-9
    ux, uy = dx / length, dy / length
    start = math.atan2(ux, -uy)                # angle of the left-hand normal
    pts = []
    for k in range(1, steps):
        a = start - math.pi * k / steps
        pts.append((center[0] + math.cos(a) * half, center[1] + math.sin(a) * half))
    return pts


def corridor_ring(points, width_m):
    """[(lat, lng)] outlining the corridor `width_m` wide around a route."""
    # Drop consecutive duplicates; they have no direction.
    route = [points[0]]
    for p in points[1:]:
        if (round(p[0], 7), round(p[1], 7)) != (round(route[-1][0], 7),
                                                round(route[-1][1], 7)):
            route.append(p)
    lat0 = sum(p[0] for p in route) / len(route)
    lng0 = sum(p[1] for p in route) / len(route)
    xy = [_to_xy(a, b, lat0, lng0) for a, b in route]
    half = width_m / 2

    left = _offset_side(xy, half, +1)
    right = _offset_side(xy, half, -1)
    end_dir = (xy[-1][0] - xy[-2][0], xy[-1][1] - xy[-2][1])
    start_dir = (xy[0][0] - xy[1][0], xy[0][1] - xy[1][1])

    # left side forward, round the far end, right side back, round the start.
    ring_xy = (left
               + _cap(xy[-1], end_dir, half)
               + list(reversed(right))
               + _cap(xy[0], start_dir, half))
    return [_to_latlng(x, y, lat0, lng0) for x, y in ring_xy]


def ring_for(shape, params):
    """The polygon ring to store in geozone_points, as [[lng, lat], ...]."""
    if shape == 'polygon':
        pts = [(p['lat'], p['lng']) for p in params['points']]
    elif shape == 'circle':
        c = params['center']
        pts = circle_ring(c['lat'], c['lng'], params['radius_m'])
    else:
        pts = corridor_ring([(p['lat'], p['lng']) for p in params['points']],
                            params['width_m'])
    return [[round(lng, 7), round(lat, 7)] for lat, lng in pts]


def from_request(data, prefix=''):
    """(shape, params_json, points_json) from a create/update body, or None
    when the body uses the old form (points only, no shape)."""
    shape = data.get(f'{prefix}geozone_shape')
    params = data.get(f'{prefix}geozone_shape_params')
    if shape is None and params is None:
        return None
    shape, clean = normalise(shape, params)
    return shape, json.dumps(clean), json.dumps(ring_for(shape, clean))
