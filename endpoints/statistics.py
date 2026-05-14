from flask import Blueprint, jsonify, current_app
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.auth import PlainTextAuthProvider
from cassandra import ConsistencyLevel
from cassandra.policies import TokenAwarePolicy, DCAwareRoundRobinPolicy

_statistics = Blueprint("Statistics", __name__)

# Cassandra connection configuration
CASSANDRA_KEYSPACE = 'navas_iot_dbx'
CASSANDRA_CONTACT_POINTS = ['165.232.128.208']
CASSANDRA_PORT = 9042
CASSANDRA_USERNAME = 'cassandra'
CASSANDRA_PASSWORD = 'Sterile-Nectar-Unrevised-Undertone-Stagnate1'
CASSANDRA_LOCAL_DC = 'datacenter1'

_cassandra_cluster = None
_cassandra_session = None

# Online/Offline determination based on heartbeat date matching today's date
# ONLINE_THRESHOLD_MINUTES = 30  # No longer used - now using date-based comparison


def get_cassandra_session():
    """Get or create Cassandra session."""
    global _cassandra_cluster, _cassandra_session
    if _cassandra_session and not _cassandra_session.is_shutdown:
        return _cassandra_session
    try:
        auth_provider = PlainTextAuthProvider(
            username=CASSANDRA_USERNAME,
            password=CASSANDRA_PASSWORD
        )
        profile = ExecutionProfile(
            load_balancing_policy=TokenAwarePolicy(DCAwareRoundRobinPolicy(local_dc=CASSANDRA_LOCAL_DC)),
            consistency_level=ConsistencyLevel.ONE
        )
        _cassandra_cluster = Cluster(
            contact_points=CASSANDRA_CONTACT_POINTS,
            port=CASSANDRA_PORT,
            auth_provider=auth_provider,
            protocol_version=4,
            execution_profiles={EXEC_PROFILE_DEFAULT: profile}
        )
        _cassandra_session = _cassandra_cluster.connect(CASSANDRA_KEYSPACE)
        return _cassandra_session
    except Exception as e:
        print(f"Error connecting to Cassandra: {e}")
        return None


def response_out(status, message, statusCode, data):
    return jsonify({
        "status": status,
        "message": message,
        "data": data
    }), statusCode


def format_token_record(token):
    """Helper function to format token records consistently."""
    return {
        "token_billing_uid": str(token['token_billing_uid']) if token['token_billing_uid'] else None,
        "client_uid": str(token['client_uid']) if token.get('client_uid') else None,
        "client_name": token.get('client_name'),
        "token_id": str(token['token_id']) if token['token_id'] else None,
        "token_name": token['token_name'],
        "token_type": token['token_type'],
        "token_status": token.get('token_status'),
        "token_hours_left": float(token['token_hours_left']) if token['token_hours_left'] else 0,
        "token_hours_used": float(token['token_hours_used']) if token['token_hours_used'] else 0,
        "token_currency": token['token_currency']
    }

# TASK 1: BILLING TOKEN STATISTICS


