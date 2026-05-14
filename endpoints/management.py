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
from .globals import check_device
import requests
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.auth import PlainTextAuthProvider
from cassandra import ConsistencyLevel
from cassandra.policies import TokenAwarePolicy, DCAwareRoundRobinPolicy
from cassandra.query import SimpleStatement


management_bp = Blueprint('management', __name__)


# Cassandra connection configuration
CASSANDRA_KEYSPACE = 'navas_iot_dbx'
CASSANDRA_CONTACT_POINTS = ['165.232.128.208']
CASSANDRA_PORT = 9042
CASSANDRA_USERNAME = 'cassandra'
CASSANDRA_PASSWORD = 'Sterile-Nectar-Unrevised-Undertone-Stagnate1'
CASSANDRA_LOCAL_DC = 'datacenter1'

_cassandra_cluster = None
_cassandra_session = None

def get_cassandra_session():
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
        print("Successfully connected to Cassandra cluster")
        return _cassandra_session
    except Exception as e:
        print(f"Error connecting to Cassandra: {e}")
        return None
    
def SendUG_Sms(ToPhoneNumber, MessageObject):
    try:

        url = "https://www.egosms.co/api/v1/json/"
        payload = json.dumps({
        "method": "SendSms",
        "userdata": {
            "username": "ericlukyamuzi",
            "password": "cipher45"
        },
        "msgdata": [
            {
                "number": str(ToPhoneNumber),
                "message": str(MessageObject),
                "senderid": "Centinnel",
                "priority": "0"
            }
        ]
        })
        headers = {
        'User-Agent': 'Apidog/1.0.0 (https://apidog.com)',
        'Content-Type': 'application/json'
        }
        response = requests.request("POST", url, headers=headers, data=payload)

        pass

    except Exception as error:
        pass

#Block Engine

