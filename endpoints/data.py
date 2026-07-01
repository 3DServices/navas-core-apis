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
from .globals import compare_years
import base64
import pandas as pd
from psycopg2 import extras
from flask import send_from_directory
from .globals import check_device
import requests
from datetime import datetime, timedelta
from flask import Response
import json
import logging
import time
import os
from .globals import CheckHardware2
from math import radians, sin, cos, sqrt, atan2
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.pagesizes import landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import pytz
import re

from cassandra.cluster import Session, Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.auth import PlainTextAuthProvider
from cassandra import ConsistencyLevel
from cassandra.policies import TokenAwarePolicy, DCAwareRoundRobinPolicy
from cassandra.query import BatchStatement, BatchType

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

data_stream = Blueprint("data_stream", __name__)

timezone = pytz.timezone('Africa/Nairobi')

def is_one_day_behind(target_date_str):
    target_date = datetime.strptime(str(target_date_str), "%d-%m-%Y").date()
    current_date = datetime.now().date()
    one_day_delta = timedelta(days=1)
    date_difference = current_date - target_date
    if abs(date_difference) >= one_day_delta:
        return True
    else:
        return target_date < current_date

def create_pdf(data, from_date, to_date, device_imei, file_name_x):
    # Define the columns and data for the table
    current_dir = os.path.dirname(os.path.abspath(__file__))
    reports_cdn_dir = os.path.join(current_dir, '..', 'reports-cdn')

    table_data = [['Trip Number', 'Trip Date', 'Trip Start Time', 'Trip End Time', 
                   'Trip Start Location', 'Trip End Location', 'Trip Mileage Passed', 
                   'Mileage at Start', 'Mileage at End', 'DriverID']]
    for item in data:
        trip_data = [item["Trip Number"], item["Trip Date"], item["Trip Start Time"], 
                     item["Trip End Time"], item["Trip Start Location"], 
                     item["Trip End Location"], item["Trip Mileage Passed"], 
                     item["Mileage at Start"], item["Mileage at End"], 
                     item["DriverID"]]
        table_data.append(trip_data)

    # Create a PDF document
    pdf_filename = f"{reports_cdn_dir}/{ file_name_x }.pdf"
    doc = SimpleDocTemplate(pdf_filename, pagesize=landscape(A4))

    styles = getSampleStyleSheet()
    heading1 = Paragraph(f"<b>Trips Report For { device_imei}, Period Of { from_date } to { to_date }</b>", styles["Heading3"])
    headings = [[heading1]]
    table_headings = Table(headings, colWidths='*')

    
    table = Table(table_data)

    # Add style to the table
    style = TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('LEFTPADDING', (0, 0), (-1, -1), 5)])

    table.setStyle(style)

    # Reduce font size for table content
    
    table.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 6.5)]))

    # Add the table to the PDF document
    doc.build([table_headings, table])
    
def Config_Sources(GetThis, target_device_imei, target_io_records, target_actual_speed_x):
    # Use Cassandra session instead of psycopg2 connection
    try:
        target_actual_speed = int(target_actual_speed_x)
    except Exception:
        try:
            target_actual_speed = int(float(target_actual_speed_x))
        except Exception:
            target_actual_speed = 0

    session = get_cassandra_session()

    # Helper to run a simple select and return list of rows
    def cassandra_query(q, params):
        try:
            if not session:
                return []
            rs = session.execute(q, params)
            return list(rs)
        except Exception:
            return []

    # Fallback behavior when Cassandra unavailable: rely on speed/defaults
    def ignition_fallback():
        if target_actual_speed <= 5 and target_actual_speed != 0:
            return 'ON'
        elif target_actual_speed > 5:
            return 'ON'
        else:
            return 'OFF'

    if GetThis == 'ignition':
        rows = cassandra_query(
            "SELECT config_param_data_source_uid FROM dll_device_local_configs WHERE config_parameter=%s AND local_device_imei=%s ALLOW FILTERING;",
            ('ignition_detection', str(target_device_imei))
        )

        if len(rows) == 1:
            IgnitionSource = rows[0][0]
            rows2 = cassandra_query(
                "SELECT event_value_executed FROM dll_io_events_executed_logs WHERE event_uid_executed=%s AND io_parent_io_event_uid=%s ALLOW FILTERING;",
                (str(IgnitionSource), str(target_io_records))
            )

            if len(rows2) == 1:
                try:
                    ConfigParameter_Value = int(rows2[0][0])
                except Exception:
                    return ignition_fallback()

                if ConfigParameter_Value == 1:
                    return 'ON'
                elif ConfigParameter_Value == 0:
                    return 'OFF'
                else:
                    return ignition_fallback()
            else:
                return ignition_fallback()
        else:
            return ignition_fallback()

    elif GetThis == 'driver_id':
        rows = cassandra_query(
            "SELECT config_param_data_source_uid FROM dll_device_local_configs WHERE config_parameter=%s AND local_device_imei=%s ALLOW FILTERING;",
            ('driver_detection', str(target_device_imei))
        )

        if len(rows) == 1:
            DriverIDSource = rows[0][0]
            rows2 = cassandra_query(
                "SELECT event_value_executed FROM dll_io_events_executed_logs WHERE event_uid_executed=%s AND io_parent_io_event_uid=%s ALLOW FILTERING;",
                (str(DriverIDSource), str(target_io_records))
            )

            if len(rows2) == 1:
                try:
                    ConfigParameter_Value = int(rows2[0][0])
                except Exception:
                    return 'un_registered'

                HX = hex(ConfigParameter_Value)
                HX_Clean = HX.replace("0x", "")
                original_string = HX_Clean.upper()
                reordered_string = ''.join(original_string[::-1][i:i+2][::-1] for i in range(0, len(original_string), 2))
                try:
                    reordered_string = reordered_string[:14] + '0' + reordered_string[14:]
                except Exception:
                    pass
                return reordered_string
            else:
                return 'un_registered'
        else:
            return 'No_Configuration'

    elif GetThis == 'fuel':
        rows = cassandra_query(
            "SELECT config_param_data_source_uid FROM dll_device_local_configs WHERE config_parameter=%s AND local_device_imei=%s ALLOW FILTERING;",
            ('fuel_level', str(target_device_imei))
        )

        if len(rows) == 1:
            FuelLevelSource = rows[0][0]
            rows2 = cassandra_query(
                "SELECT event_value_executed FROM dll_io_events_executed_logs WHERE event_uid_executed=%s AND io_parent_io_event_uid=%s ALLOW FILTERING;",
                (str(FuelLevelSource), str(target_io_records))
            )

            if len(rows2) == 1:
                ConfigParameter_Value = str(rows2[0][0])
                return ConfigParameter_Value
            else:
                return 'No-Data'
        else:
            return 'No_Configuration'

    elif GetThis == 'mileage':
        rows = cassandra_query(
            "SELECT config_param_data_source_uid FROM dll_device_local_configs WHERE config_parameter=%s AND local_device_imei=%s ALLOW FILTERING;",
            ('mileage_reading', str(target_device_imei))
        )

        if len(rows) == 1:
            MileageSource = rows[0][0]
            rows2 = cassandra_query(
                "SELECT event_value_executed FROM dll_io_events_executed_logs WHERE event_uid_executed=%s AND io_parent_io_event_uid=%s ALLOW FILTERING;",
                (str(MileageSource), str(target_io_records))
            )

            if len(rows2) == 1:
                try:
                    ConfigParameter_Value = rows2[0][0]
                    LatestMileage = round(float(ConfigParameter_Value) / 1000, 10)
                    return LatestMileage
                except Exception:
                    return 'No-Data'
            else:
                return 'No-Data'
        else:
            return 'No-Configuration'

def Calculate_DistanceX(Origin_Lat, Origin_Long, To_Lat, To_Long):
    print("Executed Distance Calc")
    RequestData = requests.get(f"https://api.distancematrix.ai/maps/api/distancematrix/json?origins={Origin_Lat}, {Origin_Long}&destinations={To_Lat}, {To_Long}&key=e7TojyncRvHeDpPQkq76vaEoJnxWBx8Cp9USPtreiwZ4MhSnVuTRGDqO0orgTdCS")
    api_data = RequestData.json()
    
    if(api_data['rows'][0]['elements'][0]['status'] != 'ZERO_RESULTS') and (api_data['rows'][0]['elements'][0]['status'] == 'OK'):

        KiloMeters_Covered = re.sub(r'[^\d.]', '', str(api_data['rows'][0]['elements'][0]['distance']['text']))
        TimeCovered = re.sub(r'[^\d.]', '', str(api_data['rows'][0]['elements'][0]['duration']['text']))

        data_xc = {
            "distance_covered": KiloMeters_Covered,
            "time_covered": TimeCovered
        }

        return json.dumps(data_xc)
    
    elif(api_data['rows'][0]['elements'][0]['status'] == 'ZERO_RESULTS'):
        data_xc = {
            "distance_covered": 'CORDS_ERROR',
            "time_covered": "Nothing"
        }
        return json.dumps(data_xc)



# def find_trips(data_points):
#     trips = []

#     if not data_points:
#         return trips

#     # Sort data points by timestamp
#     sorted_data = sorted(data_points, key=lambda x: x["local_system_timestamp"])

#     trip_started = False
#     current_trip = {"start_point": None, "end_point": None}

#     for point in sorted_data:
#         speed = float(point["speed_log"])

#         # Check if the trip has started
#         if not trip_started and speed > 0:
#             current_trip["start_point"] = point
#             trip_started = True

#         # Check if the trip has ended
#         elif trip_started and speed == 0:
#             current_trip["end_point"] = point
#             trips.append(current_trip)
#             trip_started = False
#             current_trip = {"start_point": None, "end_point": None}

#     # If a trip is ongoing when reaching the end of the data, append it
#     if trip_started:
#         trips.append(current_trip)

#     return trips


def find_trips(data_points):
    trips = []

    if not data_points:
        return trips

    # Sort data points by timestamp
    sorted_data = sorted(data_points, key=lambda x: x["local_system_timestamp"])

    trip_started = False
    current_trip = {"start_point": None, "end_point": None}

    for point in sorted_data:
        speed = float(point["speed_log"])

        # Check if the trip has started
        if not trip_started and speed > 0:
            current_trip["start_point"] = point
            trip_started = True

        # Check if the trip has ended
        elif trip_started and speed == 0:
            current_trip["end_point"] = point

            # Calculate distance between start and end points
            if current_trip["start_point"] and current_trip["end_point"]:
                distance_response = Calculate_DistanceX(current_trip["start_point"]["data_latitude"],
                                                        current_trip["start_point"]["data_longitude"],
                                                        current_trip["end_point"]["data_latitude"],
                                                        current_trip["end_point"]["data_longitude"])

                distance_data = json.loads(distance_response)
                if distance_data["distance_covered"] != "CORDS_ERROR":
                    distance = float(distance_data["distance_covered"])
                else:
                    distance = 0  # Set distance to 0 if calculation error occurs

                # Check if distance between start and end points exceeds threshold
                min_trip_distance = 1  # Minimum trip distance in kilometers
                if distance > min_trip_distance:
                    trips.append(current_trip)

            trip_started = False
            current_trip = {"start_point": None, "end_point": None}

    return trips




def LogReport_Request(request_uid, request_user_uid):
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    try:

        with dbconnect:
            with dbconnect.cursor() as cursor:
                currentLocal_Time = datetime.now(timezone).strftime("%I:%M:%S%p")
                currentLocal_Date = datetime.now(timezone).strftime("%d-%m-%Y")

                FullDateStamp = str(currentLocal_Date) +'_'+ str(currentLocal_Time)

                cursor.execute("INSERT INTO dll_reports_downloadable_files (request_uid, file_path, report_caller, request_status, request_datestamp) VALUES(%s, %s, %s, %s, %s)", (str(request_uid), 'NO_DIR_PATH', request_user_uid, 'in_process', str(FullDateStamp),))

    except Exception as error:
        print(str(error))


def Calculate_Fuel_Datax(mv_list, fuel_list, target_mv):
    if not mv_list or not fuel_list:
        return None  # Handle case where either mv_list or fuel_list is empty

    if target_mv in mv_list:
        return fuel_list[mv_list.index(target_mv)]  # Return corresponding fuel level if target_mv matches a value in mv_list

    if target_mv <= mv_list[0]:
        return fuel_list[0]  # Target millivolt is lower than the lowest provided value
    elif target_mv >= mv_list[-1]:
        return fuel_list[-1]  # Target millivolt is higher than the highest provided value

    # Find the index of the closest lower millivolt reading
    for idx, val in enumerate(mv_list):
        if val >= target_mv:
            lower_idx = idx - 1
            break

    mv_diff = mv_list[lower_idx + 1] - mv_list[lower_idx]
    if mv_diff == 0:
        return fuel_list[lower_idx]  # Avoid division by zero

    side_a = (fuel_list[lower_idx + 1] - fuel_list[lower_idx]) / mv_diff

    target_fuel = side_a * (target_mv - mv_list[lower_idx]) + fuel_list[lower_idx]

    return target_fuel


