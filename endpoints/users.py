from flask import Flask
from flask import Blueprint
from flask import request, make_response
import psycopg2
from flask import json
from flask import jsonify
import datetime
import random
from flask import current_app
import base64
import bcrypt
from decimal import Decimal
from .globals import reply, require_permission, require_auth, log_audit_event
import uuid
import requests
from .jwt_utils import create_access_token, create_refresh_token
from config import JWT_REFRESH_EXPIRY_DAYS


users_bp = Blueprint('users_bp', __name__)

@users_bp.route("/", methods=["GET", "POST"])
def home():
    return "<h1 style='color: red;'>SENTINEL_API_BASE</h1>"



# ── Role name resolution ────────────────────────────────────────────────────
#
# Accepts EITHER a role name (canonical, stored in dll_access_relay) OR a
# role UID (PK of dll_roles). Returns the canonical name, or None if the
# input matches neither. Lets the user-creation endpoints accept whichever
# the caller sends without writing a dangling reference into
# account_clearance — the latter caused the "user has no permissions"
# diagnosis we shipped a fix for.

def _resolve_role_name(cursor, role_identifier):
    """Return canonical role_name for an identifier (either name or UID).

    Performs at most two SELECTs. Returns None if neither lookup matches.
    """
    ident = str(role_identifier or "").strip()
    if not ident:
        return None
    # 1) Try by name (the common case)
    cursor.execute(
        "SELECT role_name FROM dll_roles "
        "WHERE role_name = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
        (ident,),
    )
    row = cursor.fetchone()
    if row is not None:
        return row[0]
    # 2) Fall back to UID
    cursor.execute(
        "SELECT role_name FROM dll_roles "
        "WHERE role_uid = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
        (ident,),
    )
    row = cursor.fetchone()
    if row is not None:
        return row[0]
    return None


