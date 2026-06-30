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
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.auth import PlainTextAuthProvider
from cassandra import ConsistencyLevel
from cassandra.policies import TokenAwarePolicy, DCAwareRoundRobinPolicy
from cassandra.query import SimpleStatement
from .globals import reply, require_permission
import base64
from .globals import check_device
import uuid


devices_bp = Blueprint('devices', __name__)

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


def get_postgres_connection():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    return dbconnect
#register device
@devices_bp.route("/devices/create", methods=["POST"])
@require_permission('devices.create')
def register_device():

    _cassandra_session = get_cassandra_session()
    if not _cassandra_session:
        return reply('error', 500, 'Failed to connect to Cassandra', '')
    payload_data = request.get_json()

    try:

        if(len(str(payload_data['data']['asset_model'])) > 1) and (len(str(payload_data['data']['unit_vendor'])) > 3) and (len(str(payload_data['data']['unit_imei'])) > 3) and (len(str(payload_data['data']['service_provider'])) > 3):

            AssetModel = str(payload_data['data']['asset_model'])
            AssetVendor = str(payload_data['data']['unit_vendor'])
            AssetImei = str(payload_data['data']['unit_imei'])
            AssetParentOwner = str(payload_data['data']['service_provider'])

            print(f"*********** IMEI Passed : {AssetImei} ***********\n\n")
            select_query = _cassandra_session.prepare("SELECT device_local_uid FROM dll_device_registrar WHERE device_imei = ?")
            rows = _cassandra_session.execute(select_query, [str(AssetImei)])

            if not rows:
                DeviceLocal_UID = str(uuid.uuid4())

                _save_device_query = _cassandra_session.prepare("INSERT INTO dll_device_registrar (device_local_uid, device_imei, device_hardware, device_vendor, device_status, date_created, service_provider_uid, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
                _cassandra_session.execute(_save_device_query,
                    (DeviceLocal_UID, AssetImei, AssetModel, AssetVendor, 'un_used', str(datetime.datetime.now().date()), AssetParentOwner, datetime.datetime.now().date())
                )
                
                data_back = {
                    "device_local_uid": DeviceLocal_UID,
                    "device_imei": AssetImei
                }
                return reply('success', 200, 'Device Registration SuccessFul', data_back)
            
            else:
                return reply('error', 400, 'Imei Number not available', '')
            
        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, error, '')
    

