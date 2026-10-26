"""
driver_rules -- what a driver record must hold, and when a driver may be put
in a vehicle. Routes in driver_registry.py; tables in migration 052.

Pure: no Flask, no database, no clock (`today` is passed in), so
tests/test_driver_rules.py runs without a server.

Registering a driver
  Required    full_name, phone, permit_number, permit_expiry, permit_classes
  Optional    ibutton_id, national_id (NIN), employee_number, emergency_name,
              emergency_phone, home_branch, notes   (the photo is uploaded
              separately)

Assigning a driver to a unit
  Only an active driver whose permit has not expired. One current unit per
  driver and one current driver per unit -- the routes end the old
  assignment, and the database's partial unique indexes refuse a second.
"""

import re
from datetime import date, datetime, timedelta

STATUSES = ('active', 'suspended', 'blacklisted', 'inactive')

# Uganda driving permit classes (Traffic and Road Safety Act). Codes only:
# the app shows the code and a short description.
PERMIT_CLASSES = ('A', 'B', 'C', 'CM', 'CH', 'DL', 'DM', 'DH', 'E', 'F', 'G')

# A permit this close to expiry is flagged in the app, before it blocks
# assignment.
EXPIRY_WARNING = timedelta(days=30)

NAME_MAX = 150
NOTES_MAX = 1000

_PERMIT_RE = re.compile(r'^[A-Z0-9][A-Z0-9/-]{2,39}$')
# Uganda NIN: 14 letters and digits, e.g. CM90012345ABCD.
_NIN_RE = re.compile(r'^[A-Z0-9]{14}$')
# An iButton (DS1990A) serial: 64 bits, written as up to 16 hex digits. The
# tracker sends it as driver_id in the same form.
_IBUTTON_RE = re.compile(r'^[0-9A-F]{6,16}$')


