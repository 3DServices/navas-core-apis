# -*- coding: utf-8 -*-
"""Tests for endpoints/driver_rules.py (driver management).

driver_rules.py is pure, so it imports directly.

Run:  python tests/test_driver_rules.py
"""

import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'endpoints'))

import driver_rules as dr                                 # noqa: E402

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


def eq(name, got, want):
    check(name, got == want, 'got %r, want %r' % (got, want))


TODAY = date(2026, 10, 26)

VALID = {
    'full_name': '  Okello   John ',
    'phone': '0772 123 456',
    'permit_number': 'ug 1234567/a',
    'permit_expiry': '2028-03-31',
    'permit_classes': 'b, cm',
}

# ── phone numbers ─────────────────────────────────────────────────────────
for given in ('0772123456', '0772 123 456', '256772123456', '+256772123456',
              '+256 772-123-456', '772123456'):
    eq('phone %r' % given, dr.normalise_phone(given), '+256772123456')
eq('another country keeps its code', dr.normalise_phone('+254 712 345678'),
   '+254712345678')
for bad in ('', '12345', '0072123456', 'phone', '+2567721234567'):
    eq('not a phone %r' % bad, dr.normalise_phone(bad), None)

# ── iButton IDs ───────────────────────────────────────────────────────────
eq('iButton with dashes', dr.normalise_ibutton('01-23-45-67-89-ab-cd-ef'),
   '0123456789ABCDEF')
eq('iButton with 0x', dr.normalise_ibutton('0x00000A1B2C3D'), '00000A1B2C3D')
eq('iButton with spaces', dr.normalise_ibutton('A1 B2 C3 D4'), 'A1B2C3D4')
eq('not hex', dr.normalise_ibutton('XYZ12345'), None)
eq('too long', dr.normalise_ibutton('0123456789ABCDEF0'), None)
eq('too short', dr.normalise_ibutton('A1B2'), None)

# ── permit classes ────────────────────────────────────────────────────────
eq('classes in official order', dr.parse_classes('cm, B, b'), (['B', 'CM'], []))
eq('classes from a list', dr.parse_classes(['DH', 'a']), (['A', 'DH'], []))
eq('unknown class', dr.parse_classes('B, Z'), (['B'], ['Z']))

# ── registering ───────────────────────────────────────────────────────────
clean, errors = dr.validate(VALID)
eq('a valid driver has no errors', errors, {})
eq('name tidied', clean['full_name'], 'Okello John')
eq('phone normalised', clean['phone'], '+256772123456')
eq('permit upper-case, no spaces', clean['permit_number'], 'UG1234567/A')
eq('expiry parsed', clean['permit_expiry'], date(2028, 3, 31))
eq('classes stored', clean['permit_classes'], 'B,CM')
eq('optional fields not sent are not stored', 'national_id' in clean, False)

_, errors = dr.validate({})
eq('every required field is asked for',
   sorted(errors), ['full_name', 'permit_classes', 'permit_expiry',
                    'permit_number', 'phone'])

_, errors = dr.validate(dict(VALID, phone='123'))
eq('a bad phone is refused', 'phone' in errors, True)
_, errors = dr.validate(dict(VALID, permit_expiry='31/02/2027'))
eq('an impossible date is refused', 'permit_expiry' in errors, True)
_, errors = dr.validate(dict(VALID, permit_classes=''))
eq('no class is refused', 'permit_classes' in errors, True)

# ── optional fields ───────────────────────────────────────────────────────
clean, errors = dr.validate(dict(
    VALID, ibutton_id='01:23:45:67:89:AB:CD:EF', national_id='cm 90012345abcd',
    employee_number='E-0042', emergency_name='Achen Mary',
    emergency_phone='0701 234567', home_branch='Mbale', notes='Night shifts'))
eq('optional fields valid', errors, {})
eq('iButton normalised', clean['ibutton_id'], '0123456789ABCDEF')
eq('NIN upper-case, no spaces', clean['national_id'], 'CM90012345ABCD')
eq('emergency phone normalised', clean['emergency_phone'], '+256701234567')