#get all devices
@devices_bp.route("/devices/all", methods=["POST"])
@require_permission('devices.view')
def get_devices():

    _cassandra_session = get_cassandra_session()
    if not _cassandra_session:
        return reply('error', 500, 'Failed to connect to Cassandra', '')
    payload_data = request.get_json()

    try:

        if(len(str(payload_data['data']['data_level'])) > 2) and (len(str(payload_data['data']['account_uid'])) > 2):

            dataLevel = payload_data['data']['data_level']
            AccountID = payload_data['data']['account_uid']

            if(dataLevel == 'service_provider'):
                _data_query = _cassandra_session.prepare("SELECT * FROM dll_device_registrar WHERE service_provider_uid = ? ALLOW FILTERING")
                rows = _cassandra_session.execute(_data_query,(AccountID,))

                if rows:
                    data_adapter = rows
                    devices_found = []

                    for row in data_adapter:
                        single_device = {
                            "device_local_uid": row.device_local_uid,
                            "device_hardware": row.device_hardware,
                            "device_vendor": row.device_vendor,
                            "device_status": row.device_status,
                            "device_imei": row.device_imei,
                            "date_created": row.date_created,
                            "billing_status": check_device(row.device_imei)
                        }

                        devices_found.append(single_device)
                    return reply('success', 200, 'Found Account', devices_found)
                    
                else:
                    return reply('error', 400, 'No Devices Found', '')


            elif(dataLevel == 'client'):

                _data_query = _cassandra_session.prepare("SELECT * FROM dll_device_registrar WHERE client_uid = ?")
                rows = _cassandra_session.execute(
                    _data_query,
                    (AccountID,)
                )

                if rows:
                    data_adapter = rows
                    devices_found = []

                    for row in data_adapter:
                        single_device = {
                            "device_local_uid": row.device_local_uid,
                            "device_hardware": row.device_hardware,
                            "device_vendor": row.device_vendor,
                            "device_status": row.device_status,
                            "device_imei": row.device_imei,
                            "date_created": row.date_created,
                            "billing_status": check_device(row.device_imei)
                        }

                        devices_found.append(single_device)
                    return reply('success', 200, 'Found Account', devices_found)

                else:
                    return reply('error', 400, 'No Devices Found', '')


            elif(dataLevel == 'inhouse'):

                rows = _cassandra_session.execute(
                    "SELECT * FROM dll_device_registrar"
                )

                if rows:
                    data_adapter = rows
                    devices_found = []

                    for row in data_adapter:
                        single_device = {
                            "device_local_uid": row.device_local_uid,
                            "device_hardware": row.device_hardware,
                            "device_vendor": row.device_vendor,
                            "device_status": row.device_status,
                            "device_imei": row.device_imei,
                            "service_provider": row.service_provider_uid,
                            "date_created": row.date_created,
                            "billing_status": check_device(row.device_imei)
                        }

                        devices_found.append(single_device)
                    return reply('success', 200, 'Found Account', devices_found)

                else:
                    return reply('error', 400, 'No Devices Found', '')

            else:
                return reply('error', 400, 'Unknown data level', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


#get configured devices
@devices_bp.route("/devices/configured/all", methods=["POST"])
def get_configured_devices():
    _cassandra_session = get_cassandra_session()
    if not _cassandra_session:
        return reply('error', 500, 'Failed to connect to Cassandra', '')
    payload_data = request.get_json()

    try:
        if(len(str(payload_data['data']['data_level'])) > 2) and (len(str(payload_data['data']['account_uid'])) > 2):
            dataLevel = payload_data['data']['data_level']
            AccountID = payload_data['data']['account_uid']

            if(dataLevel == 'service_provider'):
                _data_query = _cassandra_session.prepare("SELECT device_imei FROM dll_device_registrar WHERE service_provider_uid = ? ALLOW FILTERING")
                rows = _cassandra_session.execute(_data_query, (AccountID,))
                if rows:
                    data_adapter = rows
                    devices_found = []
                    for row in data_adapter:
                        FoundIMEI = row.device_imei
                        _simcard_query = _cassandra_session.prepare("SELECT device_name, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, events_attached, device_billing_status, device_client FROM dll_device_basic_data WHERE device_imei = ?")
                        rows_basic = _cassandra_session.execute(_simcard_query, (FoundIMEI,))
                        DeviceBasicData_Adapter = rows_basic[0] if rows_basic else None
                        if DeviceBasicData_Adapter:
                            SimCard = DeviceBasicData_Adapter.device_simcard
                            # Using PostgreSQL for dll_telecom_assets query
                            conn = get_postgres_connection()
                            cur = conn.cursor()
                            cur.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid = %s", (SimCard,))
                            rows_simcard = cur.fetchone()
                            #conn.close()
                            SimcardData = rows_simcard if rows_simcard else None
                            SimcardNumber = SimcardData[0] if SimcardData else None
                            _hardware_query = _cassandra_session.prepare("SELECT device_vendor, device_hardware FROM dll_device_registrar WHERE device_imei = ?")
                            rows_hardware = _cassandra_session.execute(_hardware_query, (FoundIMEI,))
                            Hardware_dataAdapter = rows_hardware[0] if rows_hardware else None
                            Hardware = Hardware_dataAdapter.device_vendor if Hardware_dataAdapter else None
                            HardwareModel = Hardware_dataAdapter.device_hardware if Hardware_dataAdapter else None
                            
                            # Query to get the client name
                            cur.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid = %s", (DeviceBasicData_Adapter.device_client,))
                            client_record = cur.fetchone()
                            client_name = client_record[0] if client_record else None

                            # Query to get the subscription end date
                            cur.execute("SELECT end_date FROM dll_device_subscriptions WHERE device_imei_number = %s", (FoundIMEI,))
                            subscription_record = cur.fetchone()
                            expiry_date = subscription_record[0] if subscription_record else '0'

                            SingleBasic_Data = {
                                "device_name": DeviceBasicData_Adapter.device_name,
                                "simcard": SimcardNumber,
                                "simcard_uid": SimCard,
                                "car_make": DeviceBasicData_Adapter.device_car_make,
                                "car_model": DeviceBasicData_Adapter.device_car_model,
                                "vin_number": DeviceBasicData_Adapter.device_vin_number,
                                "car_type": DeviceBasicData_Adapter.device_car_type,
                                "events_attached": DeviceBasicData_Adapter.events_attached,
                                "billing_status": DeviceBasicData_Adapter.device_billing_status,
                                "device_imei": FoundIMEI,
                                "subscription_end_date": expiry_date,
                                "client_uid": DeviceBasicData_Adapter.device_client,
                                "client_name": client_name,
                                "hardware": Hardware,
                                "hardware_model": HardwareModel
                            }
                            devices_found.append(SingleBasic_Data)
                    if(len(devices_found) > 0):
                        return reply('success', 200, 'Found Devices', devices_found)
                    elif(len(devices_found) == 0):
                        return reply('error', 400, 'No Devices Found', '')
                else:
                    return reply('error', 400, 'No Devices Found', '')

            elif(dataLevel == 'client'):
                _client_data_query = _cassandra_session.prepare("SELECT device_imei FROM dll_device_basic_data WHERE device_client = ? ALLOW FILTERING")
                rows = _cassandra_session.execute(_client_data_query, (AccountID,))
                if rows:
                    data_adapter = rows
                    devices_found = []
                    for row in data_adapter:
                        FoundIMEI = row.device_imei
                        _simcard_query = _cassandra_session.prepare("SELECT device_name, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, events_attached, device_billing_status, device_client FROM dll_device_basic_data WHERE device_imei = ?")
                        rows_basic = _cassandra_session.execute(_simcard_query, (FoundIMEI,))
                        DeviceBasicData_Adapter = rows_basic[0] if rows_basic else None
                        if True:
                            SimCard = DeviceBasicData_Adapter.device_simcard
                            # Using PostgreSQL for dll_telecom_assets query
                            conn = get_postgres_connection()
                            cur = conn.cursor()
                            cur.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid = %s", (SimCard,))
                            rows_simcard = cur.fetchone()
                            #conn.close()
                            SimcardData = rows_simcard if rows_simcard else None
                            SimcardNumber = SimcardData[0] if SimcardData else None
                            _hardware_query = _cassandra_session.prepare("SELECT device_vendor, device_hardware FROM dll_device_registrar WHERE device_imei = ?")
                            rows_hardware = _cassandra_session.execute(_hardware_query, (FoundIMEI,))
                            Hardware_dataAdapter = rows_hardware[0] if rows_hardware else None
                            Hardware = Hardware_dataAdapter.device_vendor if Hardware_dataAdapter else None
                            HardwareModel = Hardware_dataAdapter.device_hardware if Hardware_dataAdapter else None
                            cur.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid = %s", (DeviceBasicData_Adapter.device_client,))
                            client_record = cur.fetchone()
                            client_name = client_record[0] if client_record else None

                            # Query to get the subscription end date
                            cur.execute("SELECT subscription_status FROM dll_device_subscriptions WHERE device_imei_number = %s", (FoundIMEI,))
                            subscription_record = cur.fetchone()
                            expiry_date = subscription_record[0] if subscription_record else 'token_subscription_status_not_found'

                            SingleBasic_Data = {
                                "device_name": DeviceBasicData_Adapter.device_name,
                                "simcard": SimcardNumber,
                                "simcard_uid": SimCard,
                                "car_make": DeviceBasicData_Adapter.device_car_make,
                                "car_model": DeviceBasicData_Adapter.device_car_model,
                                "vin_number": DeviceBasicData_Adapter.device_vin_number,
                                "car_type": DeviceBasicData_Adapter.device_car_type,
                                "events_attached": DeviceBasicData_Adapter.events_attached,
                                #"billing_status": 'running',
                                "billing_status": expiry_date,
                                "device_imei": FoundIMEI,
                                "subscription_status": expiry_date,
                                #"subscription_status": "running",
                                "client_uid": DeviceBasicData_Adapter.device_client,
                                "client_name": client_name,
                                "hardware": Hardware,
                                "hardware_model": HardwareModel
                            }
                            devices_found.append(SingleBasic_Data)
                    if(len(devices_found) > 0):
                        return reply('success', 200, 'Found Devices', devices_found)
                    elif(len(devices_found) == 0):
                        return reply('error', 400, 'No Devices Found', '')
                else:
                    return reply('error', 400, 'No Devices Found', '')

            elif(dataLevel == 'inhouse'):
                _inhouse_data_query = _cassandra_session.prepare("SELECT device_imei FROM dll_device_registrar")
                rows = _cassandra_session.execute(_inhouse_data_query)
                if rows:
                    data_adapter = rows
                    devices_found = []
                    for row in data_adapter:
                        FoundIMEI = row.device_imei
                        _simcard_query = _cassandra_session.prepare("SELECT device_name, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, events_attached, device_billing_status, device_client FROM dll_device_basic_data WHERE device_imei = ?")
                        rows_basic = _cassandra_session.execute(_simcard_query, (FoundIMEI,))
                        DeviceBasicData_Adapter = rows_basic[0] if rows_basic else None
                        if DeviceBasicData_Adapter:
                            SimCard = DeviceBasicData_Adapter.device_simcard
                            # Using PostgreSQL for dll_telecom_assets query
                            conn = get_postgres_connection()
                            cur = conn.cursor()
                            cur.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid = %s", (SimCard,))
                            rows_simcard = cur.fetchone()
                            #conn.close()
                            SimcardData = rows_simcard if rows_simcard else None
                            SimcardNumber = SimcardData[0] if SimcardData else None
                            _hardware_query = _cassandra_session.prepare("SELECT device_vendor, device_hardware FROM dll_device_registrar WHERE device_imei = ?")
                            rows_hardware = _cassandra_session.execute(_hardware_query, (FoundIMEI,))
                            Hardware_dataAdapter = rows_hardware[0] if rows_hardware else None
                            Hardware = Hardware_dataAdapter.device_vendor if Hardware_dataAdapter else None
                            HardwareModel = Hardware_dataAdapter.device_hardware if Hardware_dataAdapter else None
                            cur.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid = %s", (DeviceBasicData_Adapter.device_client,))
                            client_record = cur.fetchone()
                            client_name = client_record[0] if client_record else None

                            # Query to get the subscription end date
                            cur.execute("SELECT subscription_status FROM dll_device_subscriptions WHERE device_imei_number = %s", (FoundIMEI,))
                            subscription_record = cur.fetchone()
                            expiry_date = subscription_record[0] if subscription_record else 'token_subscription_status_not_found'

                            SingleBasic_Data = {
                                "device_name": DeviceBasicData_Adapter.device_name,
                                "simcard": SimcardNumber,
                                "simcard_uid": SimCard,
                                "car_make": DeviceBasicData_Adapter.device_car_make,
                                "car_model": DeviceBasicData_Adapter.device_car_model,
                                "vin_number": DeviceBasicData_Adapter.device_vin_number,
                                "car_type": DeviceBasicData_Adapter.device_car_type,
                                "events_attached": DeviceBasicData_Adapter.events_attached,
                                #"billing_status": 'running',
                                "billing_status": expiry_date,
                                "client_uid": DeviceBasicData_Adapter.device_client,
                                "client_name": client_name,
                                "subscription_status": expiry_date,
                                #"subscription_status": "running",
                                "hardware": Hardware,
                                "hardware_model": HardwareModel,
                                "device_imei": FoundIMEI 
                            }
                            devices_found.append(SingleBasic_Data)
                    return reply('success', 200, 'Found Devices', devices_found)
                else:
                    return reply('error', 400, 'No Devices Found', '')
            else:
                return reply('error', 400, 'Unknown data level', '')
        else:
            return reply('error', 400, 'Something Is Missing', '')
    except Exception as error:
        return reply('error', 500, error, '')


@devices_bp.route("/system32/devices/configured/all", methods=["POST"])
def get_system32_configured_devices():
    _cassandra_session = get_cassandra_session()
    if not _cassandra_session:
        return reply('error', 500, 'Failed to connect to Cassandra', '')
    payload_data = request.get_json()

    try:
        if(len(str(payload_data['data']['data_level'])) > 2) and (len(str(payload_data['data']['account_uid'])) > 2):
            dataLevel = payload_data['data']['data_level']
            AccountID = payload_data['data']['account_uid']

            if(dataLevel == 'service_provider'):
                _data_query = _cassandra_session.prepare("SELECT device_imei FROM dll_device_registrar WHERE service_provider_uid = ? ALLOW FILTERING")
                rows = _cassandra_session.execute(_data_query, (AccountID,))
                if rows:
                    data_adapter = rows
                    devices_found = []
                    for row in data_adapter:
                        FoundIMEI = row.device_imei
                        _simcard_query = _cassandra_session.prepare("SELECT device_name, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, events_attached, device_billing_status, device_client FROM dll_device_basic_data WHERE device_imei = ?")
                        rows_basic = _cassandra_session.execute(_simcard_query, (FoundIMEI,))
                        DeviceBasicData_Adapter = rows_basic[0] if rows_basic else None
                        if DeviceBasicData_Adapter:
                            SimCard = DeviceBasicData_Adapter.device_simcard
                            # Using PostgreSQL for dll_telecom_assets query
                            conn = get_postgres_connection()
                            cur = conn.cursor()
                            cur.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid = %s", (SimCard,))
                            rows_simcard = cur.fetchone()
                            #conn.close()
                            SimcardData = rows_simcard if rows_simcard else None
                            SimcardNumber = SimcardData[0] if SimcardData else None
                            _hardware_query = _cassandra_session.prepare("SELECT device_vendor, device_hardware FROM dll_device_registrar WHERE device_imei = ?")
                            rows_hardware = _cassandra_session.execute(_hardware_query, (FoundIMEI,))
                            Hardware_dataAdapter = rows_hardware[0] if rows_hardware else None
                            Hardware = Hardware_dataAdapter.device_vendor if Hardware_dataAdapter else None
                            HardwareModel = Hardware_dataAdapter.device_hardware if Hardware_dataAdapter else None
                            
                            # Query to get the client name
                            cur.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid = %s", (DeviceBasicData_Adapter.device_client,))
                            client_record = cur.fetchone()
                            client_name = client_record[0] if client_record else None

                            # Query to get the subscription end date
                            cur.execute("SELECT end_date FROM dll_device_subscriptions WHERE device_imei_number = %s", (FoundIMEI,))
                            subscription_record = cur.fetchone()
                            expiry_date = subscription_record[0] if subscription_record else '0'

                            SingleBasic_Data = {
                                "device_name": DeviceBasicData_Adapter.device_name,
                                "simcard": SimcardNumber,
                                "simcard_uid": SimCard,
                                "car_make": DeviceBasicData_Adapter.device_car_make,
                                "car_model": DeviceBasicData_Adapter.device_car_model,
                                "vin_number": DeviceBasicData_Adapter.device_vin_number,
                                "car_type": DeviceBasicData_Adapter.device_car_type,
                                "events_attached": DeviceBasicData_Adapter.events_attached,
                                "billing_status": DeviceBasicData_Adapter.device_billing_status,
                                "device_imei": FoundIMEI,
                                "subscription_end_date": expiry_date,
                                "client_uid": DeviceBasicData_Adapter.device_client,
                                "client_name": client_name,
                                "hardware": Hardware,
                                "hardware_model": HardwareModel
                            }
                            devices_found.append(SingleBasic_Data)
                    if(len(devices_found) > 0):
                        return reply('success', 200, 'Found Devices', devices_found)
                    elif(len(devices_found) == 0):
                        return reply('error', 400, 'No Devices Found', '')
                else:
                    return reply('error', 400, 'No Devices Found', '')

            elif(dataLevel == 'client'):

                _client_data_query = _cassandra_session.prepare("SELECT device_imei FROM dll_device_basic_data WHERE device_client = ? ALLOW FILTERING")
                rows = _cassandra_session.execute(_client_data_query, (AccountID,))
                if rows:
                    data_adapter = rows
                    devices_found = []
                    for row in data_adapter:
                        FoundIMEI = row.device_imei
                        _simcard_query = _cassandra_session.prepare("SELECT device_name, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, events_attached, device_billing_status, device_client FROM dll_device_basic_data WHERE device_imei = ?")
                        rows_basic = _cassandra_session.execute(_simcard_query, (FoundIMEI,))
                        DeviceBasicData_Adapter = rows_basic[0] if rows_basic else None
                        if True:
                            SimCard = DeviceBasicData_Adapter.device_simcard
                            # Using PostgreSQL for dll_telecom_assets query
                            conn = get_postgres_connection()
                            cur = conn.cursor()
                            cur.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid = %s", (SimCard,))
                            rows_simcard = cur.fetchone()
                            #conn.close()
                            SimcardData = rows_simcard if rows_simcard else None
                            SimcardNumber = SimcardData[0] if SimcardData else None
                            _hardware_query = _cassandra_session.prepare("SELECT device_vendor, device_hardware FROM dll_device_registrar WHERE device_imei = ?")
                            rows_hardware = _cassandra_session.execute(_hardware_query, (FoundIMEI,))
                            Hardware_dataAdapter = rows_hardware[0] if rows_hardware else None
                            Hardware = Hardware_dataAdapter.device_vendor if Hardware_dataAdapter else None
                            HardwareModel = Hardware_dataAdapter.device_hardware if Hardware_dataAdapter else None
                            cur.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid = %s", (DeviceBasicData_Adapter.device_client,))
                            client_record = cur.fetchone()
                            client_name = client_record[0] if client_record else None

                            SingleBasic_Data = {
                                "device_name": DeviceBasicData_Adapter.device_name,
                                "simcard": SimCard,
                                "simcard_uid": SimCard,
                                "car_make": DeviceBasicData_Adapter.device_car_make,
                                "car_model": DeviceBasicData_Adapter.device_car_model,
                                "vin_number": DeviceBasicData_Adapter.device_vin_number,
                                "car_type": DeviceBasicData_Adapter.device_car_type,
                                "events_attached": DeviceBasicData_Adapter.events_attached,
                                #"billing_status": 'running',
                                "device_imei": FoundIMEI,
                                #"subscription_status": expiry_date,
                                #"subscription_status": "running",
                                "client_uid": DeviceBasicData_Adapter.device_client,
                                "client_name": client_name,
                                "hardware": Hardware,
                                "hardware_model": HardwareModel
                            }
                            devices_found.append(SingleBasic_Data)
                    if(len(devices_found) > 0):
                        return reply('success', 200, 'Found Devices', devices_found)
                    elif(len(devices_found) == 0):
                        return reply('error', 400, 'No Devices Found', '')
                else:
                    return reply('error', 400, 'No Devices Found', '')

            elif(dataLevel == 'inhouse'):
                _inhouse_data_query = _cassandra_session.prepare("SELECT device_imei FROM dll_device_basic_data")
                rows = _cassandra_session.execute(_inhouse_data_query)
                if rows:
                    data_adapter = rows
                    devices_found = []
                    for row in data_adapter:
                        FoundIMEI = row.device_imei
                        _simcard_query = _cassandra_session.prepare("SELECT device_name, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, events_attached, device_billing_status, device_client FROM dll_device_basic_data WHERE device_imei = ?")
                        rows_basic = _cassandra_session.execute(_simcard_query, (FoundIMEI,))
                        DeviceBasicData_Adapter = rows_basic[0] if rows_basic else None
                        if DeviceBasicData_Adapter:
                            SimCard = DeviceBasicData_Adapter.device_simcard
                            # Using PostgreSQL for dll_telecom_assets query
                            conn = get_postgres_connection()
                            cur = conn.cursor()
                            cur.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid = %s", (SimCard,))
                            rows_simcard = cur.fetchone()
                            #conn.close()
                            SimcardData = rows_simcard if rows_simcard else None
                            SimcardNumber = SimcardData[0] if SimcardData else None
                            _hardware_query = _cassandra_session.prepare("SELECT device_vendor, device_hardware FROM dll_device_registrar WHERE device_imei = ?")
                            rows_hardware = _cassandra_session.execute(_hardware_query, (FoundIMEI,))
                            Hardware_dataAdapter = rows_hardware[0] if rows_hardware else None
                            Hardware = Hardware_dataAdapter.device_vendor if Hardware_dataAdapter else None
                            HardwareModel = Hardware_dataAdapter.device_hardware if Hardware_dataAdapter else None
                            cur.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid = %s", (DeviceBasicData_Adapter.device_client,))
                            client_record = cur.fetchone()
                            client_name = client_record[0] if client_record else None

                            # Query to get the subscription end date
                            cur.execute("SELECT subscription_status FROM dll_device_subscriptions WHERE device_imei_number = %s", (FoundIMEI,))
                            subscription_record = cur.fetchone()
                            expiry_date = subscription_record[0] if subscription_record else 'token_subscription_status_not_found'

                            SingleBasic_Data = {
                                "device_name": DeviceBasicData_Adapter.device_name,
                                "simcard": SimCard,
                                "simcard_uid": SimCard,
                                "car_make": DeviceBasicData_Adapter.device_car_make,
                                "car_model": DeviceBasicData_Adapter.device_car_model,
                                "vin_number": DeviceBasicData_Adapter.device_vin_number,
                                "car_type": DeviceBasicData_Adapter.device_car_type,
                                "events_attached": DeviceBasicData_Adapter.events_attached,
                                #"billing_status": 'running',
                                "client_uid": DeviceBasicData_Adapter.device_client,
                                "client_name": client_name,
                                #"subscription_status": expiry_date,
                                #"subscription_status": "running",
                                "hardware": Hardware,
                                "hardware_model": HardwareModel,
                                "device_imei": FoundIMEI 
                            }
                            devices_found.append(SingleBasic_Data)
                    return reply('success', 200, 'Found Devices', devices_found)
                else:
                    return reply('error', 400, 'No Devices Found', '')
            else:
                return reply('error', 400, 'Unknown data level', '')
        else:
            return reply('error', 400, 'Something Is Missing', '')
    except Exception as error:
        return reply('error', 500, error, '')


@devices_bp.route("/devices/action", methods=["POST"])
@require_permission('devices.command')
def action():
    
    payload_data = request.get_json()

    try:
        if (len(str(payload_data['data']['device_imei'])) > 3) and (len(str(payload_data['data']['action'])) > 2):

            DeviceLocalID = str(payload_data['data']['device_imei'])
            Action = str(payload_data['data']['action'])

            _cassandra_session = get_cassandra_session()
            if not _cassandra_session:
                return reply('error', 500, 'Failed to connect to Cassandra', '')

            logs = []

            if Action == 'delete':
                # Cassandra tables to check/delete
                cassandra_tables = [
                    ("dll_device_registrar", "device_imei"),
                    ("dll_device_basic_data", "device_imei"),
                    ("dll_device_local_configs", "local_device_imei"),
                    ("dll_location_registry", "data_device_imei"),
                    ("dll_wetrack_status_registry", "device_data_imei"),
                ]
                # Postgres tables to check/delete (these remain)
                postgres_tables = [
                    ("dll_fuel_level_logs", "device_imei"),
                    ("dll_mileage_logs", "device_imei"),
                    ("dll_display_params_config", "device_imei")
                ]

                # Helper for Cassandra deletes
                def cassandra_check_and_delete(table, column, value):
                    select_q = f"SELECT {column} FROM {table} WHERE {column} = ? LIMIT 1"
                    delete_q = f"DELETE FROM {table} WHERE {column} = ?"
                    stmt_select = _cassandra_session.prepare(select_q)
                    result = _cassandra_session.execute(stmt_select, (value,))
                    logs.append(f"Cassandra: Running query: {select_q} with value {value}")
                    if result and result.one():
                        logs.append(f"Record found in {table}, proceeding to delete in Cassandra.")
                        stmt_del = _cassandra_session.prepare(delete_q)
                        _cassandra_session.execute(stmt_del, (value,))
                        logs.append(f"Deleted from {table} where {column} = {value} (Cassandra)")
                    else:
                        logs.append(f"No record found in {table} where {column} = {value} (Cassandra)")

                # Helper for Postgres deletes
                def postgres_check_and_delete(table, column, value, cursor):
                    query_check = f"SELECT 1 FROM {table} WHERE {column} = %s LIMIT 1;"
                    query_delete = f"DELETE FROM {table} WHERE {column} = %s;"
                    logs.append(f"Postgres: Running query: {query_check} with value {value}")
                    cursor.execute(query_check, (value,))
                    if cursor.fetchone():  # If a record exists
                        logs.append(f"Record found in {table}, proceeding to delete. (Postgres)")
                        logs.append(f"Running query: {query_delete} with value {value}")
                        cursor.execute(query_delete, (value,))
                        logs.append(f"Deleted from {table} where {column} = {value} (Postgres)")
                    else:
                        logs.append(f"No record found in {table} where {column} = {value} (Postgres)")

                # Delete from Cassandra tables
                for table, col in cassandra_tables:
                    cassandra_check_and_delete(table, col, DeviceLocalID)

                # Delete from Postgres tables
                dbconnect = get_postgres_connection()
                with dbconnect:
                    with dbconnect.cursor() as cursor:
                        for table, col in postgres_tables:
                            postgres_check_and_delete(table, col, DeviceLocalID, cursor)
                    dbconnect.commit()
                logs.append("Cassandra & Postgres deletions committed successfully.")

                return reply('success', 200, 'Device deleted successfully', {"logs": logs})

            elif Action == 'block_billing':
                # Use Cassandra to update device_billing_status to 'blocked'
                update_query = "UPDATE dll_device_basic_data SET device_billing_status = ? WHERE device_imei = ?"
                stmt = _cassandra_session.prepare(update_query)
                _cassandra_session.execute(stmt, ('blocked', DeviceLocalID))
                return reply('success', 200, 'Device Blocking Successful', '')
            
            elif Action == 'enable_billing':
                # Use Cassandra to update device_billing_status to 'running'
                update_query = "UPDATE dll_device_basic_data SET device_billing_status = ? WHERE device_imei = ?"
                stmt = _cassandra_session.prepare(update_query)
                _cassandra_session.execute(stmt, ('running', DeviceLocalID))
                return reply('success', 200, 'Device Enabling Successful', '')

            else:
                return reply('error', 400, 'Unknown Action', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


#List Devices By Client
@devices_bp.route("/devices/configured/<string:client_id>/client", methods=["GET"])
def ClientConfigured_Devices(client_id):
    _cassandra_session = get_cassandra_session()
    if not _cassandra_session:
        return reply('error', 500, 'Failed to connect to Cassandra', '')
    try:
        if(len(str(client_id)) > 5):
            AccountID = str(client_id)
            _client_data_query = _cassandra_session.prepare("SELECT device_imei FROM dll_device_basic_data WHERE device_client = ? ALLOW FILTERING")
            rows = _cassandra_session.execute(_client_data_query, (AccountID,))
            if rows:
                data_adapter = rows
                devices_found = []
                for row in data_adapter:
                    FoundIMEI = row.device_imei
                    _simcard_query = _cassandra_session.prepare("SELECT device_name, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, events_attached, device_billing_status, device_client FROM dll_device_basic_data WHERE device_imei = ?")
                    rows_basic = _cassandra_session.execute(_simcard_query, (FoundIMEI,))
                    DeviceBasicData_Adapter = rows_basic[0] if rows_basic else None
                    if DeviceBasicData_Adapter:
                        SimCard = DeviceBasicData_Adapter.device_simcard
                        # Using PostgreSQL for dll_telecom_assets query
                        conn = get_postgres_connection()
                        cur = conn.cursor()
                        cur.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid = %s", (SimCard,))
                        rows_simcard = cur.fetchone()
                        conn.close()
                        SimcardData = rows_simcard if rows_simcard else None
                        SimcardNumber = SimcardData[0] if SimcardData else None
                        _hardware_query = _cassandra_session.prepare("SELECT device_vendor, device_hardware FROM dll_device_registrar WHERE device_imei = ?")
                        rows_hardware = _cassandra_session.execute(_hardware_query, (FoundIMEI,))
                        Hardware_dataAdapter = rows_hardware[0] if rows_hardware else None
                        Hardware = Hardware_dataAdapter.device_vendor if Hardware_dataAdapter else None
                        HardwareModel = Hardware_dataAdapter.device_hardware if Hardware_dataAdapter else None
                        
                        conn = get_postgres_connection()
                        cur = conn.cursor()
                        cur.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid = %s", (DeviceBasicData_Adapter.device_client,))
                        client_record = cur.fetchone()
                        _ClientName = client_record[0] if client_record else None
                        cur.close()
                        conn.close()

                        # Query to get the subscription end date from PostgreSQL
                        conn = get_postgres_connection()
                        cur = conn.cursor()
                        cur.execute("SELECT subscription_status FROM dll_device_subscriptions WHERE device_imei_number = %s", (FoundIMEI,))
                        subscription_record = cur.fetchone()
                        expiry_date = subscription_record[0] if subscription_record else 'token_subscription_status_not_found'
                        cur.close()
                        conn.close()

                        SingleBasic_Data = {
                            "device_name": DeviceBasicData_Adapter.device_name,
                            "simcard": SimcardNumber,
                            "simcard_uid": SimCard,
                            "car_make": DeviceBasicData_Adapter.device_car_make,
                            "car_model": DeviceBasicData_Adapter.device_car_model,
                            "vin_number": DeviceBasicData_Adapter.device_vin_number,
                            "car_type": DeviceBasicData_Adapter.device_car_type,
                            "events_attached": DeviceBasicData_Adapter.events_attached,
                            "billing_status": "running",
                            "device_imei": FoundIMEI,
                            #"subscription_status": expiry_date,
                            "subscription_status": "running",
                            "client_uid": DeviceBasicData_Adapter.device_client,
                            "client_name": _ClientName,
                            "hardware": Hardware,
                            "hardware_model": HardwareModel
                        }
                        devices_found.append(SingleBasic_Data)
                return reply('success', 200, 'Found Devices', devices_found)
            else:
                return reply('error', 400, 'No Devices Found', '')
        else:
            return reply('error', 400, 'Something Is Missing', '')
    except Exception as error:
        return reply('error', 500, error, '')


@devices_bp.route("/devices/filter/clients/<client_uid>/network/group/<group_uid>/filter-out", methods=["GET"])
def FilterRequest(client_uid, group_uid):
    try:
        ClientID = str(client_uid)
        GroupID = str(group_uid)
        if(ClientID != 'default_option') and (GroupID != 'default_option'):
            #filter by both
            _group_query = _cassandra_session.prepare("SELECT devices_attached FROM dll_device_groups WHERE group_local_uid = ?")
            rows = _cassandra_session.execute(_group_query, (GroupID,))
            if rows:
                data_adapterTunnel = rows[0]
                data_adapter = json.loads(data_adapterTunnel.devices_attached)
                if(len(data_adapter) > 0):
                    devices_found = []
                    for row in data_adapter:
                        FoundIMEI = row
                        _simcard_query = _cassandra_session.prepare("SELECT device_name, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, events_attached, device_billing_status, device_client FROM dll_device_basic_data WHERE device_imei = ?")
                        rows_basic = _cassandra_session.execute(_simcard_query, (FoundIMEI,))
                        DeviceBasicData_Adapter = rows_basic[0] if rows_basic else None
                        if DeviceBasicData_Adapter:
                            SimCard = DeviceBasicData_Adapter.device_simcard
                            # Using PostgreSQL for dll_telecom_assets query
                            conn = get_postgres_connection()
                            cur = conn.cursor()
                            cur.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid = %s", (SimCard,))
                            rows_simcard = cur.fetchone()
                            conn.close()
                            SimcardData = rows_simcard if rows_simcard else None
                            SimcardNumber = SimcardData[0] if SimcardData else None
                            _hardware_query = _cassandra_session.prepare("SELECT device_vendor, device_hardware FROM dll_device_registrar WHERE device_imei = ?")
                            rows_hardware = _cassandra_session.execute(_hardware_query, (FoundIMEI,))
                            Hardware_dataAdapter = rows_hardware[0] if rows_hardware else None
                            Hardware = Hardware_dataAdapter.device_vendor if Hardware_dataAdapter else None
                            HardwareModel = Hardware_dataAdapter.device_hardware if Hardware_dataAdapter else None
                            _client_query = _cassandra_session.prepare("SELECT client_name FROM dll_client_accounts WHERE client_uid = ?")
                            rows_client = _cassandra_session.execute(_client_query, (DeviceBasicData_Adapter.device_client,))
                            _dataLink = rows_client[0] if rows_client else None
                            _ClientName = _dataLink.client_name if _dataLink else None
                            SingleBasic_Data = {
                                "device_name": DeviceBasicData_Adapter.device_name,
                                "simcard": SimcardNumber,
                                "simcard_uid": SimCard,
                                "car_make": DeviceBasicData_Adapter.device_car_make,
                                "car_model": DeviceBasicData_Adapter.device_car_model,
                                "vin_number": DeviceBasicData_Adapter.device_vin_number,
                                "car_type": DeviceBasicData_Adapter.device_car_type,
                                "events_attached": DeviceBasicData_Adapter.events_attached,
                                "billing_status": DeviceBasicData_Adapter.device_billing_status,
                                "device_imei": FoundIMEI,
                                "client_uid": DeviceBasicData_Adapter.device_client,
                                "client_name": _ClientName,
                                "hardware": Hardware,
                                "hardware_model": HardwareModel
                            }
                            devices_found.append(SingleBasic_Data)
                    return reply('success', 200, 'Found Devices', devices_found)
                else:
                    return reply('error', 400, 'No Devices Found', '')
            else:
                return reply('error', 400, 'No Devices Found', '')
        elif(ClientID != 'default_option') and (GroupID == 'default_option'):
            #filter by client id
            _client_data_query = _cassandra_session.prepare("SELECT device_imei FROM dll_device_basic_data WHERE device_client = ?")
            rows = _cassandra_session.execute(_client_data_query, (ClientID,))
            if rows:
                data_adapter = rows
                devices_found = []
                for row in data_adapter:
                    FoundIMEI = row.device_imei
                    _simcard_query = _cassandra_session.prepare("SELECT device_name, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, events_attached, device_billing_status, device_client FROM dll_device_basic_data WHERE device_imei = ?")
                    rows_basic = _cassandra_session.execute(_simcard_query, (FoundIMEI,))
                    DeviceBasicData_Adapter = rows_basic[0] if rows_basic else None
                    if DeviceBasicData_Adapter:
                        SimCard = DeviceBasicData_Adapter.device_simcard
                        # Using PostgreSQL for dll_telecom_assets query
                        conn = get_postgres_connection()
                        cur = conn.cursor()
                        cur.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid = %s", (SimCard,))
                        rows_simcard = cur.fetchone()
                        conn.close()
                        SimcardData = rows_simcard if rows_simcard else None
                        SimcardNumber = SimcardData[0] if SimcardData else None
                        _hardware_query = _cassandra_session.prepare("SELECT device_vendor, device_hardware FROM dll_device_registrar WHERE device_imei = ?")
                        rows_hardware = _cassandra_session.execute(_hardware_query, (FoundIMEI,))
                        Hardware_dataAdapter = rows_hardware[0] if rows_hardware else None
                        Hardware = Hardware_dataAdapter.device_vendor if Hardware_dataAdapter else None
                        HardwareModel = Hardware_dataAdapter.device_hardware if Hardware_dataAdapter else None
                        _client_query = _cassandra_session.prepare("SELECT client_name FROM dll_client_accounts WHERE client_uid = ?")
                        rows_client = _cassandra_session.execute(_client_query, (DeviceBasicData_Adapter.device_client,))
                        _dataLink = rows_client[0] if rows_client else None
                        _ClientName = _dataLink.client_name if _dataLink else None
                        SingleBasic_Data = {
                            "device_name": DeviceBasicData_Adapter.device_name,
                            "simcard": SimcardNumber,
                            "simcard_uid": SimCard,
                            "car_make": DeviceBasicData_Adapter.device_car_make,
                            "car_model": DeviceBasicData_Adapter.device_car_model,
                            "vin_number": DeviceBasicData_Adapter.device_vin_number,
                            "car_type": DeviceBasicData_Adapter.device_car_type,
                            "events_attached": DeviceBasicData_Adapter.events_attached,
                            "billing_status": DeviceBasicData_Adapter.device_billing_status,
                            "device_imei": FoundIMEI,
                            "client_uid": DeviceBasicData_Adapter.device_client,
                            "client_name": _ClientName,
                            "hardware": Hardware,
                            "hardware_model": HardwareModel
                        }
                        devices_found.append(SingleBasic_Data)
                return reply('success', 200, 'Found Devices', devices_found)
            else:
                return reply('error', 400, 'No Devices Found', '')
        elif(ClientID == 'default_option') and (GroupID != 'default_option'):
            #filter by client id
            _group_query = _cassandra_session.prepare("SELECT devices_attached FROM dll_device_groups WHERE group_local_uid = ?")
            rows = _cassandra_session.execute(_group_query, (GroupID,))
            if rows:
                data_adapterTunnel = rows[0]
                data_adapter = json.loads(data_adapterTunnel.devices_attached)
                if(len(data_adapter) > 0):
                    devices_found = []
                    for row in data_adapter:
                        FoundIMEI = row
                        _simcard_query = _cassandra_session.prepare("SELECT device_name, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, events_attached, device_billing_status, device_client FROM dll_device_basic_data WHERE device_imei = ?")
                        rows_basic = _cassandra_session.execute(_simcard_query, (FoundIMEI,))
                        DeviceBasicData_Adapter = rows_basic[0] if rows_basic else None
                        if DeviceBasicData_Adapter:
                            SimCard = DeviceBasicData_Adapter.device_simcard
                            # Using PostgreSQL for dll_telecom_assets query
                            conn = get_postgres_connection()
                            cur = conn.cursor()
                            cur.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid = %s", (SimCard,))
                            rows_simcard = cur.fetchone()
                            conn.close()
                            SimcardData = rows_simcard if rows_simcard else None
                            SimcardNumber = SimcardData[0] if SimcardData else None
                            _hardware_query = _cassandra_session.prepare("SELECT device_vendor, device_hardware FROM dll_device_registrar WHERE device_imei = ?")
                            rows_hardware = _cassandra_session.execute(_hardware_query, (FoundIMEI,))
                            Hardware_dataAdapter = rows_hardware[0] if rows_hardware else None
                            Hardware = Hardware_dataAdapter.device_vendor if Hardware_dataAdapter else None
                            HardwareModel = Hardware_dataAdapter.device_hardware if Hardware_dataAdapter else None
                            _client_query = _cassandra_session.prepare("SELECT client_name FROM dll_client_accounts WHERE client_uid = ?")
                            rows_client = _cassandra_session.execute(_client_query, (DeviceBasicData_Adapter.device_client,))
                            _dataLink = rows_client[0] if rows_client else None
                            _ClientName = _dataLink.client_name if _dataLink else None
                            SingleBasic_Data = {
                                "device_name": DeviceBasicData_Adapter.device_name,
                                "simcard": SimcardNumber,
                                "simcard_uid": SimCard,
                                "car_make": DeviceBasicData_Adapter.device_car_make,
                                "car_model": DeviceBasicData_Adapter.device_car_model,
                                "vin_number": DeviceBasicData_Adapter.device_vin_number,
                                "car_type": DeviceBasicData_Adapter.device_car_type,
                                "events_attached": DeviceBasicData_Adapter.events_attached,
                                "billing_status": DeviceBasicData_Adapter.device_billing_status,
                                "device_imei": FoundIMEI,
                                "client_uid": DeviceBasicData_Adapter.device_client,
                                "client_name": _ClientName,
                                "hardware": Hardware,
                                "hardware_model": HardwareModel
                            }
                            devices_found.append(SingleBasic_Data)
                    return reply('success', 200, 'Found Devices', devices_found)
                else:
                    return reply('error', 400, 'No Devices Found', '')
            else:
                return reply('error', 400, 'No Devices Found', '')
        elif(ClientID == 'default_option') and (GroupID == 'default_option'):
            return reply("error", 400, "No Filter Parameter", "")
    except Exception as error:
        return reply("error", 500, str(error), "")


#get single configured device details
@devices_bp.route("/devices/configured/<device_imei>/details")
def single_configured_device(device_imei):
    _cassandra_session = get_cassandra_session()
    if not _cassandra_session:
        return reply('error', 500, 'Failed to connect to Cassandra', '')
    try:
        if(len(str(device_imei)) > 4):
            _basic_data_query = _cassandra_session.prepare("SELECT device_name, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, events_attached, device_billing_status, device_client FROM dll_device_basic_data WHERE device_imei = ?")
            rows = _cassandra_session.execute(_basic_data_query, (device_imei,))
            if rows:
                device_data_adapter = rows[0]
                SimCard = device_data_adapter.device_simcard
                # Using PostgreSQL for dll_telecom_assets query
                conn = get_postgres_connection()
                cur = conn.cursor()
                cur.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid = %s", (SimCard,))
                rows_simcard = cur.fetchone()
                #conn.close()
                SimcardData = rows_simcard if rows_simcard else None
                SimcardNumber = SimcardData[0] if SimcardData else None

                cur.execute("SELECT subscription_status FROM dll_device_subscriptions WHERE device_imei_number = %s", (FoundIMEI,))
                subscription_record = cur.fetchone()
                expiry_date = subscription_record[0] if subscription_record else 'token_subscription_status_not_found'

                device_data = {
                    "device_name": device_data_adapter.device_name,
                    "simcard": SimcardNumber,
                    "simcard_uid": SimCard,
                    "car_make": device_data_adapter.device_car_make,
                    "car_model": device_data_adapter.device_car_model,
                    "vin_number": device_data_adapter.device_vin_number,
                    "car_type": device_data_adapter.device_car_type,
                    "events_attached": device_data_adapter.events_attached,
                    "billing_status": "running",
                    "client_uid": device_data_adapter.device_client,
                    "subscription_end_date": expiry_date,
                    "device_imei": device_imei
                }
                return reply('success', 200, 'Device Found Successful', device_data)
            else:
                return reply('error', 400, 'No Device Found', '')
        else:
            return reply('error', 400, 'Something Is Missing', '')
    except Exception as error:
        return reply('error', 500, str(error), '')

#search for device
@devices_bp.route("/devices/simcards/create", methods=["POST"])
def search_device():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:
        if(len(str(payload_data['data']['telecom'])) > 2) and (len(str(payload_data['data']['simcard_number'])) > 2) and (len(str(payload_data['data']['simcard_owner'])) > 2):

            Telecom = str(payload_data['data']['telecom'])
            SimcardNumber = str(payload_data['data']['simcard_number'])
            SimcardOwner = str(payload_data['data']['simcard_owner'])
            SimcardOwner_Parent = str(payload_data['data']['simcard_owner_parent'])

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_telecom_assets WHERE simcard_number=%s AND asset_telecom=%s;", (SimcardNumber, Telecom,))

                    if(cursor.rowcount == 0):

                        SimcardID = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:17].encode()).decode()

                        cursor.execute("INSERT INTO dll_telecom_assets VALUES(%s, %s, %s, %s, %s, %s, %s)", (SimcardID, Telecom, SimcardNumber, datetime.datetime.now().date(), SimcardOwner, SimcardOwner_Parent, 'open',))

                        data_back = {
                            "simcard_uid": SimcardID
                        }
                        return reply('success', 200, 'Simcard registered', data_back)

                    elif(cursor.rowcount >= 1):
                        return reply('error', 400, 'Simcard number not available', '')
                    
                    else:
                        return reply('error', 400, 'Unable to complete request', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    

#get simcards
@devices_bp.route("/devices/simcards/all", methods=["GET"])
def get_simcards():

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT * FROM dll_telecom_assets")

                if(cursor.rowcount >= 1):

                    data_adapter = cursor.fetchall()
                    simcard_data = []

                    for row in data_adapter:

                        single_simcard = {
                            "simcard_number": row[2],
                            "simcard_uid": row[0],
                            "telecom": row[1],
                            "date_created": row[3],
                            "simcard_status": row[6]
                        }

                        simcard_data.append(single_simcard)

                    return reply('success', 200, 'Simcards Found', simcard_data)

                elif(cursor.rowcount == 0):
                    return reply('error', 400, 'No Simcards Found', '')
                
                else:
                    return reply('error', 400, 'Unable to complete request', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


@devices_bp.route("/devices/simcards/<simcard_owner>/all", methods=["GET"])
def get_simcards_byOwner(simcard_owner):

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    try:

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT * FROM dll_telecom_assets WHERE asset_owner=%s", (str(simcard_owner),))

                if(cursor.rowcount >= 1):

                    data_adapter = cursor.fetchall()
                    simcard_data = []

                    for row in data_adapter:

                        single_simcard = {
                            "simcard_number": row[2],
                            "simcard_uid": row[0],
                            "telecom": row[1],
                            "date_created": row[3],
                            "simcard_status": row[6]
                        }

                        simcard_data.append(single_simcard)

                    return reply('success', 200, 'Simcards Found', simcard_data)

                elif(cursor.rowcount == 0):
                    return reply('error', 400, 'No Simcards Found', '')
                
                else:
                    return reply('error', 400, 'Unable to complete request', '')

    except Exception as error:
        return reply('error', 500, str(error), '')

#update simcard
@devices_bp.route("/devices/simcards/update", methods=["PATCH"])
def update_simcard():

    try:

        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()

        if(len(str(payload_data['data']['simcard_uid'])) > 2) and (len(str(payload_data['data']['simcard_number'])) > 2) and (len(str(payload_data['data']['telecom'])) > 2):

            SimcardUID = str(payload_data['data']['simcard_uid'])
            SimcardNumber = str(payload_data['data']['simcard_number'])
            Telecom = str(payload_data['data']['telecom'])

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT asset_uid FROM dll_telecom_assets WHERE asset_uid=%s;", (SimcardUID,))

                    if(cursor.rowcount == 1):

                        cursor.execute("UPDATE dll_telecom_assets SET asset_telecom=%s, simcard_number=%s WHERE asset_uid=%s;", (Telecom, SimcardNumber, SimcardUID,))

                        return reply('success', 200, 'Simcard Update SuccessFul', '')

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'Simcard Unknown', '')
                    else:
                        return reply('error', 400, 'Unable to complete request', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    


#delete simcard
@devices_bp.route("/devices/simcards/<simcard_uid>/delete", methods=["DELETE"])
def delete_simcard(simcard_uid):

    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT asset_uid FROM dll_telecom_assets WHERE asset_uid=%s;", (str(simcard_uid),))

                if(cursor.rowcount == 1):

                    cursor.execute("DELETE FROM dll_telecom_assets WHERE asset_uid=%s;", (str(simcard_uid),))

                    return reply('success', 200, 'Simcard deleted SuccessFul', '')

                elif(cursor.rowcount == 0):
                    return reply('error', 400, 'Simcard Unknown', '')
                else:
                    return reply('error', 400, 'Unable to complete request', '')


    except Exception as error:
        return reply('error', 500, str(error), '')



#Create New Event
@devices_bp.route("/events/create", methods=["POST"])
def create_new_device_event():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    
    try:
        payload_data = request.get_json()

        if(len(str(payload_data['data']['event_name'])) > 2) and (len(str(payload_data['data']['event_description'])) > 2) and (len(str(payload_data['data']['event_condition'])) > 2) and (len(str(payload_data['data']['event_condition_value'])) > 0) and (len(str(payload_data['data']['event_owner_uid'])) > 2):

            EventName = str(payload_data['data']['event_name'])
            EventDescription = str(payload_data['data']['event_description'])
            EventCondition = str(payload_data['data']['event_condition'])
            AlertEmail = str(payload_data['data']['alert_email'])
            AlertPhoneNumbers = str(payload_data['data']['alert_phone_numbers'])
            AlertChannels = json.dumps(payload_data['data']['alert_channels'])
            EventCondition_value = str(payload_data['data']['event_condition_value'])
            EventOwner = str(payload_data['data']['event_owner_uid'])

            EventID = str(uuid.uuid4())

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("INSERT INTO dll_device_events VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);", (str(EventID), EventName, EventDescription, EventCondition, EventCondition_value, datetime.datetime.now().date(), EventOwner, '0', AlertChannels, AlertEmail, AlertPhoneNumbers,))

                    return reply('success', 200, 'Event Creation SuccessFul', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error',  500, str(error), '')
    

#update_event value and email
    
@devices_bp.route("/events/<string:event_uid>/update", methods=["POST"])
def update_event(event_uid):

    try:

        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()

        if(len(str(payload_data['data']['event_name'])) > 2) and (len(str(payload_data['data']['event_description'])) > 2) and (len(str(payload_data['data']['event_condition'])) > 2) and (len(str(payload_data['data']['event_condition_value'])) > 0):

            EventName = str(payload_data['data']['event_name'])
            EventDescription = str(payload_data['data']['event_description'])
            EventCondition = str(payload_data['data']['event_condition'])
            AlertEmail = str(payload_data['data']['alert_email'])
            AlertPhoneNumbers = str(payload_data['data']['alert_phone_numbers'])
            AlertChannels = json.dumps(payload_data['data']['alert_channels'])
            EventCondition_value = str(payload_data['data']['event_condition_value'])
            Event_UID = str(event_uid)

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_device_events WHERE event_local_uid=%s;", (str(Event_UID),))

                    if(cursor.rowcount == 1):

                        cursor.execute("UPDATE dll_device_events SET event_display_name=%s,event_description=%s,event_condition=%s,event_condition_value=%s,notification_alert_method=%s,notification_alert_channel=%s,notification_phone_numbers=%s WHERE event_local_uid=%s;", (EventName, EventDescription, EventCondition, EventCondition_value, AlertChannels, AlertEmail, AlertPhoneNumbers, Event_UID,))

                        return reply('success', 200, 'Event Update SuccessFul', '')

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'Unable to Find Event', '')

                    else:
                        return reply('error', 400, 'Unable to complete request', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    

#get all events of the account
@devices_bp.route("/events/getall", methods=["POST"])
def get_all_events():

    try:

        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()

        if(len(str(payload_data['data']['load_level'])) > 2) and (len(str(payload_data['data']['owner_uid'])) > 2):

            Load_type = str(payload_data['data']['load_level'])
            Load_owner_uid = str(payload_data['data']['owner_uid'])

            if(Load_type == 'usri'):

                with dbconnect:
                    with dbconnect.cursor() as cursor:
                        cursor.execute("SELECT * FROM dll_device_events WHERE owner_org_uid=%s;", (Load_owner_uid,))

                        if(cursor.rowcount >= 1):

                            data_adapter = cursor.fetchall()
                            events_data = []

                            for event in data_adapter:
                                single_event = {
                                    "event_uid": event[0],
                                    "event_name": event[1],
                                    "description": event[2],
                                    "condition": event[3],
                                    "condition_value": event[4],
                                    "date_created": event[5],
                                    "device_count": event[7],
                                    "alert_methods": event[8],
                                    "alert_email": event[9],
                                    "alert_phone_numbers": event[10]
                                }

                                events_data.append(single_event)
                            
                            cursor.close()
                            return reply('success', 200, 'Events Found', events_data)

                        elif(cursor.rowcount == 0):
                            return reply('error', 400, 'No Events Found', '')
                        else:
                            return reply('error', 400, 'Unable to complete request', '')

            elif(Load_type == 'ussrx'):

                with dbconnect:
                    with dbconnect.cursor() as cursor:
                        cursor.execute("SELECT * FROM dll_device_events")

                        if(cursor.rowcount >= 1):

                            data_adapter = cursor.fetchall()
                            events_data = []

                            for event in data_adapter:
                                single_event = {
                                    "event_uid": event[0],
                                    "event_name": event[1],
                                    "description": event[2],
                                    "condition": event[3],
                                    "condition_value": event[4],
                                    "date_created": event[5],
                                    "device_count": event[7],
                                    "event_owner": event[6],
                                    "alert_methods": event[8],
                                    "alert_email": event[9],
                                    "alert_phone_numbers": event[10]
                                }

                                events_data.append(single_event)

                            cursor.close()
                            return reply('success', 200, 'Events Found', events_data)

                        elif(cursor.rowcount == 0):
                            return reply('error', 400, 'No Events Found', '')
                        else:
                            return reply('error', 400, 'Unable to complete request', '')
                        
                pass
            else:
                return reply('error', 400, 'Unknown load level', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    

@devices_bp.route("/events/<string:event_id>/details", methods=["GET"])
def GetEventDetails(event_id):

    try:

        dbconnect = psycopg2.connect(current_app.config['db_link'])

        if(len(str(event_id)) > 2):

                with dbconnect:
                    with dbconnect.cursor() as cursor:
                        cursor.execute("SELECT * FROM dll_device_events WHERE event_local_uid=%s;", (str(event_id),))

                        if(cursor.rowcount >= 1):

                            data_adapter = cursor.fetchone()
                            
                            single_event = {
                                    "event_uid": data_adapter[0],
                                    "event_name": data_adapter[1],
                                    "description": data_adapter[2],
                                    "condition": data_adapter[3],
                                    "condition_value": data_adapter[4],
                                    "date_created": data_adapter[5],
                                    "device_count": data_adapter[7],
                                    "alert_methods": data_adapter[8],
                                    "alert_email": data_adapter[9],
                                    "alert_phone_numbers": data_adapter[10]
                                }
                            
                            return reply('success', 200, 'Events Found', single_event)

                        elif(cursor.rowcount == 0):
                            return reply('error', 400, 'No Event Found', '')
                        else:
                            return reply('error', 400, 'Unable to complete request', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    
#delete event
@devices_bp.route("/events/<event_uid>/delete", methods=["DELETE"])
def delete_event(event_uid):

    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT event_display_name FROM dll_device_events WHERE event_local_uid=%s;", (str(event_uid),))

                if(cursor.rowcount == 1):

                    cursor.execute("DELETE FROM dll_device_events WHERE event_local_uid=%s;", (str(event_uid),))

                    return reply('success', 200, 'Event Deleted SuccessFul', '')

                elif(cursor.rowcount == 0):
                    return reply('error', 400, 'Event Not Found', '')
                else:
                    return reply('error', 400, 'Unable to complete request', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    

#update device mileage
    
@devices_bp.route("/devices/properties/mileage/update", methods=["POST"])
def UpdateMileage():

    try:

        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()

        if(len(str(payload_data['data']['device_imei'])) > 5) and (len(str(payload_data['data']['updated_mileage'])) > 0):

            DeviceImei = str(payload_data['data']['device_imei'])
            NewMileage = str(payload_data['data']['updated_mileage'])

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_mileage_logs WHERE device_imei=%s;", (DeviceImei,))

                    if(cursor.rowcount == 1):

                        cursor.execute("UPDATE dll_mileage_logs SET mileage_log=%s WHERE device_imei=%s;", (NewMileage, DeviceImei,))

                        return reply('success', 200, 'Mileage Update SuccessFul', '')

                    elif(cursor.rowcount == 0):
                        _saveNewEntry = cursor.execute("INSERT INTO dll_mileage_logs (device_imei, log_date, mileage_log) VALUES(%s, %s, %s)", (DeviceImei, str(datetime.datetime.now().date()), str(NewMileage),))
                        dbconnect.commit()
                        return reply('success', 200, 'Mileage Registration SuccessFul', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    

#update device basic properties

@devices_bp.route("/devices/update/properties", methods=['POST'])
def update_device():
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        update_payload = request.get_json()
        _cassandra_session = get_cassandra_session()

        if (
            len(str(update_payload['data']['device_imei'])) > 4
            and len(str(update_payload['data']['device_name'])) > 1
            and len(str(update_payload['data']['simcard'])) > 4
            and len(str(update_payload['data']['car_make'])) > 4
            and len(str(update_payload['data']['car_model'])) > 4
            and len(str(update_payload['data']['client'])) > 4
            and len(str(update_payload['data']['vin_number'])) > 4
            and len(str(update_payload['data']['car_type'])) > 1
            and len(str(update_payload['data']['current_simcard'])) > 4
        ):

            UpdateImei = str(update_payload['data']['device_imei'])
            UpdateDeviceName = str(update_payload['data']['device_name'])
            UpdateSimcard = str(update_payload['data']['simcard'])
            UpdateCarMake = str(update_payload['data']['car_make'])
            UpdateCarModel = str(update_payload['data']['car_model'])
            UpdateClient = str(update_payload['data']['client'])
            UpdateVinNumber = str(update_payload['data']['vin_number'])
            UpdateCarType = str(update_payload['data']['car_type'])
            UpdateCurrentSimcard = str(update_payload['data']['current_simcard'])

            # Check for device existence in Cassandra instead of Postgres
            select_stmt = _cassandra_session.prepare(
                "SELECT device_hardware FROM dll_device_basic_data WHERE device_imei = ?"
            )
            result = _cassandra_session.execute(select_stmt, (UpdateImei,))
            device_exists = result.one()

            if device_exists:
                # Update device properties in Cassandra (not Postgres)
                update_stmt = _cassandra_session.prepare(
                    """
                    UPDATE dll_device_basic_data SET 
                        device_name = ?, 
                        device_simcard = ?, 
                        device_car_make = ?, 
                        device_car_model = ?, 
                        device_vin_number = ?, 
                        device_client = ?, 
                        device_car_type = ?
                    WHERE device_imei = ?
                    """
                )
                _cassandra_session.execute(
                    update_stmt,
                    (
                        UpdateDeviceName,
                        UpdateSimcard,
                        UpdateCarMake,
                        UpdateCarModel,
                        UpdateVinNumber,
                        UpdateClient,
                        UpdateCarType,
                        UpdateImei,
                    ),
                )

                # Update simcard usage_status in Postgres
                with dbconnect:
                    with dbconnect.cursor() as cursor:
                        cursor.execute(
                            "UPDATE dll_telecom_assets SET usage_status='open' WHERE simcard_number=%s;",
                            (UpdateCurrentSimcard,),
                        )
                        cursor.execute(
                            "UPDATE dll_telecom_assets SET usage_status='used' WHERE simcard_number=%s;",
                            (UpdateSimcard,),
                        )
                    dbconnect.commit()

                return reply('success', 200, 'device properties update successful', '')

            else:
                return reply('error', 400, 'Route Failed, device Not Found', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    

#Attach Device to Event
@devices_bp.route("/devices/events/<string:event_uid>/attach", methods=["POST"])
def AttachDevice(event_uid):

    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        devices_payload = request.get_json()
        _devicesAttached = devices_payload['data']['device_list']

        if(len(str(event_uid)) > 10) and (len(_devicesAttached) > 0):

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT device_count FROM dll_device_events WHERE event_local_uid=%s", (str(event_uid),))

                    if(cursor.rowcount == 1):
                        for _FocusDevice in _devicesAttached:
                            cursor.execute("SELECT events_attached FROM dll_device_basic_data WHERE device_imei=%s", (str(_FocusDevice),))

                            if(cursor.rowcount == 1):
                                _dataTunnelLink = cursor.fetchone()
                                _AttachedExisting_Events = json.loads(_dataTunnelLink[0])

                                if(event_uid not in _AttachedExisting_Events):
                                    _AttachedExisting_Events.append(event_uid)
                                    _NewAttachedEvents_Objt = json.dumps(_AttachedExisting_Events)
                                    cursor.execute("UPDATE dll_device_basic_data SET events_attached=%s WHERE device_imei=%s", (str(_NewAttachedEvents_Objt), str(_FocusDevice),))

                                    cursor.execute("SELECT device_count FROM dll_device_events WHERE event_local_uid=%s", (str(event_uid),))
                                    _dataTunnel = cursor.fetchone()
                                    _EventDevice_Count = _dataTunnel[0]
                                    _NewDevice_Count = int(_EventDevice_Count) + 1
                                    cursor.execute("UPDATE dll_device_events SET device_count=%s WHERE event_local_uid=%s", (str(_NewDevice_Count), str(event_uid),))
                                
                            else:
                                pass

                        return reply("success", 200, "Devices Attached SuccessFuly", "")
                    
                    elif(cursor.rowcount == 0):
                        return reply('error', 400, "Event Route Not Found", "")
                    
        else:
            return reply("error", 400, "Some data Is Missing", "")

    except Exception as error:
        return reply('error', 500, str(error), "")


#remove Event from device

@devices_bp.route("/devices/<string:device_id>/events/<string:event_uid>/remove", methods=["PUT"])
def RemoveEvent(device_id, event_uid):

    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        _EventID_Focus = str(event_uid)
        _Device_Focus = str(device_id)

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT events_attached FROM dll_device_basic_data WHERE device_imei=%s", (_Device_Focus,))

                if(cursor.rowcount == 1):

                    _dataTunnelLink = cursor.fetchone()
                    _ExistingEvents = _dataTunnelLink[0]
                    _TheEventsObject = json.loads(_ExistingEvents)

                    if(_EventID_Focus in _TheEventsObject):
                        _TheEventsObject.remove(_EventID_Focus)

                        _UpdatedEvents_Object = json.dumps(_TheEventsObject)
                        cursor.execute("UPDATE dll_device_basic_data SET events_attached=%s WHERE device_imei=%s", (str(_UpdatedEvents_Object) ,str(_Device_Focus),))
                        
                        cursor.execute("SELECT device_count FROM dll_device_events WHERE event_local_uid=%s", (str(_EventID_Focus),))
                        _dataTunnelPipe = cursor.fetchone()
                        _EventCurrentDevice_Count = int(_dataTunnelPipe[0])
                        _NewEventDevice_Count = _EventCurrentDevice_Count - 1

                        cursor.execute("UPDATE dll_device_events SET device_count=%s WHERE event_local_uid=%s", (str(_NewEventDevice_Count), str(_EventID_Focus),))

                        return reply('success', 200, "Event Removed", _TheEventsObject)
                    
                    else:
                        return reply("error", 400, "Event Is Not Attached", "")

                else:
                    return reply('error', 400, "Device Not Found", "")

    except Exception as error:
        return reply('error', 500, str(error), "")


@devices_bp.route("/devices/<string:device_imei>/events", methods=["GET"])
def GetDevice_Events(device_imei):

    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        _FocusedDevice_ID = str(device_imei)

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT events_attached FROM dll_device_basic_data WHERE device_imei=%s", (str(_FocusedDevice_ID),))

                if(cursor.rowcount == 1):

                    _dataTunnelLink = cursor.fetchone()
                    _deviceEventsList = json.loads(_dataTunnelLink[0])
                    _AttachedEvents = []

                    if(len(_deviceEventsList) > 0):

                        for EventFound in _deviceEventsList:

                            cursor.execute("SELECT event_display_name FROM dll_device_events WHERE event_local_uid=%s", (str(EventFound),))
                            _dataTunnelRoute = cursor.fetchone()
                            _EventName = _dataTunnelRoute[0]
                            _SingleEvent = {
                                "event_name": _EventName,
                                "event_id": EventFound
                            }
                            _AttachedEvents.append(_SingleEvent)

                        return reply("success", 200, "Found Events", _AttachedEvents)
                    
                    elif(len(_deviceEventsList) == 0):
                        return reply("error", 400, "No Events Attached", "")
                    
                elif(cursor.rowcount == 0):
                    return reply("error", 400, "Device Not Found", "")

    except Exception as error:
        return reply("error", 500, str(error), "")


# ── Sync Cassandra device-client mappings into PostgreSQL ────────────────────
# Run once to backfill, then the insert/update hooks keep it current.
@devices_bp.route("/devices/sync-client-devices", methods=["POST"])
def sync_client_devices():
    """
    One-time sync: reads all (device_imei, device_client, device_name) from
    Cassandra dll_device_basic_data and upserts into PostgreSQL dll_client_devices.
    Safe to re-run (uses ON CONFLICT).
    """
    _cassandra_session = get_cassandra_session()
    if not _cassandra_session:
        return reply('error', 500, 'Failed to connect to Cassandra', '')

    try:
        rows = _cassandra_session.execute(
            "SELECT device_imei, device_client, device_name FROM dll_device_basic_data"
        )

        conn = get_postgres_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS dll_client_devices (
                id          SERIAL PRIMARY KEY,
                client_uid  VARCHAR(255) NOT NULL,
                device_imei VARCHAR(50)  NOT NULL UNIQUE,
                device_name VARCHAR(255),
                created_at  TIMESTAMP DEFAULT NOW(),
                updated_at  TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_client_devices_client_uid
            ON dll_client_devices (client_uid)
        """)

        synced = 0
        skipped = 0
        for row in rows:
            imei = row.device_imei
            client = row.device_client
            name = getattr(row, 'device_name', None)

            if not imei or not client:
                skipped += 1
                continue

            cur.execute("""
                INSERT INTO dll_client_devices (client_uid, device_imei, device_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (device_imei)
                DO UPDATE SET client_uid = EXCLUDED.client_uid,
                              device_name = EXCLUDED.device_name,
                              updated_at  = NOW()
            """, (client, imei, name))
            synced += 1

        conn.commit()
        cur.close()
        conn.close()

        return reply('success', 200, f'Synced {synced} devices, skipped {skipped}', {
            'synced': synced,
            'skipped': skipped
        })

    except Exception as error:
        return reply('error', 500, str(error), '')
