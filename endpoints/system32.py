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
import traceback
from datetime import datetime, timedelta, date, time as dtime
from .globals import SubscriptionManager
from calendar import monthrange


_system32 = Blueprint("System32", __name__)

timezone = pytz.timezone('Africa/Nairobi')

def _add_months(dt, months):
    """
    Add months to a timezone-aware datetime, clamping the day to end-of-month if needed.
    """
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    last_day = monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)

def _compute_validity_window(validity_key, start_dt):
    """
    Returns (valid_start_dt, valid_end_dt) timezone-aware datetimes.
    """
    if not start_dt.tzinfo:
        start_dt = timezone.localize(start_dt)

    valid_start = start_dt

    if validity_key == "1_day":
        valid_end = valid_start + timedelta(days=1)
    elif validity_key == "1_week":
        valid_end = valid_start + timedelta(weeks=1)
    elif validity_key == "1_month":
        valid_end = _add_months(valid_start, 1)
    elif validity_key == "2_months":
        valid_end = _add_months(valid_start, 2)
    elif validity_key == "3_months":
        valid_end = _add_months(valid_start, 3)
    elif validity_key == "6_months":
        valid_end = _add_months(valid_start, 6)
    elif validity_key == "12_months":
        valid_end = _add_months(valid_start, 12)
    elif validity_key == "5_years":
        valid_end = _add_months(valid_start, 12 * 5)
    else:
        # Unknown validity: don't break webhook processing
        valid_end = None

    return valid_start, valid_end


