from flask import Blueprint, request, current_app, g
from .globals import reply, require_permission
import psycopg2
import psycopg2.extras
import uuid
from datetime import datetime, timedelta

audit_bp = Blueprint('audit_bp', __name__)


# ==========================================
# VALID ENUMS
# ==========================================
VALID_DOMAINS = ['TENANT', 'BILLING', 'VEBA', 'MONEY', 'RBAC', 'TOKEN', 'PAYMENT', 'FIRMWARE', 'SIM', 'PROTOCOL', 'ALARM', 'AI', 'AUDIT', 'CLIENT', 'SYSTEM']
VALID_SEVERITIES = ['Info', 'Warn', 'Alarm', 'Crit']
VALID_RANGES = {'1h': 1, '6h': 6, '24h': 24, '7d': 168, '30d': 720}
VALID_APPROVAL_TYPES = ['HITL', 'HIC']
VALID_APPROVAL_STATUSES = ['pending', 'approved', 'rejected', 'expired']
VALID_CHAIN_STATUSES = ['valid', 'gap', 'tampered']
VALID_COMPLIANCE_STATUSES = ['ok', 'warn', 'alert']


# ==========================================
# 1. GET /audit/events
# ==========================================
@audit_bp.route("/audit/events", methods=["GET"])
@require_permission('audit.view')
def get_audit_events():
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        domain = request.args.get('domain')
        severity = request.args.get('severity')
        actor = request.args.get('actor')
        action = request.args.get('action')
        range_val = request.args.get('range')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        tenant_id = request.args.get('tenant_id')
        search = request.args.get('search')

        # Validate domain
        if domain and domain not in VALID_DOMAINS:
            return reply('error', 400, f'Invalid domain. Valid: {", ".join(VALID_DOMAINS)}', '')

        # Validate severity
        if severity and severity not in VALID_SEVERITIES:
            return reply('error', 400, f'Invalid severity. Valid: {", ".join(VALID_SEVERITIES)}', '')

        # Validate range
        if range_val and range_val not in VALID_RANGES:
            return reply('error', 400, f'Invalid range. Valid: {", ".join(VALID_RANGES.keys())}', '')

        query = "SELECT id, timestamp, actor, action, object, domain, severity, tenant_id, ip_address, hash_prev, hash_this, meta FROM dll_audit_events WHERE 1=1"
        params = []

        if domain:
            query += " AND domain = %s"
            params.append(domain)

        if severity:
            query += " AND severity = %s"
            params.append(severity)

        if actor:
            query += " AND actor = %s"
            params.append(actor)

        if action:
            query += " AND action = %s"
            params.append(action)

        if tenant_id:
            query += " AND tenant_id = %s"
            params.append(tenant_id)

        if range_val and range_val in VALID_RANGES:
            hours = VALID_RANGES[range_val]
            query += " AND timestamp >= NOW() - INTERVAL '%s hours'"
            params.append(hours)

        if date_from:
            query += " AND timestamp >= %s"
            params.append(date_from)

        if date_to:
            query += " AND timestamp <= %s"
            params.append(date_to)

        if search:
            query += " AND (object ILIKE %s OR actor ILIKE %s OR action ILIKE %s)"
            search_pattern = f'%{search}%'
            params.extend([search_pattern, search_pattern, search_pattern])

        query += " ORDER BY timestamp DESC LIMIT 200"

        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()

                events = []
                for row in rows:
                    events.append({
                        "id": row['id'],
                        "timestamp": row['timestamp'].isoformat() + 'Z' if row['timestamp'] else None,
                        "actor": row['actor'],
                        "action": row['action'],
                        "object": row['object'],
                        "domain": row['domain'],
                        "severity": row['severity'],
                        "tenant_id": row['tenant_id'],
                        "ip_address": row['ip_address'],
                        "hash_prev": row['hash_prev'],
                        "hash_this": row['hash_this'],
                        "meta": row['meta'] if row['meta'] else {}
                    })

                return reply('success', 200, 'Audit events retrieved', events)

    except Exception as error:
        return reply('error', 500, str(error), '')
    finally:
        dbconnect.close()