@users_bp.route("/users/create", methods=["POST"])
@require_permission('users.create')
def create_user():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:

        if(len(str(payload_data['data']['account_name'])) > 4) and (len(str(payload_data['data']['username'])) > 2) and (len(str(payload_data['data']['account_type'])) > 2) and (len(str(payload_data['data']['assigned_role'])) > 2) and (len(str(payload_data['data']['email'])) > 4) and (len(str(payload_data['data']['password'])) > 4) and (len(str(payload_data['data']['root_account'])) > 4):

            AccountName = payload_data['data']['account_name']
            Username = payload_data['data']['username']
            AccountType = payload_data['data']['account_type']
            AccountRoleRaw = payload_data['data']['assigned_role']
            AccountEmail = payload_data['data']['email']
            UserCreating = payload_data['data']['author']
            RootAccount = payload_data['data']['root_account']
            raw_password = payload_data['data']['password']
            Password = bcrypt.hashpw(raw_password.encode(), bcrypt.gensalt()).decode()
            BillingType = payload_data['data']['billing_type']

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    # Resolve assigned_role to its canonical name. Accepts
                    # either a role name OR a role UID — we always store the
                    # NAME in account_clearance because that's what the
                    # downstream permission lookup queries by.
                    AccountRole = _resolve_role_name(cursor, AccountRoleRaw)
                    if AccountRole is None:
                        return reply(
                            'error', 400,
                            f"Role not found: {AccountRoleRaw!r}",
                            '',
                        )

                    cursor.execute("SELECT account_root FROM dll_access_relay WHERE log_username=%s;", (str(Username),))
                    if(cursor.rowcount == 0):
                        UserID = str(uuid.uuid4())

                        cursor.execute("INSERT INTO dll_access_relay VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, %s)", (RootAccount, UserID, AccountType, AccountRole, 'active', datetime.datetime.now().date(), AccountEmail, UserCreating, Username, Password, AccountName, 'no', 'no', 'no', BillingType, '0',))
                        
                        data_created = {
                            "account_uid": UserID
                        }

                        log_audit_event(
                            actor=UserCreating,
                            action='CREATE',
                            obj=f"User '{AccountName}' ({Username}) created with role '{AccountRole}'",
                            domain='RBAC',
                            severity='Info',
                            tenant_id=RootAccount,
                            ip_address=request.remote_addr,
                            meta={"account_uid": UserID, "account_type": AccountType, "role": AccountRole}
                        )

                        return reply('success', 200, 'Account Created SuccessFully', data_created)

                    elif(cursor.rowcount >= 1):
                        return reply('error', 400, 'Username Not Available', '')

                    else:
                        return reply('error', 400, 'Unable to complete process', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')



@users_bp.route("/users/sp/create", methods=["POST"])
@require_permission('users.create')
def create_sp_user():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:

        if(len(str(payload_data['data']['account_name'])) > 4) and (len(str(payload_data['data']['username'])) > 2) and (len(str(payload_data['data']['account_type'])) > 2) and (len(str(payload_data['data']['assigned_role'])) > 2) and (len(str(payload_data['data']['email'])) > 4) and (len(str(payload_data['data']['password'])) > 4) and (len(str(payload_data['data']['root_account'])) > 4):

            AccountName = payload_data['data']['account_name']
            Username = payload_data['data']['username']
            AccountType = payload_data['data']['account_type']
            AccountRoleRaw = payload_data['data']['assigned_role']
            AccountEmail = payload_data['data']['email']
            UserCreating = payload_data['data']['author']
            RootAccount = payload_data['data']['root_account']
            raw_password = payload_data['data']['password']
            Password = bcrypt.hashpw(raw_password.encode(), bcrypt.gensalt()).decode()
            BillingType = payload_data['data']['billing_type']
            ServiceProviderUID = payload_data['data']['sp_uid']

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    # Resolve assigned_role to its canonical name (same fix as create_user).
                    AccountRole = _resolve_role_name(cursor, AccountRoleRaw)
                    if AccountRole is None:
                        return reply(
                            'error', 400,
                            f"Role not found: {AccountRoleRaw!r}",
                            '',
                        )

                    cursor.execute("SELECT account_root FROM dll_access_relay WHERE log_username=%s;", (str(Username),))
                    if(cursor.rowcount == 0):
                        UserID = str(uuid.uuid4())

                        cursor.execute("INSERT INTO dll_access_relay VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, %s, %s)", (RootAccount, UserID, AccountType, AccountRole, 'active', datetime.datetime.now().date(), AccountEmail, UserCreating, Username, Password, AccountName, 'no', 'no', 'no', BillingType, '0', str(ServiceProviderUID),))
                        
                        data_created = {
                            "account_uid": UserID
                        }
                        return reply('success', 200, 'Account Created SuccessFully', data_created)

                    elif(cursor.rowcount >= 1):
                        return reply('error', 400, 'Username Not Available', '')
                    
                    else:
                        return reply('error', 400, 'Unable to complete process', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')

#auth user
    
@users_bp.route("/users/auth", methods=["POST"])
def auth_user():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:

        if(len(str(payload_data['data']['username'])) > 2) and (len(str(payload_data['data']['password'])) > 2):

            UsernameInputed = payload_data['data']['username']
            RawPassword = payload_data['data']['password']

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    # Fetch user by username only (password verified with bcrypt below)
                    cursor.execute(
                        "SELECT access_status, account_root, account_uid, account_clearance, account_type, log_password "
                        "FROM dll_access_relay WHERE log_username=%s;",
                        (UsernameInputed,)
                    )

                    if(cursor.rowcount == 1):

                        data_adapter = cursor.fetchone()
                        stored_password = data_adapter[5]

                        # Verify password — supports both bcrypt hashes and legacy base64
                        password_valid = False
                        if stored_password and stored_password.startswith('$2'):
                            # bcrypt hash
                            password_valid = bcrypt.checkpw(RawPassword.encode(), stored_password.encode())
                        else:
                            # Legacy base64 comparison (for accounts not yet migrated)
                            legacy_encoded = base64.b64encode(RawPassword.encode()).decode()
                            if legacy_encoded == stored_password:
                                password_valid = True
                                # Auto-migrate: upgrade to bcrypt on successful legacy login
                                new_hash = bcrypt.hashpw(RawPassword.encode(), bcrypt.gensalt()).decode()
                                cursor.execute(
                                    "UPDATE dll_access_relay SET log_password = %s WHERE account_uid = %s",
                                    (new_hash, data_adapter[2])
                                )

                        if not password_valid:
                            log_audit_event(
                                actor=UsernameInputed,
                                action='LOGIN_FAILED',
                                obj=f"Failed login attempt for '{UsernameInputed}'",
                                domain='SYSTEM',
                                severity='Warn',
                                ip_address=request.remote_addr
                            )
                            return reply('error', 400, 'Invalid Credentials, try again', '')

                        AccessStatus = data_adapter[0]

                        if(AccessStatus == 'active'):

                            account_uid = data_adapter[2]
                            account_root = data_adapter[1]
                            account_role = data_adapter[3]
                            account_type = data_adapter[4]

                            # Update last login timestamp
                            cursor.execute("UPDATE dll_access_relay SET last_login_at = NOW() WHERE account_uid = %s", (account_uid,))

                            # Generate JWT access token
                            access_token = create_access_token(account_uid, account_role, account_type, account_root)

                            # Generate refresh token
                            refresh_token, refresh_expires = create_refresh_token(account_uid)

                            user_data = {
                                "account_uid": account_uid,
                                "account_root": account_root,
                                "account_role": account_role,
                                "account_type": account_type,
                                "access_token": access_token,
                            }

                            log_audit_event(
                                actor=account_uid,
                                action='LOGIN',
                                obj=f"User '{UsernameInputed}' logged in",
                                domain='SYSTEM',
                                severity='Info',
                                tenant_id=account_root,
                                ip_address=request.remote_addr,
                                meta={"account_type": account_type, "role": account_role}
                            )

                            # Build response with HttpOnly refresh token cookie
                            response_body, status_code = reply('success', 200, 'Authentication SuccessFul', user_data)
                            resp = make_response(response_body, status_code)
                            resp.set_cookie(
                                '_nvxs_refresh_token',
                                refresh_token,
                                max_age=JWT_REFRESH_EXPIRY_DAYS * 86400,
                                httponly=True,
                                secure=True,
                                samesite='Strict',
                                path='/',
                            )
                            return resp

                        elif(AccessStatus == 'locked'):
                            log_audit_event(
                                actor=UsernameInputed,
                                action='LOGIN_BLOCKED',
                                obj=f"Login attempt by locked account '{UsernameInputed}'",
                                domain='SYSTEM',
                                severity='Warn',
                                ip_address=request.remote_addr
                            )
                            return reply('error', 401, 'Account is blocked, contact support', '')

                    elif(cursor.rowcount == 0):
                        log_audit_event(
                            actor=UsernameInputed,
                            action='LOGIN_FAILED',
                            obj=f"Failed login attempt for '{UsernameInputed}'",
                            domain='SYSTEM',
                            severity='Warn',
                            ip_address=request.remote_addr
                        )
                        return reply('error', 400, 'Invalid Credentials, try again', '')
                    else:
                        return reply('error', 400, 'Unable to authenticate account', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    


#get user details
@users_bp.route("/users/<account_uid>/details", methods=["GET"])
@require_permission('users.view')
def get_user_details(account_uid):

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT * FROM dll_access_relay WHERE account_uid=%s;", (str(account_uid),))

                if(cursor.rowcount == 1):
                    data_adapter = cursor.fetchone()
                    CreatedBY = data_adapter[7]
                    cursor.execute("SELECT display_name FROM dll_access_relay WHERE account_uid=%s", (str(CreatedBY),))
                    UserData = cursor.fetchone()
                    UserFullName = UserData[0] if UserData else str(CreatedBY)

                    user_data = {
                        "account_name": data_adapter[10],
                        "account_type": data_adapter[2],
                        "account_role": data_adapter[3],
                        "access_status": data_adapter[4],
                        "email": data_adapter[6],
                        "account_creator": data_adapter[7],
                        "account_creator_full_name": UserFullName,
                        "username": data_adapter[8],
                        "billing_type": data_adapter[14],
                        "primary_account": data_adapter[0],
                        "token_balance": data_adapter[15],
                        "date_created": data_adapter[5]
                    }
                    return reply('success', 200, 'Account Found', user_data)

                elif(cursor.rowcount == 0):
                    return reply('error', 400, 'No Account Found', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


#get all users
    
@users_bp.route("/users/all", methods=["POST"])
@require_permission('users.view')
def all_users():
    
    dbconnect = psycopg2.connect(current_app.config["db_link"])
    payload_data = request.get_json()

    try:
        if(len(str(payload_data['data']['primary_account'])) > 3):

            TargetPrimary_Account = payload_data['data']['primary_account']

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_access_relay WHERE account_root=%s;", (str(TargetPrimary_Account),))

                    if(cursor.rowcount >= 1):

                        data_adapter = cursor.fetchall()
                        user_data = []

                        for row in data_adapter:

                            CreatedBY = row[7]
                            cursor.execute("SELECT display_name FROM dll_access_relay WHERE account_uid=%s", (str(CreatedBY),))
                            UserData = cursor.fetchone()
                            UserFullName = UserData[0] if UserData else str(CreatedBY)

                            single_user = {
                                "account_name": row[10],
                                "account_type": row[2],
                                "account_role": row[3],
                                "access_status": row[4],
                                "email": row[6],
                                "account_creator": row[7],
                                "account_creator_full_name": UserFullName,
                                "username": row[8],
                                "billing_type": row[14],
                                "primary_account": row[0],
                                "account_uid": row[1],
                                "token_balance": row[15],
                                "date_created": row[5]
                            }

                            user_data.append(single_user)

                        return reply('success', 200, 'User Accounts Found', user_data)

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'No Accounts Found', '')
                    else:
                        return reply('error', 400, 'Unable to complete request', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')
        
    except Exception as errors:
        return reply('error', 500, str(errors), '')


#Get client user a service provider
@users_bp.route("/users/<service_provider_uid>/all", methods=["GET"])
@require_permission('users.view')
def all_SP_users(service_provider_uid):
    
    dbconnect = psycopg2.connect(current_app.config["db_link"])

    try:
        if True:
            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_access_relay WHERE service_provider_uid=%s;", (str(service_provider_uid),))

                    if(cursor.rowcount >= 1):

                        data_adapter = cursor.fetchall()
                        user_data = []

                        for row in data_adapter:

                            CreatedBY = row[7]
                            cursor.execute("SELECT display_name FROM dll_access_relay WHERE account_uid=%s", (str(CreatedBY),))
                            UserData = cursor.fetchone()
                            UserFullName = UserData[0] if UserData else str(CreatedBY)

                            single_user = {
                                "account_name": row[10],
                                "account_type": row[2],
                                "account_role": row[3],
                                "access_status": row[4],
                                "email": row[6],
                                "account_creator": row[7],
                                "account_creator_full_name": UserFullName,
                                "username": row[8],
                                "billing_type": row[14],
                                "primary_account": row[0],
                                "account_uid": row[1],
                                "token_balance": row[15],
                                "date_created": row[5]
                            }

                            user_data.append(single_user)

                        return reply('success', 200, 'User Accounts Found', user_data)

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'No Accounts Found', '')
                    else:
                        return reply('error', 400, 'Unable to complete request', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')
        
    except Exception as errors:
        return reply('error', 500, str(errors), '')
    
#as centinel system
@users_bp.route("/users/allx", methods=["GET"])
@require_permission('users.view')
def all_users_backOffice():
    
    dbconnect = psycopg2.connect(current_app.config["db_link"])

    try:
        if(True):
            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_access_relay WHERE account_type!= 'system_account' ORDER BY date_created DESC")

                    if(cursor.rowcount >= 1):

                        data_adapter = cursor.fetchall()
                        user_data = []

                        for row in data_adapter:

                            CreatedBY = row[7]
                            cursor.execute("SELECT display_name FROM dll_access_relay WHERE account_uid=%s", (str(CreatedBY),))
                            UserData = cursor.fetchone()
                            UserFullName = UserData[0] if UserData else str(CreatedBY)

                            PrimaryAccount = row[0]
                            cursor.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid=%s;", (str(PrimaryAccount),))
                            if(cursor.rowcount == 1):
                                dataAdapter = cursor.fetchone()
                                ClientFullName = dataAdapter[0]
                            else:
                                ClientFullName = 'NotFound'

                            single_user = {
                                "account_name": row[10],
                                "account_type": row[2],
                                "account_role": row[3],
                                "access_status": row[4],
                                "email": row[6],
                                "account_creator": row[7],
                                "account_creator_full_name": UserFullName,
                                "username": row[8],
                                "billing_type": row[14],
                                "primary_account": row[0],
                                "primary_account_name": ClientFullName,
                                "account_uid": row[1],
                                "token_balance": row[15],
                                "date_created": row[5]
                            }

                            user_data.append(single_user)

                        return reply('success', 200, 'User Accounts Found', user_data)

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'No Accounts Found', '')
                    else:
                        return reply('error', 400, 'Unable to complete request', '')
        
    except Exception as errors:
        return reply('error', 500, str(errors), '')
    
#block unblock user    
@users_bp.route("/users/action", methods=["POST"])
@require_permission('users.edit')
def action_user():

    dbconnect = psycopg2.connect(current_app.config["db_link"])
    payload_data = request.get_json()

    try:

        if(len(str(payload_data['data']['action'])) > 2) and (len(str(payload_data['data']['account_uid'])) > 2):

            Action = payload_data['data']['action']
            AccountID = payload_data['data']['account_uid']

            if(Action == 'active') or (Action == 'locked'):
                with dbconnect:
                    with dbconnect.cursor() as cursor:
                        cursor.execute("UPDATE dll_access_relay SET access_status=%s WHERE account_uid=%s;", (str(Action), str(AccountID),))

                        action_label = 'UNBLOCK' if Action == 'active' else 'BLOCK'
                        log_audit_event(
                            actor=g.current_user['account_uid'] if hasattr(g, 'current_user') else 'system',
                            action=action_label,
                            obj=f"User {AccountID} {'unblocked' if Action == 'active' else 'blocked'}",
                            domain='RBAC',
                            severity='Alarm',
                            ip_address=request.remote_addr,
                            meta={"target_uid": AccountID, "new_status": Action}
                        )

                        return reply('success', 200, 'Action SuccessFull', '')

            else:
                return reply('error', 400, 'Invalid action value (active or locked) expected', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    

@users_bp.route("/users/<user_uid>/assign-role", methods=["PUT"])
@require_permission('rbac.manage')
def assign_user_role(user_uid):
    """Assign a role to an existing user (updates account_clearance)."""
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:
        role_name = str(payload_data['data']['role_name']).strip()
        updated_by = str(payload_data['data'].get('updated_by', 'system')).strip()

        if len(role_name) < 2:
            return reply('error', 400, 'role_name is required', '')

        with dbconnect:
            with dbconnect.cursor() as cursor:
                # Verify user exists
                cursor.execute(
                    "SELECT account_uid FROM dll_access_relay WHERE account_uid = %s",
                    (str(user_uid),)
                )
                if cursor.rowcount == 0:
                    return reply('error', 404, 'User not found', '')

                # Resolve role: accept either name or UID, store the canonical name.
                resolved_role_name = _resolve_role_name(cursor, role_name)
                if resolved_role_name is None:
                    return reply('error', 404, 'Role not found', '')

                # Update user's role
                cursor.execute(
                    "UPDATE dll_access_relay SET account_clearance = %s WHERE account_uid = %s",
                    (resolved_role_name, str(user_uid))
                )
                role_name = resolved_role_name  # use canonical name in audit log below

                log_audit_event(
                    actor=g.current_user['account_uid'],
                    action='ASSIGN_ROLE',
                    obj=f"Role '{role_name}' assigned to user {user_uid}",
                    domain='RBAC',
                    severity='Alarm',
                    ip_address=request.remote_addr,
                    meta={"target_uid": user_uid, "role_name": role_name, "updated_by": updated_by}
                )

                return reply('success', 200, 'Role assigned successfully', {
                    'account_uid': str(user_uid),
                    'role_name': role_name
                })

    except Exception as error:
        return reply('error', 500, str(error), '')


@users_bp.route("/users/<user_uid>/reset-password", methods=["PUT"])
@require_permission('users.reset_password')
def reset_password(user_uid):

    try:
        dbconnect = psycopg2.connect(current_app.config["db_link"])
        Password = "444444"
        DefaultPassword = bcrypt.hashpw(Password.encode(), bcrypt.gensalt()).decode()

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("UPDATE dll_access_relay SET log_password=%s WHERE account_uid=%s;", (str(DefaultPassword), str(user_uid),))

                return reply('success', 200, "Reset SuccessFul", '')

    except Exception as error:
        return reply('error', 500, str(error), '')


@users_bp.route("/users/<user_uid>/change-password", methods=["PUT"])
def change_password(user_uid):
    try:
        dbconnect = psycopg2.connect(current_app.config["db_link"])
        payload = request.get_json()
        if(len(str(payload['data']['new_password'])) > 4):

            NewPassword = str(payload['data']['new_password'])
            UpdatedPassword = bcrypt.hashpw(NewPassword.encode(), bcrypt.gensalt()).decode()

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("UPDATE dll_access_relay SET log_password=%s WHERE account_uid=%s", (str(UpdatedPassword), str(user_uid),))

                    return reply('success', 200, 'Update SuccessFul', '')

        else:
            return reply('error', 400, 'Something Is Missing Or Password too short', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    

#Authenticate Block
@users_bp.route("/authenticate/command", methods=["POST"])
def AuthUser():

    try:
        dbconnect = psycopg2.connect(current_app.config["db_link"])
        _payload = request.get_json()

        _CommandIntent = _payload['data']['command']
        _deviceImeiNumber = _payload['data']['imei_number']
        _userPassword = _payload['data']['user_password']
        _userAuthenticating = _payload['data']['user_authenticating']
        _ActionSpeed = _payload['data']['moving_speed']
        if(len(str(_ActionSpeed)) > 0) and (len(str(_userPassword)) > 3):

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT email, log_password FROM dll_access_relay WHERE account_uid=%s", (str(_userAuthenticating),))

                    if(cursor.rowcount == 1):
                        _row = cursor.fetchone()
                        _stored_pw = _row[1]
                        _pw_valid = False
                        if _stored_pw and _stored_pw.startswith('$2'):
                            _pw_valid = bcrypt.checkpw(_userPassword.encode(), _stored_pw.encode())
                        else:
                            _pw_valid = base64.b64encode(_userPassword.encode()).decode() == _stored_pw

                        if not _pw_valid:
                            return reply("error", 400, "Incorrect Password - Rejected", "")

                        if(_CommandIntent == 'block'):

                            _Command_Payload = {
                                "data": {
                                    "command_speed": str(_ActionSpeed),
                                    "custom_command": "NO",
                                    "custom_command_text": "NA",
                                    "commanding_user": str(_userAuthenticating),
                                    "device_unit": str(_deviceImeiNumber)
                                }
                            }
                            _ApiCommand = requests.post('https://narvas.3dservices.co.ug/management/activate/immobilizer', data=json.dumps(_Command_Payload), headers={"content-type":"application/json"})
                            _ApiReply = _ApiCommand.json()

                            if(_ApiReply['status'] == 'success'):
                                return reply("success", 200, "Success-Command Sent to Unit", "")
                            elif(_ApiReply['status'] == 'error'):
                                return reply("error", 400, _ApiReply['message'], "")

                        elif(_CommandIntent == 'restore'):

                            _Command_Payload = {
                                "data": {
                                    "command_speed": "NA",
                                    "custom_command": "NO",
                                    "custom_command_text": "NA",
                                    "commanding_user": str(_userAuthenticating),
                                    "device_unit": str(_deviceImeiNumber)
                                }
                            }
                            _ApiCommand = requests.post('https://narvas.3dservices.co.ug/management/restore/immobilizer', data=json.dumps(_Command_Payload), headers={"content-type":"application/json"})
                            _ApiReply = _ApiCommand.json()

                            if(_ApiReply['status'] == 'success'):
                                return reply("success", 200, "Success-Command Sent to Unit", "")
                            elif(_ApiReply['status'] == 'error'):
                                return reply("error", 400, _ApiReply['message'], "")

                    elif(cursor.rowcount == 0):
                        return reply("error", 400, "Incorrect Password - Rejected", "")
        else:
            return reply("error", 400, "Some details are missing", "")
        
    except Exception as error:
        return reply("error", 500, str(error), "")


@users_bp.route("/accounts/users/reset-password", methods=["POST"])
def ResetPassword():
    try:
        dbconnect = psycopg2.connect(current_app.config["db_link"])
        _payload = request.get_json()

        _UserReseting = str(_payload['data']['user_resetting'])
        _OldPassword = str(_payload['data']['old_password'])
        _NewPassword = str(_payload['data']['new_password'])

        if(len(_UserReseting) > 5) and (len(_OldPassword) > 2) and (len(_NewPassword) > 2):

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT log_password FROM dll_access_relay WHERE account_uid=%s", (str(_UserReseting),))

                    if(cursor.rowcount == 1):
                        _stored_pw = cursor.fetchone()[0]
                        _pw_valid = False
                        if _stored_pw and _stored_pw.startswith('$2'):
                            _pw_valid = bcrypt.checkpw(_OldPassword.encode(), _stored_pw.encode())
                        else:
                            _pw_valid = base64.b64encode(_OldPassword.encode()).decode() == _stored_pw

                        if not _pw_valid:
                            return reply("error", 400, "Invalid Old Password - Rejected", "")

                        _NewHash = bcrypt.hashpw(_NewPassword.encode(), bcrypt.gensalt()).decode()
                        cursor.execute("UPDATE dll_access_relay SET log_password=%s WHERE account_uid=%s", (str(_NewHash), str(_UserReseting),))

                        return reply("success", 200, "Password Reset SuccessFul", "")

                    elif(cursor.rowcount == 0):
                        return reply("error", 400, "Invalid Old Password - Rejected", "")

        else:
            return reply("error", 400, "Some details are missing", "")

    except Exception as error:
        return reply("error", 500, str(error), "")


@users_bp.route("/app/version", methods=["GET"])
def AppVersion():
    try:
        dbconnect = psycopg2.connect(current_app.config["db_link"])

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT app_version FROM dll_app_version")
                _dataTunnel = cursor.fetchone()
                _AppVersion = _dataTunnel[0]
                _Response = {
                    "app_version": _AppVersion,
                    "android_url": "https://play.google.com/store/apps/details?id=com.santripe.cards",
                    "ios_url": "https://apps.apple.com/no/app/mcf-radio/id1543167917"
                }
                return reply("success", 200, "Version Found", _Response)

    except Exception as error:
        return reply("error", 500, str(error), "")