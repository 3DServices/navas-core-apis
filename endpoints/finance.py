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
from decimal import Decimal
from .globals import reply, require_permission
import base64
import requests
from .globals import check_device
import uuid
import string
from .globals import SubscriptionManager

finance_bp = Blueprint("Finance", __name__)

def MoMoPayment_Charge(PhoneNumber, Country, Curreny, LocalAmount, PaymentReferance):
    try:
        _Payload = {
            "auth":{
                "api_key":"pki_7ve43chhGgAEBag49ZNqJ6AZ3e29CGgqgHWgP9pxfw7AdjsMqx9ZFmaPqYHL7"
            },
            "data":{
                "local_country": Country,
                "local_currency": Curreny.upper(),
                "local_phone": PhoneNumber,
                "local_amount": LocalAmount,
                "app_transaction_uid": PaymentReferance
            }
        }
        print(_Payload)
        _DebitUser = requests.post('https://optimus.santripe.com/collections/mobile-money', data=json.dumps(_Payload), headers={"Content-type":"application/json"})
        _ReplyFrom_API = _DebitUser.json()

        return _ReplyFrom_API

    except Exception as error:
        return "internal_error"


@finance_bp.route("/payments/tokens/buy", methods=["POST"])
#@require_permission('finance.create.mobile_money_payment')
def BuyTokens():
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _payload = request.get_json()

        # Debug: Print what we received
        print("=== BUY TOKENS PAYLOAD ===")
        print(json.dumps(_payload, indent=2))
        print("==========================")

        # Validate required fields
        required_fields = ['token_buyer', 'token_uid', 'mobile_money_number', 'token_quantity']
        if 'data' not in _payload:
            return reply('error', 400, 'Missing data object in request', '')
        
        missing_fields = [field for field in required_fields if field not in _payload['data']]
        if missing_fields:
            return reply('error', 400, f'Missing required fields: {", ".join(missing_fields)}', '')

        _TokenBuyer = str(_payload['data']['token_buyer'])
        _TokenNumber = str(_payload['data']['token_uid'])
        _MoMobileMoney_Number = str(_payload['data']['mobile_money_number'])
        _TokenQuantity = str(_payload['data']['token_quantity'])

        if (len(_TokenBuyer) > 5) and (len(_TokenNumber) > 0) and (len(_MoMobileMoney_Number) > 5) and (len(_TokenQuantity) > 0) and (int(_TokenQuantity) > 0):

            _LocalCountry = None

            with _dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT token_amount, token_currency, billing_unit "
                    "FROM dll_tokens_registry WHERE token_id=%s",
                    (str(_TokenNumber),)
                )

                if cursor.rowcount == 0:
                    return reply("error", 400, "Billing Token Not Found", "")

                _token_row = cursor.fetchone()
                _TokenPaymentAmount = _token_row[0]

                if _TokenPaymentAmount is None:
                    return reply("error", 400, "Token has no price configured", "")

                _TokenPaymentCurrency = str(_token_row[1]).upper()
                _TokenValidity = _token_row[2]

            if _TokenPaymentCurrency == 'KES':
                _LocalCountry = 'kenya'
            elif _TokenPaymentCurrency == 'UGX':
                _LocalCountry = 'uganda'

            _TotalAmount_Payable = Decimal(str(_TokenPaymentAmount)) * Decimal(str(_TokenQuantity))
            _PaymentReferance = str(uuid.uuid4())
            _PaymentRoute = MoMoPayment_Charge(
                _MoMobileMoney_Number, _LocalCountry, _TokenPaymentCurrency,
                str(_TotalAmount_Payable), _PaymentReferance
            )

            # Check if payment gateway returned an error
            if _PaymentRoute == "internal_error":
                return reply("error", 500, "Payment Gateway Error - Please Try Again", "")

            _InitiatePayment = _PaymentRoute['status']

            if _InitiatePayment == 'success':
                RemoteReferance = _PaymentRoute['data']['api_referance']

                with _dbconnect.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO dll_payment_logs (payment_uid, payment_account, token_number, token_validity, total_cost, payment_currency, payment_date, payment_status, payment_owner, remote_uid, token_quantity) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (_PaymentReferance, _TokenBuyer, _TokenNumber, _TokenValidity,
                         _TotalAmount_Payable, _TokenPaymentCurrency,
                         str(datetime.datetime.now().date()), 'pending', '3dservices',
                         RemoteReferance, _TokenQuantity,)
                    )
                    _dbconnect.commit()

                _ResponseObjt = {
                    "transaction_uid": _PaymentReferance
                }
                return reply("success", 201, "Payment Processing - Enter PIN", _ResponseObjt)

            elif _InitiatePayment == 'error':
                return reply("error", 400, "Check Your Payment Information", "")

        else:
            return reply("error", 400, "Some Information Is Missing", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    

#check payment status
@finance_bp.route("/payments/transactions/<transaction_uid>/status", methods=["GET"])
def TransactionStatus(transaction_uid):
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute("SELECT payment_status FROM dll_payment_logs WHERE payment_uid=%s", (str(transaction_uid),))

                if(cursor.rowcount == 1):
                    _dataTunnel = cursor.fetchone()
                    _TransactionStatus = _dataTunnel[0]
                    
                    _StatusObjt = {
                        "transaction_status": _TransactionStatus.lower()
                    }

                    return reply("success", 200, "Transaction Found", _StatusObjt)

                elif(cursor.rowcount == 0):
                    return reply("error", 400, "Transaction Not Found", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    

def generate_token_string():
    parts = []
    for _ in range(6):
        part = ''.join(random.choices(string.ascii_uppercase, k=4))
        parts.append(part)
    return '-'.join(parts)

#Receive payment webhook
@finance_bp.route("/payments/transactions/notifications", methods=["POST"])
def TransactionUpdate():
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _payload = request.get_json()

        Amount_Settled = _payload['data']['amount_settled']
        External_Referance = _payload['data']['external_referance']
        Payment_Status = _payload['data']['status']
        Event_Triggered = _payload['event_type']

        if(Event_Triggered == 'mobile_money_collection'):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("UPDATE dll_payment_logs SET payment_status=%s WHERE remote_uid=%s;", (Payment_Status, External_Referance,))
                    
                    if(Payment_Status == 'successful'):
                        
                        cursor.execute("SELECT token_number, token_validity, payment_account, token_quantity  FROM dll_payment_logs WHERE remote_uid=%s", (str(External_Referance),))

                        if(cursor.rowcount == 1):
                            _dataTunnel = cursor.fetchone()
                            _TokenUID = _dataTunnel[0]
                            _TokenValidity = _dataTunnel[1]
                            _ClientUID = _dataTunnel[2]
                            _TotalTokenQuantity = _dataTunnel[3]

                            cursor.execute("DELETE FROM dll_user_token_accounts WHERE token_balance=%s AND client_uid=%s AND token_status='expired'", (_TokenUID, _ClientUID,))
                            for i in range(int(_TotalTokenQuantity)):
                                #_TokenNumber = str(generate_token_string())
                                _TokenBillingUID = str(uuid.uuid4())
                                cursor.execute("INSERT INTO dll_user_token_accounts (client_uid, token_balance, token_status, token_hours_used, token_hours_left, token_billing_uid) VALUES(%s, %s, %s, %s, %s, %s)", (_ClientUID, _TokenUID, 'active', 0, _TokenValidity, _TokenBillingUID))

                    return "Processed-OK", 200
        else:
            pass

    except Exception as error:
        return reply('error', 500, str(error), "")


@finance_bp.route("/tokens/special/authorize", methods=["POST"])
@require_permission('finance.tokens.special_authorize')
def SpecialTokenAuthorization():
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _payload = request.get_json()

        _TokenUID_Authorized = _payload['data']['token_uid']
        _QuantityAuthorized = _payload['data']['quantity_authorized']
        _ClientUID_Authorized = _payload['data']['client_uid']

        if(len(_TokenUID_Authorized) < 0) and (len(_QuantityAuthorized) < 0) and (len(_ClientUID_Authorized) < 0):
            return reply('error', 400, 'Missing required fields: token_uid, quantity_authorized, client_uid', '')
        
        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                for i in range(int(_QuantityAuthorized)):
                    _TokenBillingUID = str(uuid.uuid4())
                    cursor.execute("INSERT INTO dll_user_token_accounts (client_uid, token_balance, token_status, token_hours_used, token_hours_left, token_billing_uid, token_units_left, token_used_units) VALUES(%s, %s, %s, %s, %s, %s, %s, %s)", (_ClientUID_Authorized, _TokenUID_Authorized, 'new', 0, 0, _TokenBillingUID, 0, 0,))

        return reply('success', 200, 'Token(s) Authorized SuccessFully', '')


    except Exception as error:
        return reply('error', 500, str(error), "")

#get transactions
@finance_bp.route("/payments/transactions/<transaction_owner>/list", methods=["GET"])
@require_permission('finance.view')
def TransactionLogs(transaction_owner):
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute("SELECT payment_uid,token_number,token_validity,total_cost,payment_currency,payment_date,payment_status FROM dll_payment_logs WHERE payment_account=%s ORDER BY id DESC", (str(transaction_owner),))

                if(cursor.rowcount >= 1):

                    _dataTunnel = cursor.fetchall()
                    _transactionTmp_Holder = []

                    for Payment in _dataTunnel:

                        _SingleTransaction = {
                            "transaction_uid": Payment[0],
                            "token_count": Payment[1],
                            "token_validity": Payment[2],
                            "total_cost": str(Payment[3]),
                            "payment_currency": str(Payment[4]),
                            "date": Payment[5],
                            "payment_status": Payment[6]
                        }
                        _transactionTmp_Holder.append(_SingleTransaction)

                    return reply("success", 200, "Found Transactions", _transactionTmp_Holder)

                elif(cursor.rowcount == 0):
                    return reply("error", 400, "No Transactions", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    

#Get Tokens available
@finance_bp.route("/finance/accounts/<account_parent>/tokens", methods=["GET"])
def GetAccountTokens(account_parent):
    
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute("SELECT token_number, token_validity, token_status, date_created FROM dll_tokens_registry WHERE token_owner=%s ORDER BY id DESC", (str(account_parent),))

                if(cursor.rowcount >= 1):
                    _TokenData = cursor.fetchall()
                    _TokensTmpHolder = []

                    for EachToken in _TokenData:
                        _SingleToken = {
                            "token_number": EachToken[0],
                            "token_validity": EachToken[1],
                            "token_status": EachToken[2],
                            "date_created": EachToken[3]
                        }
                        _TokensTmpHolder.append(_SingleToken)

                    return reply("success", 200, "Found Tokens", _TokensTmpHolder)

                elif(cursor.rowcount == 0):
                    return reply("error", 400, "No Tokens Found", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    

#get token stats
@finance_bp.route("/finance/accounts/<account_parent>/tokens/status", methods=["GET"])
def TokenStats(account_parent):
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])

        with _dbconnect:
            with _dbconnect.cursor() as cursor:

                _TokenStats = []

                cursor.execute("SELECT COUNT(token_number) AS tt_onemonth FROM dll_tokens_registry WHERE token_status=%s AND token_validity=%s AND token_owner=%s", ('un_used', '1', str(account_parent),))
                _Tunnel1Link = cursor.fetchone()
                _Tunnel1DataCount = _Tunnel1Link[0]
                _Dt_Object = {
                    "one_month": _Tunnel1DataCount
                }
                _TokenStats.append(_Dt_Object)

                validity_periods = [3, 6, 12, 36]
                validity_labels = ["three_months", "six_months", "twelve_months", "three_years"]

                for validity, label in zip(validity_periods, validity_labels):
                    cursor.execute(
                        """
                        SELECT COUNT(token_number) AS total_tokens
                        FROM dll_tokens_registry
                        WHERE token_status=%s AND token_validity=%s AND token_owner=%s
                        """,
                        ('un_used', str(validity), str(account_parent))
                    )
                    result = cursor.fetchone()
                    token_count = result[0] if result else 0
                    _Dt_Object = {label: token_count}
                    _TokenStats.append(_Dt_Object)

                return reply("success", 200, "Log Sent", _TokenStats)
                
    except Exception as error:
        return reply("error", 500, str(error), "")
    

#Renew Device
@finance_bp.route("/finance/subscriptions/devices/<device_imei>/period/<renewal_period>/account/<account_uid_renewing>/renew", methods=["PUT"])
def RenewDevice(device_imei, renewal_period, account_uid_renewing):
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _DeviceImei = str(device_imei)
        _RenewalPeriod = str(renewal_period)
        _UserRenewing = str(account_uid_renewing)

        _Renewal_Verdict = SubscriptionManager(_UserRenewing, _RenewalPeriod, _DeviceImei)

        if(_Renewal_Verdict == 'success-proceed'):
            
            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("UPDATE dll_device_basic_data SET device_billing_status=%s WHERE device_imei=%s", ('running', _DeviceImei,))

                    return reply("success", 200, "Device Renewal SuccessFul", "")

        elif(_Renewal_Verdict == 'no-tokens'):
            return reply("error", 400, f"No Tokens For {_RenewalPeriod} Months", "")
        
        elif(_Renewal_Verdict == 'error-reject'):
            return reply("error", 400, "Account Tokens Route Not Found", "")

    except Exception as error:
        return reply("error", 500, str(error), "")


@finance_bp.route("/finance/payments", methods=["GET"])
def GetPayments():
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute("SELECT payment_uid, payment_account, token_number, token_validity, total_cost, payment_currency, payment_date, payment_status FROM dll_payment_logs ORDER BY id DESC")

                if(cursor.rowcount >= 1):

                    _dataTunnel = cursor.fetchall()
                    _paymentTmp_Holder = []

                    for Payment in _dataTunnel:
                        _clientID = Payment[1]
                        cursor.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid=%s", (str(_clientID),))
                        if cursor.rowcount == 1:
                            _clientDataTunnel = cursor.fetchone()
                            _clientName = _clientDataTunnel[0]
                        else:
                            _clientName = "Unknown Client"
                            
                        _SinglePayment = {
                            "transaction_uid": Payment[0],
                            "payment_account": Payment[1],
                            "client_name": _clientName,
                            "token_number": Payment[2],
                            "token_validity": Payment[3],
                            "total_cost": str(Payment[4]),
                            "payment_currency": str(Payment[5]),
                            "date": Payment[6],
                            "payment_status": Payment[7]
                        }
                        _paymentTmp_Holder.append(_SinglePayment)

                    return reply("success", 200, "Found Payments", _paymentTmp_Holder)

                elif(cursor.rowcount == 0):
                    return reply("error", 400, "No Payments Found", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    