def Calculate_OBD_Fuel_Data(hex_value):
    # Step 1: Clean the input (remove whitespace and standardize format)
    cleaned_value = hex_value.strip().lower()  # Remove whitespace and convert to lowercase for consistency

    # Step 2: Remove optional "0x" prefix if present
    if cleaned_value.startswith("0x"):
        cleaned_value = cleaned_value[2:]  # Strip "0x" if it exists

    # Step 3: Validate that the remaining string is hexadecimal
    if not all(c in "0123456789abcdef" for c in cleaned_value):
        print("Error: Invalid hex format")
        return None  # Return None or handle as needed for invalid format

    # Step 4: Convert the cleaned hexadecimal string to an integer
    try:
        raw_fuel_value = int(cleaned_value, 16)  # Convert hex to integer
    except ValueError as e:
        print(f"Conversion error: {e}")
        return None

    # Step 5: Apply calibration factor to get fuel level in liters
    calibration_factor = 10  # Example factor, can be adjusted if needed
    calibrated_fuel_level = raw_fuel_value / calibration_factor

    return round(calibrated_fuel_level, 2)


@data_stream.route("/data/msic/fuel-calculator", methods=["POST"])
def CalculateFuel_Level():
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    try:
        payload = request.get_json()

        # Extract values safely
        TargetDevice_IMEI = payload['data'].get('device_imei', '')
        Received_FuelValue = str(int(round(float(payload['data'].get('fuel_lyrical', '0').strip() or 0)))) if payload['data'].get('fuel_lyrical', '').strip().replace('.', '', 1).isdigit() else "0"
        FuelLevel_Source = str(payload['data']['data_source'])

        if(FuelLevel_Source == '270') or (FuelLevel_Source == '12') or (FuelLevel_Source == '201') and (FuelLevel_Source != '84') and (FuelLevel_Source != 'lls_lvl_add1'):

            print(f"Received TargetDevice_IMEI: {TargetDevice_IMEI}")
            print(f"Received Fuel Value: '{Received_FuelValue}' (Length: {len(Received_FuelValue)})")

            # Check if IMEI and Fuel Value are valid
            if not TargetDevice_IMEI or not Received_FuelValue:
                print("Invalid or missing data")
                return reply("error", 400, "Invalid or missing data", '')

            # Initialize the decoded fuel value
            Decoded_FuelValue = None

            # **Validate Fuel Value Format**
            if isinstance(Received_FuelValue, str):
                # Check if it starts with '0x' and is a valid hex string
                if Received_FuelValue.startswith("0x"):
                    try:
                        if len(Received_FuelValue) > 2 and Received_FuelValue[2:].isalnum():
                            Decoded_FuelValue = int(Received_FuelValue, 16)
                            print(f"Decoded Hex Value: {Decoded_FuelValue}")
                        else:
                            print("Invalid hex format after 0x prefix")
                            return reply("error", 400, "Invalid hex format for fuel value", '')
                    except ValueError as ve:
                        print(f"Hex conversion error: {ve}")
                        return reply("error", 400, f"Hex conversion error: {ve}", '')
                else:
                    try:
                        if Received_FuelValue.isdigit():
                            Decoded_FuelValue = int(Received_FuelValue)
                            print(f"Parsed Integer Value: {Decoded_FuelValue}")
                        else:
                            print("Received non-numeric fuel value")
                            return reply("error", 400, "Invalid numeric format for fuel value", '')
                    except ValueError as ve:
                        print(f"Integer conversion error: {ve}")
                        return reply("error", 400, f"Integer conversion error: {ve}", '')

            # Ensure Decoded_FuelValue is valid
            if Decoded_FuelValue is None:
                print("Failed to parse fuel value")
                return reply("error", 400, "Failed to parse fuel value", '')

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute(
                        "SELECT milivots, milivots_fuel FROM dll_calibrated_fuel_data WHERE device_imei=%s;",
                        (str(TargetDevice_IMEI),)
                    )

                    print(f"Cursor Rowcount: {cursor.rowcount}")

                    if cursor.rowcount == 1:
                        Fuel_CalibratedData = cursor.fetchone()
                        print(f"Fetched Calibration Data: {Fuel_CalibratedData}")

                        mv_data = json.loads(Fuel_CalibratedData[0])
                        fuel_data = json.loads(Fuel_CalibratedData[1])

                        # Verify that calibration data lists are valid
                        if (len(mv_data) > 3) and (len(fuel_data) > 3):
                            try:
                                Calibrated_Milivots = [int(mv) for mv in mv_data if mv.strip()]
                                Calibrated_Milivots_FuelLitres = [int(l) for l in fuel_data if l.strip()]
                            except ValueError as ve:
                                print(f"Error in calibration data conversion: {ve}")
                                return reply("error", 400, "Invalid calibration data format", '')

                            Discovered_Fuel_Level = Calculate_Fuel_Datax(
                                Calibrated_Milivots, Calibrated_Milivots_FuelLitres, Decoded_FuelValue
                            )

                            if Discovered_Fuel_Level is not None:
                                Finaldta = {"fuel_level": int(round(Discovered_Fuel_Level)), "calibrated": {"milivots": Calibrated_Milivots, "fuel_litres": Calibrated_Milivots_FuelLitres}}
                                return reply('success', 200, "Fuel Calculation SuccessFuL", Finaldta)
                            else:
                                Finaldta = {"fuel_level": 0}
                                return reply('error', 400, 'MV Value Out Of Calibrated Range', Finaldta)

                    Finaldta = {"fuel_level": Decoded_FuelValue}
                    return reply('success', 200, 'No Calibration Data Found, Used Received Value', Finaldta)
                

        elif(FuelLevel_Source == '84') or (FuelLevel_Source == 'lls_lvl_add1'):

            _FuelLevel = Calculate_OBD_Fuel_Data(Received_FuelValue)
            Finaldta = {"fuel_level": _FuelLevel}

            return reply("success", 200, "Fuel data Found", Finaldta)
        



    except Exception as error:
        print(f"Exception Occurred: {str(error)}")
        return reply("error", 500, str(error), '')



#Get Trips report as Excell
@data_stream.route("/data-stream/trips/excel", methods=["POST"])
def ComputeTrips_EXCELL():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:

        if(len(str(payload_data['data']['device_imei'])) > 4) and (len(str(payload_data['data']['from_date'])) > 4) and (len(str(payload_data['data']['to_date'])) > 4) and (len(str(payload_data['data']['request_origin_uid'])) > 5) and (len(str(payload_data['data']['request_origin_user_uid'])) > 5):

            DeviceImei = payload_data['data']['device_imei']
            FromDate = payload_data['data']['from_date']
            ToDate = payload_data['data']['to_date']
            Offset_Record = payload_data['data']['offset_log']
            OriginRequest_UID = payload_data['data']['request_origin_uid']
            OriginUser_UID = payload_data['data']['request_origin_user_uid']
            Record_Count = int(payload_data['data']['record_count'])
            
            LogReport_Request(OriginRequest_UID, OriginUser_UID)

            TripsCore_Data=[]
            PrimaryData = []
            Excel_Data = []

            PreviousFuel_Level = ''
            PreviousMileage = ''
            PreviousDriverID = ''

            SelectedMileage = ''
            SelectedFuel_Level = ''
            SelectedDriverID = ''

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("INSERT INTO dll_reports_downloadable_files (request_uid, file_path, report_caller, request_status) VALUES(%s, %s, %s, %s)", (str(OriginRequest_UID), 'NO_DIR_PATH', OriginUser_UID, 'in_process',))

                    cursor.execute("SELECT data_longitude, data_latitude, speed_log, data_hdop, local_system_datestamp, record_io_events_uid, geocoded_location, local_system_timestamp, data_connected_satelites, batch_uid, data_idx, ROW_NUMBER() OVER (ORDER BY data_idx DESC) AS row_index FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY data_longitude, data_latitude ORDER BY data_idx DESC) AS row_num FROM dll_location_registry WHERE data_device_imei = %s AND TO_DATE(local_system_datestamp, 'DD-MM-YYYY') BETWEEN TO_DATE(%s, 'DD-MM-YYYY') AND TO_DATE(%s, 'DD-MM-YYYY')) AS subquery WHERE row_num = 1 ORDER BY data_idx DESC LIMIT %s OFFSET %s;", (str(DeviceImei), FromDate, ToDate, Record_Count, Offset_Record,))

                    if(cursor.rowcount >= 1):
                        
                        raw_data_adapter = cursor.fetchall()
                        
                        for Trip in raw_data_adapter:
                            
                            RecordIO_UID = Trip[5]
                            SPEED = Trip[2]

                            if(RecordIO_UID != "NA"):
                                FocusIgnition_Status = Config_Sources('ignition', DeviceImei, RecordIO_UID, int(SPEED))
                                FocusMileage = Config_Sources('mileage', DeviceImei, RecordIO_UID, SPEED)
                                FocusFuelLevel = Config_Sources('fuel', DeviceImei, RecordIO_UID, SPEED)
                                FocusDriverID = Config_Sources('driver_id', DeviceImei, RecordIO_UID, SPEED)

                                #For Mileage
                                if(FocusMileage == 'No-Data') and (PreviousMileage != ''):
                                    SelectedMileage = PreviousMileage
                                elif(FocusMileage == 'No-Data') and (PreviousMileage == ''):
                                    PreviousMileage = '000.00'
                                    SelectedMileage = '000.00'
                                elif(FocusMileage != 'No-Data') and (PreviousMileage == ''):
                                    PreviousMileage = FocusMileage
                                    SelectedMileage = FocusMileage
                                elif(FocusMileage != 'No-Data') and (PreviousMileage != FocusMileage):
                                    PreviousMileage = FocusMileage
                                    SelectedMileage = FocusMileage

                                #For Fuel Level
                                if(FocusFuelLevel == 'No-Data') and (PreviousFuel_Level != ''):
                                    SelectedFuel_Level = PreviousFuel_Level
                                elif(FocusFuelLevel == 'No-Data') and (PreviousFuel_Level == ''):
                                    PreviousFuel_Level = '000.00'
                                    SelectedFuel_Level = '000.00'
                                elif(FocusFuelLevel != 'No-Data') and (PreviousFuel_Level == ''):
                                    PreviousFuel_Level = FocusFuelLevel
                                    SelectedFuel_Level = FocusFuelLevel
                                elif(FocusFuelLevel != 'No-Data') and (PreviousFuel_Level != FocusFuelLevel):
                                    PreviousFuel_Level = FocusFuelLevel
                                    SelectedFuel_Level = FocusFuelLevel

                                #For DriverID
                                if(FocusDriverID == 'No-Data') and (PreviousDriverID != ''):
                                    SelectedDriverID = PreviousDriverID
                                elif(FocusDriverID == 'No-Data') and (PreviousDriverID == ''):
                                    PreviousDriverID = '000.00'
                                    SelectedDriverID = '000.00'
                                elif(FocusDriverID != 'No-Data') and (PreviousDriverID == ''):
                                    PreviousDriverID = FocusDriverID
                                    SelectedDriverID = FocusDriverID
                                elif(FocusDriverID != 'No-Data') and (PreviousDriverID != FocusDriverID):
                                    if(FocusDriverID == 'un_registered') and (PreviousDriverID != 'un_registered'):
                                        SelectedDriverID = PreviousDriverID
                                    elif(FocusDriverID == '00') and (PreviousDriverID != '00'):
                                        SelectedDriverID = PreviousDriverID
                                    elif(FocusDriverID != '00') and (PreviousDriverID != '00'):
                                        PreviousDriverID = FocusDriverID
                                        SelectedDriverID = FocusDriverID
                                    elif(FocusDriverID != 'un_registered') and (PreviousDriverID != 'un_registered'):
                                        PreviousDriverID = FocusDriverID
                                        SelectedDriverID = FocusDriverID
                                    elif(FocusDriverID != 'un_registered') and (PreviousDriverID == 'un_registered'):
                                        PreviousDriverID = FocusDriverID
                                        SelectedDriverID = FocusDriverID
                                    elif(FocusDriverID == 'un_registered') and (PreviousDriverID == 'un_registered'):
                                        SelectedDriverID = 'un_registered'
                                

                                SingleEndUser_Object = {
                                    "iginition": FocusIgnition_Status,
                                    "mileage": SelectedMileage,
                                    "fuel_level": SelectedFuel_Level,
                                    "driver_id": SelectedDriverID
                                }
                                SingleTripx_Record = {
                                    "data_longitude": Trip[0],
                                    "data_latitude": Trip[1],
                                    "speed_log": Trip[2],
                                    "data_hdop": Trip[3],
                                    "local_system_datestamp": Trip[4],
                                    "record_io_events_uid": Trip[5],
                                    "geocoded_location": Trip[6],
                                    "local_system_timestamp": Trip[7],
                                    "data_connected_satelites": Trip[8],
                                    "batch_uid": Trip[9],
                                    "data_idx": Trip[10],
                                    "row_number": Trip[-1],
                                    "enduser_data": SingleEndUser_Object
                                }
                            else:
                                SingleEndUser_Object = {}

                            SingleTripx_Record = {
                                "data_longitude": Trip[0],
                                "data_latitude": Trip[1],
                                "speed_log": Trip[2],
                                "data_hdop": Trip[3],
                                "local_system_datestamp": Trip[4],
                                "record_io_events_uid": Trip[5],
                                "geocoded_location": Trip[6],
                                "local_system_timestamp": Trip[7],
                                "data_connected_satelites": Trip[8],
                                "batch_uid": Trip[9],
                                "data_idx": Trip[10],
                                "row_number": Trip[-1],
                                "enduser_data": SingleEndUser_Object
                            }
                            
                            TripsCore_Data.append(SingleTripx_Record)

                        trips = find_trips(TripsCore_Data)
                        
                        for i, trip in enumerate(trips, start=1):
                            if trip["start_point"] is not None and trip["end_point"] is not None:
                                if trip["start_point"]["local_system_timestamp"] and trip["end_point"]["local_system_timestamp"]:
                                    start_time = trip["start_point"]["local_system_timestamp"]
                                    end_time = trip["end_point"]["local_system_timestamp"]

                                    Starting_Lat = trip["start_point"]["data_latitude"]
                                    Starting_Long = trip["start_point"]["data_longitude"]

                                    End_Lat = trip["end_point"]["data_latitude"]
                                    End_Long = trip["end_point"]["data_longitude"]

                                    distance_pool_x = Calculate_DistanceX(Starting_Lat, Starting_Long, End_Lat, End_Long)
                                    distance_data = json.loads(distance_pool_x)
                                    distance = float(distance_data["distance_covered"])

                                    OneTrip_Object = {
                                        "trip_number": i,
                                        "start_time": start_time,
                                        "end_time": end_time,
                                        "start_point_dta": trip["start_point"],
                                        "end_point_dta": trip["end_point"],
                                        "mileage_passed": distance
                                    }
                                    PrimaryData.append(OneTrip_Object)

                        for ExportData in PrimaryData:
                            
                            if(len(ExportData['start_point_dta']['enduser_data']) > 1) and (len(ExportData['end_point_dta']['enduser_data']) > 1) and ('enduser_data' in str(ExportData)):
                                SingleTrip_Out = {
                                    "Trip Number": ExportData['trip_number'],
                                    "Trip Date": ExportData['start_point_dta']['local_system_datestamp'],
                                    "Trip Start Time": ExportData['start_time'],
                                    "Trip End Time":ExportData['end_time'],
                                    "Trip Start Location": ExportData['start_point_dta']['geocoded_location'],
                                    "Trip End Location": ExportData['end_point_dta']['geocoded_location'],
                                    "Trip Mileage Passed": str(ExportData['mileage_passed'])+" KM",
                                    "Mileage at Start": str(ExportData['start_point_dta']['enduser_data']['mileage']) +" KM",
                                    "Mileage at End": str(ExportData['end_point_dta']['enduser_data']['mileage']) +" KM",
                                    "DriverID": ExportData['end_point_dta']['enduser_data']['driver_id']
                                }
                            elif(len(ExportData['start_point_dta']['enduser_data']) == 0) and ('enduser_data' in str(ExportData)):
                                SingleTrip_Out = {
                                    "Trip Number": ExportData['trip_number'],
                                    "Trip Date": ExportData['start_point_dta']['local_system_datestamp'],
                                    "Trip Start Time": ExportData['start_time'],
                                    "Trip End Time":ExportData['end_time'],
                                    "Trip Start Location": ExportData['start_point_dta']['geocoded_location'],
                                    "Trip End Location": ExportData['end_point_dta']['geocoded_location'],
                                    "Trip Mileage Passed": 'No_Data',
                                    "Mileage at Start": 'No_Data',
                                    "Mileage at End": "No_Data",
                                    "DriverID": "No_Data"
                                }
                        
                            Excel_Data.append(SingleTrip_Out)

                        df = pd.DataFrame(Excel_Data)
                        FN = "trips_report_"+str(random.randint(32, 9233392920293)+random.randint(50, 20002930020222)+random.randint(450, 2000293)+random.randint(857, 901404139))[:29]
                        FileName = FN + '.xlsx'

                        current_dir = os.path.dirname(os.path.abspath(__file__))
                        reports_cdn_dir = os.path.join(current_dir, '..', 'reports-cdn')

                        with pd.ExcelWriter(f'{reports_cdn_dir}/{FileName}', engine='xlsxwriter') as writer:
                            df.to_excel(writer, index=False, sheet_name=f"Trips_For_{DeviceImei}")
                            worksheet = writer.sheets[f"Trips_For_{DeviceImei}"]
                            
                            column_widths = {'Trip Number': 15, 'Trip Date': 15, 'Trip Start Time': 20, 'Trip End Time': 20, 'Trip Start Location': 38, 'Trip End Location': 38, 'Trip Mileage Passed': 20, 'Mileage at Start': 30, 'Mileage at End': 30, 'DriverID': 27}
                            for i, width in enumerate(column_widths.values()):
                                worksheet.set_column(i, i, width)

                        PhysicalPath = current_app.config['base_url'] + "reports-cdn/" + FileName

                        cursor.execute("UPDATE dll_reports_downloadable_files SET file_path=%s, request_status='completed' WHERE request_uid=%s;", (str(PhysicalPath), str(OriginRequest_UID),))

                        return reply('success', 200, 'Processing Excell Report, Keep Checking', '')

                    elif(cursor.rowcount == 0):
                        cursor.execute("UPDATE dll_reports_downloadable_files SET request_status='no-data' WHERE request_uid=%s;", (str(OriginRequest_UID),))
                        return reply('error', 400, 'No Trips Data Found', '')
                    
        else:
            return reply('error', 400, 'Something Is Missing', '')
        
    except Exception as error:
        print(error)
        return reply('error', 500, str(error), '')


