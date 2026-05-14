from flask import Flask
from flask import Blueprint
from flask import request
import requests
import json
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
import psycopg2
from .globals import reply
from .globals import config_element_data
from .globals import config_element_formular_data
from .globals import SubscriptionManager
from typing import Any, Dict, Optional, Tuple, List

from cassandra.cluster import Session
from cassandra.query import BatchStatement
from cassandra.query import BatchType

import uuid

device_config = Blueprint('device_configs', __name__)

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

@device_config.route("/configurations/new", methods=["POST"])
def new_configs():
    _cassandra_session = get_cassandra_session()
    if not _cassandra_session:
        return reply('error', 500, 'Failed to connect to Cassandra', '')
    dbconnect = psycopg2.connect(current_app.config["db_link"])

    payload_data = request.get_json()

    try:
        if(len(str(payload_data['data']['device_hardware'])) > 0) and (len(str(payload_data['data']['plate_number'])) > 2) and (len(str(payload_data['data']['simcard_number'])) > 2) and (len(str(payload_data['data']['car_make'])) > 2) and (len(str(payload_data['data']['car_model'])) > 2) and (len(str(payload_data['data']['device_client'])) > 2) and (len(str(payload_data['data']['vin_number'])) > 2) and (len(str(payload_data['data']['car_type'])) > 2) and (len(str(payload_data['data']['ignition_detect'])) > 0) and (len(str(payload_data['data']['engine_blocking'])) > 0) and (len(str(payload_data['data']['driver_detection'])) > 0) and (len(str(payload_data['data']['cfg_usr'])) > 5) and (len(str(payload_data['data']['token_billing_uid'])) > 0):
            
            _DeviceConfigurator = str(payload_data['data']['cfg_usr'])
            _Subscription_Token = str(payload_data['data']['token_billing_uid'])
            Device_Imei = str(payload_data['data']['device_imei'])

            _SubscriptionVerdict = SubscriptionManager("not_neccessary", _Subscription_Token, Device_Imei)
            
            #print(f"Verdict : {_SubscriptionVerdict}")

            if(_SubscriptionVerdict == 'success-proceed'):
            
                Device_Hardware = str(payload_data['data']['device_hardware'])
                Device_PlateNumber = str(payload_data['data']['plate_number'])
                SimcardUID = str(payload_data['data']['simcard_number'])
                Car_Make = str(payload_data['data']['car_make'])
                Car_Model = str(payload_data['data']['car_model'])
                VinNumber = str(payload_data['data']['vin_number'])
                CarType = str(payload_data['data']['car_type'])
                ClientUID = str(payload_data['data']['device_client'])
                # OtherConfigs removed as per request

                CustomInput1 = str(payload_data['data']['custom_input1'])
                CustomInput2 = str(payload_data['data']['custom_input2'])
                CustomInput3 = str(payload_data['data']['custom_input3'])
                CustomInput4 = str(payload_data['data']['custom_input4'])
                IgnitionDetection = str(payload_data['data']['ignition_detect'])
                EngineBlocking_Enabled = str(payload_data['data']['engine_blocking'])
                DriverDetection = str(payload_data['data']['driver_detection'])
                Din1_WorkTime = str(payload_data['data']['din1_work_time'])
                Din2_WorkTime = str(payload_data['data']['din2_work_time'])
                Din3_WorkTime = str(payload_data['data']['din3_work_time'])
                Din4_WorkTime = str(payload_data['data']['din4_work_time'])
                EngineRpm = str(payload_data['data']['engine_rpm'])
                Fuel_Consumption = str(payload_data['data']['fuel_consumption'])
                Fuel_Level = str(payload_data['data']['fuel_level'])
                Milage_Reading = str(payload_data['data']['milage_reading'])
                StateOfChange = str(payload_data['data']['state_of_change'])
                TempratureReading = str(payload_data['data']['temperature_reading'])
                Weight_Reading = str(payload_data['data']['weight_reading'])
                IgnitionFormular = str(payload_data['data']['ignition_formular'])
                Din1_WorkTime_Formular = str(payload_data['data']['din1_worktime_formular'])
                Din2_WorkTime_Formular = str(payload_data['data']['din2_worktime_formular'])
                Din3_WorkTime_Formular = str(payload_data['data']['din3_worktime_formular'])
                Din4_WorkTime_Formular = str(payload_data['data']['din4_worktime_formular'])
                Fuel_Consumption_Formular = str(payload_data['data']['fuel_consumption_formular'])
                Fuel_Level_Formular = str(payload_data['data']['fuel_level_formular'])
                Milage_Formular = str(payload_data['data']['milage_formular'])
                Engine_Rpm_Formular = str(payload_data['data']['engine_rpm_formular'])
                State_Of_Change_Formular = str(payload_data['data']['state_of_change_formular'])
                Temprature_Fomular = str(payload_data['data']['temperature_formular'])
                Weight_Formular = str(payload_data['data']['weight_formular'])
                CustomInput1_Formular = str(payload_data['data']['custom_input1_formular'])
                CustomInput2_Formular = str(payload_data['data']['custom_input2_formular'])
                CustomInput3_Formular = str(payload_data['data']['custom_input3_formular'])
                CustomInput4_Formular = str(payload_data['data']['custom_input4_formular'])
                ReFuel_Liters_PerMinute = str(payload_data['data']['refuel_litres_inminute'])
                ReFuel_Minimum_Litres = str(payload_data['data']['minimum_refuel_litres'])
                Refuel_settling_Time = str(payload_data['data']['refuel_settling_time'])
                Refueling_Speed = str(payload_data['data']['refueling_speed'])
                Read_Drains_FromCan = str(payload_data['data']['read_drains_from_can'])
                Detect_DrainsIn_Motion = str(payload_data['data']['enabled_refueling_speed'])
                MiliVolts_Objects = json.dumps(payload_data['data']['milivolts'])
                MiliVolts_Litres = json.dumps(payload_data['data']['volt_litres'])
                CalculateMileage = str(payload_data['data']['calculate_mileage'])

                select_device_query = _cassandra_session.prepare(
                    "SELECT device_status FROM dll_device_registrar WHERE device_imei = ?"
                )
                result = _cassandra_session.execute(select_device_query, (Device_Imei,))
                if result.one():
                    device_props = result.one()
                    device_status = device_props.device_status

                    if device_status == 'un_used':
                        select_config_query = _cassandra_session.prepare(
                            "SELECT local_config_uid FROM dll_device_local_configs WHERE local_device_imei = ?"
                        )
                        result = _cassandra_session.execute(select_config_query, (Device_Imei,))
                        if not result.one():
                            insert_config_query = _cassandra_session.prepare(
                                "INSERT INTO dll_device_local_configs (local_device_imei, local_config_uid, config_parameter, config_param_data_source_uid, config_formular, last_config_date, last_config_user) VALUES (?, ?, ?, ?, ?, ?, ?)"
                            )
                            insert_basic_query = _cassandra_session.prepare(
                                "INSERT INTO dll_device_basic_data (device_imei, device_simcard, device_car_make, device_car_model, device_vin_number, device_car_type, device_hardware, events_attached, device_billing_status, device_client, date_activated, device_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                            )
                            update_device_query = _cassandra_session.prepare(
                                "UPDATE dll_device_registrar SET device_status = ? WHERE device_imei = ?"
                            )
                            insert_other_query = _cassandra_session.prepare(
                                "INSERT INTO dll_other_settings (device_imei, setting_name, setting_value) VALUES (?, ?, ?)"
                            )

                            # Insert configurations
                            LocalConfig_UID = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID, 'custom_input1', CustomInput1, CustomInput1_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID2 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID2, 'custom_input2', CustomInput2, CustomInput2_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID3 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID3, 'custom_input3', CustomInput3, CustomInput3_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID4 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID4, 'custom_input4', CustomInput4, CustomInput4_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID5 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID5, 'din1_working_time', Din1_WorkTime, Din1_WorkTime_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID6 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID6, 'din2_working_time', Din2_WorkTime, Din2_WorkTime_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID7 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID7, 'din3_working_time', Din3_WorkTime, Din3_WorkTime_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID8 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID8, 'din4_working_time', Din4_WorkTime, Din4_WorkTime_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID9 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID9, 'driver_detection', DriverDetection, 'none', str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID10 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID10, 'engine_blocking_state', EngineBlocking_Enabled, 'none', str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID11 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID11, 'engine_rpm', EngineRpm, Engine_Rpm_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID12 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID12, 'fuel_consumption', Fuel_Consumption, Fuel_Consumption_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID13 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID13, 'fuel_level', Fuel_Level, Fuel_Level_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID14 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID14, 'ignition_detection', IgnitionDetection, IgnitionFormular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID15 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID15, 'mileage_reading', Milage_Reading, Milage_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID16 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID16, 'state_change', StateOfChange, State_Of_Change_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID17 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID17, 'temprature', TempratureReading, Temprature_Fomular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID18 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID18, 'weight', Weight_Reading, Weight_Formular, str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID19 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID19, 'refueling_per_minute', ReFuel_Liters_PerMinute, 'none', str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID20 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID20, 'refueling_minimum', ReFuel_Minimum_Litres, 'none', str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID21 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID21, 'refueling_settling_time', Refuel_settling_Time, 'none', str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID22 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID22, 'refueling_motion_speed', Refueling_Speed, 'none', str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID23 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID23, 'read_drains_from_can', Read_Drains_FromCan, 'none', str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID24 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID24, 'detect_drains_inmotion', Detect_DrainsIn_Motion, 'none', str(datetime.datetime.now().date()), 'sentiel_api'))

                            LocalConfig_UID25 = base64.b64encode(str(str(random.randint(45, 9040000))+str(random.randint(150, 1940101))+str(random.randint(670, 9111202)))[:18].encode()).decode()
                            _cassandra_session.execute(insert_config_query, (Device_Imei, LocalConfig_UID25, 'detect_drains_inmotion', Detect_DrainsIn_Motion, 'none', str(datetime.datetime.now().date()), 'sentiel_api'))

                            t = []
                            Events = json.dumps(t)
                            _todayDate = datetime.datetime.now().date()

                            _cassandra_session.execute(insert_basic_query, (
                                str(Device_Imei), str(SimcardUID),
                                str(Car_Make), str(Car_Model), str(VinNumber), str(CarType), str(Device_Hardware), str(Events), 'running', str(ClientUID), str(_todayDate), str(Device_PlateNumber)
                            ))

                            _cassandra_session.execute(update_device_query, ('used', Device_Imei))

                            with dbconnect:
                                with dbconnect.cursor() as cursor:
                                    if len(MiliVolts_Objects) > 0 and len(MiliVolts_Litres) > 0:
                                        cursor.execute("INSERT INTO dll_calibrated_fuel_data (device_imei, milivots, milivots_fuel) VALUES(%s, %s, %s);", (str(Device_Imei), str(MiliVolts_Objects), str(MiliVolts_Litres)))
                                    else:
                                        pass
                                    cursor.execute("UPDATE dll_telecom_assets SET usage_status = %s WHERE asset_uid = %s;", ('used', str(SimcardUID),))

                            _cassandra_session.execute(insert_other_query, (Device_Imei, 'calculate_mileage', CalculateMileage))

                            return reply('success', 200, 'Device Configuration Successful', '')

                        elif result.one():
                            return reply('error', 400, 'Device Re-Configuration Not Allowed. Update Instead', '')
                        else:
                            return reply('error', 400, 'Unable to complete configuration', '')
                    elif device_status == 'used':
                        return reply('error', 400, 'Device Already Used', '')
                else:
                    return reply('error', 400, 'Unknown Device IMEI', '')
            
            elif _SubscriptionVerdict == 'token-expired':
                return reply('error', 400, 'Token Is Expired', "")

            elif _SubscriptionVerdict == 'token-not-found':
                return reply('error', 400, 'Token Not Found', '')
            else:
                return reply('error', 400, 'Unknown Subscription Error', _SubscriptionVerdict)
        else:
            return reply('error', 400, 'Something Is Missing', '')
        
    except Exception as error:
        return reply('error', 500, str(error), '')


