"""
waswa_products.py — Waswa's product tools (PPMM).

Phase 2. These are the functions Waswa calls instead of being told about
products in its prompt. The master prompt's A1.3 rule is that the path runs
PPMM database -> tool call -> Waswa, so that adding a product to the catalogue
changes what Waswa says without anyone rewriting a prompt.

Design rules these functions keep:

  * A not-found is a successful answer, not an error. `found: False` with
    near-miss candidates is what lets Waswa say "I don't have that in approved
    information" instead of inventing a product. Appendix D test 5 checks it.
  * Every result carries authority_level and source_ref, so the caller can
    record the evidence behind an answer and the Phase 4 validator has
    something to check the draft against.
  * Nothing here reads marketing copy. These tables are level 1 — approved
    product data. Website content lives in a separate index at level 5 and
    cannot be returned by a product tool.
  * Empty is not the same as false. A product with no hardware rows is not a
    product with no hardware requirements, so compatibility_check answers
    "cannot confirm from data" and the conversation goes to a site survey.
"""

import difflib

import psycopg2
from flask import current_app

# How close a fuzzy match must be before it is offered as a candidate.
_FUZZY_CUTOFF = 0.6
_MAX_CANDIDATES = 5

_PRODUCT_COLUMNS = (
    "product_uid, product_code, product_name, customer_facing_name, "
    "product_description, service_type, product_family, outcomes, "
    "asset_types, token_class, country_scope, lifecycle_status, "
    "authority_level, source_ref, catalog_version, attributes_loaded_at"
)


def _connect():
    return psycopg2.connect(current_app.config['db_link'])


def _row_to_product(row):
    (uid, code, name, cf_name, description, service_type, family, outcomes,
     asset_types, token_class, country_scope, status, authority, source_ref,
     catalog_version, loaded_at) = row
    return {
        'product_uid': uid,
        'product_code': code,
        'product_name': name,
        'customer_facing_name': cf_name or name,
        'description': description,
        'service_type': service_type,
        'product_family': family,
        'outcomes': outcomes,
        'asset_types': asset_types,
        'token_class': token_class,
        'country_scope': country_scope,
        'lifecycle_status': status or 'active',
        'authority_level': authority if authority is not None else 1,
        'source_ref': source_ref or 'abi_products_manager',
        'catalog_version': catalog_version,
        'attributes_loaded': loaded_at is not None,
    }


def _key(text):
    return ' '.join(str(text or '').split()).lower()


def _all_names(cur):
    """lowercased name or alias -> [product_uid, ...].

    A name maps to a LIST, not a single uid, because the catalogue holds
    duplicates: the same product exists once as an approved catalogue row with
    a 3D-PRD code and a service_type, and again as an ad-hoc row created
    through /billing/products/create with neither. Keying a dict by name
    collapses those two and silently picks whichever the query returned last,
    which is how a product answer loses its service type without anyone
    noticing.

    Aliases never override a real product name.
    """
    index = {}
    cur.execute("SELECT product_name, product_uid FROM abi_products_manager")
    if cur.rowcount > 0:
        for name, uid in cur.fetchall():
            key = _key(name)
            if key:
                index.setdefault(key, []).append(uid)

    cur.execute("SELECT alias, product_uid FROM abi_product_aliases")
    if cur.rowcount > 0:
        for alias, uid in cur.fetchall():
            key = _key(alias)
            if key and key not in index:
                index[key] = [uid]
    return index


def _preferred(cur, uids):
    """(chosen_uid, others) when a name maps to several product rows.

    The approved catalogue row wins: it carries the product code and the
    service type, and the master prompt's authority ladder puts approved
    product data above anything else. The others are returned so the answer
    can say the ambiguity exists rather than hiding it.
    """
    if len(uids) == 1:
        return uids[0], []
    cur.execute(
        "SELECT product_uid FROM abi_products_manager "
        "WHERE product_uid = ANY(%s) "
        "ORDER BY CASE WHEN product_code LIKE '3D-PRD-%%' THEN 0 ELSE 1 END, "
        "         CASE WHEN service_type IS NOT NULL AND service_type <> '' "
        "              THEN 0 ELSE 1 END, "
        "         product_uid",
        (list(uids),),
    )
    ordered = [r[0] for r in cur.fetchall()] if cur.rowcount > 0 else list(uids)
    return ordered[0], ordered[1:]