#Get Trips report as DPF
@data_stream.route("/data-stream/trips/pdf", methods=["POST"])
def ComputeTrips_PDF():

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    payload_data = request.get_json()

    try:

        if(len(str(payload_data['data']['device_imei'])) > 4) and (len(str(payload_data['data']['from_date'])) > 4) and (len(str(payload_data['data']['to_date'])) > 4) and (len(str(payload_data['data']['offset_log'])) > 0) and (len(str(payload_data['data']['request_origin_uid'])) > 5) and (len(str(payload_data['data']['request_origin_user_uid'])) > 5):

            DeviceImei = payload_data['data']['device_imei']
            FromDate = payload_data['data']['from_date']
            ToDate = payload_data['data']['to_date']
            Offset_Record = payload_data['data']['offset_log']
            OriginRequest_UID = payload_data['data']['request_origin_uid']
            OriginUser_UID = payload_data['data']['request_origin_user_uid']
            Record_Count = int(payload_data['data']['record_count'])

            LogReport_Request(OriginRequest_UID, OriginUser_UID)

            TripsCore_Data=[]
            PrimaryData = []
            Excel_Data = []

            PreviousFuel_Level = ''
            PreviousMileage = ''
            PreviousDriverID = ''

            SelectedMileage = ''
            SelectedFuel_Level = ''
            SelectedDriverID = ''

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT data_longitude, data_latitude, speed_log, data_hdop, local_system_datestamp, record_io_events_uid, geocoded_location, local_system_timestamp, data_connected_satelites, batch_uid, data_idx, ROW_NUMBER() OVER (ORDER BY data_idx DESC) AS row_index FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY data_longitude, data_latitude ORDER BY data_idx DESC) AS row_num FROM dll_location_registry WHERE data_device_imei = %s AND TO_DATE(local_system_datestamp, 'DD-MM-YYYY') BETWEEN TO_DATE(%s, 'DD-MM-YYYY') AND TO_DATE(%s, 'DD-MM-YYYY')) AS subquery WHERE row_num = 1 ORDER BY data_idx DESC LIMIT %s OFFSET %s;", (str(DeviceImei), FromDate, ToDate, Record_Count, Offset_Record,))

                    if(cursor.rowcount >= 1):
                        
                        raw_data_adapter = cursor.fetchall()
                        
                        for Trip in raw_data_adapter:
                            
                            RecordIO_UID = Trip[5]
                            SPEED = Trip[2]

                            if(RecordIO_UID != "NA"):
                                FocusIgnition_Status = Config_Sources('ignition', DeviceImei, RecordIO_UID, int(SPEED))
                                FocusMileage = Config_Sources('mileage', DeviceImei, RecordIO_UID, SPEED)
                                FocusFuelLevel = Config_Sources('fuel', DeviceImei, RecordIO_UID, SPEED)
                                FocusDriverID = Config_Sources('driver_id', DeviceImei, RecordIO_UID, SPEED)

                                #For Mileage
                                if(FocusMileage == 'No-Data') and (PreviousMileage != ''):
                                    SelectedMileage = PreviousMileage
                                elif(FocusMileage == 'No-Data') and (PreviousMileage == ''):
                                    PreviousMileage = '000.00'
                                    SelectedMileage = '000.00'
                                elif(FocusMileage != 'No-Data') and (PreviousMileage == ''):
                                    PreviousMileage = FocusMileage
                                    SelectedMileage = FocusMileage
                                elif(FocusMileage != 'No-Data') and (PreviousMileage != FocusMileage):
                                    PreviousMileage = FocusMileage
                                    SelectedMileage = FocusMileage

                                #For Fuel Level
                                if(FocusFuelLevel == 'No-Data') and (PreviousFuel_Level != ''):
                                    SelectedFuel_Level = PreviousFuel_Level
                                elif(FocusFuelLevel == 'No-Data') and (PreviousFuel_Level == ''):
                                    PreviousFuel_Level = '000.00'
                                    SelectedFuel_Level = '000.00'
                                elif(FocusFuelLevel != 'No-Data') and (PreviousFuel_Level == ''):
                                    PreviousFuel_Level = FocusFuelLevel
                                    SelectedFuel_Level = FocusFuelLevel
                                elif(FocusFuelLevel != 'No-Data') and (PreviousFuel_Level != FocusFuelLevel):
                                    PreviousFuel_Level = FocusFuelLevel
                                    SelectedFuel_Level = FocusFuelLevel

                                #For DriverID
                                if(FocusDriverID == 'No-Data') and (PreviousDriverID != ''):
                                    SelectedDriverID = PreviousDriverID
                                elif(FocusDriverID == 'No-Data') and (PreviousDriverID == ''):
                                    PreviousDriverID = '000.00'
                                    SelectedDriverID = '000.00'
                                elif(FocusDriverID != 'No-Data') and (PreviousDriverID == ''):
                                    PreviousDriverID = FocusDriverID
                                    SelectedDriverID = FocusDriverID
                                elif(FocusDriverID != 'No-Data') and (PreviousDriverID != FocusDriverID):
                                    if(FocusDriverID == 'un_registered') and (PreviousDriverID != 'un_registered'):
                                        SelectedDriverID = PreviousDriverID
                                    elif(FocusDriverID == '00') and (PreviousDriverID != '00'):
                                        SelectedDriverID = PreviousDriverID
                                    elif(FocusDriverID != '00') and (PreviousDriverID != '00'):
                                        PreviousDriverID = FocusDriverID
                                        SelectedDriverID = FocusDriverID
                                    elif(FocusDriverID != 'un_registered') and (PreviousDriverID != 'un_registered'):
                                        PreviousDriverID = FocusDriverID
                                        SelectedDriverID = FocusDriverID
                                    elif(FocusDriverID != 'un_registered') and (PreviousDriverID == 'un_registered'):
                                        PreviousDriverID = FocusDriverID
                                        SelectedDriverID = FocusDriverID
                                    elif(FocusDriverID == 'un_registered') and (PreviousDriverID == 'un_registered'):
                                        SelectedDriverID = 'un_registered'
                                

                                SingleEndUser_Object = {
                                    "iginition": FocusIgnition_Status,
                                    "mileage": SelectedMileage,
                                    "fuel_level": SelectedFuel_Level,
                                    "driver_id": SelectedDriverID
                                }
                                SingleTripx_Record = {
                                    "data_longitude": Trip[0],
                                    "data_latitude": Trip[1],
                                    "speed_log": Trip[2],
                                    "data_hdop": Trip[3],
                                    "local_system_datestamp": Trip[4],
                                    "record_io_events_uid": Trip[5],
                                    "geocoded_location": Trip[6],
                                    "local_system_timestamp": Trip[7],
                                    "data_connected_satelites": Trip[8],
                                    "batch_uid": Trip[9],
                                    "data_idx": Trip[10],
                                    "row_number": Trip[-1],
                                    "enduser_data": SingleEndUser_Object
                                }
                            else:
                                SingleEndUser_Object = {}

                            SingleTripx_Record = {
                                "data_longitude": Trip[0],
                                "data_latitude": Trip[1],
                                "speed_log": Trip[2],
                                "data_hdop": Trip[3],
                                "local_system_datestamp": Trip[4],
                                "record_io_events_uid": Trip[5],
                                "geocoded_location": Trip[6],
                                "local_system_timestamp": Trip[7],
                                "data_connected_satelites": Trip[8],
                                "batch_uid": Trip[9],
                                "data_idx": Trip[10],
                                "row_number": Trip[-1],
                                "enduser_data": SingleEndUser_Object
                            }

                            TripsCore_Data.append(SingleTripx_Record)

                        trips = find_trips(TripsCore_Data)
                        
                        for i, trip in enumerate(trips, start=1):
                            print("Executed Loop")
                            if trip["start_point"] is not None and trip["end_point"] is not None:
                                if trip["start_point"]["local_system_timestamp"] and trip["end_point"]["local_system_timestamp"]:
                                    start_time = trip["start_point"]["local_system_timestamp"]
                                    end_time = trip["end_point"]["local_system_timestamp"]

                                    Starting_Lat = trip["start_point"]["data_latitude"]
                                    Starting_Long = trip["start_point"]["data_longitude"]

                                    End_Lat = trip["end_point"]["data_latitude"]
                                    End_Long = trip["end_point"]["data_longitude"]

                                    distance_pool_x = Calculate_DistanceX(Starting_Lat, Starting_Long, End_Lat, End_Long)
                                    distance_data = json.loads(distance_pool_x)
                                    distance = float(distance_data["distance_covered"])

                                    OneTrip_Object = {
                                        "trip_number": i,
                                        "start_time": start_time,
                                        "end_time": end_time,
                                        "start_point_dta": trip["start_point"],
                                        "end_point_dta": trip["end_point"],
                                        "mileage_passed": distance
                                    }
                                    PrimaryData.append(OneTrip_Object)

                                else:
                                    print("Something Is Missing")
                            else:
                                print("Something Else")

                        for ExportData in PrimaryData:
                            
                            if(len(ExportData['start_point_dta']['enduser_data']) > 1) and (len(ExportData['end_point_dta']['enduser_data']) > 1) and ('enduser_data' in str(ExportData)):
                                SingleTrip_Out = {
                                    "Trip Number": ExportData['trip_number'],
                                    "Trip Date": ExportData['start_point_dta']['local_system_datestamp'],
                                    "Trip Start Time": ExportData['start_time'],
                                    "Trip End Time":ExportData['end_time'],
                                    "Trip Start Location": ExportData['start_point_dta']['geocoded_location'],
                                    "Trip End Location": ExportData['end_point_dta']['geocoded_location'],
                                    "Trip Mileage Passed": str(ExportData['mileage_passed'])+" KM",
                                    "Mileage at Start": str(ExportData['start_point_dta']['enduser_data']['mileage']) +" KM",
                                    "Mileage at End": str(ExportData['end_point_dta']['enduser_data']['mileage']) +" KM",
                                    "DriverID": ExportData['end_point_dta']['enduser_data']['driver_id']
                                }
                            elif(len(ExportData['start_point_dta']['enduser_data']) == 0) and ('enduser_data' in str(ExportData)):
                                SingleTrip_Out = {
                                    "Trip Number": ExportData['trip_number'],
                                    "Trip Date": ExportData['start_point_dta']['local_system_datestamp'],
                                    "Trip Start Time": ExportData['start_time'],
                                    "Trip End Time":ExportData['end_time'],
                                    "Trip Start Location": ExportData['start_point_dta']['geocoded_location'],
                                    "Trip End Location": ExportData['end_point_dta']['geocoded_location'],
                                    "Trip Mileage Passed": 'No_Data',
                                    "Mileage at Start": 'No_Data',
                                    "Mileage at End": "No_Data",
                                    "DriverID": "No_Data"
                                }
                        
                            Excel_Data.append(SingleTrip_Out)

                        File_Name_X = "trips_report_"+str(random.randint(32, 9233392920293)+random.randint(50, 20002930020222)+random.randint(450, 2000293)+random.randint(857, 901404139))[:29]

                        create_pdf(Excel_Data, FromDate, ToDate, DeviceImei, File_Name_X)

                        PhysicalPath = current_app.config['base_url'] + "reports-cdn/" + File_Name_X + ".pdf"

                        cursor.execute("UPDATE dll_reports_downloadable_files SET file_path=%s, request_status='completed' WHERE request_uid=%s;", (str(PhysicalPath), str(OriginRequest_UID),))

                        return reply('success', 200, 'Processing Report, Keep Checking', '')

                    elif(cursor.rowcount == 0):
                        cursor.execute("UPDATE dll_reports_downloadable_files SET request_status='no-data' WHERE request_uid=%s;", (str(OriginRequest_UID),))
                        return reply('error', 400, 'No Trips Data Found', '')
                    
        else:
            return reply('error', 400, 'Something Is Missing', '')
        
    except Exception as error:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("UPDATE dll_reports_downloadable_files SET request_status='failed' WHERE request_uid=%s;", (str(OriginRequest_UID),))
                print(error)
        return reply('error', 500, str(error), '')



