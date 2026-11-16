# -*- coding: utf-8 -*-
"""Tests for endpoints/branding_rules.py (client branding).

branding_rules.py is pure, so it imports directly.

Run:  python tests/test_branding_rules.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'endpoints'))

import branding_rules as br                                # noqa: E402

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


def eq(name, got, want):
    check(name, got == want, 'got %r, want %r' % (got, want))


# ── colours ───────────────────────────────────────────────────────────────
eq('hex upper-cased with #', br.normalise_hex('1d4ed8'), '#1D4ED8')
eq('short hex expanded', br.normalise_hex('#abc'), '#AABBCC')
eq('not a colour', br.normalise_hex('blue'), None)
eq('white on black is 21:1', round(br.contrast('#000000', '#FFFFFF'), 1), 21.0)
eq('dark ink on a light accent', br.ink_on('#25D366'), br.INK)
eq('white on a dark accent', br.ink_on('#1D4ED8'), br.WHITE)
check('the default brand passes its own rule',
      br.contrast(br.DEFAULT_BRAND, br.WHITE) >= br.MIN_BRAND_CONTRAST)
for name, brand, accent in br.PRESETS:
    _, errors = br.validate_look({'brand_color': brand, 'accent_color': accent})
    eq(f'preset {name} is valid', errors, {})

shades = br.shades('#1D4ED8', '#38BDF8')
check('dark shade is darker', br.luminance(shades['brand_dark']) < br.luminance('#1D4ED8'))
check('soft shade is near white', br.luminance(shades['brand_soft']) > 0.8)
eq('text on the accent', shades['on_accent'], br.INK)

# ── validating a look ─────────────────────────────────────────────────────
clean, errors = br.validate_look({'brand_color': '1d4ed8', 'assistant_name': '  Kato   Bot '})
eq('valid look', errors, {})
eq('colour cleaned', clean['brand_color'], '#1D4ED8')
eq('name spaces collapsed', clean['assistant_name'], 'Kato Bot')
eq('only fields sent change', 'accent_color' in clean, False)

clean, errors = br.validate_look({'brand_color': '', 'assistant_name': ''})
eq('empty goes back to the default', (clean, errors),
   ({'brand_color': None, 'assistant_name': None}, {}))

for name, data, field in [
        ('pale brand: white unreadable', {'brand_color': '#FFF59D'}, 'brand_color'),
        ('not a colour', {'accent_color': 'teal'}, 'accent_color'),
        ('mid-grey accent: nothing reads', {'accent_color': '#777777'}, 'accent_color'),
        ('name too short', {'assistant_name': 'K'}, 'assistant_name'),
        ('name too long', {'assistant_name': 'K' * 25}, 'assistant_name'),
        ('name starts with a digit', {'assistant_name': '9Bot'}, 'assistant_name'),
        ('name with symbols', {'assistant_name': 'Kato<script>'}, 'assistant_name')]:
    _, errors = br.validate_look(data)
    check('refused: ' + name, field in errors, repr(errors))

_, errors = br.validate_look({'brand_color': '#1D4ED8'}, allow_colors=False)
check('colours not allowed', 'brand_color' in errors, repr(errors))
_, errors = br.validate_look({'assistant_name': 'Kato'}, allow_assistant_name=False)
check('rename not allowed', 'assistant_name' in errors, repr(errors))

# ── what staff set ────────────────────────────────────────────────────────
clean, errors = br.validate_control({'enabled': 'true', 'admin_scope': 'Selected',
                                     'allowed_admins': ['a', ' a ', 'b']})
eq('control cleaned', (clean, errors),
   ({'enabled': True, 'admin_scope': 'selected', 'allowed_admins': ['a', 'b']}, {}))
_, errors = br.validate_control({'admin_scope': 'some'})
check('unknown scope refused', 'admin_scope' in errors)
_, errors = br.validate_control({'admin_scope': 'selected', 'allowed_admins': []})
check('selected with nobody refused', 'allowed_admins' in errors)
eq('defaults: off, all administrators', br.control(None),
   {'enabled': False, 'allow_colors': True, 'allow_assistant_name': True,
    'admin_scope': 'all', 'allowed_admins': []})

# ── who may edit ──────────────────────────────────────────────────────────
ON = {'enabled': True, 'allow_colors': True, 'allow_assistant_name': True,
      'admin_scope': 'all', 'allowed_admins': []}
eq('an administrator, switched on', br.edit_refusal(ON, 'u1', 'client_admin'), None)
eq("the account's own login counts as an administrator",
   br.edit_refusal(ON, 'u1', 'customer'), None)
check('an operator may not', br.edit_refusal(ON, 'u1', 'client_operator'))
check('a viewer may not', br.edit_refusal(ON, 'u1', 'client_viewer'))
check('never switched on', 'not enabled' in br.edit_refusal(None, 'u1', 'client_admin'))
check('switched off', br.edit_refusal(dict(ON, enabled=False), 'u1', 'client_admin'))
check('both parts off', br.edit_refusal(dict(ON, allow_colors=False,
                                             allow_assistant_name=False), 'u1', 'client_admin'))
SELECTED = dict(ON, admin_scope='selected', allowed_admins=['u1'])
eq('a chosen administrator', br.edit_refusal(SELECTED, 'u1', 'client_admin'), None)
check('an administrator not chosen', br.edit_refusal(SELECTED, 'u2', 'client_admin'))

# ── what the apps receive ─────────────────────────────────────────────────
out = br.effective(None)
eq('defaults when nothing is saved',
   (out['brand_color'], out['accent_color'], out['assistant_name']),
   (br.DEFAULT_BRAND, br.DEFAULT_ACCENT, 'Waswa'))
eq('nothing customised', set(out['customised'].values()), {False})
out = br.effective(dict(ON, enabled=False, brand_color='#1D4ED8', assistant_name='Kato'))
eq('switched off keeps the look', (out['brand_color'], out['assistant_name']),
   ('#1D4ED8', 'Kato'))
mine = br.for_client(dict(ON, assistant_name='Kato'), 'u1', 'client_admin')
eq('a client sees its look and may edit', (mine['assistant_name'], mine['can_edit']), ('Kato', True))
op = br.for_client(ON, 'u1', 'client_operator')
eq('an operator sees it but may not edit', (op['can_edit'], bool(op['edit_refusal'])), (False, True))
check('presets offered', len(br.defaults()['presets']) == len(br.PRESETS))

if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