def _fetch_by_uid(cur, product_uid):
    cur.execute(
        f"SELECT {_PRODUCT_COLUMNS} FROM abi_products_manager "
        "WHERE product_uid = %s",
        (product_uid,),
    )
    row = cur.fetchone() if cur.rowcount else None
    return _row_to_product(row) if row else None


def _capabilities(cur, product_uid):
    cur.execute(
        "SELECT capability, detail, source_ref, authority_level "
        "FROM abi_product_capabilities WHERE product_uid = %s "
        "ORDER BY capability",
        (product_uid,),
    )
    if cur.rowcount <= 0:
        return []
    return [
        {'capability': r[0], 'detail': r[1], 'source_ref': r[2],
         'authority_level': r[3]}
        for r in cur.fetchall()
    ]


def _hardware(cur, product_uid):
    cur.execute(
        "SELECT hardware_name, hardware_role, is_required, notes, source_ref "
        "FROM abi_product_hardware WHERE product_uid = %s "
        "ORDER BY hardware_role, hardware_name",
        (product_uid,),
    )
    if cur.rowcount <= 0:
        return []
    return [
        {'hardware_name': r[0], 'role': r[1], 'required': r[2],
         'notes': r[3], 'source_ref': r[4]}
        for r in cur.fetchall()
    ]


def _segments(cur, product_uid):
    cur.execute(
        "SELECT segment_kind, segment_value FROM abi_product_segments "
        "WHERE product_uid = %s ORDER BY segment_kind, segment_value",
        (product_uid,),
    )
    if cur.rowcount <= 0:
        return []
    return [{'kind': r[0], 'value': r[1]} for r in cur.fetchall()]


# ── Tools ───────────────────────────────────────────────────────────────────

def product_lookup(name, include_detail=True):
    """Resolve a product by name, alias, or near spelling.

    Returns {found, matched_via, product, capabilities, hardware, segments,
    candidates}. `found: False` with candidates is a real answer — Waswa should
    say it does not have that product and, at most, ask whether one of the
    candidates was meant.
    """
    query = (name or '').strip()
    if not query:
        return {'found': False, 'reason': 'no name given', 'candidates': []}

    conn = None
    try:
        conn = _connect()
        with conn:
            with conn.cursor() as cur:
                names = _all_names(cur)
                if not names:
                    return {'found': False, 'reason': 'catalogue is empty',
                            'candidates': []}

                wanted = _key(query)
                matched_uids, matched_via = None, None

                if wanted in names:
                    matched_uids, matched_via = names[wanted], 'exact'

                if not matched_uids:
                    close = difflib.get_close_matches(
                        wanted, list(names), n=_MAX_CANDIDATES,
                        cutoff=_FUZZY_CUTOFF)
                    if close:
                        # A single strong match resolves; several close ones
                        # are offered rather than guessed between.
                        if len(close) == 1 or difflib.SequenceMatcher(
                                None, wanted, close[0]).ratio() >= 0.9:
                            matched_uids, matched_via = names[close[0]], 'fuzzy'
                        else:
                            return {
                                'found': False,
                                'reason': 'several products are close to that name',
                                'candidates': close,
                            }

                if not matched_uids:
                    return {'found': False,
                            'reason': 'no approved product matches that name',
                            'candidates': []}

                matched_uid, others = _preferred(cur, matched_uids)
                product = _fetch_by_uid(cur, matched_uid)
                if not product:
                    return {'found': False, 'reason': 'product row missing',
                            'candidates': []}

                notes = []
                result = {'found': True, 'matched_via': matched_via,
                          'product': product}

                if others:
                    result['duplicate_rows'] = len(others) + 1
                    result['answered_from'] = (
                        'the approved catalogue row' if product['product_code']
                        else 'the only row available')
                    notes.append(
                        f'{len(others) + 1} product rows share this name in the '
                        f'catalogue. This answer uses '
                        f'{result["answered_from"]}. Do not present the others '
                        f'as separate products.')

                if include_detail:
                    result['capabilities'] = _capabilities(cur, matched_uid)
                    result['hardware'] = _hardware(cur, matched_uid)
                    result['segments'] = _segments(cur, matched_uid)
                    if not product['attributes_loaded']:
                        notes.append(
                            'Capability and hardware detail has not been loaded '
                            'for this product yet. Say so rather than implying '
                            'it has no capabilities.')
                    if not product['service_type']:
                        notes.append(
                            'This product row carries no service type. Do not '
                            'assign it to one.')

                if notes:
                    result['notes'] = notes
                return result
    except psycopg2.Error as error:
        return {'found': False, 'reason': f'catalogue unavailable: {error}',
                'candidates': []}
    finally:
        if conn:
            conn.close()