# 1. Expired Token Subscriptions [Excluding VEBA Tokens]
@_statistics.route("/statistics/tokens/expired", methods=["GET"])
def GetExpiredTokenSubscriptions():
    """
    Get all expired token subscriptions excluding VEBA tokens.
    Returns count and list of expired subscriptions.
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        uta.token_billing_uid,
                        uta.client_uid,
                        uta.token_balance AS token_id,
                        uta.token_status,
                        uta.token_hours_left,
                        uta.token_hours_used,
                        tr.token_name,
                        tr.token_type,
                        tr.token_currency,
                        ca.client_name
                    FROM dll_user_token_accounts uta
                    JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    LEFT JOIN dll_client_accounts ca ON uta.client_uid = ca.client_uid
                    WHERE uta.token_status = 'expired'
                      AND LOWER(tr.token_type) != 'veba'
                    ORDER BY ca.client_name, uta.token_billing_uid
                """)

                expired_tokens = cursor.fetchall()
                result = [format_token_record(token) for token in expired_tokens]

                return response_out(
                    "success",
                    f"Found {len(result)} expired token subscriptions (excluding VEBA)",
                    200,
                    {"count": len(result), "subscriptions": result}
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 2. Active Token Subscriptions [Excluding VEBA Tokens]
@_statistics.route("/statistics/tokens/active", methods=["GET"])
def GetActiveTokenSubscriptions():
    """
    Get all active token subscriptions excluding VEBA tokens.
    Returns count and list of active subscriptions.
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        uta.token_billing_uid,
                        uta.client_uid,
                        uta.token_balance AS token_id,
                        uta.token_status,
                        uta.token_hours_left,
                        uta.token_hours_used,
                        tr.token_name,
                        tr.token_type,
                        tr.token_currency,
                        ca.client_name
                    FROM dll_user_token_accounts uta
                    JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    LEFT JOIN dll_client_accounts ca ON uta.client_uid = ca.client_uid
                    WHERE uta.token_status = 'active'
                      AND LOWER(tr.token_type) != 'veba'
                    ORDER BY ca.client_name, uta.token_billing_uid
                """)

                active_tokens = cursor.fetchall()
                result = [format_token_record(token) for token in active_tokens]

                return response_out(
                    "success",
                    f"Found {len(result)} active token subscriptions (excluding VEBA)",
                    200,
                    {"count": len(result), "subscriptions": result}
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 3. Active VEBA Tokens In General
@_statistics.route("/statistics/veba/tokens/active", methods=["GET"])
def GetActiveVEBATokens():
    """
    Get all active VEBA token subscriptions across all clients.
    Active = token_status is 'active' AND token_hours_left > 0
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        uta.token_billing_uid,
                        uta.client_uid,
                        uta.token_balance AS token_id,
                        uta.token_status,
                        uta.token_hours_left,
                        uta.token_hours_used,
                        tr.token_name,
                        tr.token_type,
                        tr.token_currency,
                        ca.client_name
                    FROM dll_user_token_accounts uta
                    JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    LEFT JOIN dll_client_accounts ca ON uta.client_uid = ca.client_uid
                    WHERE LOWER(tr.token_type) = 'veba'
                      AND uta.token_status = 'active'
                      AND COALESCE(uta.token_hours_left::numeric, 0) > 0
                    ORDER BY ca.client_name, uta.token_billing_uid
                """)

                tokens = cursor.fetchall()
                result = [format_token_record(token) for token in tokens]

                return response_out(
                    "success",
                    f"Found {len(result)} active VEBA token subscriptions",
                    200,
                    {"count": len(result), "subscriptions": result}
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 4. Active VEBA Tokens by Client
@_statistics.route("/statistics/veba/tokens/active/<string:client_uid>", methods=["GET"])
def GetActiveVEBATokensByClient(client_uid):
    """
    Get active VEBA token subscriptions for a specific client.
    Active = token_status is 'active' AND token_hours_left > 0
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # First verify client exists
                cursor.execute(
                    "SELECT client_name FROM dll_client_accounts WHERE client_uid = %s",
                    (client_uid,)
                )
                client_record = cursor.fetchone()
                
                if not client_record:
                    return response_out("error", "Client not found", 404, {})
                
                client_name = client_record['client_name']

                cursor.execute("""
                    SELECT 
                        uta.token_billing_uid,
                        uta.client_uid,
                        uta.token_balance AS token_id,
                        uta.token_status,
                        uta.token_hours_left,
                        uta.token_hours_used,
                        tr.token_name,
                        tr.token_type,
                        tr.token_currency
                    FROM dll_user_token_accounts uta
                    JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    WHERE uta.client_uid = %s
                      AND LOWER(tr.token_type) = 'veba'
                      AND uta.token_status = 'active'
                      AND COALESCE(uta.token_hours_left::numeric, 0) > 0
                    ORDER BY uta.token_billing_uid
                """, (client_uid,))

                tokens = cursor.fetchall()
                result = []
                for token in tokens:
                    record = format_token_record(token)
                    record['client_name'] = client_name
                    result.append(record)

                return response_out(
                    "success",
                    f"Found {len(result)} active VEBA token subscriptions for client",
                    200,
                    {
                        "client_uid": client_uid,
                        "client_name": client_name,
                        "count": len(result),
                        "subscriptions": result
                    }
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 5. Expired VEBA Tokens In General
@_statistics.route("/statistics/veba/tokens/expired", methods=["GET"])
def GetExpiredVEBATokens():
    """
    Get all expired VEBA token subscriptions across all clients.
    Expired = token_status is 'expired' OR token_hours_left <= 0
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        uta.token_billing_uid,
                        uta.client_uid,
                        uta.token_balance AS token_id,
                        uta.token_status,
                        uta.token_hours_left,
                        uta.token_hours_used,
                        tr.token_name,
                        tr.token_type,
                        tr.token_currency,
                        ca.client_name
                    FROM dll_user_token_accounts uta
                    JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    LEFT JOIN dll_client_accounts ca ON uta.client_uid = ca.client_uid
                    WHERE LOWER(tr.token_type) = 'veba'
                      AND (uta.token_status = 'expired' OR COALESCE(uta.token_hours_left::numeric, 0) <= 0)
                    ORDER BY ca.client_name, uta.token_billing_uid
                """)

                tokens = cursor.fetchall()
                result = [format_token_record(token) for token in tokens]

                return response_out(
                    "success",
                    f"Found {len(result)} expired VEBA token subscriptions",
                    200,
                    {"count": len(result), "subscriptions": result}
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 6. Expired VEBA Tokens By Client
@_statistics.route("/statistics/veba/tokens/expired/<string:client_uid>", methods=["GET"])
def GetExpiredVEBATokensByClient(client_uid):
    """
    Get expired VEBA token subscriptions for a specific client.
    Expired = token_status is 'expired' OR token_hours_left <= 0
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # First verify client exists
                cursor.execute(
                    "SELECT client_name FROM dll_client_accounts WHERE client_uid = %s",
                    (client_uid,)
                )
                client_record = cursor.fetchone()
                
                if not client_record:
                    return response_out("error", "Client not found", 404, {})
                
                client_name = client_record['client_name']

                cursor.execute("""
                    SELECT 
                        uta.token_billing_uid,
                        uta.client_uid,
                        uta.token_balance AS token_id,
                        uta.token_status,
                        uta.token_hours_left,
                        uta.token_hours_used,
                        tr.token_name,
                        tr.token_type,
                        tr.token_currency
                    FROM dll_user_token_accounts uta
                    JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    WHERE uta.client_uid = %s
                      AND LOWER(tr.token_type) = 'veba'
                      AND (uta.token_status = 'expired' OR COALESCE(uta.token_hours_left::numeric, 0) <= 0)
                    ORDER BY uta.token_billing_uid
                """, (client_uid,))

                tokens = cursor.fetchall()
                result = []
                for token in tokens:
                    record = format_token_record(token)
                    record['client_name'] = client_name
                    result.append(record)

                return response_out(
                    "success",
                    f"Found {len(result)} expired VEBA token subscriptions for client",
                    200,
                    {
                        "client_uid": client_uid,
                        "client_name": client_name,
                        "count": len(result),
                        "subscriptions": result
                    }
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()



# TASK 3: VEBA STATISTICS

# 1. VEBA Units Enabled (Available)
@_statistics.route("/statistics/veba/units/enabled", methods=["GET"])
def GetVEBAUnitsEnabled():
    """
    Get all VEBA enabled units across all clients.
    Enabled = veba_status is 'available'
    Returns count and list of enabled units.
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        veu.id,
                        veu.device_imei_number,
                        veu.client_uid,
                        veu.veba_status,
                        veu.enabled_at,
                        veu.updated_at,
                        veu.enabled_by,
                        veu.notes,
                        ca.client_name
                    FROM dll_veba_enabled_units veu
                    LEFT JOIN dll_client_accounts ca ON veu.client_uid = ca.client_uid
                    WHERE veu.veba_status = 'available'
                    ORDER BY ca.client_name, veu.device_imei_number
                """)

                units = cursor.fetchall()
                result = []
                for unit in units:
                    result.append({
                        "id": unit['id'],
                        "device_imei": unit['device_imei_number'],
                        "client_uid": unit['client_uid'],
                        "client_name": unit['client_name'],
                        "veba_status": unit['veba_status'],
                        "enabled_at": str(unit['enabled_at']) if unit['enabled_at'] else None,
                        "updated_at": str(unit['updated_at']) if unit['updated_at'] else None,
                        "enabled_by": unit['enabled_by'],
                        "notes": unit['notes']
                    })

                return response_out(
                    "success",
                    f"Found {len(result)} VEBA enabled units",
                    200,
                    {"count": len(result), "units": result}
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 2. VEBA Units Enabled by Client
@_statistics.route("/statistics/veba/units/enabled/<string:client_uid>", methods=["GET"])
def GetVEBAUnitsEnabledByClient(client_uid):
    """
    Get VEBA enabled units for a specific client.
    Enabled = veba_status is 'available'
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Verify client exists
                cursor.execute(
                    "SELECT client_name FROM dll_client_accounts WHERE client_uid = %s",
                    (client_uid,)
                )
                client_record = cursor.fetchone()
                
                if not client_record:
                    return response_out("error", "Client not found", 404, {})
                
                client_name = client_record['client_name']

                cursor.execute("""
                    SELECT 
                        veu.id,
                        veu.device_imei_number,
                        veu.client_uid,
                        veu.veba_status,
                        veu.enabled_at,
                        veu.updated_at,
                        veu.enabled_by,
                        veu.notes
                    FROM dll_veba_enabled_units veu
                    WHERE veu.client_uid = %s
                      AND veu.veba_status = 'available'
                    ORDER BY veu.device_imei_number
                """, (client_uid,))

                units = cursor.fetchall()
                result = []
                for unit in units:
                    result.append({
                        "id": unit['id'],
                        "device_imei": unit['device_imei_number'],
                        "client_uid": unit['client_uid'],
                        "client_name": client_name,
                        "veba_status": unit['veba_status'],
                        "enabled_at": str(unit['enabled_at']) if unit['enabled_at'] else None,
                        "updated_at": str(unit['updated_at']) if unit['updated_at'] else None,
                        "enabled_by": unit['enabled_by'],
                        "notes": unit['notes']
                    })

                return response_out(
                    "success",
                    f"Found {len(result)} VEBA enabled units for client",
                    200,
                    {
                        "client_uid": client_uid,
                        "client_name": client_name,
                        "count": len(result),
                        "units": result
                    }
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 3. VEBA Units Disabled (Unavailable)
@_statistics.route("/statistics/veba/units/disabled", methods=["GET"])
def GetVEBAUnitsDisabled():
    """
    Get all VEBA disabled units across all clients.
    Disabled = veba_status is 'unavailable'
    Returns count and list of disabled units.
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        veu.id,
                        veu.device_imei_number,
                        veu.client_uid,
                        veu.veba_status,
                        veu.enabled_at,
                        veu.updated_at,
                        veu.enabled_by,
                        veu.notes,
                        ca.client_name
                    FROM dll_veba_enabled_units veu
                    LEFT JOIN dll_client_accounts ca ON veu.client_uid = ca.client_uid
                    WHERE veu.veba_status = 'unavailable'
                    ORDER BY ca.client_name, veu.device_imei_number
                """)

                units = cursor.fetchall()
                result = []
                for unit in units:
                    result.append({
                        "id": unit['id'],
                        "device_imei": unit['device_imei_number'],
                        "client_uid": unit['client_uid'],
                        "client_name": unit['client_name'],
                        "veba_status": unit['veba_status'],
                        "enabled_at": str(unit['enabled_at']) if unit['enabled_at'] else None,
                        "updated_at": str(unit['updated_at']) if unit['updated_at'] else None,
                        "enabled_by": unit['enabled_by'],
                        "notes": unit['notes']
                    })

                return response_out(
                    "success",
                    f"Found {len(result)} VEBA disabled units",
                    200,
                    {"count": len(result), "units": result}
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 4. VEBA Units Disabled by Client
@_statistics.route("/statistics/veba/units/disabled/<string:client_uid>", methods=["GET"])
def GetVEBAUnitsDisabledByClient(client_uid):
    """
    Get VEBA disabled units for a specific client.
    Disabled = veba_status is 'unavailable'
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Verify client exists
                cursor.execute(
                    "SELECT client_name FROM dll_client_accounts WHERE client_uid = %s",
                    (client_uid,)
                )
                client_record = cursor.fetchone()
                
                if not client_record:
                    return response_out("error", "Client not found", 404, {})
                
                client_name = client_record['client_name']

                cursor.execute("""
                    SELECT 
                        veu.id,
                        veu.device_imei_number,
                        veu.client_uid,
                        veu.veba_status,
                        veu.enabled_at,
                        veu.updated_at,
                        veu.enabled_by,
                        veu.notes
                    FROM dll_veba_enabled_units veu
                    WHERE veu.client_uid = %s
                      AND veu.veba_status = 'unavailable'
                    ORDER BY veu.device_imei_number
                """, (client_uid,))

                units = cursor.fetchall()
                result = []
                for unit in units:
                    result.append({
                        "id": unit['id'],
                        "device_imei": unit['device_imei_number'],
                        "client_uid": unit['client_uid'],
                        "client_name": client_name,
                        "veba_status": unit['veba_status'],
                        "enabled_at": str(unit['enabled_at']) if unit['enabled_at'] else None,
                        "updated_at": str(unit['updated_at']) if unit['updated_at'] else None,
                        "enabled_by": unit['enabled_by'],
                        "notes": unit['notes']
                    })

                return response_out(
                    "success",
                    f"Found {len(result)} VEBA disabled units for client",
                    200,
                    {
                        "client_uid": client_uid,
                        "client_name": client_name,
                        "count": len(result),
                        "units": result
                    }
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


#  GENERAL DATA STATISTICS APIs - Units Online/Offline


def get_device_online_status(cassandra_session, device_imei):
    """
    Check if a device is online based on its last heartbeat date from Cassandra.
    A device is considered online if last_heartbeat_date equals today's date.
    Uses dll_pulse_status_registry table from Cassandra.
    Returns tuple: (is_online, last_seen_timestamp, last_seen_datestamp)
    """
    try:
        # Get the latest heartbeat record for this device from Cassandra
        query = cassandra_session.prepare(
            "SELECT last_heartbeat_date, last_heartbeat_time FROM dll_pulse_status_registry WHERE device_data_imei = ? LIMIT 1"
        )
        rows = cassandra_session.execute(query, (device_imei,))
        row = rows.one()
        
        if not row:
            return False, None, None
        
        last_datestamp = row.last_heartbeat_date
        last_timestamp = row.last_heartbeat_time
        
        if not last_datestamp:
            return False, last_timestamp, last_datestamp
        
        try:
            # Get today's date
            today = datetime.now().date()
            
            # Parse last_heartbeat_date - try multiple formats
            last_date = None
            parse_error = None
            
            try:
                last_date = datetime.strptime(last_datestamp, "%d-%m-%Y").date()
            except ValueError as e1:
                try:
                    last_date = datetime.strptime(last_datestamp, "%Y-%m-%d").date()
                except ValueError as e2:
                    try:
                        last_date = datetime.strptime(last_datestamp, "%d/%m/%Y").date()
                    except ValueError as e3:
                        try:
                            last_date = datetime.strptime(last_datestamp, "%Y/%m/%d").date()
                        except ValueError as e4:
                            parse_error = f"All formats failed: {e1}, {e2}, {e3}, {e4}"
            
            if parse_error:
                print(f"[DEBUG] Device {device_imei}: Failed to parse date '{last_datestamp}' - {parse_error}")
                return False, last_timestamp, last_datestamp
            
            # Device is online if last heartbeat date equals today
            is_online = (last_date == today)
            
            # Debug logging
            print(f"[DEBUG] Device {device_imei}: last_date={last_date}, today={today}, is_online={is_online}, raw_date={last_datestamp}")
            
            return is_online, last_timestamp, last_datestamp
        except ValueError as e:
            # If parsing fails, consider device offline
            print(f"Error parsing date for device {device_imei}: {last_datestamp} - {e}")
            return False, last_timestamp, last_datestamp
            
    except Exception as e:
        print(f"Error checking online status for {device_imei}: {e}")
        return False, None, None


def get_all_configured_devices_with_clients(cassandra_session, pg_cursor):
    """
    Get all configured devices from Cassandra with their client information.
    Returns list of dicts with device_imei, device_name, client_uid, client_name
    """
    devices = []
    
    try:
        # Get all devices with their client associations from Cassandra
        query = cassandra_session.prepare(
            "SELECT device_imei, device_name, device_client FROM dll_device_basic_data"
        )
        rows = cassandra_session.execute(query)
        
        # Build a dict of client_uid -> client_name for efficiency
        client_cache = {}
        
        for row in rows:
            device_imei = row.device_imei
            device_name = row.device_name
            client_uid = row.device_client
            
            # Get client name (with caching)
            client_name = None
            if client_uid:
                if client_uid in client_cache:
                    client_name = client_cache[client_uid]
                else:
                    pg_cursor.execute(
                        "SELECT client_name FROM dll_client_accounts WHERE client_uid = %s",
                        (client_uid,)
                    )
                    client_record = pg_cursor.fetchone()
                    client_name = client_record['client_name'] if client_record else None
                    client_cache[client_uid] = client_name
            
            devices.append({
                'device_imei': device_imei,
                'device_name': device_name,
                'client_uid': client_uid,
                'client_name': client_name
            })
        
        return devices
        
    except Exception as e:
        print(f"Error getting configured devices: {e}")
        return []


def get_client_devices(cassandra_session, client_uid, pg_cursor):
    """
    Get all configured devices for a specific client.
    Returns list of dicts with device_imei, device_name, client_uid, client_name
    """
    devices = []
    
    try:
        # Get client name first
        pg_cursor.execute(
            "SELECT client_name FROM dll_client_accounts WHERE client_uid = %s",
            (client_uid,)
        )
        client_record = pg_cursor.fetchone()
        client_name = client_record['client_name'] if client_record else None
        
        # Get devices for this client from Cassandra
        query = cassandra_session.prepare(
            "SELECT device_imei, device_name FROM dll_device_basic_data WHERE device_client = ? ALLOW FILTERING"
        )
        rows = cassandra_session.execute(query, (client_uid,))
        
        for row in rows:
            devices.append({
                'device_imei': row.device_imei,
                'device_name': row.device_name,
                'client_uid': client_uid,
                'client_name': client_name
            })
        
        return devices, client_name
        
    except Exception as e:
        print(f"Error getting client devices: {e}")
        return [], None


# DEBUG ENDPOINT - Remove after testing
@_statistics.route("/statistics/debug/heartbeat/<string:device_imei>", methods=["GET"])
def DebugHeartbeat(device_imei):
    """
    Debug endpoint to check raw heartbeat data from Cassandra for a specific device.
    """
    cassandra_session = None
    try:
        cassandra_session = get_cassandra_session()
        
        if not cassandra_session:
            return response_out("error", "Failed to connect to Cassandra", 500, {})
        
        # Get raw heartbeat data
        query = cassandra_session.prepare(
            "SELECT last_heartbeat_date, last_heartbeat_time FROM dll_pulse_status_registry WHERE device_data_imei = ? LIMIT 1"
        )
        rows = cassandra_session.execute(query, (device_imei,))
        row = rows.one()
        
        if not row:
            return response_out("error", f"No heartbeat data found for device {device_imei}", 404, {})
        
        # Get today's date in various formats
        from datetime import datetime
        today = datetime.now()
        
        return response_out("success", "Heartbeat data retrieved", 200, {
            "device_imei": device_imei,
            "raw_heartbeat_date": str(row.last_heartbeat_date),
            "raw_heartbeat_time": str(row.last_heartbeat_time),
            "heartbeat_date_type": str(type(row.last_heartbeat_date)),
            "today_date": str(today.date()),
            "today_datetime": str(today),
            "comparison_formats": {
                "dd-mm-yyyy": today.strftime("%d-%m-%Y"),
                "yyyy-mm-dd": today.strftime("%Y-%m-%d"),
                "dd/mm/yyyy": today.strftime("%d/%m/%Y"),
                "yyyy/mm/dd": today.strftime("%Y/%m/%d")
            }
        })
        
    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})


# DEBUG ENDPOINT - Compare heartbeat devices vs configured devices
@_statistics.route("/statistics/debug/missing-devices", methods=["GET"])
def DebugMissingDevices():
    """
    Debug endpoint to find devices with heartbeats that aren't in device registry.
    Shows devices online today but missing from dll_device_basic_data.
    """
    cassandra_session = None
    try:
        cassandra_session = get_cassandra_session()
        
        if not cassandra_session:
            return response_out("error", "Failed to connect to Cassandra", 500, {})
        
        # Today's date
        today = datetime.now().strftime("%d-%m-%Y")
        
        # Get all devices with heartbeats today
        query1 = cassandra_session.prepare(
            "SELECT device_data_imei FROM dll_pulse_status_registry WHERE last_heartbeat_date = ? ALLOW FILTERING"
        )
        heartbeat_rows = cassandra_session.execute(query1, (today,))
        heartbeat_devices = set([row.device_data_imei for row in heartbeat_rows])
        
        # Get all configured devices
        query2 = cassandra_session.prepare(
            "SELECT device_imei FROM dll_device_basic_data"
        )
        configured_rows = cassandra_session.execute(query2)
        configured_devices = set([row.device_imei for row in configured_rows])
        
        # Find missing devices
        missing_devices = heartbeat_devices - configured_devices
        matched_devices = heartbeat_devices & configured_devices
        
        return response_out("success", "Device comparison complete", 200, {
            "today": today,
            "total_with_heartbeat_today": len(heartbeat_devices),
            "total_configured_devices": len(configured_devices),
            "devices_in_both": len(matched_devices),
            "devices_missing_from_registry": len(missing_devices),
            "missing_device_list": sorted(list(missing_devices))[:20],  # Show first 20
            "note": f"Showing first 20 of {len(missing_devices)} missing devices" if len(missing_devices) > 20 else None
        })
        
    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})



