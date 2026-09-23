"""
waswa_context.py — server-side assembly of Waswa's account context.

Replaces the client-supplied `context` string that /assistant/chat used to
trust. Every slot in the master prompt's B2.1 block is either resolved from the
database for the account behind the JWT, or reported as unknown with the reason
why. Nothing is inferred, and nothing the caller sends can influence it.

Three rules this module keeps:

  1. Unknown is a value, and so is its reason. B2.1 says an empty slot is never
     guessed. Every unresolved slot carries a reason, because "unknown" alone
     cannot tell you whether the account is empty, the query is wrong, or the
     lookup was never written.
  2. Tenant scoping happens here, once. Every figure is read for the account's
     own client_uid, so no later feature has to remember to scope.
  3. One connection per request. The caller passes it in; opening a connection
     per lookup is how a chat turn quietly becomes a multi-second one.

Reads Postgres only. Device records live in Cassandra (dll_device_basic_data)
and the per-client query there needs ALLOW FILTERING — a full scan, far too
expensive for every chat turn — so unit counts come from the subscription
tables instead, and are labelled as subscribed units rather than fleet size.
"""

import psycopg2
from flask import current_app

# Slots the master prompt (B2.1) expects.
CONTEXT_SLOTS = (
    'user_role',
    'tenant',
    'branch_or_department',
    'country',
    'language',
    'customer_class',
    'active_products',
    'active_apps',
    'asset_count_and_types',
    'token_balance_and_burn_rate',
    'open_incidents',
    'payment_standing',
    'training_status',
    'surface',
)

# Slots with no source in this database at all. Named so the gap is explicit
# rather than looking like a failed lookup.
#   country / language   not held on dll_client_accounts; finance.py takes them
#                        per request instead.
#   branch_or_department the organogram is not modelled.
#   training_status      no training records in this database.
#
# customer_class has a column as of migration 031 but is assigned by the
# business and NULL until they do it. An unassigned class is reported unknown,
# never computed from the unit count.
NO_SOURCE_YET = {
    'country': 'no country field on the client account',
    'language': 'no language field on the client account',
    'branch_or_department': 'the organogram is not modelled in this database',
    'training_status': 'no training records in this database',
}


def _connect():
    return psycopg2.connect(current_app.config['db_link'])