def product_search(capability=None, service_type=None, asset_type=None,
                   text=None, limit=10):
    """Find products by what they do, for when a customer describes a problem
    rather than naming a product."""
    clauses, params = ["(p.lifecycle_status = 'active' OR p.lifecycle_status IS NULL)"], []

    if service_type:
        clauses.append("p.service_type ILIKE %s")
        params.append(f'%{service_type}%')
    if asset_type:
        clauses.append("p.asset_types ILIKE %s")
        params.append(f'%{asset_type}%')
    if text:
        clauses.append("(p.product_name ILIKE %s OR p.product_description ILIKE %s "
                       "OR p.outcomes ILIKE %s)")
        params.extend([f'%{text}%'] * 3)
    if capability:
        clauses.append(
            "EXISTS (SELECT 1 FROM abi_product_capabilities c "
            "WHERE c.product_uid = p.product_uid AND c.capability ILIKE %s)")
        params.append(f'%{capability}%')

    conn = None
    try:
        conn = _connect()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_PRODUCT_COLUMNS} FROM abi_products_manager p "
                    "WHERE " + " AND ".join(clauses) +
                    " ORDER BY p.service_type NULLS LAST, p.product_name LIMIT %s",
                    params + [int(limit)],
                )
                rows = cur.fetchall() if cur.rowcount > 0 else []
                products = [_row_to_product(r) for r in rows]
        return {
            'count': len(products),
            'products': products,
            'criteria': {'capability': capability, 'service_type': service_type,
                         'asset_type': asset_type, 'text': text},
            'note': None if products else
                    'Nothing in the approved catalogue matches. Do not widen '
                    'the search by inventing a product.',
        }
    except psycopg2.Error as error:
        return {'count': 0, 'products': [],
                'note': f'catalogue unavailable: {error}'}
    finally:
        if conn:
            conn.close()


def product_compare(names, limit=4):
    """Side-by-side for the comparison response shape (B4.2)."""
    if not names:
        return {'compared': [], 'not_found': [],
                'note': 'no products named'}
    compared, missing = [], []
    for name in list(names)[:limit]:
        result = product_lookup(name)
        if result.get('found'):
            compared.append({
                'product': result['product'],
                'capabilities': [c['capability'] for c in result.get('capabilities', [])],
                'hardware': [h['hardware_name'] for h in result.get('hardware', [])],
            })
        else:
            missing.append({'name': name, 'reason': result.get('reason'),
                            'candidates': result.get('candidates', [])})
    return {
        'compared': compared,
        'not_found': missing,
        'note': ('Compare only on the dimensions present here. A blank is '
                 'missing data, not a missing feature.'),
    }


