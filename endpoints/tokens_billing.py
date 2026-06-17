from flask import Flask
from flask import Blueprint
from flask import request
import psycopg2
from flask import json
from flask import jsonify
import datetime
import random
from flask import current_app
import base64
from decimal import Decimal, InvalidOperation
from .globals import reply
import base64
import requests
from .globals import check_device
import uuid
import string
import pytz
from datetime import datetime
from .globals import SubscriptionManager
from zoneinfo import ZoneInfo
from .globals import require_permission

_KLA = ZoneInfo("Africa/Kampala")


_token_billing = Blueprint("TokenBilling", __name__)

timezone = pytz.timezone('Africa/Nairobi')

_VALID_TYPES = {
    'time', 'parameter', 'event', 'volume',
    'distance', 'video', 'conditional', 'action', 'compliance'
}
_VALID_UNITS = {
    'hour', 'unit', 'event', 'km', 'meter',
    'mb', 'image', 'command', 'report', 'period', 'inference'
}
_VALID_TRIGGERS = {
    'continuous', 'on_read', 'on_event', 'on_distance',
    'on_threshold', 'on_command', 'on_schedule', 'on_consume'
}
_VALID_SCOPES = {'asset', 'driver', 'fleet', 'shipment'}

_DEFAULT_UNIT = {
    'time': 'hour', 'parameter': 'unit', 'event': 'event',
    'volume': 'mb', 'distance': 'km', 'video': 'image',
    'conditional': 'event', 'action': 'command', 'compliance': 'report',
}
_DEFAULT_TRIGGER = {
    'time': 'continuous', 'parameter': 'on_read', 'event': 'on_event',
    'volume': 'on_consume', 'distance': 'on_distance', 'video': 'on_consume',
    'conditional': 'on_threshold', 'action': 'on_command', 'compliance': 'on_schedule',
}

def response_out(status, message, statusCode, data):
    return jsonify({
        "status": status,
        "message": message,
        "data": data
    }), statusCode


def _fetch_product(cursor, product_uid):
    """Return product (billing) details dict from abi_products_manager, or None if not found."""
    if not product_uid:
        return None
    cursor.execute(
        "SELECT product_uid, product_name, billing_type, billing_amount, billing_currency "
        "FROM abi_products_manager WHERE product_uid = %s",
        (str(product_uid),)
    )
    if cursor.rowcount == 0:
        return None
    row = cursor.fetchone()
    return {
        "product_uid": row[0],
        "product_name": row[1],
        "billing_type": row[2],
        "billing_amount": float(row[3]) if row[3] is not None else None,
        "billing_currency": row[4]
    }


def _compose_token_name(product_name, token_name):
    """Prefix the entered token name with the product name in caps, e.g. ('oliwa', 'LITE') -> 'OLIWA_LITE'.
    Idempotent: avoids double-prefixing if the name already carries the prefix."""
    prefix = f"{str(product_name).upper()}_"
    token_name = str(token_name).strip()
    if token_name.upper().startswith(prefix):
        return token_name
    return f"{prefix}{token_name}"