@_system32.route("/system32/payment/log", methods=["POST"])
def payment_log():

    _payload = request.get_json()
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    _payment_id = _payload['data']['payment_id']
    _payment_user = _payload['data']['payment_user_uid']
    _payment_amount = _payload['data']['payment_amount']
    _payment_currency = _payload['data']['payment_currency']
    _payment_account_uid = _payload['data']['payment_account_uid']
    _payment_phone_number = _payload['data']['payment_phone_number']
    _payment_validity = _payload['data']['payment_validity']

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute("SELECT payment_uid FROM dll_payments_manager WHERE payment_uid=%s", (_payment_id,))
            if cursor.rowcount > 0:
                return jsonify({
                    "status": "error",
                    "message": "Payment already logged"
                }), 400
            
            else:
                cursor.execute("INSERT INTO dll_payments_manager (payment_uid, payment_account, payment_amount, payment_currency, payment_status, payment_validity, validity_status, used_imei, valid_start_date, valid_end_date, payment_date, payment_user_uid) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (_payment_id, _payment_account_uid, _payment_amount, _payment_currency, 'pending', _payment_validity, 'unpaid', '', '', '', datetime.now(timezone).strftime("%d-%m-%Y %H:%M:%S"), _payment_user,))
            
            dbconnect.commit()

            return jsonify({
                "status": "success",
                "message": "Payment logged successfully",
                "data": {
                    "payment_id": _payment_id
                }
            }), 200

@_system32.route("/system32/payment/webhook", methods=["POST"])
def payment_webhook():
    """
    Webhook endpoint to receive mobile money collection notifications
    Updates dll_payments_manager table based on payment status
    """
    try:
        _payload = request.get_json()
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        
        # Validate webhook structure
        if not _payload or 'event_type' not in _payload or 'data' not in _payload:
            return jsonify({
                "status": "error",
                "message": "Invalid webhook payload structure"
            }), 400
        
        # Check if this is a mobile_money_collection event
        if _payload['event_type'] != 'mobile_money_collection':
            return jsonify({
                "status": "error",
                "message": "Unsupported event type"
            }), 400
        
        # Extract webhook data
        webhook_data = _payload['data']
        external_reference = webhook_data.get('external_referance')
        payment_status = webhook_data.get('status')
        amount_settled = webhook_data.get('amount_settled')
        settlement_currency = webhook_data.get('settlement_currency')
        webhook_date = webhook_data.get('date')
        error_message = webhook_data.get('error_message', '')
        
        # Validate required fields
        if not external_reference or not payment_status:
            return jsonify({
                "status": "error",
                "message": "Missing required fields: external_referance or status"
            }), 400
        
        # Parse the date from webhook format: "Wed, 04 Feb 2026 00:00:00 GMT"
        parsed_date_str = None
        if webhook_date:
            try:
                # Parse the GMT date string (remove timezone for parsing, then convert)
                # Format: "Wed, 04 Feb 2026 00:00:00 GMT"
                date_part = webhook_date.rsplit(' ', 1)[0]  # Remove "GMT" part
                parsed_date = datetime.strptime(date_part, "%a, %d %b %Y %H:%M:%S")
                # Convert GMT to local timezone (GMT is UTC)
                gmt_timezone = pytz.timezone('GMT')
                parsed_date = gmt_timezone.localize(parsed_date)
                # Convert to local timezone
                parsed_date = parsed_date.astimezone(timezone)
                parsed_date_str = parsed_date.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                # If date parsing fails, use current datetime
                parsed_date_str = datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S")
        else:
            parsed_date_str = datetime.now(timezone).strftime("%Y-%m-%d %H:%M:%S")
        
        with dbconnect:
            with dbconnect.cursor() as cursor:
                # Check if payment record exists
                cursor.execute("SELECT payment_uid FROM dll_payments_manager WHERE payment_uid=%s", (external_reference,))
                
                if cursor.rowcount == 0:
                    return jsonify({
                        "status": "error",
                        "message": f"Payment record not found for external_reference: {external_reference}"
                    }), 404
                
                # Update payment status and other fields
                if payment_status == 'successful':
                    # Check current payment status to prevent webhook abuse
                    cursor.execute(
                        "SELECT payment_status, payment_validity FROM dll_payments_manager WHERE payment_uid=%s",
                        (external_reference,),
                    )
                    status_row = cursor.fetchone()
                    
                    if not status_row:
                        return jsonify({
                            "status": "error",
                            "message": f"Payment record not found for external_reference: {external_reference}"
                        }), 404
                    
                    current_payment_status = status_row[0]
                    payment_validity = status_row[1] if len(status_row) > 1 else None
                    
                    # Prevent webhook abuse: only update if status is still "pending"
                    if current_payment_status != 'pending':
                        return jsonify({
                            "status": "success",
                            "message": f"Payment already processed with status: {current_payment_status}. Ignoring duplicate webhook.",
                            "data": {
                                "external_reference": external_reference,
                                "current_status": current_payment_status,
                                "webhook_status": payment_status
                            }
                        }), 200

                    # Use current date/time with timezone for validity start (not webhook date)
                    validity_start_dt = datetime.now(timezone)

                    valid_start_dt, valid_end_dt = _compute_validity_window(
                        payment_validity, validity_start_dt
                    )
                    valid_start_str = (
                        valid_start_dt.strftime("%Y-%m-%d %H:%M:%S") if valid_start_dt else None
                    )
                    valid_end_str = (
                        valid_end_dt.strftime("%Y-%m-%d %H:%M:%S") if valid_end_dt else None
                    )

                    cursor.execute("""
                        UPDATE dll_payments_manager 
                        SET payment_status=%s, 
                            payment_amount=%s, 
                            payment_currency=%s, 
                            valid_start_date=%s,
                            valid_end_date=%s,
                            validity_status=%s
                        WHERE payment_uid=%s AND payment_status='pending'
                    """, (
                        'successful',
                        amount_settled if amount_settled else None,
                        settlement_currency if settlement_currency else None,
                        valid_start_str,
                        valid_end_str,
                        'active',
                        external_reference
                    ))
                    
                    # Check if update actually occurred (rowcount > 0)
                    if cursor.rowcount == 0:
                        return jsonify({
                            "status": "success",
                            "message": "Payment was already processed. No update performed.",
                            "data": {
                                "external_reference": external_reference,
                                "current_status": current_payment_status
                            }
                        }), 200
                elif payment_status == 'failed':
                    # Update failed payment
                    cursor.execute("""
                        UPDATE dll_payments_manager 
                        SET payment_status=%s, 
                            payment_amount=%s, 
                            payment_currency=%s, 
                            payment_date=%s
                        WHERE payment_uid=%s
                    """, (
                        'failed',
                        amount_settled if amount_settled else None,
                        settlement_currency if settlement_currency else None,
                        parsed_date_str,
                        external_reference
                    ))
                else:
                    # Handle other statuses
                    cursor.execute("""
                        UPDATE dll_payments_manager 
                        SET payment_status=%s, 
                            payment_date=%s
                        WHERE payment_uid=%s
                    """, (
                        payment_status,
                        parsed_date_str,
                        external_reference
                    ))
                
                dbconnect.commit()
                
                return jsonify({
                    "status": "success",
                    "message": "Payment updated successfully",
                    "data": {
                        "external_reference": external_reference,
                        "payment_status": payment_status,
                        "amount_settled": amount_settled,
                        "error_message": error_message if error_message else None
                    }
                }), 200
                
    except psycopg2.Error as db_error:
        dbconnect.rollback()
        return jsonify({
            "status": "error",
            "message": f"Database error: {str(db_error)}"
        }), 500
    except Exception as error:
        return jsonify({
            "status": "error",
            "message": f"Webhook processing error: {str(error)}"
        }), 500

@_system32.route("/system32/payment/transactions/<payment_user_uid>", methods=["GET"])
def get_all_transactions(payment_user_uid):
    """
    Get all transactions for a specific payment_user_uid
    Returns all possible transaction details
    """
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    SELECT payment_uid, 
                           payment_account, 
                           payment_amount, 
                           payment_currency, 
                           payment_status, 
                           payment_validity, 
                           validity_status, 
                           used_imei, 
                           valid_start_date, 
                           valid_end_date, 
                           payment_date, 
                           payment_user_uid
                    FROM dll_payments_manager 
                    WHERE payment_user_uid=%s 
                    ORDER BY id DESC
                """, (payment_user_uid,))
                
                if cursor.rowcount == 0:
                    return jsonify({
                        "status": "success",
                        "message": "No transactions found",
                        "data": []
                    }), 200
                
                transactions = []
                columns = [
                    'payment_uid', 'payment_account', 'payment_amount', 
                    'payment_currency', 'payment_status', 'payment_validity',
                    'validity_status', 'used_imei', 'valid_start_date',
                    'valid_end_date', 'payment_date', 'payment_user_uid'
                ]
                
                for row in cursor.fetchall():
                    transaction = {}
                    for i, col in enumerate(columns):
                        transaction[col] = row[i]
                    transactions.append(transaction)
                
                return jsonify({
                    "status": "success",
                    "message": f"Found {len(transactions)} transaction(s)",
                    "data": transactions
                }), 200
                
    except psycopg2.Error as db_error:
        return jsonify({
            "status": "error",
            "message": f"Database error: {str(db_error)}"
        }), 500
    except Exception as error:
        return jsonify({
            "status": "error",
            "message": f"Error loading transactions: {str(error)}"
        }), 500

@_system32.route("/system32/payment/transactions/active/<payment_user_uid>", methods=["GET"])
def get_active_transactions(payment_user_uid):
    """
    Get only active transactions (validity_status='active') for a specific payment_user_uid
    Returns all possible transaction details for active transactions only
    """
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    SELECT payment_uid, 
                           payment_account, 
                           payment_amount, 
                           payment_currency, 
                           payment_status, 
                           payment_validity, 
                           validity_status, 
                           used_imei, 
                           valid_start_date, 
                           valid_end_date, 
                           payment_date, 
                           payment_user_uid
                    FROM dll_payments_manager 
                    WHERE payment_user_uid=%s AND validity_status='active'
                    ORDER BY id DESC
                """, (payment_user_uid,))
                
                if cursor.rowcount == 0:
                    return jsonify({
                        "status": "success",
                        "message": "No active transactions found",
                        "data": []
                    }), 200
                
                transactions = []
                columns = [
                    'payment_uid', 'payment_account', 'payment_amount', 
                    'payment_currency', 'payment_status', 'payment_validity',
                    'validity_status', 'used_imei', 'valid_start_date',
                    'valid_end_date', 'payment_date', 'payment_user_uid'
                ]
                
                for row in cursor.fetchall():
                    transaction = {}
                    for i, col in enumerate(columns):
                        transaction[col] = row[i]
                    transactions.append(transaction)
                
                return jsonify({
                    "status": "success",
                    "message": f"Found {len(transactions)} active transaction(s)",
                    "data": transactions
                }), 200
                
    except psycopg2.Error as db_error:
        return jsonify({
            "status": "error",
            "message": f"Database error: {str(db_error)}"
        }), 500
    except Exception as error:
        return jsonify({
            "status": "error",
            "message": f"Error loading active transactions: {str(error)}"
        }), 500

