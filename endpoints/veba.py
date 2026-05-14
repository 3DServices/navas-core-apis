from flask import Blueprint, request, jsonify, current_app
import psycopg2
import psycopg2.extras
import uuid
from datetime import datetime
import pytz

_veba = Blueprint("VEBA", __name__)
timezone = pytz.timezone('Africa/Nairobi')

def response_out(status, message, statusCode, data):
    return jsonify({
        "status": status,
        "message": message,
        "data": data
    }), statusCode


@_veba.route("/veba/enable", methods=["POST"])
def EnableVEBA():
    """
    Enable VEBA for a device
    Payload: {
        "data": {
            "device_imei": "123456789012345",
            "client_uid": "uuid-here",
            "enabled_by": "user@example.com"
        }
    }
    """
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        _payload = request.get_json()

        if not _payload or 'data' not in _payload:
            return response_out("error", "Invalid payload format", 400, {})

        _deviceImei = _payload['data'].get('device_imei')
        _clientUID = _payload['data'].get('client_uid')
        _enabledBy = _payload['data'].get('enabled_by', 'system')

        if not _deviceImei or not _clientUID:
            return response_out("error", "device_imei and client_uid are required", 400, {})

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Step 1: Check if client has active VEBA token subscription
                cursor.execute("""
                    SELECT 
                        (uta.token_hours_left)::numeric AS token_hours_left,
                        tr.token_type,
                        tr.token_name
                    FROM dll_user_token_accounts uta
                    JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    WHERE uta.client_uid = %s
                      AND tr.token_type = 'veba'
                      AND uta.token_status = 'active'
                      AND (uta.token_hours_left)::numeric > 0
                """, (_clientUID,))

                if cursor.rowcount == 0:
                    return response_out("error", "No active VEBA token subscription found. Please purchase a VEBA token first.", 403, {})

                token_info = cursor.fetchone()

                # Step 2: Check if device exists and belongs to client
                cursor.execute("""
                    SELECT device_imei_number, service_provider
                    FROM dll_device_subscriptions 
                    WHERE device_imei_number = %s AND service_provider = %s
                """, (_deviceImei, _clientUID))

                if cursor.rowcount == 0:
                    return response_out("error", "Device not found or not owned by this client", 404, {})

                # Step 3: Check if unit already exists in VEBA table
                cursor.execute("""
                    SELECT id, veba_status 
                    FROM dll_veba_enabled_units 
                    WHERE device_imei_number = %s
                """, (_deviceImei,))

                _currentTime = datetime.now(timezone)

                if cursor.rowcount == 1:
                    # Unit exists, just update status to available
                    existing_unit = cursor.fetchone()
                    
                    cursor.execute("""
                        UPDATE dll_veba_enabled_units 
                        SET veba_status = 'available', 
                            updated_at = %s,
                            enabled_by = %s
                        WHERE device_imei_number = %s
                        RETURNING id, veba_status, enabled_at, updated_at
                    """, (_currentTime, _enabledBy, _deviceImei))
                    
                    updated_unit = cursor.fetchone()
                    dbconnect.commit()

                    return response_out("success", "VEBA enabled successfully (unit already registered)", 200, {
                        "device_imei": _deviceImei,
                        "veba_status": updated_unit['veba_status'],
                        "enabled_at": str(updated_unit['enabled_at']),
                        "updated_at": str(updated_unit['updated_at']),
                        "token_hours_left": float(token_info['token_hours_left'])
                    })
                else:
                    # Unit doesn't exist, create new entry
                    cursor.execute("""
                        INSERT INTO dll_veba_enabled_units 
                        (device_imei_number, client_uid, veba_status, enabled_by, enabled_at, updated_at)
                        VALUES (%s, %s, 'available', %s, %s, %s)
                        RETURNING id, device_imei_number, veba_status, enabled_at, updated_at
                    """, (_deviceImei, _clientUID, _enabledBy, _currentTime, _currentTime))

                    new_unit = cursor.fetchone()
                    dbconnect.commit()

                    return response_out("success", "VEBA enabled and unit registered successfully", 201, {
                        "device_imei": new_unit['device_imei_number'],
                        "veba_status": new_unit['veba_status'],
                        "enabled_at": str(new_unit['enabled_at']),
                        "updated_at": str(new_unit['updated_at']),
                        "token_hours_left": float(token_info['token_hours_left'])
                    })

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


