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
import uuid
import pandas as pd
import os
import pytz
import re


_jsonReports_data_bp = Blueprint("Json_Reports_Data", __name__)

timezone = pytz.timezone('Africa/Nairobi')
def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
    
@_jsonReports_data_bp.route("/reports/raw/fuel", methods=["POST"])
def FuelLevelReport_Raw():
    try:
        # Database connection and input payload
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _payload_data = request.get_json()

        # Extract input parameters
        _ReportDevices = _payload_data['data']['report_devices']
        _StartReport_Date = str(_payload_data['data']['start_date'])
        _EndReport_Date = str(_payload_data['data']['end_date'])
        _OriginRequestID = str(uuid.uuid4())
        _OriginUserID = str(_payload_data['data']['origin_user'])
        _RequestTime_Stamp = datetime.datetime.now(timezone).strftime("%d-%m-%Y %I:%M:%S %p")

        if len(_ReportDevices) > 0 and len(_StartReport_Date) > 4 and len(_EndReport_Date) > 4:
            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    # Log request into the reports table
                    cursor.execute("""
                        INSERT INTO dll_reports_downloadable_files (request_uid, file_path, report_caller, request_status, request_datestamp, report_type)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (str(_OriginRequestID), 'NO_DIR_PATH', _OriginUserID, 'in_process', str(_RequestTime_Stamp), 'fuel',))

                    # Prepare trip data for all devices in a single query
                    device_query_placeholder = ', '.join(['%s'] * len(_ReportDevices))
                    cursor.execute(f"""
                        SELECT 
                            d.device_name, 
                            t.device_imei, 
                            t.trip_date, 
                            t.start_time, 
                            t.end_time, 
                            t.start_fuel_level, 
                            t.end_fuel_level, 
                            t.starting_location_point, 
                            t.end_location_point
                        FROM dll_trips_auditor t
                        JOIN dll_device_basic_data d ON t.device_imei = d.device_imei
                        WHERE t.trip_date BETWEEN %s AND %s 
                        AND t.device_imei IN ({device_query_placeholder})
                        AND t.trip_status = %s
                        ORDER BY t.device_imei, t.trip_date DESC
                    """, [_StartReport_Date, _EndReport_Date, *_ReportDevices, 'ended'])

                    # Fetch and process data
                    rows = cursor.fetchall()
                    if not rows:
                        cursor.execute("UPDATE dll_reports_downloadable_files SET request_status=%s WHERE request_uid=%s", ('failed', _OriginRequestID,))
                        return reply("error", 404, "No trips found for the selected devices", "")

                    # Organize data into a JSON-friendly structure
                    report_data = {}
                    for row in rows:
                        device_name = row[0]
                        device_imei = row[1]
                        trip_date = row[2]
                        start_time = row[3]
                        end_time = row[4]
                        start_location = row[7]
                        end_location = row[8]

                        # Calculate difference in fuel levels
                        start_fuel_level = safe_float(row[5])
                        end_fuel_level = safe_float(row[6])
                        fuel_diff = (start_fuel_level - end_fuel_level) if (start_fuel_level is not None and end_fuel_level is not None) else None

                        # Prepare the trip data
                        trip_data = {
                            "Trip Date": trip_date,
                            "Start Time": start_time,
                            "End Time": end_time,
                            "Start Fuel Level": start_fuel_level,
                            "End Fuel Level": end_fuel_level,
                            "Fuel Difference": fuel_diff,
                            "Start Location": start_location,
                            "End Location": end_location
                        }

                        # Organize by device
                        device_key = f"{device_name[:15]}_{device_imei[-4:]}"
                        report_data.setdefault(device_key, []).append(trip_data)

                    # Update request status to completed
                    cursor.execute("""
                        UPDATE dll_reports_downloadable_files
                        SET request_status='completed'
                        WHERE request_uid=%s
                    """, (str(_OriginRequestID),))

                    return reply("success", 200, "Trips report generated successfully", report_data)

        else:
            return reply("error", 400, "Some data is missing", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