@_statistics.route("/statistics/units/online", methods=["GET"])
def GetUnitsOnlineWholeSystem():
    """
    Get all online units across the whole system.
    A unit is considered online if last_heartbeat_date equals today's date.
    """
    dbconnect = None
    cassandra_session = None
    
    try:
        # Connect to databases
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        cassandra_session = get_cassandra_session()
        
        if not cassandra_session:
            return response_out("error", "Failed to connect to Cassandra", 500, {})
        
        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get all configured devices
                devices = get_all_configured_devices_with_clients(cassandra_session, cursor)
                
                online_units = []
                
                for device in devices:
                    is_online, last_timestamp, last_datestamp = get_device_online_status(
                        cassandra_session, device['device_imei']
                    )
                    
                    if is_online:
                        online_units.append({
                            "device_imei": device['device_imei'],
                            "device_name": device['device_name'],
                            "client_uid": device['client_uid'],
                            "client_name": device['client_name'],
                            "last_seen_timestamp": last_timestamp,
                            "last_seen_datestamp": last_datestamp,
                            "status": "online"
                        })
                
                return response_out(
                    "success",
                    f"Found {len(online_units)} online units",
                    200,
                    {
                        "count": len(online_units),
                        "total_configured_units": len(devices),
                        "criteria": "last_heartbeat_date equals today",
                        "units": online_units
                    }
                )
    
    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 2. Units Online By Client
