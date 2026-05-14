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
from flask import g
from .globals import reply, require_permission, log_audit_event
import base64

clients_bp = Blueprint('clients', __name__)

@clients_bp.route("/clients/create", methods=["POST"])
@require_permission('clients.create')
def new_client():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:
        if(len(str(payload_data['data']['client_name'])) > 3) and (len(str(payload_data['data']['client_email'])) > 2) and (len(str(payload_data['data']['client_owner'])) > 2):
            
            ClientName = str(payload_data['data']['client_name'])
            ClientEmail = str(payload_data['data']['client_email'])
            ClientOwner = str(payload_data['data']['client_owner'])

            ClientLocal_UID = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("INSERT INTO dll_client_accounts VALUES(%s, %s, %s, %s, %s, %s)", (ClientLocal_UID, ClientName, ClientEmail, datetime.datetime.now().date(), ClientOwner, ClientOwner,))

                    log_audit_event(
                        actor=g.current_user['account_uid'],
                        action='CREATE',
                        obj=f"Client '{ClientName}' created",
                        domain='CLIENT',
                        severity='Info',
                        ip_address=request.remote_addr,
                        meta={"client_uid": ClientLocal_UID, "client_email": ClientEmail}
                    )

                    return reply('success', 200, 'Client created successfully', '')
                
        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    

#get all client accounts
    
@clients_bp.route("/clients/all", methods=["GET"])
@require_permission('clients.view')
def all_clients():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT * FROM dll_client_accounts WHERE is_deleted = FALSE OR is_deleted IS NULL")

                if(cursor.rowcount >= 1):

                    data_adapter = cursor.fetchall()
                    clients = []
                    
                    for row in data_adapter:

                        single_client = {
                            "client_name": row[1],
                            "client_uid": row[0],
                            "client_email": row[2]
                        }

                        clients.append(single_client)

                    return reply('success', 200, 'Clients Found', clients)

                elif(cursor.rowcount == 0):
                    return reply('error', 400, 'No Clients Found', '')
                else:
                    return reply('error', 400, 'Unable to complete request', '')
                
    except Exception as error:
        return reply('error', 500, str(error), '')


#Get Clients By Service Provider
@clients_bp.route("/clients/<string:service_provider>/all", methods=["GET"])
@require_permission('clients.view')
def SP_CLIENTS(service_provider):

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT * FROM dll_client_accounts WHERE parent_account=%s AND (is_deleted = FALSE OR is_deleted IS NULL)", (str(service_provider),))

                if(cursor.rowcount >= 1):

                    data_adapter = cursor.fetchall()
                    clients = []
                    
                    for row in data_adapter:

                        single_client = {
                            "client_name": row[1],
                            "client_uid": row[0],
                            "client_email": row[2]
                        }

                        clients.append(single_client)

                    return reply('success', 200, 'Clients Found', clients)

                elif(cursor.rowcount == 0):
                    return reply('error', 400, 'No Clients Found', '')
                else:
                    return reply('error', 400, 'Unable to complete request', '')
                
    except Exception as error:
        return reply('error', 500, str(error), '')


#Update client
@clients_bp.route("/clients/<string:client_uid>/update", methods=["PATCH", "PUT"])
@require_permission('clients.edit')
def update_client(client_uid):
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:
        update_fields = []
        update_values = []
        
        # Build dynamic update query based on provided fields
        if 'client_name' in payload_data.get('data', {}):
            update_fields.append("client_name = %s")
            update_values.append(str(payload_data['data']['client_name']))
        
        if 'client_email' in payload_data.get('data', {}):
            update_fields.append("client_email = %s")
            update_values.append(str(payload_data['data']['client_email']))
        
        if not update_fields:
            return reply('error', 400, 'No fields to update', '')
        
        update_values.append(client_uid)
        update_query = f"UPDATE dll_client_accounts SET {', '.join(update_fields)} WHERE client_uid = %s AND (is_deleted = FALSE OR is_deleted IS NULL)"
        
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(update_query, tuple(update_values))
                
                if cursor.rowcount == 1:
                    log_audit_event(
                        actor=g.current_user['account_uid'],
                        action='UPDATE',
                        obj=f"Client {client_uid} updated",
                        domain='CLIENT',
                        severity='Info',
                        ip_address=request.remote_addr,
                        meta={"client_uid": client_uid, "fields": list(payload_data.get('data', {}).keys())}
                    )
                    return reply('success', 200, 'Client updated successfully', '')
                elif cursor.rowcount == 0:
                    return reply('error', 404, 'Client not found or is deleted', '')
                else:
                    return reply('error', 400, 'Unable to update client', '')
                    
    except Exception as error:
        return reply('error', 500, str(error), '')