def build_context(account_uid, surface='mobile', conn=None):
    """Assemble the context for [account_uid].

    Pass [conn] to reuse the caller's connection; otherwise one is opened and
    closed here.

    Returns {'known': {...}, 'unknown': {slot: reason}, 'scope': {...}}.
    Never raises: a failed lookup degrades that slot rather than the turn.
    """
    known = {'surface': surface}
    unknown = {}
    scope = {'account_uid': account_uid, 'account_root': None, 'client_uid': None}

    owns_connection = conn is None
    try:
        if owns_connection:
            conn = _connect()
        with conn.cursor() as cur:
            account, reason = _guard('account lookup', _account, cur, account_uid)
            if not account:
                for slot in CONTEXT_SLOTS:
                    if slot != 'surface':
                        unknown[slot] = reason or 'no account row for this token'
                return {'known': known, 'unknown': unknown, 'scope': scope}

            account_root, account_type, clearance, display_name = account
            scope['account_root'] = account_root
            scope['client_uid'] = account_root

            if clearance:
                known['user_role'] = str(clearance)
            if display_name:
                known['user_name'] = str(display_name)
            if account_type:
                known['account_type'] = str(account_type)

            client, reason = _guard('client lookup', _client_row, cur, account_root)
            if client:
                known['tenant'] = client['client_name']
                if client['customer_class']:
                    known['customer_class'] = client['customer_class']
                else:
                    unknown['customer_class'] = (
                        'no class assigned to this client yet')
            else:
                unknown['tenant'] = reason or (
                    f'no dll_client_accounts row for client_uid {account_root}')
                unknown['customer_class'] = reason or 'no client account row'

            # Each lookup is guarded separately. One failing query must not
            # take the rest of the context down with it, and its error must
            # reach the caller instead of a generic "unknown".
            tokens, reason = _guard('token position', _token_position,
                                    cur, account_root)
            if client and not tokens and reason == _NO_TOKEN_ROWS.format(account_root):
                # The customer record exists and simply holds no packs: that is
                # a balance of none, which the customer should be told, not an
                # unknown ("I don't have that information").
                tokens, reason = {'token_packs': 0,
                                  'note': 'this account holds no token packs yet'}, None
            _place(known, unknown, 'token_balance_and_burn_rate', tokens, reason)

            products_apps, reason = _guard('product lookup', _active_products,
                                           cur, account_root)
            products, apps = products_apps if products_apps else (None, None)
            if client and not products_apps and reason == _NO_PRODUCT_ROWS:
                products, apps, reason = 'none (no token packs yet)', 'none', None
            _place(known, unknown, 'active_products', products, reason)
            _place(known, unknown, 'active_apps', apps, reason)

            units, reason = _guard('subscribed units', _subscribed_units,
                                   cur, account_root)
            if client and not units and reason == _NO_UNIT_ROWS:
                units, reason = {'subscribed_units': 0}, None
            _place(known, unknown, 'asset_count_and_types', units, reason)

            incidents, reason = _guard('open incidents', _open_incidents,
                                       cur, account_root)
            _place(known, unknown, 'open_incidents', incidents, reason)

            payments, reason = _guard('payment history', _payment_history,
                                      cur, account_root)
            _place(known, unknown, 'payment_standing', payments, reason)

            paused, _ = _guard('pause rules', _paused_units, cur, account_root)
            if paused:
                known['paused_units'] = paused

    except Exception as error:      # noqa: BLE001 - context is best-effort
        unknown['context_assembly'] = (
            f'failed before the individual lookups: '
            f'{error.__class__.__name__}: {error}')
    finally:
        if owns_connection and conn:
            conn.close()

    for slot, reason in NO_SOURCE_YET.items():
        unknown.setdefault(slot, reason)
    for slot in CONTEXT_SLOTS:
        if slot not in known and slot not in unknown:
            unknown[slot] = 'no lookup implemented for this slot'

    return {'known': known, 'unknown': unknown, 'scope': scope}


def _guard(label, func, *args):
    """Run one lookup. Returns (value, reason).

    An exception becomes that slot's reason rather than ending the whole
    assembly. The message is kept verbatim — a slot that reads "function
    sum(character varying) does not exist" tells you what to fix; one that
    reads "unknown" does not.
    """
    try:
        result = func(*args)
    except Exception as error:      # noqa: BLE001
        return None, f'{label} failed — {error.__class__.__name__}: {error}'
    if isinstance(result, tuple) and len(result) == 2 and (
            result[1] is None or isinstance(result[1], str)):
        return result
    return result, None


def _place(known, unknown, slot, value, reason):
    """Record a resolved value, or the reason there isn't one."""
    if value:
        known[slot] = value
    else:
        unknown[slot] = reason or 'no rows for this account'


# "Nothing found" reasons that mean the customer holds none, as opposed to a
# lookup that could not tell. build_context turns these into a known zero when
# the customer record itself was found.
_NO_TOKEN_ROWS = 'no rows in dll_user_token_accounts for client_uid {}'
_NO_PRODUCT_ROWS = 'this client holds no token rows'
_NO_UNIT_ROWS = "no dll_device_subscriptions joined to this client's token accounts"


# ── Individual lookups ──────────────────────────────────────────────────────
# Each returns (value, reason). A None value with a reason is a real answer.

def _account(cur, account_uid):
    cur.execute(
        "SELECT account_root, account_type, account_clearance, display_name "
        "FROM dll_access_relay WHERE account_uid = %s",
        (str(account_uid),),
    )
    return cur.fetchone() if cur.rowcount else None


def _client_row(cur, client_uid):
    if not client_uid:
        return None
    cur.execute(
        "SELECT client_name, customer_class "
        "FROM dll_client_accounts WHERE client_uid = %s",
        (str(client_uid),),
    )
    row = cur.fetchone() if cur.rowcount else None
    if not row:
        return None
    return {'client_name': row[0], 'customer_class': row[1]}