@_statistics.route("/statistics/units/online/<string:client_uid>", methods=["GET"])
def GetUnitsOnlineByClient(client_uid):
    """
    Get online units for a specific client.
    A unit is considered online if last_heartbeat_date equals today's date.
    """
    dbconnect = None
    cassandra_session = None
    
    try:
        # Connect to databases
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        cassandra_session = get_cassandra_session()
        
        if not cassandra_session:
            return response_out("error", "Failed to connect to Cassandra", 500, {})
        
        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get devices for this client
                devices, client_name = get_client_devices(cassandra_session, client_uid, cursor)
                
                if not client_name:
                    return response_out("error", "Client not found", 404, {})
                
                online_units = []
                
                for device in devices:
                    is_online, last_timestamp, last_datestamp = get_device_online_status(
                        cassandra_session, device['device_imei']
                    )
                    
                    if is_online:
                        online_units.append({
                            "device_imei": device['device_imei'],
                            "device_name": device['device_name'],
                            "client_uid": device['client_uid'],
                            "client_name": device['client_name'],
                            "last_seen_timestamp": last_timestamp,
                            "last_seen_datestamp": last_datestamp,
                            "status": "online"
                        })
                
                return response_out(
                    "success",
                    f"Found {len(online_units)} online units for client",
                    200,
                    {
                        "client_uid": client_uid,
                        "client_name": client_name,
                        "count": len(online_units),
                        "total_client_units": len(devices),
                        "criteria": "last_heartbeat_date equals today",
                        "units": online_units
                    }
                )
    
    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 3. Total Units Offline - Whole System