clean, errors = dr.validate(dict(VALID, national_id=''))
eq('the NIN is optional', errors, {})
eq('an empty NIN is stored as none', clean['national_id'], None)

_, errors = dr.validate(dict(VALID, national_id='CM123'))
eq('a short NIN is refused', 'national_id' in errors, True)
_, errors = dr.validate(dict(VALID, ibutton_id='hello'))
eq('a bad iButton is refused', 'ibutton_id' in errors, True)
_, errors = dr.validate(dict(VALID, notes='x' * 1001))
eq('notes have a limit', 'notes' in errors, True)

# ── editing ───────────────────────────────────────────────────────────────
clean, errors = dr.validate({'home_branch': 'Jinja'}, partial=True)
eq('an edit checks only what was sent', (clean, errors),
   ({'home_branch': 'Jinja'}, {}))
_, errors = dr.validate({'phone': ''}, partial=True)
eq('an edit cannot blank a required field', 'phone' in errors, True)
clean, _ = dr.validate({'ibutton_id': ''}, partial=True)
eq('an edit can remove the iButton', clean, {'ibutton_id': None})

# ── permits and assignment ────────────────────────────────────────────────
eq('valid permit', dr.permit_state(date(2027, 1, 1), TODAY), 'valid')
eq('expiring permit', dr.permit_state(date(2026, 11, 10), TODAY), 'expiring')
eq('expires today is still valid', dr.permit_state(TODAY, TODAY), 'expiring')
eq('expired permit', dr.permit_state(date(2026, 10, 25), TODAY), 'expired')

eq('an active driver with a valid permit may drive',
   dr.assignment_refusal('active', date(2027, 1, 1), TODAY), None)
check('a suspended driver may not',
      'suspended' in (dr.assignment_refusal('suspended', date(2027, 1, 1), TODAY) or ''))
check('a blacklisted driver may not',
      'blacklisted' in (dr.assignment_refusal('blacklisted', date(2027, 1, 1), TODAY) or ''))
check('an expired permit may not',
      'expired' in (dr.assignment_refusal('active', date(2026, 1, 1), TODAY) or ''))

eq('suspend an active driver', dr.status_change_refusal('active', 'suspended'), None)
eq('reinstate a blacklisted driver', dr.status_change_refusal('blacklisted', 'active'), None)
check('no change to the same status', dr.status_change_refusal('active', 'active'))
check('no unknown status', dr.status_change_refusal('active', 'fired'))
eq('suspending ends the assignment', dr.ends_assignment('suspended'), True)
eq('staying active does not', dr.ends_assignment('active'), False)

# ── what the app receives ─────────────────────────────────────────────────
out = dr.public({
    'driver_uid': 'd1', 'full_name': 'Okello John', 'phone': '+256772123456',
    'permit_number': 'UG1', 'permit_expiry': date(2026, 11, 1),
    'permit_classes': 'B,CM', 'photo_file': 'd1.jpg', 'status': 'active',
    'current_imei': '354002396040196',
    'assigned_at': datetime(2026, 10, 26, 8, 0), 'created_at': None,
}, TODAY)
eq('classes as a list', out['permit_classes'], ['B', 'CM'])
eq('permit state included', out['permit_state'], 'expiring')
eq('photo file name not exposed, only that there is one',
   ('photo_file' in out, out['has_photo']), (False, True))
eq('current unit', out['current_imei'], '354002396040196')

# ── photos: the bytes decide, not the file name ───────────────────────────
eq('a JPEG', dr.photo_type(b'\xff\xd8\xff\xe0' + bytes(12)), 'jpg')
eq('a PNG', dr.photo_type(b'\x89PNG\r\n\x1a\n' + bytes(8)), 'png')
eq('a WebP', dr.photo_type(b'RIFF' + bytes(4) + b'WEBPVP8 '), 'webp')
eq('a PDF named photo.jpg is refused', dr.photo_type(b'%PDF-1.7\n'), None)
eq('an empty upload is refused', dr.photo_type(b''), None)

if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