@_system32.route("/system32/payment/check-imei/<imei>", methods=["GET"])
def check_imei_validity(imei):
    """
    Check if an IMEI has an active payment and if validity dates are expired
    Returns payment validity status and expiration information
    """
    rid = uuid.uuid4().hex[:12]  # short trace id for correlating logs
    logger = current_app.logger
    step = "start"
    dbconnect = None

    # helper to log row structure safely
    def _row_debug(row):
        try:
            if row is None:
                return {"row": None}
            info = {
                "row_type": str(type(row)),
            }
            # DictCursor rows can be dict-like
            if isinstance(row, dict):
                info["keys"] = list(row.keys())
                # small preview (avoid huge logs)
                info["preview"] = {k: str(row.get(k))[:120] for k in list(row.keys())[:10]}
                return info
            # tuple/list
            if hasattr(row, "__len__"):
                info["len"] = len(row)
            try:
                info["preview"] = [str(x)[:120] for x in row[:10]]
                info["types"] = [str(type(x)) for x in row[:10]]
            except Exception:
                info["preview"] = str(row)[:200]
            return info
        except Exception as e:
            return {"row_debug_error": str(e)}

    logger.info("[check_imei_validity] rid=%s imei=%s step=%s", rid, imei, step)

    try:
        step = "db_connect"
        logger.info("[check_imei_validity] rid=%s step=%s connecting_db", rid, step)
        dbconnect = psycopg2.connect(current_app.config["db_link"])

        # If you already have `timezone` in scope (pytz timezone), keep it.
        tz = timezone
        current_time = datetime.now(tz)

        step = "db_query"
        logger.info("[check_imei_validity] rid=%s step=%s executing_query", rid, step)

        with dbconnect:
            # ✅ DictCursor to avoid tuple indexing issues entirely
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                sql = """
                    SELECT
                        payment_uid,
                        payment_validity,
                        valid_start_date,
                        valid_end_date,
                        payment_status,
                        validity_status,
                        payment_user_uid
                    FROM dll_payments_manager
                    WHERE used_imei = %s AND (validity_status = 'in_use' OR validity_status = 'expired') 
                    ORDER BY payment_date DESC
                    LIMIT 1
                """

                cursor.execute(sql, (str(imei),))
                logger.info(
                    "[check_imei_validity] rid=%s step=%s query_ok status=%s rowcount=%s",
                    rid, step, getattr(cursor, "statusmessage", None), getattr(cursor, "rowcount", None)
                )

                step = "fetchone"
                row = cursor.fetchone()
                logger.info("[check_imei_validity] rid=%s step=%s row=%s", rid, step, _row_debug(row))

                if not row:
                    logger.warning("[check_imei_validity] rid=%s step=%s no_rows_found", rid, step)
                    return jsonify({
                        "status": "error",
                        "message": f"No active payment found for IMEI: {imei}",
                        "trace_id": rid,
                        "data": {
                            "imei": imei,
                            "is_valid": False,
                            "is_expired": True,
                            "reason": "No payment found for this IMEI"
                        }
                    }), 404

                step = "extract_fields"
                # RealDictCursor returns dict keys exactly as selected
                payment_uid = row.get("payment_uid")
                payment_validity = row.get("payment_validity")
                valid_start_date_val = row.get("valid_start_date")
                valid_end_date_val = row.get("valid_end_date")
                payment_status = row.get("payment_status")
                validity_status = row.get("validity_status")
                payment_user_uid = row.get("payment_user_uid")

                logger.info(
                    "[check_imei_validity] rid=%s step=%s extracted payment_uid=%s status=%s validity=%s",
                    rid, step, str(payment_uid), str(payment_status), str(validity_status)
                )
                logger.info(
                    "[check_imei_validity] rid=%s step=%s date_types start=%s end=%s",
                    rid, step, str(type(valid_start_date_val)), str(type(valid_end_date_val))
                )

                def to_aware_dt(val):
                    """Accept datetime/date/string and return timezone-aware datetime or None."""
                    if val is None:
                        return None

                    if isinstance(val, datetime):
                        dt = val
                    elif isinstance(val, date):
                        dt = datetime.combine(val, dtime.min)
                    else:
                        s = str(val).strip()
                        dt = None
                        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                            try:
                                dt = datetime.strptime(s, fmt)
                                break
                            except ValueError:
                                continue
                        if dt is None:
                            raise ValueError(f"Unsupported date format: {s}")

                    if dt.tzinfo is None:
                        if hasattr(tz, "localize"):
                            dt = tz.localize(dt)
                        else:
                            dt = dt.replace(tzinfo=tz)

                    return dt

                step = "compute_validity"
                is_expired = True
                is_valid = False
                reason = ""

                try:
                    valid_start_date = to_aware_dt(valid_start_date_val)
                    valid_end_date = to_aware_dt(valid_end_date_val)

                    logger.info(
                        "[check_imei_validity] rid=%s step=%s parsed_dates start=%s end=%s now=%s",
                        rid, step, str(valid_start_date), str(valid_end_date), str(current_time)
                    )

                    if not valid_start_date or not valid_end_date:
                        reason = "Validity dates are not set"
                    else:
                        if current_time < valid_start_date:
                            is_expired = False
                            is_valid = False
                            reason = f"Validity period has not started yet. Starts at: {valid_start_date}"
                        elif current_time > valid_end_date:
                            is_expired = True
                            is_valid = False
                            reason = f"Validity period has expired. Ended at: {valid_end_date}"
                        else:
                            is_expired = False
                            is_valid = True
                            reason = f"Payment is active and valid until: {valid_end_date}"

                except Exception as e:
                    # date parsing failures show here
                    logger.exception("[check_imei_validity] rid=%s step=%s date_parse_failed", rid, step)
                    is_expired = True
                    is_valid = False
                    reason = f"Error parsing validity dates: {str(e)}"

                step = "status_checks"
                if str(payment_status).lower() != "successful":
                    is_valid = False
                    reason = f"Payment status is '{payment_status}', not 'successful'"

                if str(validity_status).lower() != "in_use":
                    is_valid = False
                    reason = f"Validity status is '{validity_status}', not 'active'"

                logger.info(
                    "[check_imei_validity] rid=%s step=%s final is_valid=%s is_expired=%s reason=%s",
                    rid, step, is_valid, is_expired, reason
                )

                def fmt_dt(v):
                    if v is None:
                        return None
                    if isinstance(v, datetime):
                        return v.strftime("%Y-%m-%d %H:%M:%S")
                    return str(v)

                step = "return_success"
                return jsonify({
                    "status": "success",
                    "message": "IMEI validity check completed",
                    "trace_id": rid,
                    "data": {
                        "imei": imei,
                        "payment_uid": str(payment_uid),
                        "payment_validity": payment_validity,
                        "payment_status": payment_status,
                        "validity_status": validity_status,
                        "payment_user_uid": str(payment_user_uid),
                        "valid_start_date": fmt_dt(valid_start_date_val),
                        "valid_end_date": fmt_dt(valid_end_date_val),
                        "current_time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "is_valid": is_valid,
                        "is_expired": is_expired,
                        "reason": reason
                    }
                }), 200

    except psycopg2.Error:
        logger.exception("[check_imei_validity] rid=%s step=%s psycopg2_error", rid, step)
        return jsonify({"status": "error", "message": "Database error", "trace_id": rid}), 500

    except Exception:
        # ✅ this will print the *exact* stack trace (line that broke)
        logger.exception("[check_imei_validity] rid=%s step=%s unexpected_error", rid, step)
        return jsonify({
            "status": "error",
            "message": "Error checking IMEI validity (see server logs)",
            "trace_id": rid
        }), 500

    finally:
        try:
            if dbconnect:
                dbconnect.close()
        except Exception:
            logger.exception("[check_imei_validity] rid=%s step=close_db failed", rid)