@_statistics.route("/statistics/units/offline", methods=["GET"])
def GetUnitsOfflineWholeSystem():
    """
    Get all offline units across the whole system.
    A unit is considered offline if last_heartbeat_date does NOT equal today's date.
    """
    dbconnect = None
    cassandra_session = None
    
    try:
        # Connect to databases
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        cassandra_session = get_cassandra_session()
        
        if not cassandra_session:
            return response_out("error", "Failed to connect to Cassandra", 500, {})
        
        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get all configured devices
                devices = get_all_configured_devices_with_clients(cassandra_session, cursor)
                
                offline_units = []
                
                for device in devices:
                    is_online, last_timestamp, last_datestamp = get_device_online_status(
                        cassandra_session, device['device_imei']
                    )
                    
                    if not is_online:
                        offline_units.append({
                            "device_imei": device['device_imei'],
                            "device_name": device['device_name'],
                            "client_uid": device['client_uid'],
                            "client_name": device['client_name'],
                            "last_seen_timestamp": last_timestamp,
                            "last_seen_datestamp": last_datestamp,
                            "status": "offline"
                        })
                
                return response_out(
                    "success",
                    f"Found {len(offline_units)} offline units",
                    200,
                    {
                        "count": len(offline_units),
                        "total_configured_units": len(devices),
                        "criteria": "last_heartbeat_date not equal to today",
                        "units": offline_units
                    }
                )
    
    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 4. Units Offline By Client
@_statistics.route("/statistics/units/offline/<string:client_uid>", methods=["GET"])
def GetUnitsOfflineByClient(client_uid):
    """
    Get offline units for a specific client.
    A unit is considered offline if last_heartbeat_date does NOT equal today's date.
    """
    dbconnect = None
    cassandra_session = None
    
    try:
        # Connect to databases
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        cassandra_session = get_cassandra_session()
        
        if not cassandra_session:
            return response_out("error", "Failed to connect to Cassandra", 500, {})
        
        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get devices for this client
                devices, client_name = get_client_devices(cassandra_session, client_uid, cursor)
                
                if not client_name:
                    return response_out("error", "Client not found", 404, {})
                
                offline_units = []
                
                for device in devices:
                    is_online, last_timestamp, last_datestamp = get_device_online_status(
                        cassandra_session, device['device_imei']
                    )
                    
                    if not is_online:
                        offline_units.append({
                            "device_imei": device['device_imei'],
                            "device_name": device['device_name'],
                            "client_uid": device['client_uid'],
                            "client_name": device['client_name'],
                            "last_seen_timestamp": last_timestamp,
                            "last_seen_datestamp": last_datestamp,
                            "status": "offline"
                        })
                
                return response_out(
                    "success",
                    f"Found {len(offline_units)} offline units for client",
                    200,
                    {
                        "client_uid": client_uid,
                        "client_name": client_name,
                        "count": len(offline_units),
                        "total_client_units": len(devices),
                        "criteria": "last_heartbeat_date not equal to today",
                        "units": offline_units
                    }
                )
    
    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# ============================================================================
#  SIM CARD STATISTICS
# ============================================================================

