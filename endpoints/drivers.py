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
import uuid

driversbp = Blueprint('driversbp', __name__)

@driversbp.route('/drivers/score/create', methods=['POST'])
def CreateScore():
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _dataPayload = request.get_json()

        _ScoreName = _dataPayload['score_name']
        _ScoreOrder = _dataPayload['score_order'] #descending or ascending the lowest score is the best or highest score is the best
        _ScorePoints_Order = _dataPayload['score_points_order'] #add more points or reduce points
        _ViolationParameter = _dataPayload['violation_parameter'] # eg: overspeeding, harsh braking
        _PointsDenomination = _dataPayload['points_denomination'] #eg: 5 points to either add or reduce

        with _dbconnect:
            with _dbconnect.cursor() as _dbcursor:
                _dbcursor.execute("INSERT INTO dll_driver_score_configs (score_uid, score_name, score_order, score_points_order, violation_parameter, points_denomination) VALUES (%s, %s, %s, %s, %s, %s)", (str(uuid.uuid4()), _ScoreName, _ScoreOrder, _ScorePoints_Order, _ViolationParameter, _PointsDenomination))
                _dbconnect.commit()
                return reply("success", 200, "Driver Score Created", "")

    except Exception as e:
        return reply("error", 500, str(e), "")


@driversbp.route('/drivers/score/list', methods=['GET'])
def ListScores():
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])

        with _dbconnect:
            with _dbconnect.cursor() as _dbcursor:
                _dbcursor.execute("SELECT score_uid, score_name, score_order, score_points_order, violation_parameter, points_denomination FROM dll_driver_score_configs")
                _result = _dbcursor.fetchall()
                _scores = []
                for row in _result:
                    _score = {
                        "score_uid": row[0],
                        "score_name": row[1],
                        "score_order": row[2],
                        "score_points_order": row[3],
                        "violation_parameter": row[4],
                        "points_denomination": row[5]
                    }
                    _scores.append(_score)
                return reply("success", 200, "Driver Scores Retrieved", _scores)

    except Exception as e:
        return reply("error", 500, str(e), "")


@driversbp.route('/drivers/score/update', methods=['PUT'])
def UpdateScore():
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _dataPayload = request.get_json()

        _ScoreUID = _dataPayload['score_uid']
        _ScoreName = _dataPayload['score_name']
        _ScoreOrder = _dataPayload['score_order'] #descending or ascending the lowest score is the best or highest score is the best
        _ScorePoints_Order = _dataPayload['score_points_order'] #add more points or reduce points
        _ViolationParameter = _dataPayload['violation_parameter'] # eg: overspeeding, harsh braking
        _PointsDenomination = _dataPayload['points_denomination'] #eg: 5 points to either add or reduce

        with _dbconnect:
            with _dbconnect.cursor() as _dbcursor:
                _dbcursor.execute("UPDATE dll_driver_score_configs SET score_name=%s, score_order=%s, score_points_order=%s, violation_parameter=%s, points_denomination=%s WHERE score_uid=%s", (_ScoreName, _ScoreOrder, _ScorePoints_Order, _ViolationParameter, _PointsDenomination, _ScoreUID))
                _dbconnect.commit()
                return reply("success", 200, "Driver Score Updated", "")

    except Exception as e:
        return reply("error", 500, str(e), "")
    

@driversbp.route('/drivers/score/delete', methods=['DELETE'])
def DeleteScore():
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _dataPayload = request.get_json()

        _ScoreUID = _dataPayload['score_uid']

        with _dbconnect:
            with _dbconnect.cursor() as _dbcursor:
                _dbcursor.execute("DELETE FROM dll_driver_score_configs WHERE score_uid=%s", (_ScoreUID,))
                _dbconnect.commit()
                return reply("success", 200, "Driver Score Deleted", "")

    except Exception as e:
        return reply("error", 500, str(e), "")
    