#get device trips data as raw data
@data_stream.route("/data-stream/trips/history", methods=["POST"])
def trips_history():

    try:

        PreviousFuel_Level = ''
        PreviousMileage = ''
        PreviousDriverID = ''

        SelectedMileage = ''
        SelectedFuel_Level = ''
        SelectedDriverID = ''

        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()

        if(len(str(payload_data['data']['device_imei'])) > 4) and (len(str(payload_data['data']['from_date'])) > 4) and (len(str(payload_data['data']['to_date'])) > 4) and (len(str(payload_data['data']['offset_log'])) > 0) and (len(str(payload_data['data']['record_count'])) > 0):

            DeviceImei = payload_data['data']['device_imei']
            FromDate = payload_data['data']['from_date']
            ToDate = payload_data['data']['to_date']
            Offset_Record = payload_data['data']['offset_log']
            Record_Count = int(payload_data['data']['record_count'])

            device_billing_check = check_device(DeviceImei)

            if(device_billing_check == 'running'):

                TheDeviceVendor = CheckHardware2(DeviceImei)
                
                if(TheDeviceVendor == 'ruptela'):
                    TableName = "dll_io_events_config"
                    ValueColunmName = "io_display_name"
                    ConditionColunmName = "io_event_vendor_uid"

                elif(TheDeviceVendor == 'teltonika'):
                    TableName = "dll_teltonika_avl_list"
                    ValueColunmName = "avl_io_name"
                    ConditionColunmName = "avl_io_id"

                else:
                    TableName = "dll_io_events_config"
                    ValueColunmName = "io_display_name"
                    ConditionColunmName = "io_event_vendor_uid"

                if(compare_years(FromDate, ToDate) == True):
                    if(Record_Count < 15000) or (Record_Count == 15000):

                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute("SELECT data_longitude, data_latitude, speed_log, data_hdop, local_system_datestamp, record_io_events_uid, geocoded_location, local_system_timestamp, data_connected_satelites, batch_uid, data_idx, ROW_NUMBER() OVER (ORDER BY data_idx DESC) AS row_index FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY data_longitude, data_latitude ORDER BY data_idx DESC) AS row_num FROM dll_location_registry WHERE data_device_imei = %s AND TO_DATE(local_system_datestamp, 'DD-MM-YYYY') BETWEEN TO_DATE(%s, 'DD-MM-YYYY') AND TO_DATE(%s, 'DD-MM-YYYY')) AS subquery WHERE row_num = 1 ORDER BY data_idx DESC LIMIT %s OFFSET %s;", (DeviceImei, FromDate, ToDate, Record_Count, Offset_Record,))

                                if(cursor.rowcount >= 1):

                                    trips_data_adapter = cursor.fetchall()
                                    PrimaryData = {
                                        "raw_data": [],
                                        "trips_data": []
                                    }
                                    TripsData = []
                                    Trips_Records = []

                                    for trip in trips_data_adapter:

                                        RecordIO_UID = trip[5]
                                        SPEED = trip[2]

                                        cursor.execute("SELECT event_uid_executed,event_value_executed,data_idx FROM dll_io_events_executed_logs WHERE io_parent_io_event_uid=%s ORDER BY data_idx DESC;", (str(RecordIO_UID),))

                                        if(cursor.rowcount >= 1):

                                            io_events_dataAdapter = cursor.fetchall()
                                            io_events_Found = []
                                            enduser_data = []

                                            for io_event in io_events_dataAdapter:
                                                
                                                if(TheDeviceVendor == 'ruptela'):
                                                    IO_ID_Found = str(io_event[0])+".0"
                                                elif(TheDeviceVendor == 'teltonika'):
                                                    IO_ID_Found = str(io_event[0])

                                                IO_IDQuery = f"SELECT { ValueColunmName } FROM { TableName } WHERE { ConditionColunmName }=%s"
                                                cursor.execute(IO_IDQuery, (str(IO_ID_Found),))
                                                IO_NameValue_adapter = cursor.fetchone()
                                                IO_NameValue_Extracted = IO_NameValue_adapter[0]

                                                SingleIO_Event = {
                                                    IO_NameValue_Extracted:io_event[1] 
                                                }

                                                io_events_Found.append(SingleIO_Event)
                                                

                                            FocusIgnition_Status = Config_Sources('ignition', DeviceImei, RecordIO_UID, int(SPEED))
                                            FocusMileage = Config_Sources('mileage', DeviceImei, RecordIO_UID, SPEED)
                                            FocusFuelLevel = Config_Sources('fuel', DeviceImei, RecordIO_UID, SPEED)
                                            FocusDriverID = Config_Sources('driver_id', DeviceImei, RecordIO_UID, SPEED)

                                            if(FocusMileage == 'No-Data') and (PreviousMileage != ''):
                                                SelectedMileage = PreviousMileage
                                            elif(FocusMileage == 'No-Data') and (PreviousMileage == ''):
                                                PreviousMileage = '000.00'
                                                SelectedMileage = '000.00'
                                            elif(FocusMileage != 'No-Data') and (PreviousMileage == ''):
                                                PreviousMileage = FocusMileage
                                                SelectedMileage = FocusMileage
                                            elif(FocusMileage != 'No-Data') and (PreviousMileage != FocusMileage):
                                                PreviousMileage = FocusMileage
                                                SelectedMileage = FocusMileage

                                            #For Fuel Level
                                            if(FocusFuelLevel == 'No-Data') and (PreviousFuel_Level != ''):
                                                SelectedFuel_Level = PreviousFuel_Level
                                            elif(FocusFuelLevel == 'No-Data') and (PreviousFuel_Level == ''):
                                                PreviousFuel_Level = '000.00'
                                                SelectedFuel_Level = '000.00'
                                            elif(FocusFuelLevel != 'No-Data') and (PreviousFuel_Level == ''):
                                                PreviousFuel_Level = FocusFuelLevel
                                                SelectedFuel_Level = FocusFuelLevel
                                            elif(FocusFuelLevel != 'No-Data') and (PreviousFuel_Level != FocusFuelLevel):
                                                PreviousFuel_Level = FocusFuelLevel
                                                SelectedFuel_Level = FocusFuelLevel

                                            #For DriverID
                                            if(FocusDriverID == 'No-Data') and (PreviousDriverID != ''):
                                                SelectedDriverID = PreviousDriverID
                                            elif(FocusDriverID == 'No-Data') and (PreviousDriverID == ''):
                                                PreviousDriverID = '000.00'
                                                SelectedDriverID = '000.00'
                                            elif(FocusDriverID != 'No-Data') and (PreviousDriverID == ''):
                                                PreviousDriverID = FocusDriverID
                                                SelectedDriverID = FocusDriverID
                                            elif(FocusDriverID != 'No-Data') and (PreviousDriverID != FocusDriverID):
                                                if(FocusDriverID == 'un_registered') and (PreviousDriverID != 'un_registered'):
                                                    SelectedDriverID = PreviousDriverID
                                                elif(FocusDriverID == '00') and (PreviousDriverID != '00'):
                                                    SelectedDriverID = PreviousDriverID
                                                elif(FocusDriverID != '00') and (PreviousDriverID != '00'):
                                                    PreviousDriverID = FocusDriverID
                                                    SelectedDriverID = FocusDriverID
                                                elif(FocusDriverID != 'un_registered') and (PreviousDriverID != 'un_registered'):
                                                    PreviousDriverID = FocusDriverID
                                                    SelectedDriverID = FocusDriverID
                                                elif(FocusDriverID != 'un_registered') and (PreviousDriverID == 'un_registered'):
                                                    PreviousDriverID = FocusDriverID
                                                    SelectedDriverID = FocusDriverID
                                                elif(FocusDriverID == 'un_registered') and (PreviousDriverID == 'un_registered'):
                                                    SelectedDriverID = 'un_registered'

                                            SingleEndUser_Object = {
                                                "iginition": FocusIgnition_Status,
                                                "mileage": SelectedMileage,
                                                "fuel_level": SelectedFuel_Level,
                                                "driver_id": SelectedDriverID
                                            }
                                            enduser_data.append(SingleEndUser_Object)

                                            SingleTripe_Record = {
                                                "data_longitude": trip[0],
                                                "data_latitude": trip[1],
                                                "speed_log": trip[2],
                                                "data_hdop": trip[3],
                                                "local_system_datestamp": trip[4],
                                                "record_io_events_uid": trip[5],
                                                "geocoded_location": trip[6],
                                                "local_system_timestamp": trip[7],
                                                "data_connected_satelites": trip[8],
                                                "batch_uid": trip[9],
                                                "data_idx": trip[10],
                                                "data_index": trip[-1],
                                                "io_events_data": io_events_Found,
                                                "enduser_data": enduser_data
                                            }
                                            
                                            PrimaryData["raw_data"].append(SingleTripe_Record)
                                            TripsData.append(SingleTripe_Record)
                                    

                                        elif(cursor.rowcount == 0):

                                            SingleTripe_Record = {
                                                "data_longitude": trip[0],
                                                "data_latitude": trip[1],
                                                "speed_log": trip[2],
                                                "data_hdop": trip[3],
                                                "local_system_datestamp": trip[4],
                                                "record_io_events_uid": trip[5],
                                                "geocoded_location": trip[6],
                                                "local_system_timestamp": trip[7],
                                                "data_connected_satelites": trip[8],
                                                "batch_uid": trip[9],
                                                "data_idx": trip[10],
                                                "data_index": trip[-1],
                                                "io_events_data": "no-data"
                                            }

                                            PrimaryData["raw_data"].append(SingleTripe_Record)
                                            TripsData.append(SingleTripe_Record)

                                    trips = find_trips(TripsData)

                                    # Print results
                                    for i, trip in enumerate(trips, start=1):
                                        
                                        if(trip["start_point"] != None) and (trip["end_point"] != None):
                                            if(trip["start_point"]["local_system_timestamp"]) and (trip["end_point"]["local_system_timestamp"]):
                                                start_time = trip["start_point"]["local_system_timestamp"]
                                                end_time = trip["end_point"]["local_system_timestamp"]

                                                Starting_Lat = trip["start_point"]["data_latitude"]
                                                Starting_Long = trip["start_point"]["data_longitude"]

                                                End_Lat = trip["end_point"]["data_latitude"]
                                                End_Long = trip["end_point"]["data_longitude"]

                                                distance_pool_x = Calculate_DistanceX(Starting_Lat, Starting_Long, End_Lat, End_Long)
                                                distance_adapter = distance_pool_x.get_json()
                                                distance = distance_adapter['distance_covered']

                                                OneTrip_Object = {
                                                    "trip_number": i,
                                                    "start_time": start_time,
                                                    "end_time": end_time,
                                                    "start_point_dta": trip["start_point"],
                                                    "end_point_dta": trip["end_point"],
                                                    "mileage_passed": round(distance)
                                                }
                                                PrimaryData["trips_data"].append(OneTrip_Object)
                                    
                                    return reply('success', 200, 'Trips Data Found', PrimaryData)
                                    
                                elif(cursor.rowcount == 0):
                                    return reply('error', 400, 'No Trips Found', '')
                                else:
                                    return reply('error', 400, 'Unable to complete request', '')

                    else:
                        return reply('error', 400, 'Record Count Is Too High', '')

                elif(compare_years(FromDate, ToDate) == False):
                    return reply('error', 400, 'From Date and To Date Must Between 2 Years', '')
                else:
                    return reply('error', 400, 'Unable to complete request', '')
                
            elif(device_billing_check == 'blocked'):
                return reply('error', 400, 'Device Billing Is Blocked', '')
            
            elif(device_billing_check == 'not-found'):
                return reply('error', 400, 'Routing Failed, Device Cant be found', '')
            
        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, error, '')
    