@_system32.route("/system32/payment/update-imei", methods=["POST"])
def update_payment_imei():
    """
    Update the used_imei for a payment by payment_uid
    Expires the previous payment that had this IMEI by appending '_expired' to its used_imei
    """
    try:
        _payload = request.get_json()
        
        if not _payload:
            return jsonify({
                "status": "error",
                "message": "Invalid request payload"
            }), 400
        
        # Handle nested 'data' structure or direct access
        if 'data' in _payload:
            payment_uid = _payload['data'].get('payment_uid')
            new_imei = _payload['data'].get('used_imei')
        else:
            payment_uid = _payload.get('payment_uid')
            new_imei = _payload.get('used_imei')
        
        if not payment_uid or not new_imei:
            return jsonify({
                "status": "error",
                "message": "Missing required fields: payment_uid and used_imei"
            }), 400
        
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        
        with dbconnect:
            with dbconnect.cursor() as cursor:
                # Check if payment exists
                try:
                    cursor.execute("SELECT payment_uid FROM dll_payments_manager WHERE payment_uid=%s", (payment_uid,))
                    payment_row = cursor.fetchone()
                    if not payment_row:
                        return jsonify({
                            "status": "error",
                            "message": f"Payment not found for payment_uid: {payment_uid}"
                        }), 404
                except Exception as e:
                    raise Exception(f"Error checking payment existence: {str(e)}. Traceback: {traceback.format_exc()}")
                
                # Find previous payment with this IMEI (excluding already expired ones)
                try:
                    # Ensure parameters are strings, not tuples or lists
                    if isinstance(new_imei, (tuple, list)):
                        new_imei = new_imei[0] if len(new_imei) > 0 else str(new_imei)
                    if isinstance(payment_uid, (tuple, list)):
                        payment_uid = payment_uid[0] if len(payment_uid) > 0 else str(payment_uid)
                    
                    # Convert to strings to ensure proper formatting
                    new_imei_str = str(new_imei) if new_imei else None
                    payment_uid_str = str(payment_uid) if payment_uid else None
                    
                    if not new_imei_str or not payment_uid_str:
                        raise ValueError(f"Invalid parameters: new_imei={new_imei}, payment_uid={payment_uid}")
                    
                    # Create parameters tuple explicitly
                    query_params = (new_imei_str, payment_uid_str)
                    
                    cursor.execute("""
                        SELECT payment_uid, used_imei 
                        FROM dll_payments_manager 
                        WHERE used_imei=%s 
                        AND used_imei NOT LIKE '%%_expired'
                        AND payment_uid != %s
                        ORDER BY payment_date DESC
                        LIMIT 1
                    """, query_params)
                except Exception as e:
                    raise Exception(f"Error querying previous payment: {str(e)}. new_imei type: {type(new_imei)}, new_imei value: {repr(new_imei)}, payment_uid type: {type(payment_uid)}, payment_uid value: {repr(payment_uid)}. Query params: {repr(query_params) if 'query_params' in locals() else 'N/A'}. Traceback: {traceback.format_exc()}")
                
                previous_payment_uid = None
                previous_imei = None
                
                try:
                    prev_row = cursor.fetchone()
                    if prev_row:
                        try:
                            # Safely access tuple elements
                            if not isinstance(prev_row, (tuple, list)):
                                raise TypeError(f"Expected tuple/list, got {type(prev_row)}")
                            
                            if len(prev_row) < 2:
                                raise IndexError(f"Row has {len(prev_row)} elements, expected at least 2")
                            
                            previous_payment_uid = prev_row[0]
                            previous_imei = prev_row[1]
                            
                            # Expire the previous payment by appending '_expired' to used_imei
                            if previous_payment_uid and previous_imei:
                                expired_imei = f"{previous_imei}_expired"
                                cursor.execute("""
                                    UPDATE dll_payments_manager 
                                    SET used_imei=%s, validity_status='expired'
                                    WHERE payment_uid=%s
                                """, (expired_imei, previous_payment_uid,))
                        except (IndexError, TypeError, ValueError) as e:
                            # Re-raise with more context
                            raise Exception(f"Error processing previous payment row at line 629-630: {str(e)}. Row type: {type(prev_row)}, Row length: {len(prev_row) if hasattr(prev_row, '__len__') else 'N/A'}, Row content: {prev_row}. Traceback: {traceback.format_exc()}")
                except Exception as e:
                    raise Exception(f"Error fetching previous payment row: {str(e)}. Traceback: {traceback.format_exc()}")
                
                # Update the new payment with the IMEI
                try:
                    cursor.execute("""
                        UPDATE dll_payments_manager 
                        SET used_imei=%s, validity_status='in_use'
                        WHERE payment_uid=%s
                    """, (new_imei, payment_uid,))
                except Exception as e:
                    raise Exception(f"Error updating payment IMEI: {str(e)}. Traceback: {traceback.format_exc()}")
                
                try:
                    dbconnect.commit()
                except Exception as e:
                    dbconnect.rollback()
                    raise Exception(f"Error committing transaction: {str(e)}. Traceback: {traceback.format_exc()}")
                
                try:
                    response_data = {
                        "payment_uid": payment_uid,
                        "new_imei": new_imei,
                        "previous_payment_expired": previous_payment_uid is not None
                    }
                    
                    if previous_payment_uid and previous_imei:
                        response_data["previous_payment_uid"] = previous_payment_uid
                        response_data["previous_imei"] = previous_imei
                        response_data["expired_imei"] = f"{previous_imei}_expired"
                except Exception as e:
                    raise Exception(f"Error building response data: {str(e)}. Traceback: {traceback.format_exc()}")
                
                return jsonify({
                    "status": "success",
                    "message": "IMEI updated successfully",
                    "data": response_data
                }), 200
                
    except psycopg2.Error as db_error:
        if 'dbconnect' in locals():
            dbconnect.rollback()
        return jsonify({
            "status": "error",
            "message": f"Database error: {str(db_error)}",
            "traceback": traceback.format_exc()
        }), 500
    except Exception as error:
        error_traceback = traceback.format_exc()
        error_details = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": error_traceback
        }
        return jsonify({
            "status": "error",
            "message": f"Error updating IMEI: {str(error)}",
            "error_details": error_details
        }), 500


