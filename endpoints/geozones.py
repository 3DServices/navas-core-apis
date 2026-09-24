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
import re
from . import geozone_shapes


geozones_bp = Blueprint('GeoZones', __name__)

_HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')


def _color(value):
    """A #RRGGBB colour, or None."""
    value = str(value or '').strip()
    return value if _HEX_COLOR.match(value) else None


def _shape_fields(columns, row):
    """Shape and colour fields of a dll_geozones row (SELECT *), by column
    name so it does not depend on column order. Rows from before migration
    043 have no such columns and come back as a plain polygon."""
    record = dict(zip(columns, row))
    params = record.get('geozone_shape_params')
    try:
        params = json.loads(params) if params else None
    except ValueError:
        params = None
    fields = {
        "geozone_shape": record.get('geozone_shape') or 'polygon',
        "geozone_shape_params": params,
    }
    if record.get('geozone_color'):
        fields["geozone_color"] = record['geozone_color']
    if record.get('geozone_label_color'):
        fields["geozone_label_color"] = record['geozone_label_color']
    return fields


def _missing_fields(checks):
    """A message naming what the body is missing, or ''. Each check is
    (field, value, minimum length) — the old code answered "Some Data Is
    Missing" without saying which, and crashed outright on an absent key."""
    short = [name for name, value, least in checks if len(str(value or '')) < least]
    if not short:
        return ''
    if len(short) == 1:
        return short[0] + " is missing."
    return "These are missing: " + ", ".join(short) + "."


def _shape_error_reply(error):
    """A friendly message when the shape columns are missing."""
    text = str(error)
    if 'geozone_shape' in text or 'geozone_color' in text:
        return reply('error', 500, "The database is missing the geofence shape "
                     "columns. Run python run_migration_043.py on the API server, "
                     "then restart the API.", "")
    return reply('error', 500, text, "")