def _text(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def normalise_phone(value):
    """'0772 123 456', '256772123456', '+256-772-123456', '772123456' ->
    '+256772123456'. Another country's number keeps its own code ('+254...').
    None when it is not a phone number."""
    raw = str(value or '').strip()
    if not raw:
        return None
    plus = raw.startswith('+')
    digits = re.sub(r'\D', '', raw)
    if plus:
        if digits.startswith('256'):
            local = digits[3:]
        else:
            return '+' + digits if 8 <= len(digits) <= 15 else None
    elif digits.startswith('256') and len(digits) == 12:
        local = digits[3:]
    elif digits.startswith('0') and len(digits) == 10:
        local = digits[1:]
    elif len(digits) == 9:
        local = digits
    else:
        return None
    # Ugandan numbers: nine digits after +256, not starting with 0.
    if len(local) != 9 or local.startswith('0'):
        return None
    return '+256' + local


def normalise_ibutton(value):
    """'01-23-45-67-89-AB-CD-EF', '0x0123456789abcdef' -> '0123456789ABCDEF'.
    None when empty or not a tag ID."""
    raw = str(value or '').strip().upper()
    if raw.startswith('0X'):
        raw = raw[2:]
    raw = re.sub(r'[\s:.-]', '', raw)
    return raw if _IBUTTON_RE.match(raw) else None


def parse_classes(value):
    """'b, cm' or ['B', 'CM'] -> ['B', 'CM'] (known codes, in the official
    order, without repeats). Returns (classes, unknown)."""
    items = value if isinstance(value, (list, tuple)) else str(value or '').split(',')
    wanted = {_text(v).upper() for v in items if _text(v)}
    unknown = sorted(wanted - set(PERMIT_CLASSES))
    return [c for c in PERMIT_CLASSES if c in wanted], unknown


def parse_date(value):
    """'2027-03-31' (or a date) -> date; None when it will not parse."""
    if isinstance(value, date):
        return value if not isinstance(value, datetime) else value.date()
    text = _text(value)
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def validate(data, partial=False):
    """Check a driver record from the app.

    Returns (clean, errors): `clean` holds the normalised fields to store,
    `errors` maps field -> message for the client. With partial=True (an
    edit), only the fields sent are checked and required fields may be
    left out -- but not blanked.
    """
    data = data or {}
    clean, errors = {}, {}

    def sent(key):
        return key in data

    def required(key, label):
        if partial and not sent(key):
            return None
        value = _text(data.get(key))
        if not value:
            errors[key] = f'{label} is required.'
            return None
        return value

    name = required('full_name', 'Full name')
    if name is not None:
        if len(name) < 2 or len(name) > NAME_MAX:
            errors['full_name'] = f'Full name must be 2 to {NAME_MAX} characters.'
        else:
            clean['full_name'] = name

    phone_text = required('phone', 'Phone number')
    if phone_text is not None:
        phone = normalise_phone(phone_text)
        if phone is None:
            errors['phone'] = 'Enter a valid phone number, e.g. 0772 123 456.'
        else:
            clean['phone'] = phone

    permit = required('permit_number', 'Driving permit number')
    if permit is not None:
        permit = permit.upper().replace(' ', '')
        if not _PERMIT_RE.match(permit):
            errors['permit_number'] = (
                'Enter the permit number as printed: letters, digits, '
                '"/" or "-".')
        else:
            clean['permit_number'] = permit

    expiry_text = required('permit_expiry', 'Permit expiry date')
    if expiry_text is not None:
        expiry = parse_date(expiry_text)
        if expiry is None:
            errors['permit_expiry'] = 'Enter the expiry date as YYYY-MM-DD.'
        else:
            clean['permit_expiry'] = expiry

    if not partial or sent('permit_classes'):
        classes, unknown = parse_classes(data.get('permit_classes'))
        if unknown:
            errors['permit_classes'] = (
                'Unknown permit class: ' + ', '.join(unknown) + '.')
        elif not classes:
            errors['permit_classes'] = 'Choose at least one permit class.'
        else:
            clean['permit_classes'] = ','.join(classes)

    # ── optional ────────────────────────────────────────────────────────
    # Sent empty clears the field; not sent leaves it alone.
    if sent('ibutton_id'):
        raw = _text(data.get('ibutton_id'))
        if not raw:
            clean['ibutton_id'] = None
        else:
            tag = normalise_ibutton(raw)
            if tag is None:
                errors['ibutton_id'] = (
                    'Enter the iButton ID as printed on the tag: 6 to 16 '
                    'letters A-F and digits.')
            else:
                clean['ibutton_id'] = tag

    if sent('national_id'):
        raw = _text(data.get('national_id')).upper().replace(' ', '')
        if not raw:
            clean['national_id'] = None
        elif not _NIN_RE.match(raw):
            errors['national_id'] = 'A NIN is 14 letters and digits.'
        else:
            clean['national_id'] = raw

    if sent('emergency_phone'):
        raw = _text(data.get('emergency_phone'))
        if not raw:
            clean['emergency_phone'] = None
        else:
            phone = normalise_phone(raw)
            if phone is None:
                errors['emergency_phone'] = 'Enter a valid phone number.'
            else:
                clean['emergency_phone'] = phone

    for key, limit in (('employee_number', 40), ('emergency_name', NAME_MAX),
                       ('home_branch', 100), ('notes', NOTES_MAX)):
        if sent(key):
            value = _text(data.get(key)) if key != 'notes' else \
                str(data.get(key) or '').strip()
            if len(value) > limit:
                errors[key] = f'At most {limit} characters.'
            else:
                clean[key] = value or None

    return clean, errors


def permit_state(expiry, today):
    """'valid', 'expiring' (within EXPIRY_WARNING) or 'expired'."""
    if expiry is None:
        return 'expired'
    if expiry < today:
        return 'expired'
    if expiry - today <= EXPIRY_WARNING:
        return 'expiring'
    return 'valid'


def assignment_refusal(status, permit_expiry, today):
    """Why this driver may not be put in a unit, or None when they may."""
    if status != 'active':
        return {
            'suspended': 'This driver is suspended.',
            'blacklisted': 'This driver is blacklisted.',
            'inactive': 'This driver is inactive.',
        }.get(status, 'This driver is not active.')
    if permit_state(permit_expiry, today) == 'expired':
        return "This driver's permit has expired. Update it to assign them."
    return None


def status_change_refusal(current, wanted):
    """Why a status may not change from `current` to `wanted`, or None.

    Any change is allowed except to an unknown status or to the same one --
    a blacklisted driver can be reinstated, but only on purpose, which the
    routes record in the audit log with the reason given."""
    if wanted not in STATUSES:
        return 'Status must be one of: ' + ', '.join(STATUSES) + '.'
    if wanted == current:
        return f'This driver is already {wanted}.'
    return None


def ends_assignment(status):
    """A driver moved to this status leaves their unit."""
    return status != 'active'


def public(row, today):
    """A stored driver (dict of columns) as the app receives it."""
    expiry = row.get('permit_expiry')
    return {
        'driver_uid': row.get('driver_uid'),
        'full_name': row.get('full_name'),
        'phone': row.get('phone'),
        'permit_number': row.get('permit_number'),
        'permit_expiry': expiry.isoformat() if expiry else None,
        'permit_state': permit_state(expiry, today),
        'permit_classes': [c for c in str(row.get('permit_classes') or '').split(',') if c],
        'ibutton_id': row.get('ibutton_id'),
        'national_id': row.get('national_id'),
        'employee_number': row.get('employee_number'),
        'has_photo': bool(row.get('photo_file')),
        'emergency_name': row.get('emergency_name'),
        'emergency_phone': row.get('emergency_phone'),
        'home_branch': row.get('home_branch'),
        'notes': row.get('notes'),
        'status': row.get('status'),
        'status_reason': row.get('status_reason'),
        'current_imei': row.get('current_imei'),
        'assigned_at': row['assigned_at'].isoformat() if row.get('assigned_at') else None,
        'created_at': row['created_at'].isoformat() if row.get('created_at') else None,
    }


PHOTO_MAX_BYTES = 5 * 1024 * 1024


def photo_type(head):
    """The image type of an upload from its first bytes -- 'jpg', 'png' or
    'webp' -- or None. The file's own bytes decide, not its name: a renamed
    file of any other kind is refused."""
    head = bytes(head or b'')[:16]
    if head.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'webp'
    return None


PHOTO_MIME = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}


# Unique-index name -> the field the client is told is a duplicate.
DUPLICATE_FIELDS = {
    'uq_driver_phone': ('phone', 'Another driver already has this phone number.'),
    'uq_driver_permit': ('permit_number', 'Another driver already has this permit number.'),
    'uq_driver_ibutton': ('ibutton_id', 'This iButton is already given to another driver.'),
    'uq_driver_nin': ('national_id', 'Another driver already has this NIN.'),
}