@_token_billing.route("/tokens/create", methods=["POST"])
@require_permission('tokens.create')
def CreateToken():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()
    data = _payload['data']

    _TokenName            = data['token_name']
    _TokenType            = data['token_type']
    _Token_Product        = data['token_product_uid']
    _TokenParameters      = data.get('token_parameters', [])
    _BillingUnit          = data.get('billing_unit') or _DEFAULT_UNIT.get(_TokenType)
    _BillingTrigger       = data.get('billing_trigger') or _DEFAULT_TRIGGER.get(_TokenType)
    _BillingConditions    = data.get('billing_conditions', [])
    _BillingScope         = data.get('billing_scope', 'asset')
    _TokenID              = str(uuid.uuid4())
    _CreatedAt            = datetime.now(timezone).strftime("%d-%m-%Y %I:%M:%S%p")

    if _TokenType not in _VALID_TYPES:
        return response_out("error", f"Invalid token_type. Allowed: {sorted(_VALID_TYPES)}", 400, "")
    if _BillingUnit and _BillingUnit not in _VALID_UNITS:
        return response_out("error", f"Invalid billing_unit. Allowed: {sorted(_VALID_UNITS)}", 400, "")
    if _BillingTrigger and _BillingTrigger not in _VALID_TRIGGERS:
        return response_out("error", f"Invalid billing_trigger. Allowed: {sorted(_VALID_TRIGGERS)}", 400, "")
    if _BillingScope not in _VALID_SCOPES:
        return response_out("error", f"Invalid billing_scope. Allowed: {sorted(_VALID_SCOPES)}", 400, "")
    if _TokenType == 'conditional' and not _BillingConditions:
        return response_out("error", "billing_conditions is required for conditional tokens", 400, "")

    with dbconnect:
        with dbconnect.cursor() as cursor:
            product = _fetch_product(cursor, _Token_Product)
            if product is None:
                return response_out("error", "Product not found", 404, "")

            # Tag the token to its product by prefixing the product name in caps, e.g. OLIWA_LITE
            _TokenName = _compose_token_name(product["product_name"], _TokenName)

            cursor.execute(
                "SELECT id FROM dll_tokens_registry WHERE token_name=%s AND token_type=%s",
                (str(_TokenName), str(_TokenType),)
            )

            if cursor.rowcount >= 1:
                return response_out("error", "Token already exists", 409, "")

            cursor.execute(
                "INSERT INTO dll_tokens_registry "
                "(token_id, token_name, token_type, token_product_uid, token_parameters, "
                " billing_unit, billing_trigger, billing_conditions, billing_scope, date_created) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (_TokenID, _TokenName, _TokenType, str(_Token_Product),
                 json.dumps(_TokenParameters), _BillingUnit, _BillingTrigger,
                 json.dumps(_BillingConditions), _BillingScope, _CreatedAt)
            )
            dbconnect.commit()
            return response_out("success", "Token created successfully", 201, {"token_id": _TokenID, "token_name": _TokenName})


@_token_billing.route("/tokens", methods=["GET"])
def ListTokens():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute(
                "SELECT token_id, token_name, token_type, token_parameters, date_created, "
                "token_product_uid, billing_unit, billing_trigger, billing_conditions, billing_scope "
                "FROM dll_tokens_registry ORDER BY id DESC"
            )

            if cursor.rowcount == 0:
                return response_out("error", "No tokens found", 404, [])

            tokens = cursor.fetchall()
            _tokensBusket = []
            for token in tokens:
                _product_uid = token[5]
                product = _fetch_product(cursor, _product_uid)
                _tokensBusket.append({
                    "token_id": token[0],
                    "token_name": token[1],
                    "token_type": token[2],
                    "token_parameters": json.loads(token[3]) if token[3] else [],
                    "date_created": token[4],
                    "token_product_uid": _product_uid,
                    "billing_unit": token[6],
                    "billing_trigger": token[7],
                    "billing_conditions": token[8] if token[8] is not None else [],
                    "billing_scope": token[9],
                    "product": product
                })
            return response_out("success", "Tokens retrieved successfully", 200, _tokensBusket)