#Trips history replay without IOs
@data_stream.route("/data-stream/trips/history/replay", methods=["POST"])
def trips_history_replay():

    try:

        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()

        if(len(str(payload_data['data']['device_imei'])) > 4) and (len(str(payload_data['data']['from_date'])) > 4) and (len(str(payload_data['data']['to_date'])) > 4) and (len(str(payload_data['data']['offset_log'])) > 0) and (len(str(payload_data['data']['record_count'])) > 0):

            DeviceImei = payload_data['data']['device_imei']
            FromDate = payload_data['data']['from_date']
            ToDate = payload_data['data']['to_date']
            Offset_Record = payload_data['data']['offset_log']
            Record_Count = int(payload_data['data']['record_count'])

            device_billing_check = check_device(DeviceImei)

            if(device_billing_check == 'running'):

                if(compare_years(FromDate, ToDate) == True):
                    if(Record_Count < 15000) or (Record_Count == 15000):

                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute("SELECT data_longitude, data_latitude, speed_log, data_hdop, local_system_datestamp, record_io_events_uid, geocoded_location, local_system_timestamp, data_connected_satelites, batch_uid, data_idx, ROW_NUMBER() OVER (ORDER BY data_idx DESC) AS row_index FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY data_longitude, data_latitude ORDER BY data_idx DESC) AS row_num FROM dll_location_registry WHERE data_device_imei = %s AND TO_DATE(local_system_datestamp, 'DD-MM-YYYY') BETWEEN TO_DATE(%s, 'DD-MM-YYYY') AND TO_DATE(%s, 'DD-MM-YYYY')) AS subquery WHERE row_num = 1 ORDER BY data_idx DESC LIMIT %s OFFSET %s;", (DeviceImei, FromDate, ToDate, Record_Count, Offset_Record,))

                                if(cursor.rowcount >= 1):

                                    trips_data_adapter = cursor.fetchall()
                                    TripsData = []

                                    for trip in trips_data_adapter:

                        
                                            SingleTripe_Record = {
                                                "data_longitude": trip[0],
                                                "data_latitude": trip[1],
                                                "speed_log": trip[2],
                                                "data_hdop": trip[3],
                                                "local_system_datestamp": trip[4],
                                                "record_io_events_uid": trip[5],
                                                "geocoded_location": trip[6],
                                                "local_system_timestamp": trip[7],
                                                "data_connected_satelites": trip[8],
                                                "batch_uid": trip[9],
                                                "data_idx": trip[10],
                                                "data_index": trip[-1]
                                            }

                                            TripsData.append(SingleTripe_Record)


                                    return reply('success', 200, 'Trips Data Found', TripsData)
                                    
                                elif(cursor.rowcount == 0):
                                    return reply('error', 400, 'No Trips Found', '')
                                else:
                                    return reply('error', 400, 'Unable to complete request', '')

                    else:
                        return reply('error', 400, 'Record Count Is Too High', '')

                elif(compare_years(FromDate, ToDate) == False):
                    return reply('error', 400, 'From Date and To Date Must Between 2 Years', '')
                else:
                    return reply('error', 400, 'Unable to complete request', '')
                
            elif(device_billing_check == 'blocked'):
                return reply('error', 400, 'Device Billing Is Blocked', '')
            
            elif(device_billing_check == 'not-found'):
                return reply('error', 400, 'Routing Failed, Device Cant be found', '')
            
        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')



    try:

        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()

        if(len(str(payload_data['data']['device_imei'])) > 4) and (len(str(payload_data['data']['from_date'])) > 4) and (len(str(payload_data['data']['to_date'])) > 4) and (len(str(payload_data['data']['offset_log'])) > 0) and (len(str(payload_data['data']['record_count'])) > 0) and (len(str(payload_data['data']['request_origin_user_uid'])) > 2):

            DeviceImei = payload_data['data']['device_imei']
            FromDate = payload_data['data']['from_date']
            ToDate = payload_data['data']['to_date']
            Offset_Record = payload_data['data']['offset_log']
            Record_Count = int(payload_data['data']['record_count'])
            DataRequest_ID = payload_data['data']['request_uid']
            RequestOriginator = str(payload_data['data']['request_origin_user_uid'])

            device_billing_status = check_device(DeviceImei)

            if(device_billing_status == 'running'):


                if(compare_years(FromDate, ToDate) == True):
                    if(Record_Count < 15000) or (Record_Count == 15000):

                        with dbconnect:
                            with dbconnect.cursor() as cursor:
                                cursor.execute("SELECT data_device_imei, geocoded_location, data_longitude, data_latitude, speed_log, local_system_datestamp, local_system_timestamp, data_connected_satelites FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY data_longitude, data_latitude ORDER BY data_idx DESC) AS row_num FROM dll_location_registry WHERE data_device_imei = %s AND TO_DATE(local_system_datestamp, 'DD-MM-YYYY') BETWEEN TO_DATE(%s, 'DD-MM-YYYY') AND TO_DATE(%s, 'DD-MM-YYYY')) AS subquery WHERE row_num = 1 ORDER BY data_idx DESC LIMIT %s OFFSET %s;", (DeviceImei, FromDate, ToDate, Record_Count, Offset_Record,))

                                if(cursor.rowcount >= 1):

                                    trips_data_adapter = cursor.fetchall()
                                    
                                    df = pd.DataFrame(trips_data_adapter, columns=['Device', 'Trip Location', 'Longitude Cordinates', 'Latitude Cordinates', 'Moving Speed ( KM/H )', 'Trip Date', 'Trip Time', 'Satelites Available'])

                                    FN = "sentinel_trips_"+str(random.randint(32, 9233392920293)+random.randint(50, 20002930020222)+random.randint(450, 2000293)+random.randint(857, 901404139))[:29]

                                    FileName = FN + '.xlsx'

                                    df.to_excel(f'reports-cdn/{ FileName }', index=False)

                                    PhysicalPath = current_app.config['base_url'] + "reports-cdn/" + FileName

                                    cursor.execute("INSERT INTO dll_reports_downloadable_files (request_uid, file_path, report_caller) VALUES(%s, %s, %s)", (str(DataRequest_ID), str(PhysicalPath), RequestOriginator,))

                                    data_back ={
                                        "physical_file": PhysicalPath,
                                        "request_uid": DataRequest_ID,
                                        "request_status": "completed"
                                    }

                                    return reply('success', 200, 'Request Completed', data_back)
                                    
                                elif(cursor.rowcount == 0):
                                    return reply('error', 400, 'No Trips Found', '')
                                else:
                                    return reply('error', 400, 'Unable to complete request', '')

                    else:
                        return reply('error', 400, 'Record Count Is Too High', '')

                elif(compare_years(FromDate, ToDate) == False):
                    return reply('error', 400, 'From Date and To Date Must Between 2 Years', '')
                else:
                    return reply('error', 400, 'Unable to complete request', '')
                
            elif(device_billing_status == 'blocked'):
                return reply('error', 400, 'Device Billing Is Blocked', '')
            
            elif(device_billing_status == 'not-found'):
                return reply('error', 400, 'Routing Failed, Device Cant be found', '')
        else:
            return reply('error', 400, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')
    

#check trips report status
@data_stream.route("/data-stream/reports/<request_uid>/status", methods=["GET"])
def report_status(request_uid):

    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        if(len(str(request_uid)) > 3):

            RequestUID = str(request_uid)

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT file_path,request_status,request_datestamp FROM dll_reports_downloadable_files WHERE request_uid=%s;", (RequestUID,))

                    if(cursor.rowcount == 1):

                        requested_data_adapter = cursor.fetchone()
                        TargetFile_Path = requested_data_adapter[0]
                        RequestStatus = requested_data_adapter[1]
                        RequestDateStamp = requested_data_adapter[2]

                        data_back ={
                            "file_status": RequestStatus,
                            "file_path": TargetFile_Path,
                            "request_uid": RequestUID,
                            "request_datestamp": RequestDateStamp
                        }

                        return reply('success', 200, 'Request Status Found', data_back)

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'No Request Found', '')
                    else:
                        return reply('error', 400, 'Unable to complete request', '')

        else:
            return reply('error', 400, 'Missing Request ID', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


#get previous trips reports
@data_stream.route("/data-stream/reports/<reports_owner>/trips", methods=["GET"])
def get_reports(reports_owner):

    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        if(len(str(reports_owner)) > 5):

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_reports_downloadable_files WHERE report_caller=%s ORDER BY id DESC", (str(reports_owner),))

                    if(cursor.rowcount >= 1):

                        Found_Trips_Data = []
                        data_adapter = cursor.fetchall()

                        for TripFile in data_adapter:
                            Single_Trip_Report = {
                                "file_link": TripFile[2],
                                "file_progress": TripFile[4],
                                "file_request_uid": TripFile[1],
                                "file_datestamp": TripFile[5],
                                "report_type": str(TripFile[6]).upper()
                            }
                            Found_Trips_Data.append(Single_Trip_Report)

                        return reply('success', 200, 'Reports Data Found', Found_Trips_Data)

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'No Reports Data Found', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')
        
    except Exception as error:
        return reply('error', 500, str(error), '')


@data_stream.route("/data-stream/reports/<reports_owner>/<report_type>/list", methods=["GET"])
def GetReport_Files(reports_owner, report_type):

    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        if(len(str(reports_owner)) > 5):

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_reports_downloadable_files WHERE report_caller=%s AND report_type=%s ORDER BY id DESC", (str(reports_owner), str(report_type),))

                    if(cursor.rowcount >= 1):

                        Found_Trips_Data = []
                        data_adapter = cursor.fetchall()

                        for TripFile in data_adapter:
                            Single_Trip_Report = {
                                "file_link": TripFile[2],
                                "file_progress": TripFile[4],
                                "file_request_uid": TripFile[1],
                                "file_datestamp": TripFile[5],
                                "report_type": str(TripFile[6]).upper()
                            }
                            Found_Trips_Data.append(Single_Trip_Report)

                        return reply('success', 200, 'Reports Data Found', Found_Trips_Data)

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'No Reports Data Found', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')
        
    except Exception as error:
        return reply('error', 500, str(error), '')


@data_stream.route("/data-stream/reports/<reports_owner>/state/list", methods=["GET"])
def GetStateReport_Files(reports_owner):

    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        if(len(str(reports_owner)) > 5):

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT * FROM dll_reports_downloadable_files 
                        WHERE report_caller = %s 
                        AND (report_type = %s OR report_type = %s OR report_type = %s) 
                        ORDER BY id DESC
                        """,
                        (str(reports_owner), 'IGNITION_ON', 'IDILING', 'PARKING',)
                    )


                    if(cursor.rowcount >= 1):

                        Found_Trips_Data = []
                        data_adapter = cursor.fetchall()

                        for TripFile in data_adapter:
                            Single_Trip_Report = {
                                "file_link": TripFile[2],
                                "file_progress": TripFile[4],
                                "file_request_uid": TripFile[1],
                                "file_datestamp": TripFile[5],
                                "report_type": str(TripFile[6]).upper()
                            }
                            Found_Trips_Data.append(Single_Trip_Report)

                        return reply('success', 200, 'Reports Data Found', Found_Trips_Data)

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'No Reports Data Found', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')
        
    except Exception as error:
        return reply('error', 500, str(error), '')
    
#download trips file report
@data_stream.route("/reports-cdn/<access_file>", methods=['GET'])
def download_trips_report(access_file):

    directory_path = f'../reports-cdn'

    try:
        return send_from_directory(directory_path, access_file), 200
    except Exception as e:
        
        return str(e), 500
    

# ── Log a client-side generated report ──────────────────────────────────────
@data_stream.route("/data-stream/reports/log-download", methods=["POST"])
def log_client_report():
    """
    Log a client-side generated report (PDF/Excel) so it shows in Previous Reports.
    Body: { data: { report_caller, report_type, format } }
    """
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        _payload = request.get_json(force=True)
        _data = _payload.get('data', {})
        report_caller = _data.get('report_caller', '')
        report_type = _data.get('report_type', '')
        report_format = _data.get('format', 'pdf').upper()

        if len(str(report_caller)) < 5 or not report_type:
            return reply('error', 400, 'Missing report_caller or report_type', '')

        import uuid
        request_uid = str(uuid.uuid4())
        timezone = pytz.timezone("Africa/Kampala")
        current_date = datetime.now(timezone).strftime("%d-%m-%Y")
        current_time = datetime.now(timezone).strftime("%I:%M:%S%p")
        datestamp = current_date + '_' + current_time
        file_label = "client-download-" + report_format.lower()

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO dll_reports_downloadable_files
                       (request_uid, file_path, report_caller, request_status, request_datestamp, report_type)
                       VALUES(%s, %s, %s, %s, %s, %s)""",
                    (request_uid, file_label, report_caller, 'completed', datestamp, report_type.upper())
                )
        return reply('success', 200, 'Report logged', {'request_uid': request_uid})

    except Exception as error:
        return reply('error', 500, str(error), '')