def generate_local_config_uid(length: int = 18) -> str:
    """
    Generates a compact, URL-safe id.
    - stable length (no '=' padding)
    - low collision risk
    """
    raw = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode("utf-8").rstrip("=")
    return raw[:length]


def _as_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v).strip()


def extract_and_validate_data(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Validates required fields and normalizes input.
    Returns a dict with:
      - normalized strings for most fields
      - list + json-string versions for milivolts / volt_litres
    """
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    # REQUIRED (include device_imei fix)
    required_fields = {
        "device_imei":       lambda v: len(_as_str(v)) >= 14 and _as_str(v).isdigit(),
        "device_hardware":   lambda v: len(_as_str(v)) > 0,
        "plate_number":      lambda v: len(_as_str(v)) > 2,
        "simcard_number":    lambda v: len(_as_str(v)) > 2,
        "car_make":          lambda v: len(_as_str(v)) > 1,
        "car_model":         lambda v: len(_as_str(v)) > 1,
        "device_client":     lambda v: len(_as_str(v)) > 1,
        "vin_number":        lambda v: len(_as_str(v)) > 2,
        "car_type":          lambda v: len(_as_str(v)) > 1,
        "ignition_detect":   lambda v: len(_as_str(v)) > 0,
        "engine_blocking":   lambda v: len(_as_str(v)) > 0,
        "driver_detection":  lambda v: len(_as_str(v)) > 0,
        "cfg_usr":           lambda v: len(_as_str(v)) > 1,
        "payment_uid":       lambda v: len(_as_str(v)) > 0,
    }

    out: Dict[str, Any] = {}
    for k, ok in required_fields.items():
        v = data.get(k)
        if v is None or not ok(v):
            return None
        out[k] = _as_str(v)

    # OPTIONAL (keep as strings)
    optional_keys = [
        "custom_input1", "custom_input2", "custom_input3", "custom_input4",
        "din1_work_time", "din2_work_time", "din3_work_time", "din4_work_time",
        "engine_rpm", "fuel_consumption", "fuel_level", "milage_reading",
        "state_of_change", "temperature_reading", "weight_reading",
        "ignition_formular", "din1_worktime_formular", "din2_worktime_formular",
        "din3_worktime_formular", "din4_worktime_formular",
        "fuel_consumption_formular", "fuel_level_formular", "milage_formular",
        "engine_rpm_formular", "state_of_change_formular", "temperature_formular",
        "weight_formular", "custom_input1_formular", "custom_input2_formular",
        "custom_input3_formular", "custom_input4_formular",
        "refuel_litres_inminute", "minimum_refuel_litres", "refuel_settling_time",
        "refueling_speed", "read_drains_from_can", "enabled_refueling_speed",
        "calculate_mileage",
    ]
    for k in optional_keys:
        out[k] = _as_str(data.get(k, ""))

    # JSON calibration arrays: keep both list + json string
    milivolts_list = data.get("milivolts", [])
    volt_litres_list = data.get("volt_litres", [])

    if not isinstance(milivolts_list, list):
        milivolts_list = []
    if not isinstance(volt_litres_list, list):
        volt_litres_list = []

    out["milivolts_list"] = milivolts_list
    out["volt_litres_list"] = volt_litres_list
    out["milivolts_json"] = json.dumps(milivolts_list)
    out["volt_litres_json"] = json.dumps(volt_litres_list)

    return out


def _ensure_cassandra_keyspace(session: Session) -> None:
    """
    Optional: force keyspace if you set it in config.
    This prevents 'success but writing to wrong keyspace' issues.
    """
    ks = current_app.config.get("CASSANDRA_KEYSPACE")
    if ks:
        session.set_keyspace(ks)


@device_config.route("/system32/configurations/new", methods=["POST"])
def create_new_device_configuration():
    cassandra = get_cassandra_session()
    if not cassandra:
        return reply("error", 500, "Failed to connect to Cassandra", "")

    try:
        _ensure_cassandra_keyspace(cassandra)
    except Exception:
        current_app.logger.exception("Failed to set Cassandra keyspace")

    payload = request.get_json(silent=True)
    validated = extract_and_validate_data(payload)
    if not validated:
        return reply("error", 400, "Missing or invalid required fields (including device_imei)", "")

    data = validated
    imei: str = data["device_imei"]
    today_str = datetime.date.today().isoformat()
    cfg_user = data["cfg_usr"]

    # 1) Notify payment service (now uses sanitized IMEI)
    try:
        payment_response = requests.post(
            f"{current_app.config['base_url']}/system32/payment/update-imei",
            json={"data": {"used_imei": imei, "payment_uid": data["payment_uid"]}},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        payment_reply = payment_response.json() if payment_response.content else {}
    except Exception as exc:
        current_app.logger.exception("Payment update request failed")
        return reply("error", 400, f"Payment update request failed: {str(exc)}", "")

    if payment_response.status_code != 200 or payment_reply.get("status") != "success":
        msg = payment_reply.get("message", "Payment update failed")
        return reply("error", 400, msg, "")

    # 2) Check if already configured (use sanitized IMEI)
    try:
        select_query = cassandra.prepare(
            "SELECT local_config_uid FROM dll_device_local_configs WHERE local_device_imei = ? LIMIT 1"
        )
        existing = cassandra.execute(select_query, (imei,)).one()
        if existing:
            return reply("error", 400, "Device already configured. Use update endpoint instead.", "")
    except Exception as exc:
        current_app.logger.exception("Failed to check existing configuration")
        return reply("error", 500, f"Failed to check existing configuration: {str(exc)}", "")

    # 3) Build config items (parameter, value, formula)
    config_items: List[Tuple[str, str, str]] = [
        ("custom_input1",           data["custom_input1"],            data["custom_input1_formular"]),
        ("custom_input2",           data["custom_input2"],            data["custom_input2_formular"]),
        ("custom_input3",           data["custom_input3"],            data["custom_input3_formular"]),
        ("custom_input4",           data["custom_input4"],            data["custom_input4_formular"]),
        ("din1_working_time",       data["din1_work_time"],           data["din1_worktime_formular"]),
        ("din2_working_time",       data["din2_work_time"],           data["din2_worktime_formular"]),
        ("din3_working_time",       data["din3_work_time"],           data["din3_worktime_formular"]),
        ("din4_working_time",       data["din4_work_time"],           data["din4_worktime_formular"]),
        ("driver_detection",        data["driver_detection"],         "none"),
        ("engine_blocking_state",   data["engine_blocking"],          "none"),
        ("engine_rpm",              data["engine_rpm"],               data["engine_rpm_formular"]),
        ("fuel_consumption",        data["fuel_consumption"],         data["fuel_consumption_formular"]),
        ("fuel_level",              data["fuel_level"],               data["fuel_level_formular"]),
        ("ignition_detection",      data["ignition_detect"],          data["ignition_formular"]),
        ("mileage_reading",         data["milage_reading"],           data["milage_formular"]),
        ("state_change",            data["state_of_change"],          data["state_of_change_formular"]),
        ("temprature",              data["temperature_reading"],      data["temperature_formular"]),
        ("weight",                  data["weight_reading"],           data["weight_formular"]),
        ("refueling_per_minute",    data["refuel_litres_inminute"],   "none"),
        ("refueling_minimum",       data["minimum_refuel_litres"],    "none"),
        ("refueling_settling_time", data["refuel_settling_time"],     "none"),
        ("refueling_motion_speed",  data["refueling_speed"],          "none"),
        ("read_drains_from_can",    data["read_drains_from_can"],     "none"),
        ("detect_drains_inmotion",  data["enabled_refueling_speed"],  "none"),
    ]

    # 4) DB writes (Cassandra + Postgres)
    try:
        insert_config = cassandra.prepare("""
            INSERT INTO dll_device_local_configs (
                local_device_imei, local_config_uid, config_parameter,
                config_param_data_source_uid, config_formular,
                last_config_date, last_config_user
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """)

        insert_basic = cassandra.prepare("""
            INSERT INTO dll_device_basic_data (
                device_imei, device_simcard, device_car_make, device_car_model,
                device_vin_number, device_car_type, device_hardware,
                events_attached, device_billing_status, device_client,
                date_activated, device_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)

        insert_other = cassandra.prepare("""
            INSERT INTO dll_other_settings (device_imei, setting_name, setting_value)
            VALUES (?, ?, ?)
        """)

        # Use UNLOGGED batch (same partition keys = imei) to reduce round-trips
        batch = BatchStatement(batch_type=BatchType.UNLOGGED)

        # configs
        for param, value, formula in config_items:
            # Skip purely empty optional settings with no formula
            if (not value) and (formula == "none"):
                continue
            local_uid = generate_local_config_uid()
            batch.add(insert_config, (
                imei, local_uid, param,
                value, formula,
                today_str, cfg_user
            ))

        # basic device data
        empty_events = json.dumps([])
        batch.add(insert_basic, (
            imei,
            data["simcard_number"],
            data["car_make"],
            data["car_model"],
            data["vin_number"],
            data["car_type"],
            data["device_hardware"],
            empty_events,
            "running",
            data["device_client"],
            today_str,
            data["plate_number"],
        ))

        # other settings (use normalized value; avoid payload raw)
        batch.add(insert_other, (imei, "calculate_mileage", data.get("calculate_mileage", "")))

        # Execute Cassandra batch
        cassandra.execute(batch)

        # Postgres: only insert calibrated data if arrays are non-empty (FIXED check)
        milivolts_list = data["milivolts_list"]
        volt_litres_list = data["volt_litres_list"]
        mv_json = data["milivolts_json"]
        vl_json = data["volt_litres_json"]

        if milivolts_list and volt_litres_list:
            with psycopg2.connect(current_app.config["db_link"]) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO dll_calibrated_fuel_data
                        (device_imei, milivots, milivots_fuel)
                        VALUES (%s, %s, %s)
                        """,
                        (imei, mv_json, vl_json),
                    )
                conn.commit()

        # Light read-back verification (helps catch "wrong env/keyspace")
        try:
            check_basic = cassandra.execute(
                "SELECT device_imei FROM dll_device_basic_data WHERE device_imei = ? LIMIT 1",
                (imei,),
            ).one()

            check_cfg = cassandra.execute(
                "SELECT count(*) AS c FROM dll_device_local_configs WHERE local_device_imei = ?",
                (imei,),
            ).one()

            if not check_basic:
                raise RuntimeError("Cassandra verification failed: dll_device_basic_data row not found after insert.")
            if not check_cfg or int(getattr(check_cfg, "c", 0)) == 0:
                raise RuntimeError("Cassandra verification failed: no local config rows found after insert.")

        except Exception:
            # If you prefer: return error instead of logging.
            current_app.logger.exception("Post-write verification warning (possible wrong env/keyspace)")

        return reply("success", 200, "Device configuration completed successfully", "")

    except Exception as exc:
        current_app.logger.exception("Device config failed")
        return reply("error", 500, f"Configuration failed: {str(exc)}", "")

@device_config.route("/configurations/update", methods=["POST"])
def update_configs():
    _cassandra_session = get_cassandra_session()
    if not _cassandra_session:
        return reply('error', 500, 'Failed to connect to Cassandra', '')
    dbconnect = psycopg2.connect(current_app.config["db_link"])

    payload_data = request.get_json()

    try:
        if(3 < 100):

            Device_Imei = str(payload_data['data']['device_imei'])
            CustomInput1 = str(payload_data['data']['custom_input1'])
            CustomInput2 = str(payload_data['data']['custom_input2'])
            CustomInput3 = str(payload_data['data']['custom_input3'])
            CustomInput4 = str(payload_data['data']['custom_input4'])
            # OtherConfigs removed as per request
            IgnitionDetection = str(payload_data['data']['ignition_detect'])
            EngineBlocking_Enabled = str(payload_data['data']['engine_blocking'])
            DriverDetection = str(payload_data['data']['driver_detection'])
            Din1_WorkTime = str(payload_data['data']['din1_work_time'])
            Din2_WorkTime = str(payload_data['data']['din2_work_time'])
            Din3_WorkTime = str(payload_data['data']['din3_work_time'])
            Din4_WorkTime = str(payload_data['data']['din4_work_time'])
            EngineRpm = str(payload_data['data']['engine_rpm'])
            Fuel_Consumption = str(payload_data['data']['fuel_consumption'])
            Fuel_Level = str(payload_data['data']['fuel_level'])
            Milage_Reading = str(payload_data['data']['milage_reading'])
            StateOfChange = str(payload_data['data']['state_of_change'])
            TempratureReading = str(payload_data['data']['temperature_reading'])
            Weight_Reading = str(payload_data['data']['weight_reading'])
            IgnitionFormular = str(payload_data['data']['ignition_formular'])
            Din1_WorkTime_Formular = str(payload_data['data']['din1_worktime_formular'])
            Din2_WorkTime_Formular = str(payload_data['data']['din2_worktime_formular'])
            Din3_WorkTime_Formular = str(payload_data['data']['din3_worktime_formular'])
            Din4_WorkTime_Formular = str(payload_data['data']['din4_worktime_formular'])
            Fuel_Consumption_Formular = str(payload_data['data']['fuel_consumption_formular'])
            Fuel_Level_Formular = str(payload_data['data']['fuel_level_formular'])
            Milage_Formular = str(payload_data['data']['milage_formular'])
            Engine_Rpm_Formular = str(payload_data['data']['engine_rpm_formular'])
            State_Of_Change_Formular = str(payload_data['data']['state_of_change_formular'])
            Temprature_Fomular = str(payload_data['data']['temperature_formular'])
            Weight_Formular = str(payload_data['data']['weight_formular'])
            CustomInput1_Formular = str(payload_data['data']['custom_input1_formular'])
            CustomInput2_Formular = str(payload_data['data']['custom_input2_formular'])
            CustomInput3_Formular = str(payload_data['data']['custom_input3_formular'])
            CustomInput4_Formular = str(payload_data['data']['custom_input4_formular'])
            ReFuel_Liters_PerMinute = str(payload_data['data']['refuel_litres_inminute'])
            ReFuel_Minimum_Litres = str(payload_data['data']['minimum_refuel_litres'])
            Refuel_settling_Time = str(payload_data['data']['refuel_settling_time'])
            Refueling_Speed = str(payload_data['data']['refueling_speed'])
            Read_Drains_FromCan = str(payload_data['data']['read_drains_from_can'])
            Detect_DrainsIn_Motion = str(payload_data['data']['enabled_refueling_speed'])
            MiliVolts_Objects = payload_data['data']['milivolts']
            MiliVolts_Litres = payload_data['data']['volt_litres']
            CalculateMileage = str(payload_data['data']['calculate_mileage'])

            select_config_query = _cassandra_session.prepare(
                "SELECT local_config_uid FROM dll_device_local_configs WHERE local_device_imei = ?"
            )
            result = _cassandra_session.execute(select_config_query, (Device_Imei,))
            if result.one():
                update_config_query = _cassandra_session.prepare(
                    "UPDATE dll_device_local_configs SET config_param_data_source_uid = ?, config_formular = ? WHERE local_device_imei = ? AND config_parameter = ?"
                )
                update_other_query = _cassandra_session.prepare(
                    "UPDATE dll_other_settings SET setting_value = ? WHERE device_imei = ? AND setting_name = ?"
                )

                _cassandra_session.execute(update_config_query, (CustomInput1, CustomInput1_Formular, Device_Imei, 'custom_input1'))
                _cassandra_session.execute(update_config_query, (CustomInput2, CustomInput2_Formular, Device_Imei, 'custom_input2'))
                _cassandra_session.execute(update_config_query, (CustomInput3, CustomInput3_Formular, Device_Imei, 'custom_input3'))
                _cassandra_session.execute(update_config_query, (CustomInput4, CustomInput4_Formular, Device_Imei, 'custom_input4'))
                _cassandra_session.execute(update_config_query, (Din1_WorkTime, Din1_WorkTime_Formular, Device_Imei, 'din1_working_time'))
                _cassandra_session.execute(update_config_query, (Din2_WorkTime, Din2_WorkTime_Formular, Device_Imei, 'din2_working_time'))
                _cassandra_session.execute(update_config_query, (Din3_WorkTime, Din3_WorkTime_Formular, Device_Imei, 'din3_working_time'))
                _cassandra_session.execute(update_config_query, (Din4_WorkTime, Din4_WorkTime_Formular, Device_Imei, 'din4_working_time'))
                _cassandra_session.execute(update_config_query, (DriverDetection, 'none', Device_Imei, 'driver_detection'))
                _cassandra_session.execute(update_config_query, (EngineBlocking_Enabled, 'none', Device_Imei, 'engine_blocking_state'))
                _cassandra_session.execute(update_config_query, (EngineRpm, Engine_Rpm_Formular, Device_Imei, 'engine_rpm'))
                _cassandra_session.execute(update_config_query, (Fuel_Consumption, Fuel_Consumption_Formular, Device_Imei, 'fuel_consumption'))
                _cassandra_session.execute(update_config_query, (Fuel_Level, Fuel_Level_Formular, Device_Imei, 'fuel_level'))
                _cassandra_session.execute(update_config_query, (IgnitionDetection, IgnitionFormular, Device_Imei, 'ignition_detection'))
                _cassandra_session.execute(update_config_query, (Milage_Reading, Milage_Formular, Device_Imei, 'mileage_reading'))
                _cassandra_session.execute(update_config_query, (StateOfChange, State_Of_Change_Formular, Device_Imei, 'state_change'))
                _cassandra_session.execute(update_config_query, (TempratureReading, Temprature_Fomular, Device_Imei, 'temprature'))
                _cassandra_session.execute(update_config_query, (Weight_Reading, Weight_Formular, Device_Imei, 'weight'))
                _cassandra_session.execute(update_config_query, (ReFuel_Liters_PerMinute, 'none', Device_Imei, 'refueling_per_minute'))
                _cassandra_session.execute(update_config_query, (ReFuel_Minimum_Litres, 'none', Device_Imei, 'refueling_minimum'))
                _cassandra_session.execute(update_config_query, (Refuel_settling_Time, 'none', Device_Imei, 'refueling_settling_time'))
                _cassandra_session.execute(update_config_query, (Refueling_Speed, 'none', Device_Imei, 'refueling_motion_speed'))
                _cassandra_session.execute(update_config_query, (Read_Drains_FromCan, 'none', Device_Imei, 'read_drains_from_can'))
                _cassandra_session.execute(update_config_query, (Detect_DrainsIn_Motion, 'none', Device_Imei, 'detect_drains_inmotion'))

                with dbconnect:
                    with dbconnect.cursor() as cursor:
                        if len(MiliVolts_Objects) > 0 and len(MiliVolts_Litres) > 0:
                            cursor.execute("SELECT milivots, milivots_fuel FROM dll_calibrated_fuel_data WHERE device_imei=%s;", (str(Device_Imei),))
                            if cursor.rowcount >= 1:
                                existing_config = cursor.fetchone()
                                H_M = existing_config[0]
                                C_M = existing_config[1]
                                K_Milivolts = json.loads(H_M)
                                K_MiliVlt_Litres = json.loads(C_M)

                                for item in MiliVolts_Objects:
                                    K_Milivolts.append(item)
                                
                                for item in MiliVolts_Litres:
                                    K_MiliVlt_Litres.append(item)

                                V_Milivots_Upd = json.dumps(K_Milivolts)
                                V_Milivots_Litres_Upd = json.dumps(K_MiliVlt_Litres)

                                cursor.execute("UPDATE dll_calibrated_fuel_data SET milivots=%s, milivots_fuel=%s WHERE device_imei=%s;", (str(V_Milivots_Upd), str(V_Milivots_Litres_Upd), str(Device_Imei),))
                            elif cursor.rowcount == 0:
                                pass

                        cursor.execute("UPDATE dll_other_settings SET setting_value=%s WHERE setting_name=%s AND device_imei=%s;", (str(CalculateMileage), 'calculate_mileage', str(Device_Imei),))

                return reply('success', 200, 'Device Configuration Update SuccessFul', '')

            elif not result.one():
                return reply('error', 400, 'Device Not Found, try again', '')
            else:
                return reply('error', 400, 'Unable to complete configuration update', '')
            
        else:
            return reply('error', 400, 'Something Is Missing', '')
        
    except Exception as error:
        return reply('error', 500, str(error), '')

@device_config.route("/configurations/device/<device_imei>/config-data/<parameter_load>/<parameter_type>/load", methods=["GET"])
def get_config(device_imei, parameter_load, parameter_type):
    _cassandra_session = get_cassandra_session()
    if not _cassandra_session:
        return reply('error', 500, 'Failed to connect to Cassandra', '')

    try:
        select_config_query = _cassandra_session.prepare(
            "SELECT * FROM dll_device_local_configs WHERE local_device_imei = ?"
        )
        result = _cassandra_session.execute(select_config_query, (device_imei,))
        if result.one():
            if parameter_type == "element":
                return_value = config_element_data(parameter_load, device_imei)
                
                device_data = {
                    parameter_load: return_value
                }

                return reply('success', 200, 'Configuration data Found', device_data)

            elif parameter_type == 'formula':
                return_value = config_element_formular_data(parameter_load, device_imei)
                
                device_data = {
                    parameter_load: return_value
                }

                return reply('success', 200, 'Configuration data Found', device_data)

        elif not result.one():
            return reply('error', 400, 'Device Not Found', '')
        else:
            return reply('error', 400, 'Unable to process request', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
