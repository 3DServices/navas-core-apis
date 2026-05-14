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

groups_bp = Blueprint('Groups', __name__)

@groups_bp.route("/groups/create", methods=["POST"])
def CreateGroup():

    try:
        _dbconnect = psycopg2.connect(current_app.config["db_link"])
        _payload_object = request.get_json()

        _GroupName = str(_payload_object['data']['group_name'])
        _GroupParent_Owner = str(_payload_object['data']['group_parent_owner'])
        _GroupID = str(uuid.uuid4())

        if(len(_GroupName) > 4) and (len(_GroupParent_Owner) > 6):
            
            _devices = []
            _default_devices = json.dumps(_devices)

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("INSERT INTO dll_device_groups (group_local_uid, group_display_name, owner_parent_uid, devices_attached) VALUES(%s, %s, %s, %s)", (_GroupID, _GroupName, _GroupParent_Owner, str(_default_devices),))
                    _dbconnect.commit()

                    return reply("success", 200, "Group Created", "")

        else:
            return reply("error", 400, "Some data Is Missing", "")
        
    except Exception as error:
        return reply('error', 500, str(error), '')
    

@groups_bp.route("/groups/<string:level>/<string:parent_uid>/list", methods=["GET"])
def GetAccount_Groups(level, parent_uid):

    try:
        _dbconnect = psycopg2.connect(current_app.config["db_link"])
        _UserLevel = str(level)
        _ParentOwnerID = str(parent_uid)

        if(_UserLevel == 'inhouse'):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_device_groups")

                    if(cursor.rowcount >= 1):
                        _dataTunnelLink = cursor.fetchall()
                        _dataGroup_Holder = []
                        

                        for _Group in _dataTunnelLink:
                            _devicesAttached = json.loads(_Group[3])
                            _attachedDeviceNames = []
                            _attachedUsers = []

                            for _deviceImei in _devicesAttached:
                                cursor.execute("SELECT device_name FROM dll_device_basic_data WHERE device_imei=%s", (str(_deviceImei),))
                                if(cursor.rowcount == 1):
                                    _deviceDataTunnel = cursor.fetchone()
                                    _Attached_DeviceName = _deviceDataTunnel[0]
                                    _attachedDeviceNames.append(_Attached_DeviceName)
                                else:
                                    _Attached_DeviceName = 'Imei-Deleted'
                                    _attachedDeviceNames.append(_Attached_DeviceName)
                            
                            _GroupID_Focused = _Group[0]

                            cursor.execute("SELECT user_attached FROM dll_group_attachments WHERE group_attached=%s", (_GroupID_Focused,))
                            if(cursor.rowcount >= 1):
                                _dataTunnel = cursor.fetchall()
                                for _USER_CI in _dataTunnel:
                                    _UserID_Attached = _USER_CI[0]

                                    cursor.execute("SELECT display_name FROM dll_access_relay WHERE account_uid=%s", (_UserID_Attached,))
                                    _userTunneldata = cursor.fetchone()
                                    _UserFullName = _userTunneldata[0]

                                    _singleUser = {
                                        "account_fullname": _UserFullName,
                                        "account_uid": _UserID_Attached
                                    }
                                    _attachedUsers.append(_singleUser)


                            _SingleGroup = {
                                "group_uid": _Group[0],
                                "group_name": _Group[1],
                                "devices": _attachedDeviceNames,
                                "device_imei": _devicesAttached,
                                "users": _attachedUsers
                            }
                            _dataGroup_Holder.append(_SingleGroup)

                        return reply("success", 200, "Groups Found", _dataGroup_Holder)
                    else:
                        return reply("error", 400, "No Groups Found", "")
        
        elif(_UserLevel == 'client'):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_device_groups WHERE owner_parent_uid=%s", (_ParentOwnerID,))

                    if(cursor.rowcount >= 1):
                        _dataTunnelLink = cursor.fetchall()
                        _dataGroup_Holder = []

                        for _Group in _dataTunnelLink:
                            _devicesAttached = json.loads(_Group[3])
                            _attachedDeviceNames = []
                            _attachedUsers = []

                            for _deviceImei in _devicesAttached:
                                cursor.execute("SELECT device_name FROM dll_device_basic_data WHERE device_imei=%s", (str(_deviceImei),))
                                if(cursor.rowcount == 1):
                                    _deviceDataTunnel = cursor.fetchone()
                                    _Attached_DeviceName = _deviceDataTunnel[0]
                                    _attachedDeviceNames.append(_Attached_DeviceName)
                                else:
                                    _Attached_DeviceName = 'Imei-Deleted'
                                    _attachedDeviceNames.append(_Attached_DeviceName)

                            _GroupID_Focused = _Group[0]

                            cursor.execute("SELECT user_attached FROM dll_group_attachments WHERE group_attached=%s", (_GroupID_Focused,))
                            if(cursor.rowcount >= 1):
                                _dataTunnel = cursor.fetchall()
                                for _USER_CI in _dataTunnel:
                                    _UserID_Attached = _USER_CI[0]

                                    cursor.execute("SELECT display_name FROM dll_access_relay WHERE account_uid=%s", (_UserID_Attached,))
                                    _userTunneldata = cursor.fetchone()
                                    _UserFullName = _userTunneldata[0]

                                    _singleUser = {
                                        "account_fullname": _UserFullName,
                                        "account_uid": _UserID_Attached
                                    }
                                    _attachedUsers.append(_singleUser)


                            _SingleGroup = {
                                "group_uid": _Group[0],
                                "group_name": _Group[1],
                                "devices": _attachedDeviceNames,
                                "device_imei": _devicesAttached,
                                "users": _attachedUsers
                            }
                            _dataGroup_Holder.append(_SingleGroup)

                        return reply("success", 200, "Groups Found", _dataGroup_Holder)
                    
                    else:
                        return reply("error", 400, "No Groups Found", "")
                    
        elif(_UserLevel == 'service_provider'):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("SELECT * FROM dll_device_groups WHERE owner_parent_uid=%s", (_ParentOwnerID,))

                    if(cursor.rowcount >= 1):
                        _dataTunnelLink = cursor.fetchall()
                        _dataGroup_Holder = []

                        for _Group in _dataTunnelLink:
                            _devicesAttached = json.loads(_Group[3])
                            _attachedDeviceNames = []
                            _attachedUsers = []

                            for _deviceImei in _devicesAttached:
                                cursor.execute("SELECT device_name FROM dll_device_basic_data WHERE device_imei=%s", (str(_deviceImei),))
                                if(cursor.rowcount == 1):
                                    _deviceDataTunnel = cursor.fetchone()
                                    _Attached_DeviceName = _deviceDataTunnel[0]
                                    _attachedDeviceNames.append(_Attached_DeviceName)
                                else:
                                    _Attached_DeviceName = 'Imei-Deleted'
                                    _attachedDeviceNames.append(_Attached_DeviceName)

                            _GroupID_Focused = _Group[0]

                            cursor.execute("SELECT user_attached FROM dll_group_attachments WHERE group_attached=%s", (_GroupID_Focused,))
                            if(cursor.rowcount >= 1):
                                _dataTunnel = cursor.fetchall()
                                for _USER_CI in _dataTunnel:
                                    _UserID_Attached = _USER_CI[0]

                                    cursor.execute("SELECT display_name FROM dll_access_relay WHERE account_uid=%s", (_UserID_Attached,))
                                    _userTunneldata = cursor.fetchone()
                                    _UserFullName = _userTunneldata[0]

                                    _singleUser = {
                                        "account_fullname": _UserFullName,
                                        "account_uid": _UserID_Attached
                                    }
                                    _attachedUsers.append(_singleUser)


                            _SingleGroup = {
                                "group_uid": _Group[0],
                                "group_name": _Group[1],
                                "devices": _attachedDeviceNames,
                                "device_imei": _devicesAttached,
                                "users": _attachedUsers
                            }
                            _dataGroup_Holder.append(_SingleGroup)

                        return reply("success", 200, "Groups Found", _dataGroup_Holder)
                    
                    else:
                        return reply("error", 400, "No Groups Found", "")
        else:
            return reply("error", 400, "Unknown Level", "")
        
    except Exception as error:
        return reply("error", 500, str(error), "")
    