@geozones_bp.route("/geozones/create", methods=["POST"])
def CreateGezone():
    
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _geozone_payload = request.get_json()

        _Body = (_geozone_payload or {}).get('data') or {}

        # New form: a shape (polygon / circle / line) and its details. The
        # stored ring is computed from the shape, not taken from the client.
        # Old form: geozone_points sent as the ring itself. A shape body has
        # no geozone_points, so nothing here may insist on one.
        try:
            _Shaped = geozone_shapes.from_request(_Body)
        except geozone_shapes.ShapeError as shape_error:
            return reply("error", 400, str(shape_error), "")

        _GeoZoneName = str(_Body.get('geozone_name') or '').lower()
        _GeoZoneDescription = str(_Body.get('geozone_decription')
                                  or _Body.get('geozone_description') or '')
        _GeoZoneOwner = str(_Body.get('geozone_owner') or '')
        _Color = _LabelColor = None

        if _Shaped:
            _Shape, _ShapeParams, _GeoZonePoints = _Shaped
            _Color = _color(_Body.get('geozone_color'))
            _LabelColor = _color(_Body.get('geozone_label_color'))
        else:
            _GeoZonePoints = str(_Body.get('geozone_points') or '')

        _Missing = _missing_fields(
            [('geozone_name', _GeoZoneName, 5),
             ('geozone_decription', _GeoZoneDescription, 6),
             ('geozone_owner', _GeoZoneOwner, 6)]
            + ([] if _Shaped else [('geozone_points', _GeoZonePoints, 3)]))
        if _Missing:
            return reply("error", 400, _Missing, "")

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                # Scoped to the owner: two clients may each have a "main
                # depot", and a clash across clients used to tell one of
                # them that the other had a zone by that name.
                cursor.execute("SELECT geozone_name FROM dll_geozones WHERE geozone_name=%s AND geozone_owner=%s", (_GeoZoneName, _GeoZoneOwner,))

                if(cursor.rowcount == 0):
                    _GeozoneID = str(uuid.uuid4())
                    if _Shaped:
                        cursor.execute("INSERT INTO dll_geozones (geozone_uid, geozone_name, geozone_description, geozone_points, geozone_owner, date_created, geozone_shape, geozone_shape_params, geozone_color, geozone_label_color) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (_GeozoneID, _GeoZoneName, _GeoZoneDescription, _GeoZonePoints, _GeoZoneOwner, str(datetime.datetime.now().date()), _Shape, _ShapeParams, _Color, _LabelColor,))
                    else:
                        cursor.execute("INSERT INTO dll_geozones (geozone_uid, geozone_name, geozone_description, geozone_points, geozone_owner, date_created) VALUES(%s,%s,%s,%s,%s,%s)", (_GeozoneID, _GeoZoneName, _GeoZoneDescription, _GeoZonePoints, _GeoZoneOwner, str(datetime.datetime.now().date()),))

                    return reply('success', 200, "Geozone Created SuccessFully", _GeozoneID)

                elif(cursor.rowcount >= 1):
                    return reply("error", 400, "You already have a geofence called '" + _GeoZoneName + "'.", "")

    except Exception as error:
        return _shape_error_reply(error)
    

@geozones_bp.route("/geozones/<string:geozone_id>/update", methods=["PUT"])
def UpdateGeozone(geozone_id):

    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _geozone_payload = request.get_json()

        _Body = (_geozone_payload or {}).get('data') or {}
        _GeozoneID = str(geozone_id)

        try:
            _Shaped = geozone_shapes.from_request(_Body, prefix='new_')
        except geozone_shapes.ShapeError as shape_error:
            return reply("error", 400, str(shape_error), "")

        _GeoZoneName = str(_Body.get('new_geozone_name') or '').lower()
        _GeoZoneDescription = str(_Body.get('new_geozone_decription')
                                  or _Body.get('new_geozone_description') or '')

        if _Shaped:
            _Shape, _ShapeParams, _GeoZonePoints = _Shaped
        else:
            _GeoZonePoints = str(_Body.get('new_geozone_points') or '')

        _Missing = _missing_fields(
            [('new_geozone_name', _GeoZoneName, 5),
             ('new_geozone_decription', _GeoZoneDescription, 6)]
            + ([] if _Shaped else [('new_geozone_points', _GeoZonePoints, 6)]))
        if _Missing:
            return reply("error", 400, _Missing, "")

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute("SELECT geozone_name FROM dll_geozones WHERE geozone_uid=%s", (_GeozoneID,))

                if(cursor.rowcount == 0):
                    return reply('error', 400, "Geozone Not Found", "")

                elif(cursor.rowcount >= 1):
                    if _Shaped:
                        cursor.execute("UPDATE dll_geozones SET geozone_name=%s, geozone_description=%s, geozone_points=%s, geozone_shape=%s, geozone_shape_params=%s WHERE geozone_uid=%s", (_GeoZoneName, _GeoZoneDescription, _GeoZonePoints, _Shape, _ShapeParams, _GeozoneID,))
                    else:
                        cursor.execute("UPDATE dll_geozones SET geozone_name=%s, geozone_description=%s, geozone_points=%s WHERE geozone_uid=%s", (_GeoZoneName, _GeoZoneDescription, _GeoZonePoints, _GeozoneID,))

                    return reply("success", 200, "Geozone Updated", "")

    except Exception as error:
        return _shape_error_reply(error)
    

@geozones_bp.route("/geozones/<string:owner_uid>/list/<string:access_level>/load", methods=["GET"])
def GetGeoZone(owner_uid, access_level):

    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _GeozoneOwnerID = str(owner_uid)
        _AccessLevel = str(access_level)

        if(len(_GeozoneOwnerID) > 5) and (len(_AccessLevel) > 2):

            if(_AccessLevel == 'service_provider'):

                with _dbconnect:
                    with _dbconnect.cursor() as cursor:
                        cursor.execute("SELECT * FROM dll_geozones WHERE geozone_owner=%s", (_GeozoneOwnerID,))

                        if(cursor.rowcount >= 1):

                            _dataTunnelLink = cursor.fetchall()
                            _Columns = [d[0] for d in cursor.description]
                            _dataHolder = []

                            for _Geozone in _dataTunnelLink:

                                _SingleGeozone = {
                                    "geozone_name": _Geozone[2],
                                    "geozone_uid": _Geozone[1],
                                    "geozone_description": _Geozone[3],
                                    "geozone_points": _Geozone[4],
                                    "date_created": _Geozone[6],
                                    **_shape_fields(_Columns, _Geozone)
                                }
                                _dataHolder.append(_SingleGeozone)

                            return reply("success", 200, "Geozones Found", _dataHolder)

                        elif(cursor.rowcount == 0):
                            return reply("error", 400, "No Geozones Found", "")
            
            elif(_AccessLevel == 'client'):

                with _dbconnect:
                    with _dbconnect.cursor() as cursor:
                        cursor.execute("SELECT * FROM dll_geozones WHERE geozone_owner=%s", (_GeozoneOwnerID,))

                        if(cursor.rowcount >= 1):

                            _dataTunnelLink = cursor.fetchall()
                            _Columns = [d[0] for d in cursor.description]
                            _dataHolder = []

                            for _Geozone in _dataTunnelLink:

                                _SingleGeozone = {
                                    "geozone_name": _Geozone[2],
                                    "geozone_uid": _Geozone[1],
                                    "geozone_description": _Geozone[3],
                                    "geozone_points": _Geozone[4],
                                    "date_created": _Geozone[6],
                                    **_shape_fields(_Columns, _Geozone)
                                }
                                _dataHolder.append(_SingleGeozone)

                            return reply("success", 200, "Geozones Found", _dataHolder)

                        elif(cursor.rowcount == 0):
                            return reply("error", 400, "No Geozones Found", "")
                        
            elif(_AccessLevel == 'inhouse'):

                with _dbconnect:
                    with _dbconnect.cursor() as cursor:
                        cursor.execute("SELECT * FROM dll_geozones")

                        if(cursor.rowcount >= 1):

                            _dataTunnelLink = cursor.fetchall()
                            _Columns = [d[0] for d in cursor.description]
                            _dataHolder = []

                            for _Geozone in _dataTunnelLink:

                                _ZoneOwner = _Geozone[5]
                                cursor.execute("SELECT display_name FROM dll_access_relay WHERE account_uid=%s", (str(_ZoneOwner),))
                                if(cursor.rowcount == 1):
                                    _dataTunnelConnector = cursor.fetchone()
                                    _OwnerName = _dataTunnelConnector[0]

                                    _SingleGeozone = {
                                        "geozone_name": _Geozone[2],
                                        "geozone_uid": _Geozone[1],
                                        "geozone_description": _Geozone[3],
                                        "geozone_points": _Geozone[4],
                                        "date_created": _Geozone[6],
                                        "geozone_owner": _Geozone[5],
                                        "geozone_owner_name": _OwnerName,
                                        **_shape_fields(_Columns, _Geozone)
                                    }
                                    _dataHolder.append(_SingleGeozone)

                                else:
                                    cursor.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid=%s", (str(_ZoneOwner),))
                                    if(cursor.rowcount == 1):
                                        _dataTunnelConnector = cursor.fetchone()
                                        _OwnerName = _dataTunnelConnector[0]

                                        _SingleGeozone = {
                                            "geozone_name": _Geozone[2],
                                            "geozone_uid": _Geozone[1],
                                            "geozone_description": _Geozone[3],
                                            "geozone_points": _Geozone[4],
                                            "date_created": _Geozone[6],
                                            "geozone_owner": _Geozone[5],
                                            "geozone_owner_name": _OwnerName,
                                        **_shape_fields(_Columns, _Geozone)
                                        }
                                        _dataHolder.append(_SingleGeozone)


                            return reply("success", 200, "Geozones Found", _dataHolder)

                        elif(cursor.rowcount == 0):
                            return reply("error", 400, "No Geozones Found", "")
                
        else:
            return reply("error", 400, "Some Data Is Missing", "")

    except Exception as error:
        return reply("error", 500, str(error), "")


@geozones_bp.route("/geozones/<string:geozone_id>/attach", methods=["POST"])
def AttachDevices(geozone_id):

    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _dataPayload = request.get_json()

        _GeozoneID = str(geozone_id)
        _devicesList = _dataPayload['data']['devices']

        if(len(_GeozoneID) > 5) and (len(_devicesList) > 0):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    
                    for _device in _devicesList:

                        cursor.execute("SELECT attached_geozones FROM dll_geozone_attachments WHERE device_imei=%s", (str(_device),))

                        if(cursor.rowcount == 0):
                            _attachList = []
                            _attachList.append(_GeozoneID)
                            _attachedListObject = json.dumps(_attachList)
                            cursor.execute("INSERT INTO dll_geozone_attachments (device_imei, attached_geozones) VALUES(%s, %s);", (_device, str(_attachedListObject),))

                        elif(cursor.rowcount == 1):
                            _dataTunnelBelt = cursor.fetchone()
                            _existingList = _dataTunnelBelt[0]
                            _ZonesList = json.loads(_existingList)

                            if(_GeozoneID not in _ZonesList):

                                _ZonesList.append(_GeozoneID)
                                _UpdatedList = json.dumps(_ZonesList)

                                cursor.execute("UPDATE dll_geozone_attachments SET attached_geozones=%s WHERE device_imei=%s", (_UpdatedList, str(_device),))


                            else:
                                return reply('success', 200, "Geozone Already Attached", "")

                    return reply('success', 200, "Geozone Attached", "")

        else:
            return reply('error', 400, "Some Data Is Missing", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    

@geozones_bp.route("/geozones/<string:geozone_id>/detach/<string:device_id>/action", methods=["PUT"])
def DetachGeozone(geozone_id, device_id):

    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])

        _GeozoneID = str(geozone_id)
        _DeviceImei = str(device_id)

        if(len(_GeozoneID) > 5) and (len(_DeviceImei) > 3):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                        cursor.execute("SELECT attached_geozones FROM dll_geozone_attachments WHERE device_imei=%s", (str(_DeviceImei),))

                        if(cursor.rowcount == 0):
                            return reply("error", 400, "Device Route Not Found", "")

                        elif(cursor.rowcount == 1):
                            _dataTunnelBelt = cursor.fetchone()
                            _existingList = _dataTunnelBelt[0]
                            _ZonesList = json.loads(_existingList)

                            if(_GeozoneID in _ZonesList):

                                _ZonesList.remove(_GeozoneID)
                                _UpdatedList = json.dumps(_ZonesList)

                                cursor.execute("UPDATE dll_geozone_attachments SET attached_geozones=%s WHERE device_imei=%s", (str(_UpdatedList), _DeviceImei,))
                                
                                return reply("success", 200, "Geozone Detached", "")
                            
                            else:
                                return reply('error', 400, "Geozone Not Attached", "")

        else:
            return reply("error", 400, "Some data Is Missing", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    

@geozones_bp.route("/geozones/devices/<string:device_uid>/list", methods=["GET"])
def GetGeozones(device_uid):

    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _FocusDeviceID = str(device_uid)

        if(len(_FocusDeviceID) > 5):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("SELECT attached_geozones FROM dll_geozone_attachments WHERE device_imei=%s", (_FocusDeviceID,))

                    if(cursor.rowcount == 1):

                        _dataTunnelLink = cursor.fetchone()
                        _AttachedGeoZones = json.loads(_dataTunnelLink[0])
                        _AvailableZones = []

                        if(len(_AttachedGeoZones) > 0):
                            for _Zone in _AttachedGeoZones:
                                cursor.execute("SELECT geozone_name, geozone_description FROM dll_geozones WHERE geozone_uid=%s", (str(_Zone),))
                                _ZoneDataTunnel = cursor.fetchone()
                                _ZoneName = _ZoneDataTunnel[0]
                                _ZoneDescription = _ZoneDataTunnel[1]

                                _SingleZone = {
                                    "zone_uid": _Zone,
                                    "zone_name": _ZoneName,
                                    "zone_description": _ZoneDescription
                                }
                                _AvailableZones.append(_SingleZone)

                            return reply("success", 200, "Found Geozones", _AvailableZones)
                        else:
                            return reply("error", 400, "No Geozones Attached", "")
                    else:
                        return reply("error", 400, "Device Not Found", "")

        else:
            return reply("error", 400, "Some data is Missing", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    

@geozones_bp.route("/geozones/<string:geozone_id>/details", methods=["GET"])
def GetGeoZoneData(geozone_id):

    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _geozoneID = str(geozone_id)

        if(len(_geozoneID) > 6):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_geozones WHERE geozone_uid=%s", (_geozoneID,))

                    if(cursor.rowcount == 1):

                        _dataTunnel = cursor.fetchone()
                        _Record = dict(zip([d[0] for d in cursor.description], _dataTunnel))
                        _dataHolder = {
                            "geozone_name": _Record['geozone_name'],
                            "geozone_description": _Record['geozone_description'],
                            "geopoints": _Record['geozone_points'],
                            **_shape_fields(list(_Record.keys()), list(_Record.values()))
                        }

                        return reply("success", 200, "Found Geozone", _dataHolder)

                    else:
                        return reply("error", 400, "No Geozone Found", "")

        else:
            return reply("error", 400, "Some data Is Missing", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    

@geozones_bp.route("/geozones/<string:geozone_id>/delete", methods=["DELETE"])
def DeleteGeoZoneData(geozone_id):

    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _geozoneID = str(geozone_id)

        if(len(_geozoneID) > 6):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("SELECT geozone_name FROM dll_geozones WHERE geozone_uid=%s", (_geozoneID,))

                    if(cursor.rowcount == 1):

                       cursor.execute("DELETE FROM dll_geozones WHERE geozone_uid=%s", (_geozoneID,))
                       cursor.execute("DELETE FROM dll_geozone_attachments WHERE attached_geozones=%s", (_geozoneID,))

                       return reply("success", 200, "Geozone Deleted SuccessFully", "")

                    else:
                        return reply("error", 400, "No Geozone Found", "")

        else:
            return reply("error", 400, "Some data Is Missing", "")

    except Exception as error:
        return reply("error", 500, str(error), "")


@geozones_bp.route("/geozones/<string:geozone_id>/attached-devices", methods=["GET"])
def GetAttachedDevices(geozone_id):
    """Return all device IMEIs that have this geozone in their attached_geozones list."""
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _geozoneID = str(geozone_id)

        if len(_geozoneID) < 6:
            return reply("error", 400, "Some data is Missing", "")

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                # Find all device rows whose attached_geozones JSON array contains this geozone
                cursor.execute(
                    "SELECT device_imei, attached_geozones FROM dll_geozone_attachments"
                )
                _attachedDevices = []

                for row in cursor.fetchall():
                    _deviceImei = row[0]
                    try:
                        _zones = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                    except Exception:
                        _zones = []

                    if _geozoneID in [str(z) for z in _zones]:
                        _attachedDevices.append(_deviceImei)

                if len(_attachedDevices) > 0:
                    return reply("success", 200, "Found attached devices", _attachedDevices)
                else:
                    return reply("success", 200, "No devices attached", [])

    except Exception as error:
        return reply("error", 500, str(error), "")


# ═══════════════════════════════════════════════════════════════════════════════
# GEOZONE GROUPS — CRUD + assign/remove geofences to/from groups
#
# Table: dll_geozone_groups
#   group_uid         UUID PK
#   group_name        TEXT
#   group_description TEXT
#   group_owner       TEXT (owner_uid — same as geozone_owner)
#   date_created      TEXT
#
# Geozones link to groups via a nullable group_uid column on dll_geozones.
# ═══════════════════════════════════════════════════════════════════════════════

@geozones_bp.route("/geozones/groups/create", methods=["POST"])
def CreateGeozoneGroup():
    """Create a new geozone group for the customer."""
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _payload = request.get_json()

        _GroupName = str(_payload['data']['group_name']).strip()
        _GroupDescription = str(_payload['data'].get('group_description', '')).strip()
        _GroupOwner = str(_payload['data']['group_owner'])

        if len(_GroupName) < 2 or len(_GroupOwner) < 5:
            return reply("error", 400, "Group name and owner are required", "")

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT group_uid FROM dll_geozone_groups WHERE group_name=%s AND group_owner=%s",
                    (_GroupName.lower(), _GroupOwner)
                )
                if cursor.rowcount > 0:
                    return reply("error", 400, "A group with this name already exists", "")

                _GroupUID = str(uuid.uuid4())
                cursor.execute(
                    "INSERT INTO dll_geozone_groups (group_uid, group_name, group_description, group_owner, date_created) VALUES (%s, %s, %s, %s, %s)",
                    (_GroupUID, _GroupName.lower(), _GroupDescription, _GroupOwner, str(datetime.datetime.now().date()))
                )
                return reply("success", 201, "Group created successfully", {"group_uid": _GroupUID})

    except Exception as error:
        return reply("error", 500, str(error), "")


@geozones_bp.route("/geozones/groups/<string:owner_uid>/list", methods=["GET"])
def ListGeozoneGroups(owner_uid):
    """List all geozone groups for an owner, with count of geozones in each."""
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _OwnerUID = str(owner_uid)

        if len(_OwnerUID) < 5:
            return reply("error", 400, "Owner UID is required", "")

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT group_uid, group_name, group_description, group_owner, date_created FROM dll_geozone_groups WHERE group_owner=%s ORDER BY date_created DESC",
                    (_OwnerUID,)
                )

                if cursor.rowcount == 0:
                    return reply("success", 200, "No groups found", [])

                _groups = []
                for row in cursor.fetchall():
                    _gid = row[0]
                    cursor.execute(
                        "SELECT COUNT(*) FROM dll_geozones WHERE group_uid=%s",
                        (_gid,)
                    )
                    _count = cursor.fetchone()[0]

                    _groups.append({
                        "group_uid": _gid,
                        "group_name": row[1],
                        "group_description": row[2],
                        "group_owner": row[3],
                        "date_created": row[4],
                        "geozone_count": _count
                    })

                return reply("success", 200, "Groups retrieved", _groups)

    except Exception as error:
        return reply("error", 500, str(error), "")


@geozones_bp.route("/geozones/groups/<string:group_uid>/update", methods=["PUT"])
def UpdateGeozoneGroup(group_uid):
    """Update a geozone group name or description."""
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _payload = request.get_json()
        _GroupUID = str(group_uid)

        _GroupName = str(_payload['data'].get('group_name', '')).strip()
        _GroupDescription = str(_payload['data'].get('group_description', '')).strip()

        if len(_GroupName) < 2:
            return reply("error", 400, "Group name is required", "")

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute(
                    "UPDATE dll_geozone_groups SET group_name=%s, group_description=%s WHERE group_uid=%s",
                    (_GroupName.lower(), _GroupDescription, _GroupUID)
                )
                if cursor.rowcount == 0:
                    return reply("error", 404, "Group not found", "")

                return reply("success", 200, "Group updated", "")

    except Exception as error:
        return reply("error", 500, str(error), "")


@geozones_bp.route("/geozones/groups/<string:group_uid>/delete", methods=["DELETE"])
def DeleteGeozoneGroup(group_uid):
    """Delete a geozone group. Unlinks any geozones assigned to it."""
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _GroupUID = str(group_uid)

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute(
                    "UPDATE dll_geozones SET group_uid=NULL WHERE group_uid=%s",
                    (_GroupUID,)
                )
                cursor.execute(
                    "DELETE FROM dll_geozone_groups WHERE group_uid=%s",
                    (_GroupUID,)
                )
                if cursor.rowcount == 0:
                    return reply("error", 404, "Group not found", "")

                return reply("success", 200, "Group deleted", "")

    except Exception as error:
        return reply("error", 500, str(error), "")


@geozones_bp.route("/geozones/groups/<string:group_uid>/assign", methods=["POST"])
def AssignGeozonesToGroup(group_uid):
    """Assign one or more geozones to a group."""
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _payload = request.get_json()
        _GroupUID = str(group_uid)
        _GeozoneUIDs = _payload['data'].get('geozone_uids', [])

        if not _GeozoneUIDs:
            return reply("error", 400, "No geozones provided", "")

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute("SELECT group_uid FROM dll_geozone_groups WHERE group_uid=%s", (_GroupUID,))
                if cursor.rowcount == 0:
                    return reply("error", 404, "Group not found", "")

                _updated = 0
                for _zid in _GeozoneUIDs:
                    cursor.execute(
                        "UPDATE dll_geozones SET group_uid=%s WHERE geozone_uid=%s",
                        (_GroupUID, str(_zid))
                    )
                    _updated += cursor.rowcount

                return reply("success", 200, str(_updated) + " geozones assigned to group", {"updated": _updated})

    except Exception as error:
        return reply("error", 500, str(error), "")


@geozones_bp.route("/geozones/groups/<string:group_uid>/remove", methods=["POST"])
def RemoveGeozonesFromGroup(group_uid):
    """Remove one or more geozones from a group (sets group_uid to NULL)."""
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])
        _payload = request.get_json()
        _GroupUID = str(group_uid)
        _GeozoneUIDs = _payload['data'].get('geozone_uids', [])

        if not _GeozoneUIDs:
            return reply("error", 400, "No geozones provided", "")

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                _removed = 0
                for _zid in _GeozoneUIDs:
                    cursor.execute(
                        "UPDATE dll_geozones SET group_uid=NULL WHERE geozone_uid=%s AND group_uid=%s",
                        (str(_zid), _GroupUID)
                    )
                    _removed += cursor.rowcount

                return reply("success", 200, str(_removed) + " geozones removed from group", {"removed": _removed})

    except Exception as error:
        return reply("error", 500, str(error), "")
    