"""
branding_rules -- a client's own look for the OLIWA web console and mobile app:
two colours and the assistant's name. Routes in branding.py; table in
migration 058.

Pure: no Flask, no database, so tests/test_branding_rules.py runs without a
server.

Who may change it
  3D Services staff decide, per client, in the CMS (branding.control):
    enabled               the client may customise at all (off by default)
    allow_colors          ... its colours
    allow_assistant_name  ... the assistant's name
    admin_scope           'all' of the client's administrators (the default),
                          or only the 'selected' ones in allowed_admins
  Operators and viewers never may. Staff with branding.override may change or
  reset a client's look for them.

  Switching a client off stops further changes and keeps its current look;
  staff reset it separately if they want the defaults back.

What is checked
  Colours are #RRGGBB. The brand colour carries white text (headers, buttons),
  so it must be dark enough for white to read on it: at least 4:1, about as
  readable as OLIWA's own teal (#128C7E is 4.1:1; WCAG AA for body text is
  4.5:1, so the rule is no stricter than the product itself). The
  accent colour (call-to-action buttons) must be readable with either white or
  dark text; the readable one is sent with it. The assistant's name is 2 to 24
  characters: letters, digits, spaces, hyphens and apostrophes, starting with
  a letter.
"""

import re

DEFAULT_BRAND = '#128C7E'
DEFAULT_ACCENT = '#25D366'
DEFAULT_ASSISTANT = 'Waswa'

WHITE = '#FFFFFF'
INK = '#111B21'
MIN_CONTRAST = 4.5          # accent, with its best text colour
MIN_BRAND_CONTRAST = 4.0    # brand, with white text

NAME_MIN, NAME_MAX = 2, 24
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 '\-]*$")
_HEX = re.compile(r'^#?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$')

ADMIN_SCOPES = ('all', 'selected')
ADMIN_ROLES = frozenset({'client_admin', 'customer', 'customer_tracker', 'admin'})
MAX_ALLOWED_ADMINS = 200

CONTROL_DEFAULTS = {
    'enabled': False,
    'allow_colors': True,
    'allow_assistant_name': True,
    'admin_scope': 'all',
    'allowed_admins': [],
}

# Ready-made palettes the console offers. Each passes the checks below.
PRESETS = (
    ('OLIWA teal', DEFAULT_BRAND, DEFAULT_ACCENT),
    ('Ocean blue', '#1D4ED8', '#38BDF8'),
    ('Royal purple', '#6D28D9', '#F59E0B'),
    ('Crimson', '#B91C1C', '#FBBF24'),
    ('Forest', '#166534', '#84CC16'),
    ('Charcoal', '#1F2937', '#F97316'),
)


# ── colours ──────────────────────────────────────────────────────────────────

def normalise_hex(value):
    """'#1d4ed8', '1D4ED8', '#abc' -> '#1D4ED8' / '#AABBCC'; None if not a
    colour."""
    text = str(value or '').strip()
    match = _HEX.match(text)
    if not match:
        return None
    digits = match.group(1).upper()
    if len(digits) == 3:
        digits = ''.join(c * 2 for c in digits)
    return '#' + digits