def compatibility_check(product_name, deployed_hardware=None):
    """Can this product run on this hardware?

    Three verdicts, and the third one matters most: 'cannot_confirm' is what
    sends the conversation to a site survey instead of to a wrong sale.
    """
    result = product_lookup(product_name)
    if not result.get('found'):
        return {'verdict': 'unknown_product', 'product': product_name,
                'reason': result.get('reason'),
                'candidates': result.get('candidates', [])}

    product = result['product']
    hardware = result.get('hardware', [])

    if not hardware:
        return {
            'verdict': 'cannot_confirm',
            'product': product['product_name'],
            'reason': 'no hardware requirements recorded for this product',
            'next_step': 'site survey or confirmation from the technical team',
        }

    required = [h['hardware_name'] for h in hardware if h['required']]
    if not deployed_hardware:
        return {
            'verdict': 'cannot_confirm',
            'product': product['product_name'],
            'requires': required,
            'reason': 'the customer\'s deployed hardware was not provided',
            'next_step': 'confirm what is installed on the vehicles',
        }

    deployed = [str(h).strip().lower() for h in deployed_hardware]
    matched = [h for h in required if any(h.lower() in d or d in h.lower()
                                          for d in deployed)]
    unmatched = [h for h in required if h not in matched]

    if not unmatched:
        return {'verdict': 'compatible', 'product': product['product_name'],
                'requires': required, 'satisfied_by': deployed}
    return {
        'verdict': 'cannot_confirm',
        'product': product['product_name'],
        'requires': required,
        'missing': unmatched,
        'reason': 'the deployed hardware does not cover every requirement',
        'next_step': 'site survey to confirm what is fitted',
    }


# ── Tool specifications for the model ───────────────────────────────────────

TOOL_SPECS = [
    {
        'type': 'function',
        'function': {
            'name': 'product_lookup',
            'description': (
                'Look up one product in the approved PPMM catalogue by name. '
                'Use this before saying anything about a specific product. '
                'Returns found: false when there is no such approved product.'),
            'parameters': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string',
                             'description': 'Product name as the customer said it.'},
                },
                'required': ['name'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'product_search',
            'description': (
                'Find products by capability, service type, asset type or free '
                'text. Use when the customer describes a problem rather than '
                'naming a product.'),
            'parameters': {
                'type': 'object',
                'properties': {
                    'capability': {'type': 'string'},
                    'service_type': {
                        'type': 'string',
                        'description': 'e.g. Fuel Telematics, Vehicle Telematics.'},
                    'asset_type': {'type': 'string',
                                   'description': 'e.g. truck, motorcycle, generator.'},
                    'text': {'type': 'string'},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'product_compare',
            'description': 'Compare two or more approved products side by side.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'names': {'type': 'array', 'items': {'type': 'string'}},
                },
                'required': ['names'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'compatibility_check',
            'description': (
                'Check whether a product can run on hardware the customer '
                'already has. Returns cannot_confirm when the data does not '
                'settle it — never assume compatibility.'),
            'parameters': {
                'type': 'object',
                'properties': {
                    'product_name': {'type': 'string'},
                    'deployed_hardware': {'type': 'array',
                                          'items': {'type': 'string'}},
                },
                'required': ['product_name'],
            },
        },
    },
]

_DISPATCH = {
    'product_lookup': product_lookup,
    'product_search': product_search,
    'product_compare': product_compare,
    'compatibility_check': compatibility_check,
}


def dispatch(tool_name, arguments):
    """Run a tool by name. Unknown tools and bad arguments return a result the
    model can read, rather than raising into the request."""
    func = _DISPATCH.get(tool_name)
    if not func:
        return {'error': f'no such tool: {tool_name}'}
    try:
        return func(**(arguments or {}))
    except TypeError as error:
        return {'error': f'bad arguments for {tool_name}: {error}'}
    except Exception as error:      # noqa: BLE001 - never break the turn
        return {'error': f'{tool_name} failed: {error}'}