@_token_billing.route("/tokens/budget-offer", methods=["POST"])
def TokensBudgetOffer():
    """Given a currency and an amount, return the available tokens whose product
    billing price (same currency) fits within that budget."""
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()
    data = (_payload or {}).get('data', {})

    _Currency = data.get('currency')
    _Amount   = data.get('amount')

    if not _Currency or str(_Currency).strip() == "":
        return response_out("error", "currency is required", 400, [])
    if _Amount is None:
        return response_out("error", "amount is required", 400, [])

    try:
        _Budget = Decimal(str(_Amount))
    except (InvalidOperation, ValueError, TypeError):
        return response_out("error", "amount must be a number", 400, [])

    if _Budget <= Decimal('0'):
        return response_out("error", "amount must be greater than zero", 400, [])

    _Currency = str(_Currency).strip().upper()

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute(
                "SELECT t.token_id, t.token_name, t.token_type, t.token_product_uid, "
                "       t.billing_unit, t.billing_trigger, t.billing_scope, "
                "       p.product_name, p.billing_type, p.billing_amount, p.billing_currency "
                "FROM dll_tokens_registry t "
                "JOIN abi_products_manager p ON t.token_product_uid = p.product_uid "
                "WHERE UPPER(p.billing_currency) = %s "
                "  AND p.billing_amount IS NOT NULL "
                "  AND p.billing_amount > 0 "
                "  AND p.billing_amount <= %s "
                "ORDER BY p.billing_amount ASC",
                (_Currency, _Budget)
            )

            if cursor.rowcount == 0:
                return response_out("success", "No tokens fit within this budget", 200, [])

            _offers = []
            for row in cursor.fetchall():
                _price = Decimal(str(row[9]))
                _offers.append({
                    "token_id": row[0],
                    "token_name": row[1],
                    "token_type": row[2],
                    "token_product_uid": row[3],
                    "billing_unit": row[4],
                    "billing_trigger": row[5],
                    "billing_scope": row[6],
                    "product_name": row[7],
                    "billing_type": row[8],
                    "billing_amount": float(_price),
                    "billing_currency": row[10],
                    "max_quantity_affordable": int(_Budget // _price)
                })

            return response_out("success", "Tokens within budget retrieved successfully", 200, {
                "currency": _Currency,
                "budget": float(_Budget),
                "tokens": _offers
            })


@_token_billing.route("/tokens/<string:token_id>", methods=["GET"])
def GetSingleToken(token_id):
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute(
                "SELECT token_id, token_name, token_type, token_parameters, date_created, "
                "token_product_uid, billing_unit, billing_trigger, billing_conditions, billing_scope "
                "FROM dll_tokens_registry WHERE token_id=%s",
                (token_id,)
            )

            if cursor.rowcount == 0:
                return response_out("error", "Token not found", 404, [])

            row = cursor.fetchone()
            _product_uid = row[5]
            product = _fetch_product(cursor, _product_uid)

            token = {
                "token_id": row[0],
                "token_name": row[1],
                "token_type": row[2],
                "token_parameters": json.loads(row[3]) if row[3] else [],
                "date_created": row[4],
                "token_product_uid": _product_uid,
                "billing_unit": row[6],
                "billing_trigger": row[7],
                "billing_conditions": row[8] if row[8] is not None else [],
                "billing_scope": row[9],
                "product": product
            }
            return response_out("success", "Token retrieved successfully", 200, token)


@_token_billing.route("/tokens/<string:token_id>", methods=["DELETE"])
@require_permission('tokens.delete')
def DeleteToken(token_id):
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute("DELETE FROM dll_tokens_registry WHERE token_id=%s", (token_id,))

            if cursor.rowcount == 0:
                return response_out("error", "Token not found", 404, [])

            dbconnect.commit()
            return response_out("success", "Token deleted successfully", 200, [])


@_token_billing.route("/tokens/<string:token_id>", methods=["PUT"])
@require_permission('tokens.update')
def UpdateToken(token_id):
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()

    data = _payload['data']
    _TokenName            = data['token_name']
    _TokenType            = data['token_type']
    _Token_Product        = data['token_product_uid']
    _TokenParameters      = data.get('token_parameters', [])
    _BillingUnit          = data.get('billing_unit') or _DEFAULT_UNIT.get(_TokenType)
    _BillingTrigger       = data.get('billing_trigger') or _DEFAULT_TRIGGER.get(_TokenType)
    _BillingConditions    = data.get('billing_conditions', [])
    _BillingScope         = data.get('billing_scope', 'asset')

    if _TokenType not in _VALID_TYPES:
        return response_out("error", f"Invalid token_type. Allowed: {sorted(_VALID_TYPES)}", 400, "")

    with dbconnect:
        with dbconnect.cursor() as cursor:
            product = _fetch_product(cursor, _Token_Product)
            if product is None:
                return response_out("error", "Product not found", 404, [])

            # Keep the token tagged to its product by prefixing the product name in caps, e.g. OLIWA_LITE
            _TokenName = _compose_token_name(product["product_name"], _TokenName)

            cursor.execute(
                "UPDATE dll_tokens_registry "
                "SET token_name=%s, token_type=%s, token_product_uid=%s, token_parameters=%s, "
                "    billing_unit=%s, billing_trigger=%s, billing_conditions=%s, billing_scope=%s "
                "WHERE token_id=%s",
                (_TokenName, _TokenType, str(_Token_Product),
                 json.dumps(_TokenParameters), _BillingUnit, _BillingTrigger,
                 json.dumps(_BillingConditions), _BillingScope, token_id)
            )

            if cursor.rowcount == 0:
                return response_out("error", "Token not found", 404, [])

            dbconnect.commit()
            return response_out("success", "Token updated successfully", 200, {"token_name": _TokenName})


@_token_billing.route("/tokens/<string:client_uid>/balance", methods=["GET"])
@require_permission('tokens.view_balance')
def ClientToken_Balance(client_uid):
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute(
                "SELECT client_uid, client_name FROM dll_client_accounts WHERE client_uid=%s",
                (client_uid,)
            )

            if cursor.rowcount == 0:
                return response_out("error", "Client not found", 404, {})

            client_info = cursor.fetchone()
            client_name = client_info[1]

            cursor.execute(
                "SELECT token_hours_left, token_hours_used, token_balance, token_billing_uid, token_used_units, token_units_left, token_status "
                "FROM dll_user_token_accounts WHERE client_uid=%s",
                (client_uid,)
            )

            if cursor.rowcount == 0:
                return response_out("success", "Client has no tokens allocated", 200, {
                    "client_uid": client_uid,
                    "client_name": client_name,
                    "token_hours_left": 0,
                    "token_hours_used": 0,
                    "token_used_units": 0,
                    "token_units_left": 0,
                    "token_status": None,
                    "token_uid": None,
                    "token_name": "No tokens",
                    "token_billing_uid": None,
                    "product": None
                })

            def _resolve_token(cursor, token_uid):
                """Return (token_name, product_dict) for a token_id from dll_tokens_registry."""
                cursor.execute(
                    "SELECT token_name, token_product_uid "
                    "FROM dll_tokens_registry WHERE token_id=%s",
                    (token_uid,)
                )
                if cursor.rowcount == 0:
                    return "Token Deleted", None
                row = cursor.fetchone()
                product = _fetch_product(cursor, row[1])
                return row[0], product

            if cursor.rowcount == 1:
                token_balance = cursor.fetchone()
                token_name, product = _resolve_token(cursor, token_balance[2])
                return response_out("success", "Client token balance retrieved successfully", 200, {
                    "client_uid": client_uid,
                    "client_name": client_name,
                    "token_hours_left": token_balance[0],
                    "token_hours_used": token_balance[1],
                    "token_used_units": token_balance[4],
                    "token_units_left": token_balance[5],
                    "token_status": token_balance[6],
                    "token_uid": token_balance[2],
                    "token_name": token_name,
                    "token_billing_uid": token_balance[3],
                    "product": product
                })

            elif cursor.rowcount > 1:
                _tokens_existing = cursor.fetchall()
                _runningTokens = []
                for token in _tokens_existing:
                    token_name, product = _resolve_token(cursor, token[2])
                    _runningTokens.append({
                        "client_uid": client_uid,
                        "client_name": client_name,
                        "token_hours_left": token[0],
                        "token_hours_used": token[1],
                        "token_used_units": token[4],
                        "token_units_left": token[5],
                        "token_status": token[6],
                        "token_uid": token[2],
                        "token_name": token_name,
                        "token_billing_uid": token[3],
                        "product": product
                    })
                return response_out("success", "Multiple tokens found", 200, _runningTokens)


#transfer token
@_token_billing.route("/tokens/transfer", methods=["POST"])
def TransferToken():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()

    _SourceClientUID = _payload['data']['source_client_uid']
    _DestinationClientUID = _payload['data']['destination_client_uid']
    _TokenID = _payload['data']['token_billing_uid']

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute(
                "SELECT token_hours_left, token_balance FROM dll_user_token_accounts "
                "WHERE client_uid=%s AND token_billing_uid=%s",
                (_SourceClientUID, _TokenID)
            )

            if cursor.rowcount == 0:
                return response_out("error", "Source client or token not found", 404, [])

            _TransferToken_Details = cursor.fetchone()
            _SourceTokenHoursLeft = _TransferToken_Details[0]
            _SourceTokenUID = _TransferToken_Details[1]

            cursor.execute(
                "SELECT token_balance FROM dll_user_token_accounts "
                "WHERE client_uid=%s AND token_balance=%s AND token_status='expired'",
                (_DestinationClientUID, _SourceTokenUID)
            )
            if cursor.rowcount == 0:
                _TokenBilling_UID = str(uuid.uuid4())
                cursor.execute(
                    "INSERT INTO dll_user_token_accounts "
                    "(client_uid, token_balance, token_status, token_hours_used, token_hours_left, token_billing_uid) "
                    "VALUES(%s, %s, %s, %s, %s, %s)",
                    (_DestinationClientUID, _SourceTokenUID, 'active', 0, _SourceTokenHoursLeft, _TokenBilling_UID)
                )
                cursor.execute(
                    "DELETE FROM dll_user_token_accounts WHERE client_uid=%s AND token_billing_uid=%s",
                    (_SourceClientUID, _TokenID)
                )
                dbconnect.commit()
                return response_out("success", "Token transferred successfully", 200, [])

            elif cursor.rowcount == 1:
                _DestinationToken_Details = cursor.fetchone()
                _DestinationTokenHoursLeft = _DestinationToken_Details[0]

                if _SourceTokenHoursLeft > 0:
                    cursor.execute(
                        "UPDATE dll_user_token_accounts SET token_hours_left=%s "
                        "WHERE ctid IN (SELECT ctid FROM dll_user_token_accounts "
                        "WHERE client_uid=%s AND token_balance=%s AND token_status='expired' LIMIT 1)",
                        (_DestinationTokenHoursLeft + _SourceTokenHoursLeft, _DestinationClientUID, _SourceTokenUID)
                    )
                    cursor.execute(
                        "DELETE FROM dll_user_token_accounts WHERE client_uid=%s AND token_billing_uid=%s",
                        (_SourceClientUID, _TokenID)
                    )
                    dbconnect.commit()
                    return response_out("success", "Token transferred successfully", 200, [])

            return response_out("error", "Token transfer failed", 400, [])


#moving a unit to another token with more time to run
@_token_billing.route("/tokens/subscriptions/update", methods=["POST"])
def UpdateDevice_Subscription():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()

    _NewToken_BillingUID = _payload['data']['new_token_billing_uid']
    _deviceImei = _payload['data']['device_imei']

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute(
                "SELECT token_hours_left FROM dll_user_token_accounts WHERE token_billing_uid=%s",
                (str(_NewToken_BillingUID),)
            )

            if cursor.rowcount == 1:
                _TunnelData = cursor.fetchone()
                _TokenHours_Left = _TunnelData[0]

                if int(_TokenHours_Left) >= 1:
                    current_time = datetime.now(timezone).strftime("%I:%M:%S%p")
                    currentLocal_Date = datetime.now(timezone).strftime("%d-%m-%Y")

                    cursor.execute(
                        "SELECT id FROM dll_device_subscriptions WHERE device_imei_number=%s",
                        (str(_deviceImei),)
                    )

                    if cursor.rowcount == 1:
                        cursor.execute(
                            "UPDATE dll_device_subscriptions "
                            "SET subscription_status=%s, start_date=%s, start_counting_time=%s, token_billing_uid=%s "
                            "WHERE device_imei_number=%s",
                            ('active', str(currentLocal_Date), str(current_time),
                             str(_NewToken_BillingUID), str(_deviceImei))
                        )
                        dbconnect.commit()
                        return response_out("success", "Device Subscription Updated Successfully", 200, "")

                    elif cursor.rowcount == 0:
                        return response_out("error", "Device subscription not found", 404, "")

                elif int(_TokenHours_Left) < 1:
                    return response_out("error", "Token expired", 400, "")

            else:
                return response_out("error", "Token not found", 404, "")


#pause token billing
@_token_billing.route("/tokens/subscriptions/pause", methods=["POST"])
def PauseSubscription():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()

    _deviceImei = _payload['data']['device_imei']

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute(
                "SELECT subscription_status FROM dll_device_subscriptions WHERE device_imei_number=%s",
                (str(_deviceImei),)
            )

            if cursor.rowcount == 1:
                _subscription_status = cursor.fetchone()[0]

                if _subscription_status == 'active':
                    cursor.execute(
                        "UPDATE dll_device_subscriptions SET subscription_status=%s WHERE device_imei_number=%s",
                        ('paused', str(_deviceImei))
                    )
                    dbconnect.commit()
                    return response_out("success", "Device Subscription Paused Successfully", 200, "")

                elif _subscription_status == 'paused':
                    return response_out("error", "Device Subscription is already Paused", 400, "")

                elif _subscription_status == 'expired':
                    return response_out("error", "Device Subscription is Expired", 400, "")

            elif cursor.rowcount == 0:
                return response_out("error", "Device subscription not found", 404, "")


#restore token billing
@_token_billing.route("/tokens/subscriptions/restore", methods=["POST"])
def RestoreSubscription():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()

    _deviceImei = _payload['data']['device_imei']

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute(
                "SELECT subscription_status FROM dll_device_subscriptions WHERE device_imei_number=%s",
                (str(_deviceImei),)
            )

            if cursor.rowcount == 1:
                _subscription_status = cursor.fetchone()[0]

                if _subscription_status == 'paused':
                    cursor.execute(
                        "SELECT token_billing_uid FROM dll_device_subscriptions WHERE device_imei_number=%s",
                        (str(_deviceImei),)
                    )
                    if cursor.rowcount == 1:
                        _NewToken_BillingUID = cursor.fetchone()[0]

                        cursor.execute(
                            "SELECT token_status FROM dll_user_token_accounts WHERE token_billing_uid=%s",
                            (str(_NewToken_BillingUID),)
                        )
                        if cursor.rowcount == 1:
                            _Token_Status = cursor.fetchone()[0]
                            if _Token_Status == 'active':
                                cursor.execute(
                                    "UPDATE dll_device_subscriptions SET subscription_status=%s WHERE device_imei_number=%s",
                                    ('active', str(_deviceImei))
                                )
                                dbconnect.commit()
                                return response_out("success", "Device Subscription Restored Successfully", 200, "")

                            elif _Token_Status == 'expired':
                                return response_out("error", "Device Token is Expired", 400, "")
                        else:
                            return response_out("error", "Device Subscription Token Not Found For User Account", 400, "")
                    else:
                        return response_out("error", "Device Subscription Malfunctioning", 400, "")

                elif _subscription_status == 'active':
                    return response_out("error", "Device Subscription is already Active", 400, "")

                elif _subscription_status == 'expired':
                    return response_out("error", "Device Subscription is Expired", 400, "")

            elif cursor.rowcount == 0:
                return response_out("error", "Device subscription not found", 404, "")


@_token_billing.route("/subscriptions/device/status", methods=["POST"])
@require_permission('subscriptions.view_status')
def CheckSubscriptionStatus():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()

    _deviceImei = _payload['data']['device_imei']

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute(
                "SELECT subscription_status,start_date,start_counting_time FROM dll_device_subscriptions WHERE device_imei_number=%s AND subscription_status IN ('active', 'paused')",
                (str(_deviceImei),)
            )

            if cursor.rowcount == 1:
                _dataLink = cursor.fetchone()
                _subscription_status = _dataLink[0]
                _start_date = str(_dataLink[1])
                _start_time = str(_dataLink[2])

                return response_out("success", "Device Subscription Status Retrieved Successfully", 200, {"subscription_status": _subscription_status, "start_date": _start_date, "start_time": _start_time})

            elif cursor.rowcount == 0:
                return response_out("error", "Device subscription not found", 404, "")
            
@_token_billing.route("/subscriptions/device/renew", methods=["POST"])
@require_permission('subscriptions.renew')
def RenewSubscription():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()

    _deviceImei = _payload['data']['device_imei']
    _token_billing_uid = _payload['data']['token_billing_uid']

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute(
                "SELECT subscription_status FROM dll_device_subscriptions WHERE device_imei_number=%s AND subscription_status IN ('expired', 'active')",
                (str(_deviceImei),)
            )

            if cursor.rowcount == 1:
                    now_kla    = datetime.now(_KLA)
                    current_time = now_kla.strftime("%H:%M:%S")
                    currentLocal_Date = now_kla.date().isoformat()
                    
                    cursor.execute("UPDATE dll_user_token_accounts SET token_status = %s WHERE token_billing_uid = %s;", ('active', str(_token_billing_uid),))

                    cursor.execute("UPDATE dll_device_subscriptions SET subscription_status = %s WHERE device_imei_number = %s", ('depleted', str(_deviceImei),))

                    cursor.execute(
                        "INSERT INTO dll_device_subscriptions (subscription_status, start_date, start_counting_time, device_imei_number, token_billing_uid) VALUES (%s, %s, %s, %s, %s)",
                        ('active', str(currentLocal_Date), str(current_time), str(_deviceImei), str(_token_billing_uid),)
                    )
                    dbconnect.commit()
                    return response_out("success", "Device Subscription Renewed Successfully", 200, "")

            elif cursor.rowcount == 0:
                    now_kla    = datetime.now(_KLA)
                    current_time = now_kla.strftime("%H:%M:%S")
                    currentLocal_Date = now_kla.date().isoformat()
                    
                    cursor.execute("UPDATE dll_user_token_accounts SET token_status = %s WHERE token_billing_uid = %s;", ('active', str(_token_billing_uid),))

                    cursor.execute("UPDATE dll_device_subscriptions SET subscription_status = %s WHERE device_imei_number = %s", ('depleted', str(_deviceImei),))

                    cursor.execute(
                        "INSERT INTO dll_device_subscriptions (subscription_status, start_date, start_counting_time, device_imei_number, token_billing_uid) VALUES (%s, %s, %s, %s, %s)",
                        ('active', str(currentLocal_Date), str(current_time), str(_deviceImei), str(_token_billing_uid),)
                    )
                    dbconnect.commit()
                    return response_out("success", "Device Subscription Started Successfully", 200, "")