def _channels(hex_colour):
    h = hex_colour.lstrip('#')
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def luminance(hex_colour):
    """WCAG relative luminance, 0 (black) to 1 (white)."""
    def linear(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (linear(c) for c in _channels(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG contrast ratio, 1 to 21."""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def ink_on(hex_colour):
    """The text colour that reads best on [hex_colour]: white or dark ink."""
    return WHITE if contrast(hex_colour, WHITE) >= contrast(hex_colour, INK) else INK


def mix(hex_colour, other, amount):
    """[hex_colour] moved [amount] (0..1) of the way to [other]."""
    a, b = _channels(hex_colour), _channels(other)
    out = [round((x + (y - x) * amount) * 255) for x, y in zip(a, b)]
    return '#' + ''.join(f'{v:02X}' for v in out)


def shades(brand, accent):
    """Everything the apps paint with, worked out from the two colours, so a
    client picks two and still gets a consistent palette."""
    return {
        'brand_color': brand,
        'brand_dark': mix(brand, '#000000', 0.3),     # app bars, headers
        'brand_light': mix(brand, WHITE, 0.25),
        'brand_soft': mix(brand, WHITE, 0.9),         # selected rows, chips
        'on_brand': WHITE,
        'accent_color': accent,
        'accent_pressed': mix(accent, '#000000', 0.12),
        'on_accent': ink_on(accent),
    }


# ── validation ───────────────────────────────────────────────────────────────

def clean_name(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def validate_look(data, allow_colors=True, allow_assistant_name=True):
    """The look a client (or staff) sent. Only the fields sent change; a field
    sent empty goes back to the default (stored as None).

    Returns (clean, errors). A field the client may not change is an error,
    not silently dropped, so the console says why."""
    data = data or {}
    clean, errors = {}, {}

    for key, label in (('brand_color', 'brand colour'), ('accent_color', 'accent colour')):
        if key not in data:
            continue
        if not allow_colors:
            errors[key] = 'Your account may not change its colours.'
            continue
        raw = data.get(key)
        if raw is None or str(raw).strip() == '':
            clean[key] = None
            continue
        colour = normalise_hex(raw)
        if colour is None:
            errors[key] = f'Enter the {label} as #RRGGBB, e.g. #1D4ED8.'
            continue
        clean[key] = colour

    brand = clean.get('brand_color')
    if brand and contrast(brand, WHITE) < MIN_BRAND_CONTRAST:
        errors['brand_color'] = ('White text is hard to read on this colour. '
                                 'Choose a darker brand colour.')
    accent = clean.get('accent_color')
    if accent and max(contrast(accent, WHITE), contrast(accent, INK)) < MIN_CONTRAST:
        errors['accent_color'] = ('Neither white nor dark text reads well on '
                                  'this colour. Choose a lighter or darker one.')

    if 'assistant_name' in data:
        if not allow_assistant_name:
            errors['assistant_name'] = 'Your account may not rename the assistant.'
        else:
            name = clean_name(data.get('assistant_name'))
            if not name:
                clean['assistant_name'] = None
            elif not NAME_MIN <= len(name) <= NAME_MAX:
                errors['assistant_name'] = (
                    f'The name is {NAME_MIN} to {NAME_MAX} characters.')
            elif not _NAME.match(name):
                errors['assistant_name'] = ('Use letters, digits, spaces, hyphens '
                                            'or apostrophes, starting with a letter.')
            else:
                clean['assistant_name'] = name
    return clean, errors


def _flag(value):
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def validate_control(data):
    """What staff set for a client in the CMS. Only the fields sent change.
    Returns (clean, errors)."""
    data = data or {}
    clean, errors = {}, {}
    for key in ('enabled', 'allow_colors', 'allow_assistant_name'):
        if key in data:
            clean[key] = _flag(data[key])
    if 'admin_scope' in data:
        scope = str(data.get('admin_scope') or '').strip().lower()
        if scope not in ADMIN_SCOPES:
            errors['admin_scope'] = 'Choose all administrators, or selected ones.'
        else:
            clean['admin_scope'] = scope
    if 'allowed_admins' in data:
        raw = data.get('allowed_admins') or []
        if isinstance(raw, str):
            raw = raw.split(',')
        if not isinstance(raw, (list, tuple)):
            errors['allowed_admins'] = 'Send the administrators as a list.'
        else:
            uids = list(dict.fromkeys(str(u).strip() for u in raw if str(u).strip()))
            if len(uids) > MAX_ALLOWED_ADMINS:
                errors['allowed_admins'] = f'At most {MAX_ALLOWED_ADMINS} administrators.'
            else:
                clean['allowed_admins'] = uids
    scope = clean.get('admin_scope')
    if scope == 'selected' and 'allowed_admins' in clean and not clean['allowed_admins']:
        errors['allowed_admins'] = 'Choose at least one administrator.'
    return clean, errors


# ── who may edit ─────────────────────────────────────────────────────────────

def is_client_admin(role):
    return str(role or '').strip().lower() in ADMIN_ROLES


def edit_refusal(settings, account_uid, role):
    """Why this client user may not change the look, or None when they may.

    settings  the client's row (None when staff never switched it on)"""
    if not is_client_admin(role):
        return 'Only your account administrators can change the branding.'
    s = settings or {}
    if not s.get('enabled'):
        return ('Branding is not enabled for your account. '
                'Contact 3D Services to have it switched on.')
    if not (s.get('allow_colors') or s.get('allow_assistant_name')):
        return 'Branding is not enabled for your account.'
    if (s.get('admin_scope') or 'all') == 'selected' \
            and str(account_uid) not in (s.get('allowed_admins') or []):
        return ('Only the administrators 3D Services chose can change the '
                'branding of your account.')
    return None


# ── what the apps receive ────────────────────────────────────────────────────

def effective(settings):
    """The look to paint with: the client's choices, or the defaults. Applies
    whether or not the client may still edit it (switching a client off keeps
    its look)."""
    s = settings or {}
    brand = s.get('brand_color') or DEFAULT_BRAND
    accent = s.get('accent_color') or DEFAULT_ACCENT
    out = shades(brand, accent)
    out['assistant_name'] = s.get('assistant_name') or DEFAULT_ASSISTANT
    out['customised'] = {
        'brand_color': bool(s.get('brand_color')),
        'accent_color': bool(s.get('accent_color')),
        'assistant_name': bool(s.get('assistant_name')),
    }
    return out


def control(settings):
    """The CMS switches for a client, with the defaults filled in."""
    s = settings or {}
    out = {k: s.get(k, v) if s.get(k) is not None else v
           for k, v in CONTROL_DEFAULTS.items()}
    out['allowed_admins'] = list(s.get('allowed_admins') or [])
    return out


def defaults():
    return {
        'brand_color': DEFAULT_BRAND,
        'accent_color': DEFAULT_ACCENT,
        'assistant_name': DEFAULT_ASSISTANT,
        'presets': [{'name': n, 'brand_color': b, 'accent_color': a}
                    for n, b, a in PRESETS],
    }


def for_client(settings, account_uid, role):
    """GET /branding/me for a client user."""
    refusal = edit_refusal(settings, account_uid, role)
    c = control(settings)
    return dict(effective(settings),
                can_edit=refusal is None,
                edit_refusal=refusal,
                enabled=c['enabled'],
                allow_colors=c['allow_colors'],
                allow_assistant_name=c['allow_assistant_name'],
                defaults=defaults())