@groups_bp.route("/groups/<string:group_uid>/update", methods=["PUT"])
def UpdateGroup(group_uid):

    try:
        _dbconnect = psycopg2.connect(current_app.config["db_link"])
        _FocusGroup_UID = str(group_uid)
        _payload_data = request.get_json()

        _NewGroupName = str(_payload_data['data']['new_group_name'])

        if(len(_NewGroupName) > 4) and (len(_FocusGroup_UID) > 6):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("UPDATE dll_device_groups SET group_display_name=%s WHERE group_local_uid=%s", (_NewGroupName, _FocusGroup_UID,))

                    return reply("success", 200, "Group Updated", "")

        else:
            return reply("error", 400, "Some data is Missing", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    

@groups_bp.route("/groups/<string:group_uid>/delete", methods=["DELETE"])
def DeleteGroup(group_uid):

    try:
        _dbconnect = psycopg2.connect(current_app.config["db_link"])
        _TargetGroupID = str(group_uid)

        if(len(_TargetGroupID) > 5):

            with _dbconnect:
                with  _dbconnect.cursor() as cursor:
                    cursor.execute("DELETE FROM dll_device_groups WHERE group_local_uid=%s", (_TargetGroupID,))

                    return reply("success", 200, "Group Deleted", "")

        else:
            return reply("error", 400, "Some data is Missing", "")

    except Exception as error:
        return reply("error", 500, str(error), "")



@groups_bp.route("/groups/<string:group_uid>/attach-devices", methods=["POST"])
def AttachDevices(group_uid):

    try:
        _dbconnect = psycopg2.connect(current_app.config["db_link"])
        _FocusGroupID = str(group_uid)
        _payload = request.get_json()

        _devicesAttached = _payload['data']['devices']

        if(len(_devicesAttached) > 0):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("SELECT devices_attached FROM dll_device_groups WHERE group_local_uid=%s", (_FocusGroupID,))

                    if(cursor.rowcount >= 1):

                        _dataTunnelLink = cursor.fetchone()
                        _Existing_devicesAttached_Found = json.loads(_dataTunnelLink[0])

                        for _deviceNominated in _devicesAttached:
                            if(_deviceNominated not in _Existing_devicesAttached_Found):
                                _Existing_devicesAttached_Found.append(_deviceNominated)

                            else:
                                pass
                        
                        _NewUpdatedDevices_Attached = json.dumps(_Existing_devicesAttached_Found)
                        cursor.execute("UPDATE dll_device_groups SET devices_attached=%s WHERE group_local_uid=%s", (str(_NewUpdatedDevices_Attached), _FocusGroupID,))

                        return reply("success", 200, "Devices Attached", "")
                    
                    else:
                        return reply("error", 400, "Group Not Found", "")

        else:
            return reply("error", 400, "No Devices Selected", "")

    except Exception as error:
        return reply("error", 500, str(error), "")


@groups_bp.route("/groups/<string:group_uid>/attach-user/<string:user_uid>/selected", methods=["PUT"])
def AttachUser(group_uid, user_uid):

    try:
        _dbconnect = psycopg2.connect(current_app.config["db_link"])
        _FocusedGroupID = str(group_uid)
        _UserAttached = str(user_uid)

        if(len(_FocusedGroupID) > 6) and (len(_UserAttached) > 5):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("SELECT attachment_uid FROM dll_group_attachments WHERE user_attached=%s AND group_attached=%s", (str(_UserAttached), str(_FocusedGroupID),))

                    if(cursor.rowcount == 0):
                        _attachmentUID = str(uuid.uuid4())
                        cursor.execute("INSERT INTO dll_group_attachments (attachment_uid, user_attached, group_attached) VALUES(%s, %s, %s)", (_attachmentUID, _UserAttached, _FocusedGroupID,))

                        return reply("success", 200, "Attachment SuccessFul", "")

                    elif(cursor.rowcount >= 1):
                        return reply("error", 400, "User Attachment Exists", "")

        else:
            return reply("error", 400, "Some data is missing", "")
        
    except Exception as error:
        return reply("error", 500, str(error), "")
    


@groups_bp.route("/groups/user/<string:user_uid>/list-devices", methods=["GET"])
def GetDevicesAttached(user_uid):

    try:
        _dbconnect = psycopg2.connect(current_app.config["db_link"])
        _TargetUserID = str(user_uid)

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute("SELECT group_attached FROM dll_group_attachments WHERE user_attached=%s", (_TargetUserID,))

                if(cursor.rowcount >= 1):

                    _dataTunnel_Link = cursor.fetchall()
                    _UserAssigned_Fleet = []

                    for _groupAttached in _dataTunnel_Link:

                        cursor.execute("SELECT devices_attached FROM dll_device_groups WHERE group_local_uid=%s", (_groupAttached,))

                        if(cursor.rowcount == 1):

                            _groupDataTunnelLink = cursor.fetchone()
                            _FocusedGroup_Attached_Devices = json.loads(_groupDataTunnelLink[0])

                            if(len(_FocusedGroup_Attached_Devices) > 0):

                                for _Focused_DeviceImei in _FocusedGroup_Attached_Devices:
                                    
                                    cursor.execute("SELECT device_name,device_simcard,device_car_make,device_car_model,device_vin_number,device_car_type,events_attached,device_billing_status,device_client FROM dll_device_basic_data WHERE device_imei=%s;", (str(_Focused_DeviceImei),))

                                    DeviceBasicData_Adapter = cursor.fetchone()

                                    if True:
                                        SimCard = DeviceBasicData_Adapter[1]
                                        cursor.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid=%s;", (str(SimCard),))
                                        SimcardData = cursor.fetchone()
                                        SimcardNumber = SimcardData[0]

                                        cursor.execute("SELECT device_vendor,device_hardware FROM dll_device_registrar WHERE device_imei=%s;", (str(_Focused_DeviceImei),))
                                        Hardware_dataAdapter = cursor.fetchone()
                                        Hardware = Hardware_dataAdapter[0]
                                        HardwareModel = Hardware_dataAdapter[1]

                                        _ClientID = DeviceBasicData_Adapter[8]
                                        cursor.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid=%s", (str(_ClientID),))
                                        _dataLink = cursor.fetchone()
                                        _ClientName = _dataLink[0]

                                        SingleBasic_Data = {
                                            "device_name": DeviceBasicData_Adapter[0],
                                            "simcard": SimcardNumber,
                                            "simcard_uid": SimCard,
                                            "car_make": DeviceBasicData_Adapter[2],
                                            "car_model": DeviceBasicData_Adapter[3],
                                            "vin_number": DeviceBasicData_Adapter[4],
                                            "car_type": DeviceBasicData_Adapter[5],
                                            "events_attached": DeviceBasicData_Adapter[6],
                                            "billing_status": DeviceBasicData_Adapter[7],
                                            "device_imei": _Focused_DeviceImei,
                                            "client_uid": DeviceBasicData_Adapter[8],
                                            "client_name": _ClientName,
                                            "hardware": Hardware,
                                            "hardware_model": HardwareModel
                                        }
                                        _UserAssigned_Fleet.append(SingleBasic_Data)

                            else:
                                pass
                        else:
                            pass
                    
                    if(len(_UserAssigned_Fleet) > 0):
                        return reply("success", 200, "Fleet Found", _UserAssigned_Fleet)
                    elif(len(_UserAssigned_Fleet) == 0):
                        return reply("error", 400, "No Devices Attached", _UserAssigned_Fleet)

                elif(cursor.rowcount == 0):
                    return reply("error", 400, "No Devices Found", "")

    except Exception as error:
        return reply("error", 500, str(error), "")


#Detach user from group
@groups_bp.route("/groups/<string:group_uid>/users/<string:user_uid>/detach", methods=["PUT"])
def DetachUser(group_uid, user_uid):

    try:
        _dbconnect = psycopg2.connect(current_app.config["db_link"])
        _TargetUser = str(user_uid)
        _TargetGroupID = str(group_uid)

        with _dbconnect:
            with _dbconnect.cursor() as cusror:
                cusror.execute("DELETE FROM dll_group_attachments WHERE user_attached=%s AND group_attached=%s", (_TargetUser, _TargetGroupID,))

                return reply("success", 200, "Detached SuccessFully", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    

#detach devices from group
@groups_bp.route("/groups/<string:group_uid>/detach-devices", methods=["PUT"])
def DetachDevices(group_uid):

    try:
        _dbconnect = psycopg2.connect(current_app.config["db_link"])
        _payloadObject = request.get_json()
        _NominatedList = _payloadObject['data']['devices']
        _FocusGroupID = str(group_uid)

        if(len(_NominatedList) > 0) and (len(_FocusGroupID) > 6):

            with _dbconnect:
                with _dbconnect.cursor() as cursor:
                    cursor.execute("SELECT devices_attached FROM dll_device_groups WHERE group_local_uid=%s", (_FocusGroupID,))

                    if(cursor.rowcount == 1):

                        _dataTunnelLink = cursor.fetchone()
                        _AttachedDevices_Existing = json.loads(_dataTunnelLink[0])

                        for _Nomited_DeviceImei in _NominatedList:
                            if(_Nomited_DeviceImei in _AttachedDevices_Existing):
                                _AttachedDevices_Existing.remove(_Nomited_DeviceImei)
                            else:
                                pass
                        
                        _NewAttached_devicesList = json.dumps(_AttachedDevices_Existing)
                        cursor.execute("UPDATE dll_device_groups SET devices_attached=%s WHERE group_local_uid=%s", (str(_NewAttached_devicesList), _FocusGroupID,))

                        return reply("success", 200, "Devices Detachment SuccessFul", "")
                    
                    else:
                        return reply("error", 400, "Group route not found / Deleted", "")

        elif(len(_NominatedList) == 0):
            return reply("error", 400, "Missing Some data", "")

    except Exception as error:
        return reply("error", 500, str(error), "")
    

#list group attachments for a user
@groups_bp.route("/groups/users/<string:user_uid>/list-attachments", methods=["GET"])
def ListAttachements(user_uid):

    try:
        _dbconnect = psycopg2.connect(current_app.config["db_link"])
        _TargetUser = str(user_uid)

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute("SELECT group_attached FROM dll_group_attachments WHERE user_attached=%s", (_TargetUser,))

                if(cursor.rowcount >= 1):

                    _UserTunnelLink = cursor.fetchall()
                    _AttachmentsHolder = []

                    for _attachement in _UserTunnelLink:
                        _SingleGroupID = _attachement[0]
                        cursor.execute("SELECT group_display_name FROM dll_device_groups WHERE group_local_uid=%s", (str(_SingleGroupID),))
                        if(cursor.rowcount == 1):
                            _dataLink = cursor.fetchone()
                            _GroupAttachedName = _dataLink[0]
                            _Objt = {
                                "group_name": _GroupAttachedName,
                                "group_uid": _SingleGroupID
                            }
                            _AttachmentsHolder.append(_Objt)
                        else:
                            pass

                    return reply("success", 200, "Found Attachments", _AttachmentsHolder)

                elif(cursor.rowcount == 0):
                    return reply("error", 400, "No Attachments", "")

    except Exception as error:
        return reply("error", 500, str(error), "")


#get group devices
@groups_bp.route("/groups/<string:group_uid>/devices-attached", methods=['GET'])
def GetGroupAttached_Devices(group_uid):
    try:
        _dbconnect = psycopg2.connect(current_app.config["db_link"])
        _GroupID = str(group_uid)
        _UserAssigned_Fleet = []

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute("SELECT devices_attached FROM dll_device_groups WHERE group_local_uid=%s", (_GroupID,))

                if(cursor.rowcount == 1):
                    _groupDataTunnelLink = cursor.fetchone()
                    _FocusedGroup_Attached_Devices = json.loads(_groupDataTunnelLink[0])

                    if(len(_FocusedGroup_Attached_Devices) > 0):
                        for _Focused_DeviceImei in _FocusedGroup_Attached_Devices:
                            cursor.execute(
                                "SELECT device_name,device_simcard,device_car_make,device_car_model,device_vin_number,device_car_type,events_attached,device_billing_status,device_client FROM dll_device_basic_data WHERE device_imei=%s;",
                                (str(_Focused_DeviceImei),)
                            )
                            DeviceBasicData_Adapter = cursor.fetchone()

                            if True:
                                # Uncomment below as needed
                                # SimCard = DeviceBasicData_Adapter[1]
                                # cursor.execute("SELECT simcard_number FROM dll_telecom_assets WHERE asset_uid=%s;", (str(SimCard),))
                                # SimcardData = cursor.fetchone()
                                # SimcardNumber = SimcardData[0]

                                # cursor.execute("SELECT device_vendor,device_hardware FROM dll_device_registrar WHERE device_imei=%s;", (str(_Focused_DeviceImei),))
                                # Hardware_dataAdapter = cursor.fetchone()
                                # Hardware = Hardware_dataAdapter[0]
                                # HardwareModel = Hardware_dataAdapter[1]

                                # _ClientID = DeviceBasicData_Adapter[8]
                                # cursor.execute("SELECT client_name FROM dll_client_accounts WHERE client_uid=%s", (str(_ClientID),))
                                # _dataLink = cursor.fetchone()
                                # _ClientName = _dataLink[0]

                                SingleBasic_Data = {
                                    "device_name": DeviceBasicData_Adapter[0],
                                    "device_imei": _Focused_DeviceImei
                                }
                                _UserAssigned_Fleet.append(SingleBasic_Data)
                    
                        return reply("success", 200, "Found Devices", _UserAssigned_Fleet)
                
                    else:
                        return reply("error", 400, "No Devices Attached", "")
                    
                else:
                    return reply("error", 400, "Group Not Found / Deleted", "")
    except Exception as error:
        return reply("error", 500, str(error), "")