# ── Delete a report (customer can only delete their own) ────────────────────
@data_stream.route("/data-stream/reports/<report_uid>/delete", methods=["DELETE"])
def delete_report(report_uid):
    """
    Delete a report record by its request_uid.
    Security: verifies report_caller matches the owner_uid passed in
    the request body so customers can only delete their own reports.
    """
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        _payload = request.get_json(force=True)
        owner_uid = _payload.get('owner_uid', '')

        if len(str(report_uid)) < 5 or len(str(owner_uid)) < 5:
            return reply('error', 400, 'Invalid request parameters', '')

        with dbconnect:
            with dbconnect.cursor() as cursor:
                # Only delete if report_caller matches the requesting user
                cursor.execute(
                    "DELETE FROM dll_reports_downloadable_files WHERE request_uid=%s AND report_caller=%s",
                    (str(report_uid), str(owner_uid))
                )

                if cursor.rowcount >= 1:
                    return reply('success', 200, 'Report deleted successfully', '')
                else:
                    return reply('error', 404, 'Report not found or access denied', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


# ── Get available report types ──────────────────────────────────────────────
@data_stream.route("/data-stream/reports/types/available", methods=["GET"])
def get_available_report_types():
    """
    Returns the list of report types the system supports.
    This allows the frontend to dynamically render report type options
    without hardcoding them — new types can be added here.
    """
    try:
        report_types = [
            {"key": "trips",          "label": "Trips",            "icon": "🚗", "category": "movement"},
            {"key": "overspeeding",   "label": "Overspeeding",     "icon": "⚡", "category": "safety"},
            {"key": "fuel",           "label": "Fuel Level",       "icon": "⛽", "category": "maintenance"},
            {"key": "geozone",        "label": "Geofence Breach",  "icon": "📍", "category": "safety"},
            {"key": "night_driving",  "label": "Night Driving",    "icon": "🌙", "category": "safety"},
            {"key": "IDILING",        "label": "Idling",           "icon": "🅿", "category": "state"},
            {"key": "PARKING",        "label": "Parking",          "icon": "🅿️", "category": "state"},
        ]

        return reply('success', 200, 'Report types retrieved', report_types)

    except Exception as error:
        return reply('error', 500, str(error), '')


#get parameters that are to be displayed to usr
@data_stream.route("/data-stream/configs/<device_imei>/display-params", methods=["GET"])
def get_params(device_imei):
    
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])

        if(len(str(device_imei)) > 5):

            TargetDevice_Imei = str(device_imei)

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT config_io_id FROM dll_display_params_config WHERE device_imei=%s;", (TargetDevice_Imei,))
                    if(cursor.rowcount >= 1):

                        dataAdapter = cursor.fetchall()
                        Parameters = []

                        for row in dataAdapter:
                            Parameters.append(row[0])

                        return reply('success', 200, 'Found Display Parameters', Parameters)

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'No Parameters Found', '')
                    else:
                        return reply('error', 400, 'Unable to complete request', '')

        else:
            return reply('error', 400, 'Something Is Missing', '')
        
    except Exception as error:
        return reply('error', 500, str(error), '')


#IO Events Data
    
@data_stream.route("/data-stream/<hardware>/ios", methods=['GET'])
def GetIOS(hardware):

    dblink = psycopg2.connect(current_app.config['db_link'])

    try:

        if(hardware == 'ruptela'):
            with dblink:
                with dblink.cursor() as cursor:
                    cursor.execute("SELECT io_event_vendor_uid,io_display_name FROM dll_io_events_registry;")

                    IOS_Found = cursor.fetchall()
                    IOS = []

                    for IO in IOS_Found:
                        SingleIO = {
                            'io_uid': IO[0],
                            'io_name': IO[1]
                        }

                        IOS.append(SingleIO)

                    return reply('success', 200, 'IOS Found', IOS)
                
        elif(hardware == 'teltonika'):

            with dblink:
                with dblink.cursor() as cursor:
                    cursor.execute("SELECT avl_io_id,avl_io_name FROM dll_teltonika_avl_list;")

                    IOS_Found = cursor.fetchall()
                    IOS = []

                    for IO in IOS_Found:
                        SingleIO = {
                            'io_uid': IO[0],
                            'io_name': IO[1]
                        }

                        IOS.append(SingleIO)

                    return reply('success', 200, 'IO AVLs Found', IOS)
                
        else:
            return reply('error', 400, 'Unknown Hardware type', '')




    except Exception as error:
        return reply('error', 500, str(error), '')
    
#Geocoding API
    
@data_stream.route("/data-stream/location/geocoding", methods=["POST"])
def geocoding():

    try:
        payload_data = request.get_json()

        if(len(str(payload_data['data']['logitude_cords'])) > 2) and (len(str(payload_data['data']['latitude_cords'])) > 2):

            LatitudeCords = str(payload_data['data']['latitude_cords'])
            LongitudeCords = str(payload_data['data']['logitude_cords'])

            #Gecodding_data = requests.get(f"https://maps.googleapis.com/maps/api/geocode/json?latlng={ LatitudeCords },{ LongitudeCords}&key=AIzaSyBr0ESjtbQb7jRNfKeygf75Nm0Hub6i4ns")
            #api_data = Gecodding_data.json()

            # Gecodding_data = requests.get(f"https://api.mapbox.com/geocoding/v5/mapbox.places/{LongitudeCords},{LatitudeCords}.json?access_token=sk.eyJ1Ijoib211bG9uZ28iLCJhIjoiY21kb3ZoZnNmMDVybTJxcjJxMTU0a2l2OSJ9.4YphwEQuadKHV8Uk_r3u5A")
            # api_data = Gecodding_data.json()

            #Gecodding_data = requests.get(f"https://api.tomtom.com/search/2/reverseGeocode/{ LatitudeCords },{ LongitudeCords }.json?key=ISZP8XQsiEllwh7VGGg9Zp4tgFAEdfIG")

            # if('streetName' in api_data['addresses'][0]['address']):

            #     if('municipalitySubdivision' in api_data['addresses'][0]['address']):
            #         AddrStreetName = api_data['addresses'][0]['address']['streetName']
            #         AddrSubDivision = api_data['addresses'][0]['address']['countrySubdivision']
            #         AddrMunicipality = api_data['addresses'][0]['address']['municipality']
            #         AddrMunicipalitySub = api_data['addresses'][0]['address']['municipalitySubdivision']
            #         AddrCountry = api_data['addresses'][0]['address']['country']

            #         LOCATION = AddrStreetName + ', ' + AddrMunicipalitySub + ', ' + AddrMunicipality + ', ' + AddrSubDivision + ', ' + AddrCountry

            #     else:
            #         AddrStreetName = api_data['addresses'][0]['address']['streetName']
            #         AddrSubDivision = api_data['addresses'][0]['address']['countrySubdivision']
            #         AddrMunicipality = api_data['addresses'][0]['address']['municipality']
            #         AddrMunicipalitySub = ''
            #         AddrCountry = api_data['addresses'][0]['address']['country']

            #         LOCATION = AddrMunicipality + ', ' + AddrSubDivision + ', ' + AddrCountry

            # else:
            #     if('municipalitySubdivision' in api_data['addresses'][0]['address']):
            #         AddrStreetName = ''
            #         AddrSubDivision = api_data['addresses'][0]['address']['countrySubdivision']
            #         AddrMunicipality = api_data['addresses'][0]['address']['municipality']
            #         AddrMunicipalitySub = api_data['addresses'][0]['address']['municipalitySubdivision']
            #         AddrCountry = api_data['addresses'][0]['address']['country']

            #         LOCATION = AddrMunicipalitySub + ', ' + AddrMunicipality + ', ' + AddrSubDivision + ', ' + AddrCountry

            #     else:
            #         AddrStreetName = ''
            #         AddrSubDivision = api_data['addresses'][0]['address']['countrySubdivision']
            #         AddrMunicipality = api_data['addresses'][0]['address']['municipality']
            #         AddrMunicipalitySub = ''
            #         AddrCountry = api_data['addresses'][0]['address']['country']

            #         LOCATION = AddrMunicipality + ', ' + AddrSubDivision + ', ' + AddrCountry
                    #LOCATION = api_data['results'][0]['formatted_address']

            # Try Nominatim with retry (rate limit = 1 req/sec)
            LOCATION = None
            import time as _time
            for _attempt in range(2):
                try:
                    geocode_request = requests.get(
                        "https://nominatim.openstreetmap.org/reverse",
                        params={"lat": LatitudeCords, "lon": LongitudeCords, "format": "json"},
                        headers={"User-Agent": "NarvasFleet/1.0 (support@navas.ug)"},
                        timeout=15,
                    )
                    if geocode_request.ok:
                        api_reply = geocode_request.json()
                        if 'display_name' in api_reply:
                            LOCATION = api_reply['display_name']
                            break
                except Exception:
                    pass
                if _attempt == 0:
                    _time.sleep(1.1)  # respect Nominatim 1 req/sec rate limit

            # Fallback: return raw coordinates if geocoding failed
            if not LOCATION:
                LOCATION = f"{LatitudeCords}, {LongitudeCords}"

            geocodding_data = {
                "location": LOCATION
            }

            return reply('success', 200, 'Location Found', geocodding_data)

        else:
            return reply('error', 200, 'Something Is Missing', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


#get description of config parameter
@data_stream.route("/data-stream/msic/<io_param_uid>/io-desc/<hardware>/load", methods=['GET'])
def getIO_data(io_param_uid, hardware):

    try:

        dbconnect = psycopg2.connect(current_app.config['db_link'])

        if(hardware == 'ruptela'):

            IO_Cleaned = str(io_param_uid) + '.0'

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT io_display_name,io_data_type,io_min_value,io_max_value,io_units,io_default_error,io_description FROM dll_io_events_config WHERE io_event_vendor_uid=%s;", (str(IO_Cleaned),))

                    if(cursor.rowcount == 1):

                        parameter_dataAdapter = cursor.fetchone()
                        ParameterObject = {
                            "display_name": parameter_dataAdapter[0],
                            "data_type": parameter_dataAdapter[1],
                            "min_value": parameter_dataAdapter[2],
                            "max_value": parameter_dataAdapter[3],
                            "units": parameter_dataAdapter[4],
                            "default_error": parameter_dataAdapter[5],
                            "more_description": parameter_dataAdapter[6]
                        }

                        return reply('success', 200, 'Parameter Loaded', ParameterObject)

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'Parameter Routing Failed-Not Found', '')
                    
                    else:
                        return reply('error', 400, 'Unable to complete request', '')

        elif(hardware == 'teltonika'):

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT avl_io_name FROM dll_teltonika_avl_list WHERE avl_io_id=%s;", (str(io_param_uid),))

                    if(cursor.rowcount == 1):

                        parameter_dataAdapter = cursor.fetchone()
                        ParameterObject = {
                            "display_name": parameter_dataAdapter[0],
                            "data_type": 'no-data',
                            "min_value": 'no-data',
                            "max_value": 'no-data',
                            "units": 'no-data',
                            "default_error": 'no-data',
                            "more_description": 'no-data'
                        }

                        return reply('success', 200, 'Parameter Loaded', ParameterObject)

                    elif(cursor.rowcount == 0):
                        return reply('error', 400, 'Parameter Routing Failed-Not Found', '')
        
    except Exception as error:
        return reply('error', 500, str(error), '')