# ==========================================
# 2. GET /audit/kpis
# ==========================================
@audit_bp.route("/audit/kpis", methods=["GET"])
@require_permission('audit.view')
def get_audit_kpis():
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                # Ingest P95 - approximate from recent events
                cursor.execute("""
                    SELECT COALESCE(
                        EXTRACT(EPOCH FROM (PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY created_at - timestamp)))::int,
                        0
                    ) FROM dll_audit_events WHERE timestamp >= NOW() - INTERVAL '24 hours'
                """)
                ingest_p95 = cursor.fetchone()[0] or 0

                # Log gaps in last 24h
                cursor.execute("""
                    SELECT COUNT(*) FROM dll_audit_hash_chain
                    WHERE status = 'gap' AND created_at >= NOW() - INTERVAL '24 hours'
                """)
                log_gaps = cursor.fetchone()[0] or 0

                # Sensitive actions in last 24h (Alarm + Crit severity)
                cursor.execute("""
                    SELECT COUNT(*) FROM dll_audit_events
                    WHERE severity IN ('Alarm', 'Crit') AND timestamp >= NOW() - INTERVAL '24 hours'
                """)
                sensitive_actions = cursor.fetchone()[0] or 0

                # Retention days from compliance table
                cursor.execute("""
                    SELECT value FROM dll_audit_compliance WHERE key = 'Retention OK' ORDER BY checked_at DESC LIMIT 1
                """)
                retention_row = cursor.fetchone()
                retention_days = 180
                if retention_row and retention_row[0]:
                    try:
                        retention_days = int(retention_row[0].split('/')[0])
                    except (ValueError, IndexError):
                        retention_days = 180

                return reply('success', 200, 'Audit KPIs retrieved', {
                    "ingest_p95_seconds": ingest_p95,
                    "log_gaps_24h": log_gaps,
                    "sensitive_actions_24h": sensitive_actions,
                    "retention_days": retention_days
                })

    except Exception as error:
        return reply('error', 500, str(error), '')
    finally:
        dbconnect.close()


# ==========================================
# 3. GET /audit/hash-chain
# ==========================================
@audit_bp.route("/audit/hash-chain", methods=["GET"])
@require_permission('audit.view')
def get_hash_chain():
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT block_id, hash, prev_hash, event_count, created_at, status
                    FROM dll_audit_hash_chain
                    ORDER BY block_id DESC
                    LIMIT 100
                """)
                rows = cursor.fetchall()

                chain = []
                for row in rows:
                    chain.append({
                        "block_id": row['block_id'],
                        "hash": row['hash'],
                        "prev_hash": row['prev_hash'],
                        "event_count": row['event_count'],
                        "created_at": row['created_at'].isoformat() + 'Z' if row['created_at'] else None,
                        "status": row['status']
                    })

                return reply('success', 200, 'Hash chain retrieved', chain)

    except Exception as error:
        return reply('error', 500, str(error), '')
    finally:
        dbconnect.close()


# ==========================================
# 4. GET /audit/approvals
# ==========================================
@audit_bp.route("/audit/approvals", methods=["GET"])
@require_permission('audit.view')
def get_approvals():
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT id, type, title, domain, tenant_name, requirement, status, requested_at, requested_by
                    FROM dll_audit_approvals
                    ORDER BY requested_at DESC
                    LIMIT 100
                """)
                rows = cursor.fetchall()

                approvals = []
                for row in rows:
                    approvals.append({
                        "id": row['id'],
                        "type": row['type'],
                        "title": row['title'],
                        "domain": row['domain'],
                        "tenant_name": row['tenant_name'],
                        "requirement": row['requirement'],
                        "status": row['status'],
                        "requested_at": row['requested_at'].isoformat() + 'Z' if row['requested_at'] else None,
                        "requested_by": row['requested_by']
                    })

                return reply('success', 200, 'Approvals retrieved', approvals)

    except Exception as error:
        return reply('error', 500, str(error), '')
    finally:
        dbconnect.close()


# ==========================================
# 5. PATCH /audit/approvals/<id>/approve
# ==========================================
@audit_bp.route("/audit/approvals/<approval_id>/approve", methods=["PATCH"])
@require_permission('audit.approve')
def approve_approval(approval_id):
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        resolved_by = g.current_user['account_uid']

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT id, status FROM dll_audit_approvals WHERE id = %s",
                    (str(approval_id),)
                )
                if cursor.rowcount == 0:
                    return reply('error', 404, 'Approval not found', '')

                row = cursor.fetchone()
                if row[1] != 'pending':
                    return reply('error', 400, f'Approval already {row[1]}', '')

                cursor.execute(
                    "UPDATE dll_audit_approvals SET status = 'approved', resolved_at = NOW(), resolved_by = %s WHERE id = %s",
                    (str(resolved_by), str(approval_id))
                )

                return reply('success', 200, 'Approval approved', {
                    "approval_id": approval_id,
                    "status": "approved"
                })

    except Exception as error:
        return reply('error', 500, str(error), '')
    finally:
        dbconnect.close()