#Trash client (soft delete)
@clients_bp.route("/clients/<string:client_uid>/trash", methods=["PATCH", "POST"])
@require_permission('clients.delete')
def trash_client(client_uid):
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:
        deleted_by = payload_data.get('data', {}).get('deleted_by', 'system') if payload_data else 'system'
        
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "UPDATE dll_client_accounts SET is_deleted = TRUE, deleted_at = %s, deleted_by = %s WHERE client_uid = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                    (datetime.datetime.now(), deleted_by, client_uid)
                )
                
                if cursor.rowcount == 1:
                    log_audit_event(
                        actor=g.current_user['account_uid'],
                        action='TRASH',
                        obj=f"Client {client_uid} moved to trash",
                        domain='CLIENT',
                        severity='Warn',
                        ip_address=request.remote_addr,
                        meta={"client_uid": client_uid, "deleted_by": deleted_by}
                    )
                    return reply('success', 200, 'Client moved to trash', '')
                elif cursor.rowcount == 0:
                    return reply('error', 404, 'Client not found or already deleted', '')
                else:
                    return reply('error', 400, 'Unable to trash client', '')
                    
    except Exception as error:
        return reply('error', 500, str(error), '')


#Restore client from trash
@clients_bp.route("/clients/<string:client_uid>/restore", methods=["PATCH", "POST"])
@require_permission('clients.edit')
def restore_client(client_uid):
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "UPDATE dll_client_accounts SET is_deleted = FALSE, deleted_at = NULL, deleted_by = NULL WHERE client_uid = %s AND is_deleted = TRUE",
                    (client_uid,)
                )
                
                if cursor.rowcount == 1:
                    log_audit_event(
                        actor=g.current_user['account_uid'],
                        action='RESTORE',
                        obj=f"Client {client_uid} restored from trash",
                        domain='CLIENT',
                        severity='Info',
                        ip_address=request.remote_addr,
                        meta={"client_uid": client_uid}
                    )
                    return reply('success', 200, 'Client restored successfully', '')
                elif cursor.rowcount == 0:
                    return reply('error', 404, 'Client not found in trash', '')
                else:
                    return reply('error', 400, 'Unable to restore client', '')
                    
    except Exception as error:
        return reply('error', 500, str(error), '')


#Get trashed clients
@clients_bp.route("/clients/trashed", methods=["GET"])
def trashed_clients():
    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT * FROM dll_client_accounts WHERE is_deleted = TRUE ORDER BY deleted_at DESC")

                if cursor.rowcount >= 1:
                    data_adapter = cursor.fetchall()
                    clients = []
                    
                    for row in data_adapter:
                        single_client = {
                            "client_uid": row[0],
                            "client_name": row[1],
                            "client_email": row[2],
                            "date_created": str(row[3]) if len(row) > 3 else None,
                            "deleted_at": str(row[6]) if len(row) > 6 else None,
                            "deleted_by": row[7] if len(row) > 7 else None
                        }
                        clients.append(single_client)

                    return reply('success', 200, 'Trashed clients found', clients)
                elif cursor.rowcount == 0:
                    return reply('success', 200, 'No trashed clients found', [])
                else:
                    return reply('error', 400, 'Unable to complete request', '')
                
    except Exception as error:
        return reply('error', 500, str(error), '')