def _token_position(cur, client_uid):
    """Units left, units used and how many token packs are held.

    Reads token_units_left / token_used_units. Do NOT use token_hours_left or
    token_hours_used: those columns are tombstoned and every row stores the
    literal string "column deprecated use token_units_left column". Anything
    summing them gets nothing, and anything calling float() on them raises.

    These are units, not hours, and they are reported under names that say so.
    A figure whose unit is guessed is a fabricated figure.
    """
    if not client_uid:
        return None, 'no client_uid on the account'
    # The hours columns have a datatype history (see migration 002,
    # "fix_token_hours_datatype"), so sum through a text-and-regex cast that
    # works whether the column is numeric or character varying, and ignores
    # any non-numeric value rather than failing the whole lookup.
    # Every column on this table is text, so a value is one of three things:
    # a number, a sentinel the billing code writes in place of one, or
    # something unexpected. They are counted separately, because a sentinel is
    # a state to report and only the third is a fault.
    number = r"^\s*-?[0-9][0-9,]*(\.[0-9]+)?\s*$"
    sentinel = r"unfined|undefined|waiting_for_first_use|deprecated"
    total = ("COALESCE(SUM(CASE WHEN {col} ~ %(re)s THEN "
             "REPLACE(TRIM({col}), ',', '')::numeric ELSE 0 END), 0)")
    numeric = "COUNT(*) FILTER (WHERE {col} ~ %(re)s)"
    pending = "COUNT(*) FILTER (WHERE {col} ~* %(sent)s)"
    cur.execute(
        "SELECT COUNT(*), "
        "       COUNT(*) FILTER (WHERE LOWER(token_status) = 'active'), "
        "       STRING_AGG(DISTINCT LOWER(token_status), ', '), "
        "       " + total.format(col='token_units_left') + ", "
        "       " + numeric.format(col='token_units_left') + ", "
        "       " + total.format(col='token_used_units') + ", "
        "       " + numeric.format(col='token_used_units') + ", "
        "       " + pending.format(col='token_units_left') + ", "
        "       COUNT(*) FILTER (WHERE token_units_left IS NULL) "
        "FROM dll_user_token_accounts WHERE client_uid = %(uid)s",
        {'re': number, 'sent': sentinel, 'uid': str(client_uid)},
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return None, _NO_TOKEN_ROWS.format(client_uid)

    (packs, active_packs, statuses, units_left, numeric_left,
     units_used, numeric_used, awaiting, null_left) = row

    position = {
        'token_packs': int(packs),
        'active_token_packs': int(active_packs or 0),
        'pack_statuses': statuses,
        # Burn rate needs a time series; Phase 6 computes it from consumption
        # history. Saying so beats reporting a number we have not measured.
        'burn_rate': 'not measured yet',
    }

    # A number is only reported when at least one row actually held one.
    # Summing zero parseable values would report 0 as a measurement.
    if numeric_left:
        position['token_units_left'] = float(units_left or 0)
        if numeric_left < packs:
            position['units_left_counted_from'] = f'{numeric_left} of {packs} packs'
    if numeric_used:
        position['token_units_used'] = float(units_used or 0)

    if awaiting:
        position['packs_awaiting_first_use'] = int(awaiting)
        position['note'] = (
            f'{awaiting} of {packs} packs carry '
            f'"units_unfined_waiting_for_first_use" — their units are not set '
            f'until the pack is first used, so they are not a balance of zero')

    unexpected = int(packs) - int(numeric_left) - int(awaiting) - int(null_left)
    if unexpected > 0:
        position['unreadable_unit_values'] = unexpected

    # Unknown only when nothing about the position could be established. Packs
    # awaiting first use are a state worth telling the customer, not a gap.
    if not numeric_left and not numeric_used and not awaiting:
        return None, (
            f'{packs} token rows for this client; {null_left} have a NULL '
            f'token_units_left and the rest hold a value that is neither a '
            f'number nor a recognised sentinel')

    return position, None


def _active_products(cur, client_uid):
    """((products, add-on apps), reason) behind the client's tokens.

    NOTE the column-name trap: dll_user_token_accounts.token_balance does NOT
    hold a balance — it holds the token_id from dll_tokens_registry, which
    ClientToken_Balance in tokens_billing.py resolves the same way. The units
    are in token_units_left / token_used_units; the similarly named hours
    columns are tombstoned (see _token_position).
    """
    if not client_uid:
        return None, 'no client_uid on the account'
    cur.execute(
        "SELECT DISTINCT p.product_name, p.service_type "
        "FROM dll_user_token_accounts ta "
        "JOIN dll_tokens_registry t ON t.token_id = ta.token_balance "
        "JOIN abi_products_manager p ON p.product_uid = t.token_product_uid "
        "WHERE ta.client_uid = %s",
        (str(client_uid),),
    )
    rows = cur.fetchall() if cur.rowcount > 0 else []
    if not rows:
        # Say which link in the chain broke. "No product resolved" could mean
        # three different things, and only one of them is a data problem the
        # business needs to hear about.
        cur.execute(
            "SELECT COUNT(*), "
            "       COUNT(t.token_id), "
            "       COUNT(t.token_product_uid), "
            "       COUNT(p.product_uid) "
            "FROM dll_user_token_accounts ta "
            "LEFT JOIN dll_tokens_registry t ON t.token_id = ta.token_balance "
            "LEFT JOIN abi_products_manager p "
            "       ON p.product_uid = t.token_product_uid "
            "WHERE ta.client_uid = %s",
            (str(client_uid),),
        )
        packs, matched_tokens, with_product, with_row = cur.fetchone()
        if not packs:
            return None, _NO_PRODUCT_ROWS
        if not matched_tokens:
            return None, (
                f'{packs} token rows, but none of their token_balance values '
                f'match a token_id in dll_tokens_registry — the tokens these '
                f'packs were sold against are not in the registry')
        if not with_product:
            return None, (f'{matched_tokens} of {packs} token rows resolve to a '
                          f'registry token, but none of those tokens carry a '
                          f'token_product_uid')
        # These are token account ROWS, not distinct tokens — several packs
        # commonly share one token — so the counts are phrased as rows.
        return None, (
            f'{with_product} of {packs} token rows resolve to a registry token '
            f'carrying a product_uid, but {with_row} of those products exist in '
            f'abi_products_manager — the product rows those tokens point at are '
            f'gone')
    products, apps = [], []
    for name, service_type in rows:
        entry = {'product_name': name,
                 'service_type': service_type or 'unclassified'}
        if service_type and 'add-on' in service_type.lower():
            apps.append(entry)
        else:
            products.append(entry)
    return (products or None, apps or None), None


def _subscribed_units(cur, client_uid):
    """Units with a subscription, grouped by status.

    Deliberately not called fleet size: it counts units subscribed through a
    token, which is not every vehicle the customer owns.
    """
    if not client_uid:
        return None, 'no client_uid on the account'
    cur.execute(
        "SELECT ds.subscription_status, COUNT(*) "
        "FROM dll_device_subscriptions ds "
        "JOIN dll_user_token_accounts ta "
        "  ON ta.token_billing_uid = ds.token_billing_uid "
        "WHERE ta.client_uid = %s "
        "GROUP BY ds.subscription_status",
        (str(client_uid),),
    )
    rows = cur.fetchall() if cur.rowcount > 0 else []
    if not rows:
        return None, _NO_UNIT_ROWS
    by_status = {(r[0] or 'unknown'): int(r[1]) for r in rows}
    return {
        'subscribed_units': sum(by_status.values()),
        'by_subscription_status': by_status,
        'unit_types': 'not read (device records live in Cassandra)',
    }, None


def _open_incidents(cur, owner_uid):
    """Unread fired alerts in the last 30 days."""
    if not owner_uid:
        return None, 'no client_uid on the account'
    try:
        cur.execute(
            "SELECT COUNT(*), MIN(date_triggered) "
            "FROM dll_event_notifications "
            "WHERE owner_uid = %s AND is_read = FALSE "
            "  AND date_triggered > NOW() - INTERVAL '30 days'",
            (str(owner_uid),),
        )
        row = cur.fetchone()
    except psycopg2.Error as error:
        # The table is only defined in a comment block in events.py, never in
        # a migration, so it may not exist. Say which, rather than "unknown".
        return None, f'dll_event_notifications unreadable: {error}'
    if not row:
        return None, 'no result from dll_event_notifications'
    return {
        'unread_alerts_30d': int(row[0] or 0),
        'oldest_unread': row[1].isoformat() if row[1] else None,
    }, None


def _payment_history(cur, owner_uid):
    """Observed payment facts — not a judgement about standing.

    Waswa may say when the last payment was and how many there have been. It
    may not conclude that an account is in good or bad standing: that is a
    credit assessment, and nothing here authorises one.
    """
    if not owner_uid:
        return None, 'no client_uid on the account'
    try:
        cur.execute(
            "SELECT payment_status, COUNT(*), MAX(payment_date) "
            "FROM dll_payment_logs WHERE payment_account = %s "
            "GROUP BY payment_status ORDER BY COUNT(*) DESC",
            (str(owner_uid),),
        )
        rows = cur.fetchall() if cur.rowcount > 0 else []
    except psycopg2.Error as error:
        return None, f'dll_payment_logs unreadable: {error}'
    if not rows:
        return None, f'no payments logged for {owner_uid}'

    # Report the statuses as they are stored. An earlier version counted
    # "successful" by guessing that the column says success% or complete%,
    # and reported 0 of 5 because it says something else — a wrong number
    # presented as a fact. Which strings mean paid is the business's to say,
    # not mine to infer.
    by_status = {(r[0] or 'unrecorded'): int(r[1]) for r in rows}
    last_date = max((r[2] for r in rows if r[2]), default=None)
    return {
        'payments_recorded': sum(by_status.values()),
        'by_status': by_status,
        'last_payment_date': str(last_date) if last_date else None,
        'note': 'observed payment records only — not a credit assessment, '
                'and no status here is interpreted as paid or unpaid',
    }, None


def _paused_units(cur, owner_uid):
    """Active pause rules, which explain 'why is this unit not reporting'."""
    if not owner_uid:
        return None
    try:
        cur.execute(
            "SELECT mode, COUNT(*) FROM dll_pause_rules "
            "WHERE owner_uid = %s AND active = TRUE GROUP BY mode",
            (str(owner_uid),),
        )
        rows = cur.fetchall() if cur.rowcount > 0 else []
    except psycopg2.Error:
        return None
    if not rows:
        return None
    return {(r[0] or 'unknown'): int(r[1]) for r in rows}


# ── Rendering for the prompt ────────────────────────────────────────────────

def render_for_prompt(context):
    """Render the context as the text injected into the system prompt.

    Unknown slots are named, not omitted. A model that cannot see which slots
    are missing will fill them in; one told 'customer_class: unknown' has been
    given the answer B2.1 requires it to give.
    """
    lines = ['Account context (authoritative — the only figures you may state):']

    for key, value in sorted(context.get('known', {}).items()):
        lines.append(f'- {key}: {_flatten(value)}')

    unknown = context.get('unknown', {})
    visible = {k: v for k, v in unknown.items() if not k.startswith('_')}
    if visible:
        lines.append('')
        lines.append('Unknown — you do not have these. Do not infer them, and '
                     'say plainly that you do not have them if asked:')
        for key in sorted(visible):
            lines.append(f'- {key}: unknown')

    return '\n'.join(lines)


def _flatten(value):
    if isinstance(value, dict):
        return ', '.join(f'{k}={_flatten(v)}' for k, v in value.items())
    if isinstance(value, list):
        return '; '.join(_flatten(v) for v in value)
    return str(value)
