from flask import Blueprint, jsonify, current_app, request
import psycopg2
import psycopg2.extras
from datetime import datetime

gateways_bp = Blueprint("Gateways", __name__)

def response_out(status, message, statusCode, data):
    return jsonify({
        "status": status,
        "message": message,
        "data": data
    }), statusCode


@gateways_bp.route("/gateways/mobile-money", methods=["GET"])
def GetMobileMoneyGatewayStatus():
    """
    Get current status for all mobile money payment gateways.
    
    Returns:
        - Gateway name (telecom)
        - Status (OK, DEGRADED, DOWN, MAINTENANCE)
        - Message with metrics
        - Severity level (green, alarm, critical)
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get current status for all gateways
                cursor.execute("""
                    SELECT 
                        id,
                        telecom,
                        api_status,
                        message,
                        created_at,
                        updated_at
                    FROM dll_gateway_status
                    WHERE is_current_message = TRUE
                    ORDER BY telecom
                """)
                
                gateways = cursor.fetchall()
                
                # Format response for frontend
                gateway_list = []
                for gw in gateways:
                    # Determine severity based on status
                    status = gw['api_status']
                    if status == 'DOWN':
                        severity = 'critical'
                    elif status == 'DEGRADED':
                        severity = 'alarm'
                    else:
                        severity = 'green'
                    
                    gateway_list.append({
                        "id": gw['id'],
                        "name": gw['telecom'],
                        "status": gw['api_status'],
                        "meta": gw['message'] or 'Monitoring',
                        "sev": severity,
                        "updated_at": gw['updated_at'].isoformat() if gw['updated_at'] else None
                    })
                
                return response_out(
                    "success",
                    f"Retrieved status for {len(gateway_list)} mobile money gateways",
                    200,
                    {
                        "gateways": gateway_list,
                        "total_count": len(gateway_list),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


@gateways_bp.route("/gateways/mobile-money/<string:telecom_name>", methods=["GET"])
def GetGatewayHistory(telecom_name):
    """
    Get status history for a specific gateway.
    
    Args:
        telecom_name: Gateway name (e.g., 'M-Pesa KE', 'MTN MoMo UG')
    
    Returns:
        Current and historical status messages for the gateway
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get all status records for this gateway
                cursor.execute("""
                    SELECT 
                        id,
                        telecom,
                        api_status,
                        message,
                        is_current_message,
                        created_at,
                        updated_at
                    FROM dll_gateway_status
                    WHERE telecom = %s
                    ORDER BY created_at DESC
                    LIMIT 50
                """, (telecom_name,))
                
                history = cursor.fetchall()
                
                if not history:
                    return response_out("error", f"Gateway '{telecom_name}' not found", 404, {})
                
                # Get current status
                current = next((h for h in history if h['is_current_message']), None)
                
                return response_out(
                    "success",
                    f"Retrieved history for gateway '{telecom_name}'",
                    200,
                    {
                        "gateway_name": telecom_name,
                        "current_status": dict(current) if current else None,
                        "history": [dict(h) for h in history],
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )

    except Exception as e:
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()


@gateways_bp.route("/gateways/mobile-money/update", methods=["POST"])
def UpdateGatewayStatus():
    """
    Update status for a mobile money gateway.
    
    Request body:
        {
            "telecom": "M-Pesa KE",
            "api_status": "OK",
            "message": "success 98.9% • p95 9.2s"
        }
    
    This will:
    - Mark the current message as historical (is_current_message = FALSE)
    - Insert new status as current (is_current_message = TRUE)
    """
    dbconnect = None
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload = request.get_json()
        
        telecom = payload.get('telecom')
        api_status = payload.get('api_status')
        message = payload.get('message')
        
        if not telecom or not api_status:
            return response_out("error", "Missing required fields: telecom, api_status", 400, {})

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Mark existing current message as historical
                cursor.execute("""
                    UPDATE dll_gateway_status
                    SET is_current_message = FALSE,
                        updated_at = NOW()
                    WHERE telecom = %s
                    AND is_current_message = TRUE
                """, (telecom,))
                
                # Insert new current message
                cursor.execute("""
                    INSERT INTO dll_gateway_status (
                        telecom, api_status, message, is_current_message, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, TRUE, NOW(), NOW()
                    )
                    RETURNING id, telecom, api_status, message, created_at
                """, (telecom, api_status, message))
                
                result = cursor.fetchone()
                dbconnect.commit()
                
                return response_out(
                    "success",
                    f"Status updated for gateway '{telecom}'",
                    200,
                    {
                        "id": result['id'],
                        "telecom": result['telecom'],
                        "api_status": result['api_status'],
                        "message": result['message'],
                        "created_at": result['created_at'].isoformat()
                    }
                )

    except Exception as e:
        if dbconnect:
            dbconnect.rollback()
        return response_out("error", f"Server error: {str(e)}", 500, {})
    finally:
        if dbconnect:
            dbconnect.close()