@data_stream.route("/data-stream/msic/<device_imei>/io-data/values", methods=["GET"])
def GetIO_Values(device_imei):

    try:

        dbconnect = psycopg2.connect(current_app.config['db_link'])

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT device_hardware FROM dll_device_registrar WHERE device_imei=%s;", (str(device_imei),))
                if(cursor.rowcount == 1):

                    hardware_properties_adapter = cursor.fetchone()
                    HardwareModel = hardware_properties_adapter[0]
                    ExemptedModels = ["wetrack2", "gt06n-device", "wetrack_lite"]

                    if(HardwareModel in ExemptedModels):
                        return reply('error', 400, 'Device Hardware Not Supported for this Feature', '')
                    else:

                        cursor.execute("SELECT config_io_id FROM dll_display_params_config WHERE device_imei=%s;", (str(device_imei),))
                        if(cursor.rowcount >= 1):

                            dataAdapter = cursor.fetchall()
                            DisplayValue_Data = []

                            for row in dataAdapter:
                                Configured_DispParamName = row[0]
                                pass

                            

                        elif(cursor.rowcount == 0):
                            return reply('error', 400, 'No Parameters Found', '')
                        else:
                            return reply('error', 400, 'Unable to complete request', '')



                elif(cursor.rowcount == 0):
                    return reply('error', 400, 'Device Not Found', '')
        
    except Exception as error:
        return reply('error', 500, str(error), '')


@data_stream.route("/data/msic/<msic_context>/<msic_target_device>/load", methods=['GET'])
def msic_context(msic_context, msic_target_device):
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    try:
        if(msic_context == 'mileage_calculate_setting'):

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("SELECT setting_value FROM dll_other_settings WHERE setting_name='calculate_mileage' AND device_imei=%s;", (str(msic_target_device),))

                    if(cursor.rowcount == 1):

                        data_pipe = cursor.fetchone()

                        dataReply = {
                            "setting": data_pipe[0]
                        }
                        return reply('success', 200, 'Setting Found SuccessFul', dataReply)

                    elif(cursor.rowcount == 0):

                        dataReply = {
                            "setting": "enabled"
                        }

                        return reply('success', 200, 'No Setting Found, Used Default Setting', dataReply)

    except Exception as error:
        return reply('error', 500, str(error), '')


# ── Trip report data (lightweight, no heavy deps) ───────────────────────────
# Returns trip data from dll_trips_auditor as JSON.
# The frontend generates the PDF/Excel client-side.