@management_bp.route("/management/activate/immobilizer", methods=['POST'])
def Immobilize():
    try:
        cassandra_session = get_cassandra_session()
        if cassandra_session is None:
            return reply('error', 500, 'Cassandra connection failed', '')

        payload_data = request.get_json()

        ImmobilizeSpeed_Sent = payload_data['data']['command_speed']
        IsCustomCommand = payload_data['data']['custom_command']
        CustomCommand_Text = payload_data['data']['custom_command_text']
        UserCommanding = payload_data['data']['commanding_user']
        TargetUnit = str(payload_data['data']['device_unit'])

        if len(str(IsCustomCommand)) > 1:
            if len(str(UserCommanding)) > 4 and len(str(TargetUnit)) > 4:
                # Get device_vendor from Cassandra
                query = "SELECT device_vendor FROM dll_device_registrar WHERE device_imei=?"
                prepared = cassandra_session.prepare(query)
                result = cassandra_session.execute(prepared, [TargetUnit])
                deviceProps_data_adapter = result.one()

                if deviceProps_data_adapter:
                    ExistingHardware = str(deviceProps_data_adapter.device_vendor)

                    dbconnect = psycopg2.connect(current_app.config['db_link'])

                    if ExistingHardware == 'ruptela':
                        if len(str(ImmobilizeSpeed_Sent)) > 0:
                            Ruptela_ImmobilizerCommand = f"  immobilizer {ImmobilizeSpeed_Sent}"
                            #Start Send SMS HERE
                            #End Send SMS HERE
                            LogDate = datetime.datetime.now().date()
                            # Store in Postgres
                            with dbconnect:
                                with dbconnect.cursor() as cursor:
                                    cursor.execute(
                                        "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                        (str(TargetUnit), str(Ruptela_ImmobilizerCommand), str(UserCommanding), str(LogDate))
                                    )
                            return reply("success", 200, "Immobilizing Command Transmition SuccessFul", '')
                        else:
                            return reply('error', 400, 'Immobilizing Command Speed Missing', '')

                    elif ExistingHardware == 'teltonika':
                        query = "SELECT config_param_data_source_uid FROM dll_device_local_configs WHERE local_device_imei=? AND config_parameter=?"
                        prepared = cassandra_session.prepare(query)
                        result = cassandra_session.execute(prepared, (TargetUnit, 'engine_blocking_state'))
                        data_adapter = result.one()
                        Immobilizer_DOUT_Source = int(data_adapter.config_param_data_source_uid) if data_adapter else None

                        if Immobilizer_DOUT_Source == 1:
                            Teltonika_ImmobilizerCommand = f"setdigout 1 ? {ImmobilizeSpeed_Sent}"
                        elif Immobilizer_DOUT_Source == 2:
                            Teltonika_ImmobilizerCommand = f"setdigout ?1 ? {ImmobilizeSpeed_Sent}"
                        else:
                            return reply("error", 400, "Immobilizer Configuration Is Non-Compatible ( DOUT-1 or DOUT-2 or DOUT-3 )", '')

                        # Get simcard number from Postgres
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute("SELECT device_simcard FROM dll_device_basic_data WHERE device_imei=%s", (TargetUnit,))
                                _dataTunnelLink = cursor.fetchone()
                                _SimcardID = _dataTunnelLink[0] if _dataTunnelLink else None

                                _SimcardNumber = ""
                                if _SimcardID:
                                    cursor.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid=%s", (str(_SimcardID),))
                                    _tunnelLink = cursor.fetchone()
                                    _SimcardNumber = str(_tunnelLink[0]) if _tunnelLink else ""

                        if _SimcardNumber:
                            if _SimcardNumber[:3] == '256':
                                SendUG_Sms("+" + str(_SimcardNumber), Teltonika_ImmobilizerCommand)
                            elif _SimcardNumber[:4] == '+256':
                                phone_number = _SimcardNumber[1:]
                                SendUG_Sms(phone_number, Teltonika_ImmobilizerCommand)

                        LogDate = datetime.datetime.now().date()
                        # Store in Postgres
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                    (TargetUnit, str(Teltonika_ImmobilizerCommand), str(UserCommanding), str(LogDate))
                                )
                        return reply("success", 200, "Immobilizing Command Transmition SuccessFul", '')

                    elif ExistingHardware == 'concox':
                        Concox_ImmobilizerCommand = "RELAY,1#"
                        # Get simcard number from Postgres
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute("SELECT device_simcard FROM dll_device_basic_data WHERE device_imei=%s", (TargetUnit,))
                                _dataTunnelLink = cursor.fetchone()
                                _SimcardID = _dataTunnelLink[0] if _dataTunnelLink else None

                                _SimcardNumber = ""
                                if _SimcardID:
                                    cursor.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid=%s", (str(_SimcardID),))
                                    _tunnelLink = cursor.fetchone()
                                    _SimcardNumber = str(_tunnelLink[0]) if _tunnelLink else ""

                        if _SimcardNumber:
                            if _SimcardNumber[:3] == '256':
                                SendUG_Sms("+" + str(_SimcardNumber), Concox_ImmobilizerCommand)
                            elif _SimcardNumber[:4] == '+256':
                                phone_number = _SimcardNumber[1:]
                                SendUG_Sms(phone_number, Concox_ImmobilizerCommand)

                        LogDate = datetime.datetime.now().date()
                        # Store in Postgres
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                    (TargetUnit, str(Concox_ImmobilizerCommand), str(UserCommanding), str(LogDate))
                                )
                        return reply("success", 200, "Immobilizing Command Transmition SuccessFul", '')

                    elif ExistingHardware == 'xirgo_global':
                        Xirgo_ImmobilizerCommand = "RELAY,1#"
                        # Get simcard number from Postgres
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute("SELECT device_simcard FROM dll_device_basic_data WHERE device_imei=%s", (TargetUnit,))
                                _dataTunnelLink = cursor.fetchone()
                                _SimcardID = _dataTunnelLink[0] if _dataTunnelLink else None

                                _SimcardNumber = ""
                                if _SimcardID:
                                    cursor.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid=%s", (str(_SimcardID),))
                                    _tunnelLink = cursor.fetchone()
                                    _SimcardNumber = str(_tunnelLink[0]) if _tunnelLink else ""

                        if _SimcardNumber:
                            if _SimcardNumber[:3] == '256':
                                SendUG_Sms("+" + str(_SimcardNumber), Xirgo_ImmobilizerCommand)
                            elif _SimcardNumber[:4] == '+256':
                                phone_number = _SimcardNumber[1:]
                                SendUG_Sms(phone_number, Xirgo_ImmobilizerCommand)

                        LogDate = datetime.datetime.now().date()
                        # Store in Postgres
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                    (TargetUnit, str(Xirgo_ImmobilizerCommand), str(UserCommanding), str(LogDate))
                                )
                        return reply("success", 200, "Immobilizing Command Transmition SuccessFul", '')

                    elif ExistingHardware == 'king_sword':
                        KingSword_ImmobilizerCommand = "RELAY,1#"
                        # Get simcard number from Postgres
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute("SELECT device_simcard FROM dll_device_basic_data WHERE device_imei=%s", (TargetUnit,))
                                _dataTunnelLink = cursor.fetchone()
                                _SimcardID = _dataTunnelLink[0] if _dataTunnelLink else None

                                _SimcardNumber = ""
                                if _SimcardID:
                                    cursor.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid=%s", (str(_SimcardID),))
                                    _tunnelLink = cursor.fetchone()
                                    _SimcardNumber = str(_tunnelLink[0]) if _tunnelLink else ""

                        if _SimcardNumber:
                            if _SimcardNumber[:3] == '256':
                                SendUG_Sms("+" + str(_SimcardNumber), KingSword_ImmobilizerCommand)
                            elif _SimcardNumber[:4] == '+256':
                                phone_number = _SimcardNumber[1:]
                                SendUG_Sms(phone_number, KingSword_ImmobilizerCommand)

                        LogDate = datetime.datetime.now().date()
                        # Store in Postgres
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                    (TargetUnit, str(KingSword_ImmobilizerCommand), str(UserCommanding), str(LogDate))
                                )
                        return reply("success", 200, "Immobilizing Command Transmition SuccessFul", '')

                    elif ExistingHardware == 'other':
                        if len(str(CustomCommand_Text)) > 1:
                            #Start Send SMS HERE
                            #End Send SMS HERE
                            LogDate = datetime.datetime.now().date()
                            # Store in Postgres
                            with dbconnect:
                                with dbconnect.cursor() as cursor:
                                    cursor.execute(
                                        "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                        (TargetUnit, str(CustomCommand_Text), str(UserCommanding), str(LogDate))
                                    )
                            return reply("success", 200, "Immobilizing Command Transmition SuccessFul", '')
                        else:
                            return reply("success", 400, "Custom Command Text Missing", '')
                    else:
                        return reply('error', 400, 'Hardware Recognition Error', '')
                else:
                    return reply('error', 400, 'No Device Found', '')
            else:
                return reply("error", 400, "Commanding User or Device Unit Imei is Missing", "")
        else:
            return reply('error', 400, 'Custom Command Definition Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


#Restore Engine


@management_bp.route("/management/restore/immobilizer", methods=['POST'])
def RestoreImmobilize():
    try:
        cassandra_session = get_cassandra_session()
        if cassandra_session is None:
            return reply('error', 500, 'Cassandra connection failed', '')

        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()

        ImmobilizeSpeed_Sent = payload_data['data']['command_speed']
        IsCustomCommand = payload_data['data']['custom_command']
        CustomCommand_Text = payload_data['data']['custom_command_text']
        UserCommanding = payload_data['data']['commanding_user']
        TargetUnit = str(payload_data['data']['device_unit'])

        if len(str(IsCustomCommand)) > 1:
            if len(str(UserCommanding)) > 4 and len(str(TargetUnit)) > 4:
                # Get device_vendor from Cassandra
                query = "SELECT device_vendor FROM dll_device_registrar WHERE device_imei=?"
                prepared = cassandra_session.prepare(query)
                result = cassandra_session.execute(prepared, [TargetUnit])
                deviceProps_data_adapter = result.one()

                if deviceProps_data_adapter:
                    ExistingHardware = str(deviceProps_data_adapter.device_vendor)

                    if ExistingHardware == 'ruptela':
                        Ruptela_ResetImmobilizerCommand = "  resetimmob"
                        #Start Send SMS HERE
                        #End Send SMS HERE
                        LogDate = datetime.datetime.now().date()
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                    (TargetUnit, Ruptela_ResetImmobilizerCommand, UserCommanding, LogDate)
                                )
                        return reply("success", 200, "Restore Command Transmition SuccessFul", '')

                    elif ExistingHardware == 'teltonika':
                        query = "SELECT config_param_data_source_uid FROM dll_device_local_configs WHERE local_device_imei=? AND config_parameter=?"
                        prepared = cassandra_session.prepare(query)
                        result = cassandra_session.execute(prepared, (TargetUnit, 'engine_blocking_state'))
                        data_adapter = result.one()
                        Immobilizer_DOUT_Source = int(data_adapter.config_param_data_source_uid) if data_adapter else None

                        if Immobilizer_DOUT_Source == 1:
                            Teltonika_ImmobilizerCommand = "setdigout 0 ?"
                        elif Immobilizer_DOUT_Source == 2:
                            Teltonika_ImmobilizerCommand = "setdigout ?0 ?"
                        else:
                            return reply("error", 400, "Immobilizer Configuration Is Non-Compatible ( DOUT-1 or DOUT-2 or DOUT-3 )", '')

                        _SimcardNumber = ""
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute("SELECT device_simcard FROM dll_device_basic_data WHERE device_imei=%s", (TargetUnit,))
                                _dataTunnelLink = cursor.fetchone()
                                _SimcardID = _dataTunnelLink[0] if _dataTunnelLink else None

                                if _SimcardID:
                                    cursor.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid=%s", (str(_SimcardID),))
                                    _tunnelLink = cursor.fetchone()
                                    _SimcardNumber = str(_tunnelLink[0]) if _tunnelLink else ""

                        if _SimcardNumber:
                            if _SimcardNumber[:3] == '256':
                                SendUG_Sms("+" + str(_SimcardNumber), Teltonika_ImmobilizerCommand)
                            elif _SimcardNumber[:4] == '+256':
                                phone_number = _SimcardNumber[1:]
                                SendUG_Sms(phone_number, Teltonika_ImmobilizerCommand)

                        LogDate = datetime.datetime.now().date()
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                    (TargetUnit, Teltonika_ImmobilizerCommand, UserCommanding, LogDate)
                                )
                        return reply("success", 200, "Restore Command Transmition SuccessFul", '')

                    elif ExistingHardware == 'concox':
                        Concox_ImmobilizerCommand = "RELAY,0#"
                        _SimcardNumber = ""
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute("SELECT device_simcard FROM dll_device_basic_data WHERE device_imei=%s", (TargetUnit,))
                                _dataTunnelLink = cursor.fetchone()
                                _SimcardID = _dataTunnelLink[0] if _dataTunnelLink else None

                                if _SimcardID:
                                    cursor.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid=%s", (str(_SimcardID),))
                                    _tunnelLink = cursor.fetchone()
                                    _SimcardNumber = str(_tunnelLink[0]) if _tunnelLink else ""

                        if _SimcardNumber:
                            if _SimcardNumber[:3] == '256':
                                SendUG_Sms("+" + str(_SimcardNumber), Concox_ImmobilizerCommand)
                            elif _SimcardNumber[:4] == '+256':
                                phone_number = _SimcardNumber[1:]
                                SendUG_Sms(phone_number, Concox_ImmobilizerCommand)

                        LogDate = datetime.datetime.now().date()
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                    (TargetUnit, Concox_ImmobilizerCommand, UserCommanding, LogDate)
                                )
                        return reply("success", 200, "Restore Command Transmition SuccessFul", '')

                    elif ExistingHardware == 'xirgo_global':
                        Xirgo_ResetImmobilizerCommand = "RELAY,0#"
                        _SimcardNumber = ""
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute("SELECT device_simcard FROM dll_device_basic_data WHERE device_imei=%s", (TargetUnit,))
                                _dataTunnelLink = cursor.fetchone()
                                _SimcardID = _dataTunnelLink[0] if _dataTunnelLink else None

                                if _SimcardID:
                                    cursor.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid=%s", (str(_SimcardID),))
                                    _tunnelLink = cursor.fetchone()
                                    _SimcardNumber = str(_tunnelLink[0]) if _tunnelLink else ""

                        if _SimcardNumber:
                            if _SimcardNumber[:3] == '256':
                                SendUG_Sms("+" + str(_SimcardNumber), Xirgo_ResetImmobilizerCommand)
                            elif _SimcardNumber[:4] == '+256':
                                phone_number = _SimcardNumber[1:]
                                SendUG_Sms(phone_number, Xirgo_ResetImmobilizerCommand)

                        LogDate = datetime.datetime.now().date()
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                    (TargetUnit, Xirgo_ResetImmobilizerCommand, UserCommanding, LogDate)
                                )
                        return reply("success", 200, "Restore Command Transmition SuccessFul", '')

                    elif ExistingHardware == 'king_sword':
                        KingSword_ResetImmobilizerCommand = "RELAY,0#"
                        _SimcardNumber = ""
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute("SELECT device_simcard FROM dll_device_basic_data WHERE device_imei=%s", (TargetUnit,))
                                _dataTunnelLink = cursor.fetchone()
                                _SimcardID = _dataTunnelLink[0] if _dataTunnelLink else None

                                if _SimcardID:
                                    cursor.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid=%s", (str(_SimcardID),))
                                    _tunnelLink = cursor.fetchone()
                                    _SimcardNumber = str(_tunnelLink[0]) if _tunnelLink else ""

                        if _SimcardNumber:
                            if _SimcardNumber[:3] == '256':
                                SendUG_Sms("+" + str(_SimcardNumber), KingSword_ResetImmobilizerCommand)
                            elif _SimcardNumber[:4] == '+256':
                                phone_number = _SimcardNumber[1:]
                                SendUG_Sms(phone_number, KingSword_ResetImmobilizerCommand)

                        LogDate = datetime.datetime.now().date()
                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                    (TargetUnit, KingSword_ResetImmobilizerCommand, UserCommanding, LogDate)
                                )
                        return reply("success", 200, "Restore Command Transmition SuccessFul", '')

                    elif ExistingHardware == 'other':
                        if len(str(CustomCommand_Text)) > 1:
                            #Start Send SMS HERE
                            #End Send SMS HERE
                            LogDate = datetime.datetime.now().date()
                            with dbconnect:
                                with dbconnect.cursor() as cursor:
                                    cursor.execute(
                                        "INSERT INTO dll_command_sending_logs (device_commanded, command_sent, user_commanding, date_commanded) VALUES(%s,%s,%s,%s)",
                                        (TargetUnit, CustomCommand_Text, UserCommanding, LogDate)
                                    )
                            return reply("success", 200, "Restore Command Transmition SuccessFul", '')
                        else:
                            return reply("success", 400, "Custom Command Text Missing", '')

                    else:
                        return reply('error', 400, 'Hardware Recognition Error', '')
                else:
                    return reply('error', 400, 'No Device Found', '')
            else:
                return reply("error", 400, "Commanding User or Device Unit Imei is Missing", "")
        else:
            return reply('error', 400, 'Custom Command Definition Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