@_statistics.route("/statistics/sims/summary", methods=["GET"])
def GetSimCardsSummary():
    """
    Get comprehensive SIM card statistics across all clients.
    Returns counts for active, in-stock, inactive, and used SIMs.
    
    Statuses:
    - active: Assigned and operational
    - in-stock: Purchased, not assigned
    - inactive: Disabled/suspended
    - used: Consumed/depleted (if prepaid)
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get counts for each status
                cursor.execute("""
                    SELECT 
                        usage_status,
                        COUNT(*) as count
                    FROM dll_telecom_assets
                    GROUP BY usage_status
                """)
                
                status_counts = cursor.fetchall()
                
                # Initialize counters
                active_count = 0
                in_stock_count = 0
                inactive_count = 0
                used_count = 0
                other_count = 0
                total_count = 0
                
                # Process results
                for row in status_counts:
                    status = row['usage_status']
                    count = row['count']
                    total_count += count
                    
                    if status == 'active':
                        active_count = count
                    elif status == 'in-stock':
                        in_stock_count = count
                    elif status == 'inactive':
                        inactive_count = count
                    elif status == 'used':
                        used_count = count
                    else:
                        other_count += count
                
                # Calculate percentage of available (in-stock) SIMs
                open_percentage = round((in_stock_count / total_count * 100), 2) if total_count > 0 else 0
                
                return response_out(
                    "success",
                    f"SIM card statistics retrieved successfully",
                    200,
                    {
                        "total_sims": total_count,
                        "active": active_count,
                        "in_stock": in_stock_count,
                        "inactive": inactive_count,
                        "used": used_count,
                        "other": other_count,
                        "open_percentage": open_percentage
                    }
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


@_statistics.route("/statistics/sims/summary/<string:client_uid>", methods=["GET"])
def GetSimCardsSummaryByClient(client_uid):
    """
    Get comprehensive SIM card statistics for a specific client.
    Returns counts for active, in-stock, inactive, and used SIMs filtered by owner or owner_parent.
    
    Args:
        client_uid: The client UID to filter SIMs by (checks both asset_owner and asset_owner_parent)
    
    Statuses:
    - active: Assigned and operational
    - in-stock: Purchased, not assigned
    - inactive: Disabled/suspended
    - used: Consumed/depleted (if prepaid)
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get client name
                cursor.execute("""
                    SELECT client_name FROM dll_client_accounts WHERE client_uid = %s
                """, (client_uid,))
                
                client_result = cursor.fetchone()
                client_name = client_result['client_name'] if client_result else None
                
                if not client_name:
                    return response_out("error", "Client not found", 404, {})
                
                # Get counts for each status filtered by client
                cursor.execute("""
                    SELECT 
                        usage_status,
                        COUNT(*) as count
                    FROM dll_telecom_assets
                    WHERE asset_owner = %s OR owner_parent = %s
                    GROUP BY usage_status
                """, (client_uid, client_uid))
                
                status_counts = cursor.fetchall()
                
                # Initialize counters
                active_count = 0
                in_stock_count = 0
                inactive_count = 0
                used_count = 0
                other_count = 0
                total_count = 0
                
                # Process results
                for row in status_counts:
                    status = row['usage_status']
                    count = row['count']
                    total_count += count
                    
                    if status == 'active':
                        active_count = count
                    elif status == 'in-stock':
                        in_stock_count = count
                    elif status == 'inactive':
                        inactive_count = count
                    elif status == 'used':
                        used_count = count
                    else:
                        other_count += count
                
                # Calculate percentage of available (in-stock) SIMs
                open_percentage = round((in_stock_count / total_count * 100), 2) if total_count > 0 else 0
                
                return response_out(
                    "success",
                    f"SIM card statistics retrieved successfully for client",
                    200,
                    {
                        "client_uid": client_uid,
                        "client_name": client_name,
                        "total_sims": total_count,
                        "active": active_count,
                        "in_stock": in_stock_count,
                        "inactive": inactive_count,
                        "used": used_count,
                        "other": other_count,
                        "open_percentage": open_percentage
                    }
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# BILLING MODULE ENDPOINTS


# 1. Clients with High Token Subscriptions
@_statistics.route("/statistics/clients/high-subscriptions", methods=["GET"])
def GetClientsWithHighSubscriptions():
    """
    Get clients ranked by number of active device subscriptions.
    Returns clients ordered by subscription count (highest first).
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        ds.service_provider AS client_uid,
                        ca.client_name,
                        ca.client_email,
                        COUNT(ds.device_imei_number) AS total_subscriptions,
                        COUNT(CASE WHEN ds.subscription_status = 'active' THEN 1 END) AS active_subscriptions,
                        COUNT(CASE WHEN ds.subscription_status = 'paused' THEN 1 END) AS paused_subscriptions,
                        COUNT(CASE WHEN ds.subscription_status = 'expired' THEN 1 END) AS expired_subscriptions
                    FROM dll_device_subscriptions ds
                    LEFT JOIN dll_client_accounts ca ON ds.service_provider = ca.client_uid
                    GROUP BY ds.service_provider, ca.client_name, ca.client_email
                    ORDER BY total_subscriptions DESC, active_subscriptions DESC
                """)

                clients = cursor.fetchall()
                result = []
                
                for client in clients:
                    result.append({
                        "client_uid": str(client['client_uid']) if client['client_uid'] else None,
                        "client_name": client['client_name'],
                        "client_email": client['client_email'],
                        "total_subscriptions": int(client['total_subscriptions']),
                        "active_subscriptions": int(client['active_subscriptions']),
                        "paused_subscriptions": int(client['paused_subscriptions']),
                        "expired_subscriptions": int(client['expired_subscriptions'])
                    })

                return response_out(
                    "success",
                    f"Found {len(result)} clients ranked by subscription count",
                    200,
                    {"count": len(result), "clients": result}
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 2. Paused Token Subscriptions
@_statistics.route("/statistics/tokens/paused", methods=["GET"])
def GetPausedTokenSubscriptions():
    """
    Get all paused token subscriptions with device and client details.
    Returns count and list of paused subscriptions.
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        ds.device_imei_number,
                        ds.service_provider AS client_uid,
                        ds.subscription_status,
                        ds.start_date,
                        ds.token_billing_uid,
                        ca.client_name,
                        ca.client_email,
                        uta.token_balance AS token_id,
                        uta.token_hours_left,
                        uta.token_hours_used,
                        tr.token_name,
                        tr.token_type,
                        tr.token_currency
                    FROM dll_device_subscriptions ds
                    LEFT JOIN dll_client_accounts ca ON ds.service_provider = ca.client_uid
                    LEFT JOIN dll_user_token_accounts uta ON ds.token_billing_uid = uta.token_billing_uid
                    LEFT JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    WHERE ds.subscription_status = 'paused'
                    ORDER BY ca.client_name, ds.device_imei_number
                """)

                paused_subscriptions = cursor.fetchall()
                result = []
                
                for sub in paused_subscriptions:
                    result.append({
                        "device_imei": str(sub['device_imei_number']) if sub['device_imei_number'] else None,
                        "client_uid": str(sub['client_uid']) if sub['client_uid'] else None,
                        "client_name": sub['client_name'],
                        "client_email": sub['client_email'],
                        "subscription_status": sub['subscription_status'],
                        "start_date": str(sub['start_date']) if sub['start_date'] else None,
                        "token_billing_uid": str(sub['token_billing_uid']) if sub['token_billing_uid'] else None,
                        "token_id": str(sub['token_id']) if sub['token_id'] else None,
                        "token_name": sub['token_name'],
                        "token_type": sub['token_type'],
                        "token_currency": sub['token_currency'],
                        "token_hours_left": float(sub['token_hours_left']) if sub['token_hours_left'] else 0,
                        "token_hours_used": float(sub['token_hours_used']) if sub['token_hours_used'] else 0
                    })

                return response_out(
                    "success",
                    f"Found {len(result)} paused token subscriptions",
                    200,
                    {"count": len(result), "subscriptions": result}
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 3. Top Spenders - Identify Valuable Customers
@_statistics.route("/billing/clients/top-spenders", methods=["GET"])
def GetTopSpendingClients():
    """
    Get clients ranked by total spending (successful payments only).
    Returns top clients by revenue contribution.
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        pl.payment_account AS client_uid,
                        ca.client_name,
                        ca.client_email,
                        pl.payment_currency,
                        COUNT(pl.payment_uid) AS total_transactions,
                        SUM(pl.total_cost::numeric) AS total_spent,
                        AVG(pl.total_cost::numeric) AS avg_transaction_value,
                        MAX(pl.payment_date) AS last_payment_date,
                        COUNT(CASE WHEN pl.payment_status = 'success' THEN 1 END) AS successful_payments,
                        COUNT(CASE WHEN pl.payment_status = 'pending' THEN 1 END) AS pending_payments,
                        COUNT(CASE WHEN pl.payment_status = 'failed' THEN 1 END) AS failed_payments
                    FROM dll_payment_logs pl
                    LEFT JOIN dll_client_accounts ca ON pl.payment_account = ca.client_uid
                    WHERE pl.payment_status = 'success'
                    GROUP BY pl.payment_account, ca.client_name, ca.client_email, pl.payment_currency
                    ORDER BY total_spent DESC
                    LIMIT 50
                """)

                clients = cursor.fetchall()
                result = []
                
                for client in clients:
                    result.append({
                        "client_uid": str(client['client_uid']) if client['client_uid'] else None,
                        "client_name": client['client_name'],
                        "client_email": client['client_email'],
                        "currency": client['payment_currency'],
                        "total_spent": float(client['total_spent']) if client['total_spent'] else 0,
                        "total_transactions": int(client['total_transactions']),
                        "avg_transaction_value": round(float(client['avg_transaction_value']), 2) if client['avg_transaction_value'] else 0,
                        "last_payment_date": str(client['last_payment_date']) if client['last_payment_date'] else None,
                        "successful_payments": int(client['successful_payments']),
                        "pending_payments": int(client['pending_payments']),
                        "failed_payments": int(client['failed_payments'])
                    })

                return response_out(
                    "success",
                    f"Found {len(result)} top-spending clients",
                    200,
                    {"count": len(result), "clients": result}
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 4. Active Token Inventory Value
@_statistics.route("/billing/tokens/active-value", methods=["GET"])
def GetActiveTokenValue():
    """
    Calculate total monetary value of active tokens in circulation.
    Shows token inventory value and utilization metrics.
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get aggregate value of all active tokens
                cursor.execute("""
                    SELECT 
                        tr.token_currency,
                        COUNT(DISTINCT uta.token_billing_uid) AS active_accounts,
                        SUM(uta.token_hours_left::numeric) AS total_hours_remaining,
                        SUM(uta.token_hours_used::numeric) AS total_hours_consumed,
                        SUM(tr.token_amount::numeric) AS total_token_value,
                        AVG(uta.token_hours_left::numeric) AS avg_hours_remaining,
                        COUNT(DISTINCT uta.client_uid) AS unique_clients
                    FROM dll_user_token_accounts uta
                    JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    WHERE uta.token_status = 'active'
                      AND LOWER(tr.token_type) != 'veba'
                    GROUP BY tr.token_currency
                """)

                currency_summary = cursor.fetchall()
                
                # Get token type breakdown
                cursor.execute("""
                    SELECT 
                        tr.token_type,
                        tr.token_name,
                        tr.token_currency,
                        COUNT(uta.token_billing_uid) AS active_count,
                        SUM(tr.token_amount::numeric) AS total_value,
                        AVG(uta.token_hours_left::numeric) AS avg_hours_left
                    FROM dll_user_token_accounts uta
                    JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    WHERE uta.token_status = 'active'
                      AND LOWER(tr.token_type) != 'veba'
                    GROUP BY tr.token_type, tr.token_name, tr.token_currency
                    ORDER BY total_value DESC
                """)

                token_breakdown = cursor.fetchall()

                result = {
                    "summary_by_currency": [],
                    "token_breakdown": []
                }
                
                for currency in currency_summary:
                    result["summary_by_currency"].append({
                        "currency": currency['token_currency'],
                        "active_accounts": int(currency['active_accounts']),
                        "unique_clients": int(currency['unique_clients']),
                        "total_value": float(currency['total_token_value']) if currency['total_token_value'] else 0,
                        "total_hours_remaining": float(currency['total_hours_remaining']) if currency['total_hours_remaining'] else 0,
                        "total_hours_consumed": float(currency['total_hours_consumed']) if currency['total_hours_consumed'] else 0,
                        "avg_hours_remaining": round(float(currency['avg_hours_remaining']), 2) if currency['avg_hours_remaining'] else 0
                    })
                
                for token in token_breakdown:
                    result["token_breakdown"].append({
                        "token_type": token['token_type'],
                        "token_name": token['token_name'],
                        "currency": token['token_currency'],
                        "active_count": int(token['active_count']),
                        "total_value": float(token['total_value']) if token['total_value'] else 0,
                        "avg_hours_left": round(float(token['avg_hours_left']), 2) if token['avg_hours_left'] else 0
                    })

                return response_out(
                    "success",
                    "Token inventory value calculated successfully",
                    200,
                    result
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 5. Low Balance Alerts - Proactive Customer Notifications
@_statistics.route("/billing/tokens/low-balance", methods=["GET"])
def GetLowBalanceAccounts():
    """
    Get token accounts with critically low balance (< 24 hours remaining).
    For proactive customer alerts and renewal campaigns.
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        uta.token_billing_uid,
                        uta.client_uid,
                        ca.client_name,
                        ca.client_email,
                        uta.token_balance AS token_id,
                        uta.token_hours_left,
                        uta.token_hours_used,
                        uta.token_status,
                        tr.token_name,
                        tr.token_type,
                        tr.token_currency,
                        tr.token_amount,
                        tr.token_validity,
                        COUNT(ds.device_imei_number) AS active_devices
                    FROM dll_user_token_accounts uta
                    JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    LEFT JOIN dll_client_accounts ca ON uta.client_uid = ca.client_uid
                    LEFT JOIN dll_device_subscriptions ds ON uta.token_billing_uid = ds.token_billing_uid 
                        AND ds.subscription_status = 'active'
                    WHERE uta.token_status = 'active'
                      AND uta.token_hours_left::numeric < 24
                      AND uta.token_hours_left::numeric > 0
                      AND LOWER(tr.token_type) != 'veba'
                    GROUP BY uta.token_billing_uid, uta.client_uid, ca.client_name, ca.client_email,
                             uta.token_balance, uta.token_hours_left, uta.token_hours_used, uta.token_status,
                             tr.token_name, tr.token_type, tr.token_currency, tr.token_amount, tr.token_validity
                    ORDER BY uta.token_hours_left::numeric ASC
                """)

                low_balance_accounts = cursor.fetchall()
                result = []
                
                for account in low_balance_accounts:
                    hours_left = float(account['token_hours_left']) if account['token_hours_left'] else 0
                    urgency_level = "critical" if hours_left < 6 else "high" if hours_left < 12 else "medium"
                    
                    result.append({
                        "token_billing_uid": str(account['token_billing_uid']) if account['token_billing_uid'] else None,
                        "client_uid": str(account['client_uid']) if account['client_uid'] else None,
                        "client_name": account['client_name'],
                        "client_email": account['client_email'],
                        "token_id": str(account['token_id']) if account['token_id'] else None,
                        "token_name": account['token_name'],
                        "token_type": account['token_type'],
                        "token_currency": account['token_currency'],
                        "token_amount": float(account['token_amount']) if account['token_amount'] else 0,
                        "token_validity": account['token_validity'],
                        "hours_remaining": hours_left,
                        "hours_used": float(account['token_hours_used']) if account['token_hours_used'] else 0,
                        "active_devices": int(account['active_devices']),
                        "urgency_level": urgency_level
                    })

                return response_out(
                    "success",
                    f"Found {len(result)} accounts with low balance (< 24 hours)",
                    200,
                    {"count": len(result), "accounts": result}
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 6. Expiring Subscriptions - Renewal Pipeline
@_statistics.route("/billing/subscriptions/expiring", methods=["GET"])
def GetExpiringSubscriptions():
    """
    Get device subscriptions expiring within the next 30 days.
    Supports renewal pipeline and customer retention.
    Optional query param: days (default: 30)
    """
    dbconnect = None
    try:
        from flask import request
        days_ahead = request.args.get('days', 30, type=int)
        
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT 
                        ds.device_imei_number,
                        ds.service_provider AS client_uid,
                        ds.subscription_status,
                        ds.start_date,
                        ds.token_billing_uid,
                        ca.client_name,
                        ca.client_email,
                        uta.token_balance AS token_id,
                        tr.token_name,
                        tr.token_type,
                        tr.token_currency,
                        tr.token_amount,
                        CASE 
                            WHEN uta.token_hours_left::numeric > 0 
                            THEN FLOOR(uta.token_hours_left::numeric / 24)::integer
                            ELSE 0
                        END AS days_until_expiry
                    FROM dll_device_subscriptions ds
                    LEFT JOIN dll_client_accounts ca ON ds.service_provider = ca.client_uid
                    LEFT JOIN dll_user_token_accounts uta ON ds.token_billing_uid = uta.token_billing_uid
                    LEFT JOIN dll_tokens_registry tr ON uta.token_balance = tr.token_id
                    WHERE ds.subscription_status = 'active'
                      AND uta.token_hours_left::numeric > 0
                      AND uta.token_hours_left::numeric <= (%s * 24)
                    ORDER BY days_until_expiry ASC, ca.client_name
                """, (days_ahead,))

                expiring_subs = cursor.fetchall()
                result = []
                
                for sub in expiring_subs:
                    days_left = int(sub['days_until_expiry']) if sub['days_until_expiry'] else 0
                    urgency = "immediate" if days_left <= 7 else "high" if days_left <= 14 else "medium"
                    
                    result.append({
                        "device_imei": str(sub['device_imei_number']) if sub['device_imei_number'] else None,
                        "client_uid": str(sub['client_uid']) if sub['client_uid'] else None,
                        "client_name": sub['client_name'],
                        "client_email": sub['client_email'],
                        "subscription_status": sub['subscription_status'],
                        "start_date": str(sub['start_date']) if sub['start_date'] else None,
                        "days_until_expiry": days_left,
                        "urgency": urgency,
                        "token_billing_uid": str(sub['token_billing_uid']) if sub['token_billing_uid'] else None,
                        "token_id": str(sub['token_id']) if sub['token_id'] else None,
                        "token_name": sub['token_name'],
                        "token_type": sub['token_type'],
                        "token_currency": sub['token_currency'],
                        "renewal_amount": float(sub['token_amount']) if sub['token_amount'] else 0
                    })

                return response_out(
                    "success",
                    f"Found {len(result)} subscriptions expiring within {days_ahead} days",
                    200,
                    {"count": len(result), "days_ahead": days_ahead, "subscriptions": result}
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 7. Revenue Summary - Executive Dashboard
@_statistics.route("/billing/revenue/summary", methods=["GET"])
def GetRevenueSummary():
    """
    Get comprehensive revenue analytics and financial metrics.
    Includes totals, trends, and payment method breakdown.
    Optional query params: period (today|week|month|year|all)
    """
    dbconnect = None
    try:
        from flask import request
        period = request.args.get('period', 'all', type=str).lower()
        
        # Determine date filter
        date_filter = ""
        if period == 'today':
            date_filter = "AND pl.payment_date::date = CURRENT_DATE"
        elif period == 'week':
            date_filter = "AND pl.payment_date::date >= CURRENT_DATE - INTERVAL '7 days'"
        elif period == 'month':
            date_filter = "AND pl.payment_date::date >= CURRENT_DATE - INTERVAL '30 days'"
        elif period == 'year':
            date_filter = "AND pl.payment_date::date >= CURRENT_DATE - INTERVAL '365 days'"
        
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Overall revenue metrics
                cursor.execute(f"""
                    SELECT 
                        pl.payment_currency,
                        COUNT(pl.payment_uid) AS total_transactions,
                        COUNT(CASE WHEN pl.payment_status = 'success' THEN 1 END) AS successful_transactions,
                        COUNT(CASE WHEN pl.payment_status = 'pending' THEN 1 END) AS pending_transactions,
                        COUNT(CASE WHEN pl.payment_status = 'failed' THEN 1 END) AS failed_transactions,
                        SUM(CASE WHEN pl.payment_status = 'success' THEN pl.total_cost::numeric ELSE 0 END) AS total_revenue,
                        AVG(CASE WHEN pl.payment_status = 'success' THEN pl.total_cost::numeric END) AS avg_transaction_value,
                        MAX(CASE WHEN pl.payment_status = 'success' THEN pl.total_cost::numeric END) AS max_transaction,
                        MIN(CASE WHEN pl.payment_status = 'success' THEN pl.total_cost::numeric END) AS min_transaction,
                        COUNT(DISTINCT pl.payment_account) AS unique_customers
                    FROM dll_payment_logs pl
                    WHERE 1=1 {date_filter}
                    GROUP BY pl.payment_currency
                """)

                revenue_by_currency = cursor.fetchall()
                
                # Daily revenue trend (last 30 days)
                cursor.execute(f"""
                    SELECT 
                        pl.payment_date,
                        pl.payment_currency,
                        COUNT(pl.payment_uid) AS transactions,
                        SUM(CASE WHEN pl.payment_status = 'success' THEN pl.total_cost::numeric ELSE 0 END) AS revenue
                    FROM dll_payment_logs pl
                    WHERE pl.payment_date::date >= CURRENT_DATE - INTERVAL '30 days'
                    GROUP BY pl.payment_date, pl.payment_currency
                    ORDER BY pl.payment_date DESC
                    LIMIT 30
                """)

                daily_trend = cursor.fetchall()
                
                # Token package revenue breakdown
                cursor.execute(f"""
                    SELECT 
                        pl.token_number AS token_id,
                        tr.token_name,
                        tr.token_type,
                        pl.payment_currency,
                        COUNT(pl.payment_uid) AS purchases,
                        SUM(CASE WHEN pl.payment_status = 'success' THEN pl.total_cost::numeric ELSE 0 END) AS revenue
                    FROM dll_payment_logs pl
                    LEFT JOIN dll_tokens_registry tr ON pl.token_number = tr.token_id
                    WHERE pl.payment_status = 'success' {date_filter}
                    GROUP BY pl.token_number, tr.token_name, tr.token_type, pl.payment_currency
                    ORDER BY revenue DESC
                """)

                token_revenue = cursor.fetchall()

                result = {
                    "period": period,
                    "summary_by_currency": [],
                    "daily_trend": [],
                    "token_performance": []
                }
                
                for currency in revenue_by_currency:
                    success_rate = (int(currency['successful_transactions']) / int(currency['total_transactions']) * 100) if currency['total_transactions'] > 0 else 0
                    
                    result["summary_by_currency"].append({
                        "currency": currency['payment_currency'],
                        "total_revenue": float(currency['total_revenue']) if currency['total_revenue'] else 0,
                        "total_transactions": int(currency['total_transactions']),
                        "successful_transactions": int(currency['successful_transactions']),
                        "pending_transactions": int(currency['pending_transactions']),
                        "failed_transactions": int(currency['failed_transactions']),
                        "success_rate": round(success_rate, 2),
                        "avg_transaction_value": round(float(currency['avg_transaction_value']), 2) if currency['avg_transaction_value'] else 0,
                        "max_transaction": float(currency['max_transaction']) if currency['max_transaction'] else 0,
                        "min_transaction": float(currency['min_transaction']) if currency['min_transaction'] else 0,
                        "unique_customers": int(currency['unique_customers'])
                    })
                
                for day in daily_trend:
                    result["daily_trend"].append({
                        "date": str(day['payment_date']) if day['payment_date'] else None,
                        "currency": day['payment_currency'],
                        "transactions": int(day['transactions']),
                        "revenue": float(day['revenue']) if day['revenue'] else 0
                    })
                
                for token in token_revenue:
                    result["token_performance"].append({
                        "token_id": str(token['token_id']) if token['token_id'] else None,
                        "token_name": token['token_name'],
                        "token_type": token['token_type'],
                        "currency": token['payment_currency'],
                        "purchases": int(token['purchases']),
                        "revenue": float(token['revenue']) if token['revenue'] else 0
                    })

                return response_out(
                    "success",
                    f"Revenue summary generated for period: {period}",
                    200,
                    result
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


# 8. Client Dashboard Statistics Cards
@_statistics.route("/statistics/clients/overview", methods=["GET"])
def GetClientOverviewStats():
    """
    Get overview statistics for the TenantTower dashboard cards.
    Returns: total clients, total subscriptions, expired subscription clients.
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Total active clients
                cursor.execute("""
                    SELECT COUNT(*) AS total_clients
                    FROM dll_client_accounts
                    WHERE is_deleted = FALSE OR is_deleted IS NULL
                """)
                total_clients = cursor.fetchone()['total_clients']

                # Total subscriptions (all token accounts)
                cursor.execute("""
                    SELECT COUNT(*) AS total_subscriptions
                    FROM dll_user_token_accounts
                """)
                total_subscriptions = cursor.fetchone()['total_subscriptions']

                # Clients with all subscriptions expired (no active ones remaining)
                cursor.execute("""
                    SELECT COUNT(DISTINCT uta.client_uid) AS expired_clients
                    FROM dll_user_token_accounts uta
                    WHERE uta.token_status = 'expired'
                      AND NOT EXISTS (
                          SELECT 1 FROM dll_user_token_accounts active
                          WHERE active.client_uid = uta.client_uid
                            AND active.token_status = 'active'
                      )
                """)
                expired_clients = cursor.fetchone()['expired_clients']

                return response_out(
                    "success",
                    "Client overview statistics retrieved",
                    200,
                    {
                        "total_clients": int(total_clients),
                        "total_subscriptions": int(total_subscriptions),
                        "expired_subscription_clients": int(expired_clients)
                    }
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()