@_system32.route("/system32/devices/update/properties", methods=['POST'])
def system32_update_device():

    try:

        dbconnect = psycopg2.connect(current_app.config['db_link'])
        update_payload = request.get_json()

        if(len(str(update_payload['data']['device_imei'])) > 4) and (len(str(update_payload['data']['device_name'])) > 1) and (len(str(update_payload['data']['simcard'])) > 4) and (len(str(update_payload['data']['car_make'])) > 4) and (len(str(update_payload['data']['car_model'])) > 4) and (len(str(update_payload['data']['client'])) > 4) and (len(str(update_payload['data']['vin_number'])) > 4) and (len(str(update_payload['data']['car_type'])) > 1) and (len(str(update_payload['data']['current_simcard'])) > 4):

            UpdateImei = str(update_payload['data']['device_imei'])
            UpdateDeviceName = str(update_payload['data']['device_name'])
            UpdateSimcard = str(update_payload['data']['simcard'])
            UpdateCarMake = str(update_payload['data']['car_make'])
            UpdateCarModel = str(update_payload['data']['car_model'])
            UpdateClient = str(update_payload['data']['client'])
            UpdateVinNumber = str(update_payload['data']['vin_number'])
            UpdateCarType = str(update_payload['data']['car_type'])
            UpdateCurrentSimcard = str(update_payload['data']['current_simcard'])

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT device_hardware FROM dll_device_basic_data WHERE device_imei=%s;", (str(UpdateImei),))

                    if(cursor.rowcount == 1):

                        cursor.execute("UPDATE dll_device_basic_data SET device_name=%s, device_simcard=%s, device_car_make=%s, device_car_model=%s,device_vin_number=%s, device_client=%s, device_car_type=%s WHERE device_imei=%s;", (UpdateDeviceName, UpdateSimcard, UpdateCarMake, UpdateCarModel, str(UpdateVinNumber), UpdateClient, UpdateCarType, str(UpdateImei),))

                        return reply('success', 200, 'device properties update successful', '')

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'Route Failed, device Not Found', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')