# ==========================================
# 6. PATCH /audit/approvals/<id>/reject
# ==========================================
@audit_bp.route("/audit/approvals/<approval_id>/reject", methods=["PATCH"])
@require_permission('audit.approve')
def reject_approval(approval_id):
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        resolved_by = g.current_user['account_uid']

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT id, status FROM dll_audit_approvals WHERE id = %s",
                    (str(approval_id),)
                )
                if cursor.rowcount == 0:
                    return reply('error', 404, 'Approval not found', '')

                row = cursor.fetchone()
                if row[1] != 'pending':
                    return reply('error', 400, f'Approval already {row[1]}', '')

                cursor.execute(
                    "UPDATE dll_audit_approvals SET status = 'rejected', resolved_at = NOW(), resolved_by = %s WHERE id = %s",
                    (str(resolved_by), str(approval_id))
                )

                return reply('success', 200, 'Approval rejected', {
                    "approval_id": approval_id,
                    "status": "rejected"
                })

    except Exception as error:
        return reply('error', 500, str(error), '')
    finally:
        dbconnect.close()


# ==========================================
# 7. GET /audit/compliance
# ==========================================
@audit_bp.route("/audit/compliance", methods=["GET"])
@require_permission('audit.view')
def get_compliance():
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT key, value, status, checked_at
                    FROM dll_audit_compliance
                    ORDER BY id ASC
                """)
                rows = cursor.fetchall()

                items = []
                checked_at = None
                for row in rows:
                    items.append({
                        "key": row['key'],
                        "value": row['value'],
                        "status": row['status']
                    })
                    if row['checked_at']:
                        checked_at = row['checked_at'].isoformat() + 'Z'

                return reply('success', 200, 'Compliance snapshot retrieved', {
                    "items": items,
                    "checked_at": checked_at
                })

    except Exception as error:
        return reply('error', 500, str(error), '')
    finally:
        dbconnect.close()


# ==========================================
# 8. POST /audit/export
# ==========================================
@audit_bp.route("/audit/export", methods=["POST"])
@require_permission('audit.export')
def request_export():
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        payload_data = request.get_json()

        if not payload_data or 'data' not in payload_data:
            return reply('error', 400, 'Missing request body', '')

        data = payload_data['data']
        tenant_id = data.get('tenant_id')
        date_range = data.get('date_range', 'last_24h')
        include_sub_tenants = data.get('include_sub_tenants', False)
        formats = data.get('formats', ['pdf'])
        redact_pii = data.get('redact_pii', True)
        include_raw_payloads = data.get('include_raw_payloads', False)
        approver_ids = data.get('approver_ids', [])

        if not tenant_id:
            return reply('error', 400, 'tenant_id is required', '')

        export_id = 'exp-' + str(uuid.uuid4())[:8]
        approval_id = 'apr-' + str(uuid.uuid4())[:8]
        requested_by = g.current_user['account_uid']

        with dbconnect:
            with dbconnect.cursor() as cursor:
                # Create the export record
                cursor.execute("""
                    INSERT INTO dll_audit_exports
                    (export_id, approval_id, tenant_id, date_range, include_sub_tenants, formats, redact_pii, include_raw_payloads, approver_ids, status, requested_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending_approval', %s)
                """, (
                    export_id, approval_id, str(tenant_id), str(date_range),
                    bool(include_sub_tenants),
                    psycopg2.extras.Json(formats),
                    bool(redact_pii),
                    bool(include_raw_payloads),
                    psycopg2.extras.Json(approver_ids),
                    str(requested_by)
                ))

                # Create a corresponding approval record
                cursor.execute("""
                    INSERT INTO dll_audit_approvals
                    (id, type, title, domain, tenant_name, requirement, status, requested_by)
                    VALUES (%s, 'HIC', %s, 'AUDIT', %s, %s, 'pending', %s)
                """, (
                    approval_id,
                    f'Audit export for tenant {tenant_id}',
                    str(tenant_id),
                    f'Needs {len(approver_ids)} approver(s)' if approver_ids else 'Needs approval',
                    str(requested_by)
                ))

                return reply('success', 200, 'Export requested', {
                    "export_id": export_id,
                    "approval_id": approval_id,
                    "status": "pending_approval"
                })

    except Exception as error:
        return reply('error', 500, str(error), '')
    finally:
        dbconnect.close()