@_veba.route("/veba/disable", methods=["POST"])
def DisableVEBA():
    """
    Disable VEBA for a device (make unavailable)
    Payload: {
        "data": {
            "device_imei": "123456789012345"
        }
    }
    """
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        _payload = request.get_json()

        if not _payload or 'data' not in _payload:
            return response_out("error", "Invalid payload format", 400, {})

        _deviceImei = _payload['data'].get('device_imei')

        if not _deviceImei:
            return response_out("error", "device_imei is required", 400, {})

        _currentTime = datetime.now(timezone)

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    UPDATE dll_veba_enabled_units 
                    SET veba_status = 'unavailable', updated_at = %s
                    WHERE device_imei_number = %s
                    RETURNING device_imei_number, veba_status, updated_at
                """, (_currentTime, _deviceImei))

                if cursor.rowcount == 0:
                    return response_out("error", "Device not found in VEBA registry", 404, {})

                updated_unit = cursor.fetchone()
                dbconnect.commit()

                return response_out("success", "VEBA disabled successfully", 200, {
                    "device_imei": updated_unit['device_imei_number'],
                    "veba_status": updated_unit['veba_status'],
                    "updated_at": str(updated_unit['updated_at'])
                })

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


@_veba.route("/veba/status/<string:device_imei>", methods=["GET"])
def GetVEBAStatus(device_imei):
    """Get VEBA status for a specific device"""
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT device_imei_number, client_uid, veba_status, enabled_at, updated_at, enabled_by, notes
                    FROM dll_veba_enabled_units
                    WHERE device_imei_number = %s
                """, (device_imei,))

                if cursor.rowcount == 0:
                    return response_out("error", "Device not in VEBA registry", 404, {})

                veba_data = cursor.fetchone()
                
                return response_out("success", "VEBA status retrieved", 200, {
                    "device_imei": veba_data['device_imei_number'],
                    "client_uid": veba_data['client_uid'],
                    "veba_status": veba_data['veba_status'],
                    "enabled_at": str(veba_data['enabled_at']),
                    "updated_at": str(veba_data['updated_at']),
                    "enabled_by": veba_data['enabled_by'],
                    "notes": veba_data['notes']
                })

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


@_veba.route("/veba/units/<string:client_uid>", methods=["GET"])
def ListClientVEBAUnits(client_uid):
    """List all VEBA enabled units for a client"""
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT device_imei_number, veba_status, enabled_at, updated_at, enabled_by, notes
                    FROM dll_veba_enabled_units
                    WHERE client_uid = %s
                    ORDER BY updated_at DESC
                """, (client_uid,))

                units = cursor.fetchall()
                _vebaUnits = []
                
                for unit in units:
                    _vebaUnits.append({
                        "device_imei": unit['device_imei_number'],
                        "veba_status": unit['veba_status'],
                        "enabled_at": str(unit['enabled_at']),
                        "updated_at": str(unit['updated_at']),
                        "enabled_by": unit['enabled_by'],
                        "notes": unit['notes']
                    })

                return response_out("success", f"Found {len(_vebaUnits)} VEBA units", 200, _vebaUnits)

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


@_veba.route("/veba/available", methods=["GET"])
def ListAvailableVEBAUnits():
    """List all available VEBA units across all clients"""
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT v.device_imei_number, v.client_uid, v.enabled_at, v.updated_at, v.enabled_by
                    FROM dll_veba_enabled_units v
                    WHERE v.veba_status = 'available'
                    ORDER BY v.updated_at DESC
                """)

                units = cursor.fetchall()
                _availableUnits = []
                
                for unit in units:
                    _availableUnits.append({
                        "device_imei": unit['device_imei_number'],
                        "client_uid": unit['client_uid'],
                        "enabled_at": str(unit['enabled_at']),
                        "updated_at": str(unit['updated_at']),
                        "enabled_by": unit['enabled_by']
                    })

                return response_out("success", f"Found {len(_availableUnits)} available units", 200, _availableUnits)

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


@_veba.route("/veba/statistics", methods=["GET"])
def GetVEBAStatistics():
    """
    Get VEBA statistics for dashboard
    Returns:
    - Bookings today
    - Leakage attempts today
    - Settlement p95 (95th percentile settlement time)
    """
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get bookings today
                cursor.execute("""
                    SELECT COUNT(*) as bookings_today
                    FROM dll_veba_statistics
                    WHERE event_type = 'booking'
                      AND DATE(created_at) = CURRENT_DATE
                """)
                bookings_result = cursor.fetchone()
                bookings_today = bookings_result['bookings_today'] if bookings_result else 0

                # Get leakage attempts today
                cursor.execute("""
                    SELECT COUNT(*) as leakage_attempts
                    FROM dll_veba_statistics
                    WHERE event_type = 'leakage_attempt'
                      AND DATE(created_at) = CURRENT_DATE
                """)
                leakage_result = cursor.fetchone()
                leakage_attempts = leakage_result['leakage_attempts'] if leakage_result else 0

                # Get settlement p95 (95th percentile) - last 7 days
                cursor.execute("""
                    SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY settlement_time_minutes) as p95_settlement
                    FROM dll_veba_statistics
                    WHERE event_type = 'booking'
                      AND settlement_time_minutes IS NOT NULL
                      AND created_at >= CURRENT_DATE - INTERVAL '7 days'
                """)
                settlement_result = cursor.fetchone()
                settlement_p95_minutes = settlement_result['p95_settlement'] if settlement_result and settlement_result['p95_settlement'] else 0
                
                # Format settlement time for display (e.g., "18m")
                settlement_p95_display = f"{int(settlement_p95_minutes)}m" if settlement_p95_minutes else "0m"

                return response_out("success", "VEBA statistics retrieved", 200, {
                    "bookings_today": int(bookings_today),
                    "leakage_attempts": int(leakage_attempts),
                    "settlement_p95": settlement_p95_display,
                    "settlement_p95_minutes": float(settlement_p95_minutes) if settlement_p95_minutes else 0
                })

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()