@data_stream.route("/data-stream/reports/trips/generate-data", methods=["POST"])
def trips_report_data():
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()
        _cassandra_session = get_cassandra_session()

        report_devices = payload_data['data']['report_devices']
        start_date = str(payload_data['data']['start_date'])
        end_date = str(payload_data['data']['end_date'])

        print(f"[trips_report_data] report_devices={report_devices}, start_date={start_date}, end_date={end_date}")

        if len(report_devices) == 0 or len(start_date) < 5 or len(end_date) < 5:
            return reply('error', 400, 'Some data is Missing', '')

        # Convert DD-MM-YYYY to Python dates for proper PostgreSQL comparison
        from datetime import datetime as dt
        try:
            start_dt = dt.strptime(start_date, "%d-%m-%Y").date()
            end_dt = dt.strptime(end_date, "%d-%m-%Y").date()
        except ValueError:
            return reply('error', 400, 'Invalid date format. Use DD-MM-YYYY', '')

        # Ensure start <= end
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        # Format as YYYY-MM-DD strings — PostgreSQL always accepts ISO format
        start_iso = start_dt.strftime("%Y-%m-%d")
        end_iso = end_dt.strftime("%Y-%m-%d")
        print(f"[trips_report_data] parsed dates: {start_iso} to {end_iso}")

        # Fetch device names from Cassandra in bulk
        device_names = {}
        try:
            cass_query = _cassandra_session.prepare("""
                SELECT device_imei, device_name
                FROM dll_device_basic_data
                WHERE device_imei IN ?
            """)
            cass_rows = _cassandra_session.execute(cass_query, (report_devices,))
            for d in cass_rows:
                device_names[d.device_imei] = d.device_name
        except Exception:
            # Fallback: fetch one by one
            try:
                cass_query = _cassandra_session.prepare("""
                    SELECT device_imei, device_name
                    FROM dll_device_basic_data
                    WHERE device_imei = ?
                """)
                for imei in report_devices:
                    cass_row = _cassandra_session.execute(cass_query, (imei,)).one()
                    device_names[imei] = cass_row.device_name if cass_row else imei
            except Exception:
                # If Cassandra is completely down, use IMEI as name
                for imei in report_devices:
                    device_names[imei] = imei

        with dbconnect:
            with dbconnect.cursor() as cursor:
                all_trips = []

                for device_imei in report_devices:
                    device_name = device_names.get(device_imei, device_imei)

                    cursor.execute("""
                        SELECT
                            trip_uid,
                            trip_date,
                            start_time,
                            end_time,
                            start_mileage,
                            end_mileage,
                            start_fuel_level,
                            end_fuel_level,
                            driver_id,
                            starting_location_point,
                            end_location_point,
                            start_gps_cordinates,
                            end_gps_cordinates
                        FROM
                            dll_trips_auditor
                        WHERE
                            trip_date BETWEEN %s AND %s
                            AND device_imei = %s
                            AND trip_status = %s
                        ORDER BY id DESC
                    """, (start_iso, end_iso, device_imei, 'ended'))

                    print(f"[trips_report_data] device={device_imei}, rowcount={cursor.rowcount}, dates={start_iso} to {end_iso}")

                    if cursor.rowcount >= 1:
                        trips_for_device = {device_name: []}

                        for trip_row in cursor.fetchall():
                            if str(trip_row[4]) != 'NoData' and str(trip_row[5]) != 'NoData':
                                mileage_covered = abs(round(Decimal(trip_row[4]), 2) - round(Decimal(trip_row[5]), 2))
                            else:
                                mileage_covered = 'NoData'

                            trips_for_device[device_name].append({
                                "trip_uid": str(trip_row[0]) if trip_row[0] else "",
                                "trip_date": str(trip_row[1]) if trip_row[1] else "",
                                "start_time": str(trip_row[2]) if trip_row[2] else "",
                                "end_time": str(trip_row[3]) if trip_row[3] else "",
                                "start_mileage": str(trip_row[4]) if trip_row[4] else "NoData",
                                "end_mileage": str(trip_row[5]) if trip_row[5] else "NoData",
                                "mileage_covered": str(mileage_covered),
                                "start_fuel_level": str(trip_row[6]) if trip_row[6] else "NoData",
                                "end_fuel_level": str(trip_row[7]) if trip_row[7] else "NoData",
                                "driver_id": str(trip_row[8]) if trip_row[8] else "",
                                "start_location": str(trip_row[9]) if trip_row[9] else "",
                                "end_location": str(trip_row[10]) if trip_row[10] else "",
                                "start_gps_cords": str(trip_row[11]) if trip_row[11] else "",
                                "end_gps_cords": str(trip_row[12]) if trip_row[12] else ""
                            })

                        all_trips.append(trips_for_device)

                if len(all_trips) > 0:
                    return reply('success', 200, 'Found Trips', all_trips)
                else:
                    return reply('error', 400, 'No Trips Found', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


# ── Night Driving Report (lightweight — returns JSON for client-side generation) ──
@data_stream.route("/data-stream/reports/night-driving/generate-data", methods=["POST"])
def night_driving_report_data():
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()
        _cassandra_session = get_cassandra_session()

        report_devices = payload_data['data']['report_devices']
        start_date = str(payload_data['data']['start_date'])
        end_date = str(payload_data['data']['end_date'])

        print(f"[night_driving_report_data] report_devices={report_devices}, start_date={start_date}, end_date={end_date}")

        if len(report_devices) == 0 or len(start_date) < 5 or len(end_date) < 5:
            return reply('error', 400, 'Some data is Missing', '')

        from datetime import datetime as dt
        try:
            start_dt = dt.strptime(start_date, "%d-%m-%Y").date()
            end_dt = dt.strptime(end_date, "%d-%m-%Y").date()
        except ValueError:
            return reply('error', 400, 'Invalid date format. Use DD-MM-YYYY', '')

        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        # Keep DD-MM-YYYY for dll_triggered_events (date_logged is varchar)
        start_ddmmyyyy = start_dt.strftime("%d-%m-%Y")
        end_ddmmyyyy = end_dt.strftime("%d-%m-%Y")
        print(f"[night_driving_report_data] parsed dates: {start_ddmmyyyy} to {end_ddmmyyyy}")

        # Fetch device names from Cassandra
        device_names = {}
        try:
            cass_query = _cassandra_session.prepare("""
                SELECT device_imei, device_name
                FROM dll_device_basic_data
                WHERE device_imei IN ?
            """)
            cass_rows = _cassandra_session.execute(cass_query, (report_devices,))
            for d in cass_rows:
                device_names[d.device_imei] = d.device_name
        except Exception:
            try:
                cass_query = _cassandra_session.prepare("""
                    SELECT device_imei, device_name
                    FROM dll_device_basic_data
                    WHERE device_imei = ?
                """)
                for imei in report_devices:
                    cass_row = _cassandra_session.execute(cass_query, (imei,)).one()
                    device_names[imei] = cass_row.device_name if cass_row else imei
            except Exception:
                for imei in report_devices:
                    device_names[imei] = imei

        with dbconnect:
            with dbconnect.cursor() as cursor:
                all_events = []

                for device_imei in report_devices:
                    device_name = device_names.get(device_imei, device_imei)

                    cursor.execute("""
                        SELECT
                            location_logged,
                            value_from_device,
                            value_triggered,
                            location_cordinates,
                            date_logged
                        FROM dll_triggered_events
                        WHERE event_triggered = %s
                        AND device_imei = %s
                        AND TO_TIMESTAMP(date_logged, 'DD-MM-YYYY')
                            BETWEEN TO_TIMESTAMP(%s, 'DD-MM-YYYY') AND TO_TIMESTAMP(%s, 'DD-MM-YYYY')
                    """, ('night_driving', device_imei, start_ddmmyyyy, end_ddmmyyyy))

                    print(f"[night_driving_report_data] device={device_imei}, rowcount={cursor.rowcount}")

                    if cursor.rowcount >= 1:
                        events_for_device = {device_name: []}

                        for row in cursor.fetchall():
                            events_for_device[device_name].append({
                                "date_logged": str(row[4]) if row[4] else "",
                                "location_point": str(row[0]) if row[0] else "",
                                "time_violated": str(row[1]) if row[1] else "",
                                "event_triggered": str(row[2]) if row[2] else "",
                                "gps_coordinates": str(row[3]) if row[3] else ""
                            })

                        all_events.append(events_for_device)

                if len(all_events) > 0:
                    return reply('success', 200, 'Found Night Driving Events', all_events)
                else:
                    return reply('error', 400, 'No Night Driving Events Found', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


# ── State Duration Report (PARKING / IDILING — lightweight JSON) ──
@data_stream.route("/data-stream/reports/state/generate-data", methods=["POST"])
def state_report_data():
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()
        _cassandra_session = get_cassandra_session()

        report_devices = payload_data['data']['report_devices']
        start_date = str(payload_data['data']['start_date'])
        end_date = str(payload_data['data']['end_date'])
        report_state = str(payload_data['data'].get('report_state', 'PARKING'))

        print(f"[state_report_data] state={report_state}, devices={report_devices}, dates={start_date} to {end_date}")

        if len(report_devices) == 0 or len(start_date) < 5 or len(end_date) < 5:
            return reply('error', 400, 'Some data is Missing', '')

        from datetime import datetime as dt
        try:
            start_dt = dt.strptime(start_date, "%d-%m-%Y").date()
            end_dt = dt.strptime(end_date, "%d-%m-%Y").date()
        except ValueError:
            return reply('error', 400, 'Invalid date format. Use DD-MM-YYYY', '')

        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        # date_logged in dll_state_durations is a DATE column — use ISO format
        start_iso = start_dt.strftime("%Y-%m-%d")
        end_iso = end_dt.strftime("%Y-%m-%d")
        print(f"[state_report_data] ISO dates: {start_iso} to {end_iso}")

        # Fetch device names from Cassandra
        device_names = {}
        try:
            cass_query = _cassandra_session.prepare("""
                SELECT device_imei, device_name
                FROM dll_device_basic_data
                WHERE device_imei IN ?
            """)
            cass_rows = _cassandra_session.execute(cass_query, (report_devices,))
            for d in cass_rows:
                device_names[d.device_imei] = d.device_name
        except Exception:
            try:
                cass_query = _cassandra_session.prepare("""
                    SELECT device_imei, device_name
                    FROM dll_device_basic_data
                    WHERE device_imei = ?
                """)
                for imei in report_devices:
                    cass_row = _cassandra_session.execute(cass_query, (imei,)).one()
                    device_names[imei] = cass_row.device_name if cass_row else imei
            except Exception:
                for imei in report_devices:
                    device_names[imei] = imei

        with dbconnect:
            with dbconnect.cursor() as cursor:
                all_states = []

                for device_imei in report_devices:
                    device_name = device_names.get(device_imei, device_imei)

                    cursor.execute("""
                        SELECT start_time, duration_of_state, date_logged, end_time,
                               start_location, end_location,
                               start_location_cords, end_location_cords
                        FROM dll_state_durations
                        WHERE device_imei = %s
                        AND state = %s
                        AND end_time != 'Incoming'
                        AND date_logged BETWEEN %s AND %s
                    """, (device_imei, report_state, start_iso, end_iso))

                    print(f"[state_report_data] device={device_imei}, state={report_state}, rowcount={cursor.rowcount}")

                    if cursor.rowcount >= 1:
                        states_for_device = {device_name: []}

                        for row in cursor.fetchall():
                            duration_min = int(row[1]) if row[1] else 0
                            if duration_min < 60:
                                duration_str = f"{duration_min} Minutes"
                            else:
                                hours = duration_min // 60
                                minutes = duration_min % 60
                                duration_str = f"{hours}Hr{'s' if hours > 1 else ''}-{minutes}Min{'s' if minutes != 1 else ''}"

                            states_for_device[device_name].append({
                                "date_logged": str(row[2]) if row[2] else "",
                                "start_time": str(row[0]) if row[0] else "",
                                "end_time": str(row[3]) if row[3] else "",
                                "duration": duration_str,
                                "duration_minutes": duration_min,
                                "start_location": str(row[4]) if row[4] else "",
                                "end_location": str(row[5]) if row[5] else "",
                                "start_gps": str(row[6]) if row[6] else "",
                                "end_gps": str(row[7]) if row[7] else ""
                            })

                        all_states.append(states_for_device)

                if len(all_states) > 0:
                    return reply('success', 200, f'Found {report_state} Data', all_states)
                else:
                    return reply('error', 400, f'No {report_state} Data Found', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


# ── Overspeeding Report (lightweight — returns JSON for client-side generation) ──
@data_stream.route("/data-stream/reports/overspeeding/generate-data", methods=["POST"])
def overspeeding_report_data():
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()
        _cassandra_session = get_cassandra_session()

        report_devices = payload_data['data']['report_devices']
        start_date = str(payload_data['data']['start_date'])
        end_date = str(payload_data['data']['end_date'])

        print(f"[overspeeding_report_data] devices={report_devices}, dates={start_date} to {end_date}")

        if len(report_devices) == 0 or len(start_date) < 5 or len(end_date) < 5:
            return reply('error', 400, 'Some data is Missing', '')

        from datetime import datetime as dt
        try:
            start_dt = dt.strptime(start_date, "%d-%m-%Y").date()
            end_dt = dt.strptime(end_date, "%d-%m-%Y").date()
        except ValueError:
            return reply('error', 400, 'Invalid date format. Use DD-MM-YYYY', '')

        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        start_ddmmyyyy = start_dt.strftime("%d-%m-%Y")
        end_ddmmyyyy = end_dt.strftime("%d-%m-%Y")

        # Fetch device names from Cassandra
        device_names = {}
        try:
            cass_query = _cassandra_session.prepare("""
                SELECT device_imei, device_name FROM dll_device_basic_data WHERE device_imei IN ?
            """)
            cass_rows = _cassandra_session.execute(cass_query, (report_devices,))
            for d in cass_rows:
                device_names[d.device_imei] = d.device_name
        except Exception:
            try:
                cass_query = _cassandra_session.prepare("""
                    SELECT device_imei, device_name FROM dll_device_basic_data WHERE device_imei = ?
                """)
                for imei in report_devices:
                    cass_row = _cassandra_session.execute(cass_query, (imei,)).one()
                    device_names[imei] = cass_row.device_name if cass_row else imei
            except Exception:
                for imei in report_devices:
                    device_names[imei] = imei

        with dbconnect:
            with dbconnect.cursor() as cursor:
                all_events = []

                for device_imei in report_devices:
                    device_name = device_names.get(device_imei, device_imei)

                    cursor.execute("""
                        SELECT location_logged, value_from_device, value_triggered,
                               location_cordinates, date_logged
                        FROM dll_triggered_events
                        WHERE event_triggered = %s
                        AND device_imei = %s
                        AND TO_TIMESTAMP(date_logged, 'DD-MM-YYYY')
                            BETWEEN TO_TIMESTAMP(%s, 'DD-MM-YYYY') AND TO_TIMESTAMP(%s, 'DD-MM-YYYY')
                    """, ('speed', device_imei, start_ddmmyyyy, end_ddmmyyyy))

                    print(f"[overspeeding_report_data] device={device_imei}, rowcount={cursor.rowcount}")

                    if cursor.rowcount >= 1:
                        events_for_device = {device_name: []}
                        for row in cursor.fetchall():
                            events_for_device[device_name].append({
                                "date_logged": str(row[4]) if row[4] else "",
                                "location_point": str(row[0]) if row[0] else "",
                                "moving_speed": str(row[1]) + "KM/H" if row[1] else "",
                                "event_triggered": str(row[2]) if row[2] else "",
                                "gps_coordinates": str(row[3]) if row[3] else ""
                            })
                        all_events.append(events_for_device)

                if len(all_events) > 0:
                    return reply('success', 200, 'Found Overspeeding Events', all_events)
                else:
                    return reply('error', 400, 'No Overspeeding Events Found', '')

    except Exception as error:
        return reply('error', 500, str(error), '')


# ── Geozone Breach Report (lightweight — returns JSON for client-side generation) ──
@data_stream.route("/data-stream/reports/geozone/generate-data", methods=["POST"])
def geozone_report_data():
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        payload_data = request.get_json()
        _cassandra_session = get_cassandra_session()
        report_devices = payload_data['data']['report_devices']
        start_date = str(payload_data['data']['start_date'])
        end_date = str(payload_data['data']['end_date'])
        print(f"[geozone_report_data] devices={report_devices}, dates={start_date} to {end_date}")
        if len(report_devices) == 0 or len(start_date) < 5 or len(end_date) < 5:
            return reply('error', 400, 'Some data is Missing', '')
        from datetime import datetime as dt
        try:
            start_dt = dt.strptime(start_date, "%d-%m-%Y").date()
            end_dt = dt.strptime(end_date, "%d-%m-%Y").date()
        except ValueError:
            return reply('error', 400, 'Invalid date format. Use DD-MM-YYYY', '')
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt
        start_ddmmyyyy = start_dt.strftime("%d-%m-%Y")
        end_ddmmyyyy = end_dt.strftime("%d-%m-%Y")
        device_names = {}
        try:
            cass_query = _cassandra_session.prepare("SELECT device_imei, device_name FROM dll_device_basic_data WHERE device_imei IN ?")
            cass_rows = _cassandra_session.execute(cass_query, (report_devices,))
            for d in cass_rows:
                device_names[d.device_imei] = d.device_name
        except Exception:
            try:
                cass_query = _cassandra_session.prepare("SELECT device_imei, device_name FROM dll_device_basic_data WHERE device_imei = ?")
                for imei in report_devices:
                    cass_row = _cassandra_session.execute(cass_query, (imei,)).one()
                    device_names[imei] = cass_row.device_name if cass_row else imei
            except Exception:
                for imei in report_devices:
                    device_names[imei] = imei
        with dbconnect:
            with dbconnect.cursor() as cursor:
                all_events = []
                for device_imei in report_devices:
                    device_name = device_names.get(device_imei, device_imei)
                    cursor.execute("""
                        SELECT location_logged, value_from_device, value_triggered,
                               location_cordinates, date_logged
                        FROM dll_triggered_events
                        WHERE event_triggered = %s
                        AND device_imei = %s
                        AND TO_TIMESTAMP(date_logged, 'DD-MM-YYYY')
                            BETWEEN TO_TIMESTAMP(%s, 'DD-MM-YYYY') AND TO_TIMESTAMP(%s, 'DD-MM-YYYY')
                    """, ('geozone', device_imei, start_ddmmyyyy, end_ddmmyyyy))
                    print(f"[geozone_report_data] device={device_imei}, rowcount={cursor.rowcount}")
                    if cursor.rowcount >= 1:
                        events_for_device = {device_name: []}
                        for row in cursor.fetchall():
                            geozone_id = str(row[1]).replace("inside_", "") if row[1] else ""
                            geozone_name = "Unknown"
                            if geozone_id:
                                cursor.execute("SELECT geozone_name FROM dll_geozones WHERE geozone_uid = %s", (geozone_id,))
                                gz_info = cursor.fetchone()
                                geozone_name = gz_info[0] if gz_info else "Deleted Zone"
                            events_for_device[device_name].append({
                                "date_logged": str(row[4]) if row[4] else "",
                                "location_point": str(row[0]) if row[0] else "",
                                "geozone_name": geozone_name,
                                "event_triggered": str(row[2]) if row[2] else "",
                                "gps_coordinates": str(row[3]) if row[3] else ""
                            })
                        all_events.append(events_for_device)
                if len(all_events) > 0:
                    return reply('success', 200, 'Found Geozone Events', all_events)
                else:
                    return reply('error', 400, 'No Geozone Events Found', '')
    except Exception as error:
        return reply('error', 500, str(error), '')
