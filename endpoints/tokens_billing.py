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
from .globals import reply
import base64
import requests
from .globals import check_device
import uuid
import string
import pytz
from datetime import datetime
from .globals import SubscriptionManager



_token_billing = Blueprint("TokenBilling", __name__)

timezone = pytz.timezone('Africa/Nairobi')

def response_out(status, message, statusCode, data):
    return jsonify({
        "status": status,
        "message": message,
        "data": data
    }), statusCode

@_token_billing.route("/tokens/create", methods=["POST"])
def CreateToken():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()

    _TokenName = _payload['data']['token_name']
    _TokenType = _payload['data']['token_type'] #can be parameter token or dynamic
    _TokenValidity = _payload['data']['token_validity'] #in seconds
    _TokenCurrency = _payload['data']['token_currency'] #UGX or KES or RWF
    _TokenParameters = _payload['data']['token_parameters'] #array object with parameters if token type is 'parameter' its optional if token type is dynamic
    _TokenAmount = _payload['data']['token_amount'] #amount for the token
    _TokenID = str(uuid.uuid4())
    _CreatedAt = datetime.now(timezone).strftime("%d-%m-%Y %I:%M:%S%p")

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute("SELECT id FROM dll_tokens_registry WHERE token_name=%s AND token_type=%s", (str(_TokenName), str(_TokenType),))

            if(cursor.rowcount == 0):
                cursor.execute("INSERT INTO dll_tokens_registry (token_id, token_name, token_type, token_validity, token_currency, token_parameters, date_created, token_amount) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (_TokenID, _TokenName, _TokenType, _TokenValidity, _TokenCurrency, json.dumps(_TokenParameters), _CreatedAt, _TokenAmount,))

                return response_out("success", "Token created successfully", 201, {"token_id": _TokenID})

            elif(cursor.rowcount >= 1):
                return response_out("error", "Token already exists", 409, "")
            

@_token_billing.route("/tokens", methods=["GET"])
def ListTokens():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute("SELECT * FROM dll_tokens_registry ORDER BY id DESC")

            if(cursor.rowcount == 0):
                return response_out("error", "No tokens found", 404, [])

            tokens = cursor.fetchall()
            _tokensBusket = []
            for token in tokens:
                _tokensBusket.append({
                    "token_id": token[8],
                    "token_name": token[2],
                    "token_type": token[1],
                    "token_validity": token[3],
                    "token_currency": token[6],
                    "token_parameters": json.loads(token[7]),
                    "date_created": token[5],
                    "token_amount": token[4]
                })
            return response_out("success", "Tokens retrieved successfully", 200, _tokensBusket)


@_token_billing.route("/tokens/<string:token_id>", methods=["GET"])
def GetSingleToken(token_id):
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute("SELECT * FROM dll_tokens_registry WHERE token_id=%s", (token_id,))

            if(cursor.rowcount == 0):
                return response_out("error", "Token not found", 404, [])

            token = cursor.fetchone()
            token = {
                "token_id": token[8],
                    "token_name": token[2],
                    "token_type": token[1],
                    "token_validity": token[3],
                    "token_currency": token[6],
                    "token_parameters": json.loads(token[7]),
                    "date_created": token[5],
                    "token_amount": token[4]
            }
            return response_out("success", "Token retrieved successfully", 200, token)
        

@_token_billing.route("/tokens/<string:token_id>", methods=["DELETE"])
def DeleteToken(token_id):
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute("DELETE FROM dll_tokens_registry WHERE token_id=%s", (token_id,))

            if(cursor.rowcount == 0):
                return response_out("error", "Token not found", 404, [])

            return response_out("success", "Token deleted successfully", 200, [])
        

@_token_billing.route("/tokens/<string:token_id>", methods=["PUT"])
def UpdateToken(token_id):
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()

    _TokenName = _payload['data']['token_name']
    _TokenType = _payload['data']['token_type']
    _TokenValidity = _payload['data']['token_validity']
    _TokenCurrency = _payload['data']['token_currency']
    _TokenParameters = _payload['data']['token_parameters']
    _TokenAmount = _payload['data']['token_amount']

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute("UPDATE dll_tokens_registry SET token_name=%s, token_type=%s, token_validity=%s, token_currency=%s, token_parameters=%s, token_amount=%s WHERE token_id=%s", (_TokenName, _TokenType, _TokenValidity, _TokenCurrency, json.dumps(_TokenParameters), _TokenAmount, token_id))

            if(cursor.rowcount == 0):
                return response_out("error", "Token not found", 404, [])

            return response_out("success", "Token updated successfully", 200, [])
        

@_token_billing.route("/tokens/<string:client_uid>/balance", methods=["GET"])
def ClientToken_Balance(client_uid):
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as cursor:
            # First, check if client exists in dll_client_accounts
            cursor.execute("SELECT client_uid, client_name FROM dll_client_accounts WHERE client_uid=%s", (client_uid,))
            
            if(cursor.rowcount == 0):
                return response_out("error", "Client not found", 404, {})
            
            client_info = cursor.fetchone()
            client_name = client_info[1]
            
            # Now check for token accounts
            cursor.execute("SELECT token_hours_left,token_hours_used,token_balance,token_billing_uid FROM dll_user_token_accounts WHERE client_uid=%s", (client_uid,))

            if(cursor.rowcount == 0):
                # Client exists but has no tokens allocated
                return response_out("success", "Client has no tokens allocated", 200, {
                    "client_uid": client_uid,
                    "client_name": client_name,
                    "token_hours_left": 0, 
                    "token_hours_used": 0,
                    "token_uid": None,
                    "token_name": "No tokens",
                    "token_billing_uid": None
                })

            if(cursor.rowcount == 1):
                token_balance = cursor.fetchone()
                cursor.execute("SELECT token_name FROM dll_tokens_registry WHERE token_id=%s", (token_balance[2],))
                token_name = None
                if(cursor.rowcount == 1):
                    token_name = cursor.fetchone()[0]
                elif(cursor.rowcount == 0):
                    token_name = 'Token Deleted'

                _singleToken_Object = {
                    "client_uid": client_uid,
                    "client_name": client_name,
                    "token_hours_left": token_balance[0], 
                    "token_hours_used": token_balance[1],
                    "token_uid": token_balance[2],
                    "token_name": token_name,
                    "token_billing_uid": token_balance[3]
                }
                return response_out("success", "Client token balance retrieved successfully", 200, _singleToken_Object)
            
            elif(cursor.rowcount > 1):
                _tokens_existing = cursor.fetchall()
                _runningTokens = []
                for token in _tokens_existing:
                   cursor.execute("SELECT token_name FROM dll_tokens_registry WHERE token_id=%s", (token[2],))
                   token_name = None
                   if(cursor.rowcount == 1):
                       token_name = cursor.fetchone()[0]
                   elif(cursor.rowcount == 0):
                       token_name = 'Token Deleted'
                   token = {
                        "client_uid": client_uid,
                        "client_name": client_name,
                        "token_hours_left": token[0],
                        "token_hours_used": token[1],
                        "token_uid": token[2],
                        "token_name": token_name,
                        "token_billing_uid": token[3]
                    }
                   _runningTokens.append(token)
                
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
            cursor.execute("SELECT token_hours_left, token_balance FROM dll_user_token_accounts WHERE client_uid=%s AND token_billing_uid=%s", (_SourceClientUID, _TokenID))

            if(cursor.rowcount == 0):
                return response_out("error", "Source client or token not found", 404, [])

            _TransferToken_Details = cursor.fetchone()
            _SourceTokenHoursLeft = _TransferToken_Details[0]
            _SourceTokenUID = _TransferToken_Details[1]

            cursor.execute("SELECT token_balance FROM dll_user_token_accounts WHERE client_uid=%s AND token_balance=%s AND token_status='expired'", (_DestinationClientUID, _SourceTokenUID))
            if(cursor.rowcount == 0):
                _TokenBilling_UID = str(uuid.uuid4())
                cursor.execute("INSERT INTO dll_user_token_accounts (client_uid, token_balance, token_status, token_hours_used, token_hours_left, token_billing_uid) VALUES(%s, %s, %s, %s, %s, %s)", (_DestinationClientUID, _SourceTokenUID, 'active', 0, _SourceTokenHoursLeft, _TokenBilling_UID))
                cursor.execute("DELETE FROM dll_user_token_accounts WHERE client_uid=%s AND token_billing_uid=%s", (_SourceClientUID, _TokenID))

                return response_out("success", "Token transferred successfully", 200, [])

            elif(cursor.rowcount == 1):

                _DestinationToken_Details = cursor.fetchone()
                _DestinationTokenHoursLeft = _DestinationToken_Details[0]

                if(_SourceTokenHoursLeft > 0):
                    cursor.execute("UPDATE dll_user_token_accounts SET token_hours_left=%s WHERE ctid IN (SELECT ctid FROM dll_user_token_accounts WHERE client_uid=%s AND token_balance=%s AND token_status='expired' LIMIT 1)", (_DestinationTokenHoursLeft + _SourceTokenHoursLeft, _DestinationClientUID, _SourceTokenUID))
                    cursor.execute("DELETE FROM dll_user_token_accounts WHERE client_uid=%s AND token_billing_uid=%s", (_SourceClientUID, _TokenID))
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
            cursor.execute("SELECT token_hours_left FROM dll_user_token_accounts WHERE token_billing_uid=%s", (str(_NewToken_BillingUID),))

            if(cursor.rowcount == 1):
                    
                _TunnelData = cursor.fetchone()
                _TokenHours_Left = _TunnelData[0]

                if(int(_TokenHours_Left) >= 1):

                    current_time = datetime.now(timezone).strftime("%I:%M:%S%p")
                    currentLocal_Date = datetime.now(timezone).strftime("%d-%m-%Y")

                    cursor.execute("SELECT id FROM dll_device_subscriptions WHERE device_imei_number=%s", (str(_deviceImei),))
                    
                    if(cursor.rowcount == 1):
                        cursor.execute("UPDATE dll_device_subscriptions SET subscription_status=%s, start_date=%s, start_counting_time=%s, token_billing_uid=%s WHERE device_imei_number=%s", ('active', str(currentLocal_Date), str(current_time), str(_NewToken_BillingUID), str(_deviceImei)))

                        return response_out("success", "Device Subscription Updated Successfully", 200, "")
                    
                    elif(cursor.rowcount == 0):
                        
                        return response_out("error", "Device subscription not found", 404, "")

                    elif(int(_TokenHours_Left) < 1):
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
            cursor.execute("SELECT subscription_status FROM dll_device_subscriptions WHERE device_imei_number=%s", (str(_deviceImei),))

            if(cursor.rowcount == 1):
                _subscription_dataLink = cursor.fetchone()
                _subscription_status = _subscription_dataLink[0]

                if(_subscription_status == 'active'):
                    cursor.execute("UPDATE dll_device_subscriptions SET subscription_status=%s WHERE device_imei_number=%s", ('paused', str(_deviceImei)))
                    return response_out("success", "Device Subscription Paused Successfully", 200, "")
                
                elif(_subscription_status == 'paused'):
                    return response_out("error", "Device Subscription is already Paused", 400, "")
                
                elif(_subscription_status == 'expired'):
                    return response_out("error", "Device Subscription is Expired", 400, "")
            
            elif(cursor.rowcount == 0):
                return response_out("error", "Device subscription not found", 404, "")
            

#restore token billing
@_token_billing.route("/tokens/subscriptions/restore", methods=["POST"])
def RestoreSubscription():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    _payload = request.get_json()

    _deviceImei = _payload['data']['device_imei']

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute("SELECT subscription_status FROM dll_device_subscriptions WHERE device_imei_number=%s", (str(_deviceImei),))

            if(cursor.rowcount == 1):
                _subscription_dataLink = cursor.fetchone()
                _subscription_status = _subscription_dataLink[0]

                if(_subscription_status == 'paused'):
                    cursor.execute("SELECT token_billing_uid FROM dll_device_subscriptions WHERE device_imei_number=%s", (str(_deviceImei),))
                    if(cursor.rowcount == 1):
                        _AttachedToken_DataLink = cursor.fetchone()
                        _NewToken_BillingUID = _AttachedToken_DataLink[0]
                        
                        cursor.execute("SELECT token_status FROM dll_user_token_accounts WHERE token_billing_uid=%s", (str(_NewToken_BillingUID),))
                        if(cursor.rowcount == 1):
                            _Token_DataLink = cursor.fetchone()
                            _Token_Status = _Token_DataLink[0]
                            if(_Token_Status == 'active'):
                                cursor.execute("UPDATE dll_device_subscriptions SET subscription_status=%s WHERE device_imei_number=%s", ('active', str(_deviceImei)))
                                return response_out("success", "Device Subscription Restored Successfully", 200, "")
                            
                            elif(_Token_Status == 'expired'):
                                return response_out("error", "Device Token is Expired", 400, "")
                        else:
                            return response_out("error", "Device Subscription Token Not Found For User Account", 400, "")
                    else:
                        return response_out("error", "Device Subscription Malfunctioning", 400, "")
                
                elif(_subscription_status == 'active'):
                    return response_out("error", "Device Subscription is already Active", 400, "")
                
                elif(_subscription_status == 'expired'):
                    return response_out("error", "Device Subscription is Expired", 400, "")
            
            elif(cursor.rowcount == 0):
                return response_out("error", "Device subscription not found", 404, "")
            

