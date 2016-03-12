from __future__ import absolute_import
from .mtp_data_types import UInt16, UInt32, MStr, MArray
from .mtp_proto import OperationDataCodes, ResponseCodes, mtp_data, ContainerTypes
from .mtp_object import MtpObjectInfo, MtpObject
from .mtp_exception import MtpProtocolException


operations = {}


class Operation(object):
    def __init__(self, handler, ir_data=False):
        self.handler = handler
        self.ir_data = ir_data


def operation(opcode, num_params=None, session_required=True, ir_data_required=False):
    '''
    Decorator for an API operation function

    :param opcode: operation code
    :param num_params: number of parameter the operation expects (default: None)
    :param session_required: is the operation requires a session (default: True)
    :param ir_data_required: is data expected from the initiator (default: False)
    '''

    def decorator(func):
        def wrapper(self, command, response, ir_data):
            try:
                if num_params is not None:
                    if command.ctype != ContainerTypes.Command:
                        raise MtpProtocolException(ResponseCodes.INVALID_CODE_FORMAT)
                    if command.num_params() < num_params:
                        raise MtpProtocolException(ResponseCodes.PARAMETER_NOT_SUPPORTED)
                if session_required and (self.session_id is None):
                    raise MtpProtocolException(ResponseCodes.SESSION_NOT_OPEN)
                if ir_data_required and (ir_data is None):
                    raise MtpProtocolException(ResponseCodes.INVALID_DATASET)
                res = func(self, command, response, ir_data)
            except MtpProtocolException as ex:
                response.code = ex.response
                res = None
            return res

        if opcode in operations:
            raise Exception('operation %#x already defined', opcode)
        operations[opcode] = Operation(wrapper, ir_data_required)
        return wrapper

    return decorator


class MtpDevice(object):

    def __init__(self, info, properties=None):
        super(MtpDevice, self).__init__()
        self.info = info
        self.info.set_device(self)
        self.stores = {}
        self.operations = operations
        for op in self.operations:
            self.info.operations_supported.add_value(UInt16(op))
        self.events = {}
        for event in self.events:
            self.info.events_supported.add_value(UInt16(event))
        self.session_id = None
        self.last_obj = None
        self.properties = {}
        if properties is None:
            properties = []
        for prop in properties:
            self.add_property(prop)

    def add_property(self, prop):
        self.properties[prop.get_code()] = prop
        self.info.properties.add_value(UInt16(prop.get_code()))

    def get_info(self):
        return self.info.pack()

    def add_storage(self, storage):
        '''
        :type storage: MtpStorage
        :param storage: storage to add
        '''
        self.stores[storage.get_uid()] = storage
        storage.set_device(self)

    def handle_transaction(self, command, response, ir_data):
        ccode = command.code
        if ccode in operations:
            if self.last_obj and (ccode != OperationDataCodes.SendObject):
                self.last_obj.delete(0xffffffff)
                self.last_obj = None
            return self.operations[ccode].handler(self, command, response, ir_data)
        return None

    @operation(OperationDataCodes.GetDeviceInfo, num_params=0, session_required=False)
    def GetDeviceInfo(self, command, response, ir_data):
        return mtp_data(command, self.get_info())

    # @operation(OperationDataCodes., num_params=None, session_required=True)
    @operation(OperationDataCodes.OpenSession, num_params=1, session_required=False)
    def OpenSession(self, command, response, ir_data):
        if self.session_id:
            raise MtpProtocolException(ResponseCodes.SESSION_ALREADY_OPEN)
        self.session_id = command.params[0]

    @operation(OperationDataCodes.CloseSession, num_params=0)
    def CloseSession(self, command, response, ir_data):
        self.session_id = None

    @operation(OperationDataCodes.GetStorageIDs, num_params=0)
    def GetStorageIDs(self, command, response, ir_data):
        ids = list(self.stores.keys())
        data = MArray(UInt32, ids)
        return mtp_data(command, data.pack())

    @operation(OperationDataCodes.GetStorageInfo, num_params=1)
    def GetStorageInfo(self, command, response, ir_data):
        storage_id = command.get_param(0)
        storage = self.get_storage(storage_id)
        return mtp_data(command, storage.get_info())

    @operation(OperationDataCodes.GetNumObjects, num_params=1)
    def GetNumObjects(self, command, response, ir_data):
        storage_id = command.get_param(0)
        obj_fmt_code = command.get_param(1)
        handles = self.get_handles_for_store_id(storage_id, obj_fmt_code)
        # .. todo:: assoc_handle filtering
        # assoc_handle = command.get_param(2)
        return mtp_data(command, UInt32(len(handles)).pack())

    @operation(OperationDataCodes.GetObjectHandles, num_params=1)
    def GetObjectHandles(self, command, response, ir_data):
        storage_id = command.get_param(0)
        obj_fmt_code = command.get_param(1)
        handles = self.get_handles_for_store_id(storage_id, obj_fmt_code)
        # .. todo:: assoc_handle filtering
        # assoc_handle = command.get_param(2)
        return mtp_data(command, MArray(UInt32, handles).pack())

    @operation(OperationDataCodes.GetObjectInfo, num_params=1)
    def GetObjectInfo(self, command, response, ir_data):
        handle = command.get_param(0)
        obj = self.get_object(handle)
        return mtp_data(command, obj.get_info())

    @operation(OperationDataCodes.GetObject, num_params=1)
    def GetObject(self, command, response, ir_data):
        handle = command.get_param(0)
        obj = self.get_object(handle)
        return mtp_data(command, obj.data)

    @operation(OperationDataCodes.GetThumb, num_params=1)
    def GetThumb(self, command, response, ir_data):
        handle = command.get_param(0)
        obj = self.get_object(handle)
        return mtp_data(command, obj.get_thumb())

    @operation(OperationDataCodes.DeleteObject, num_params=1)
    def DeleteObject(self, command, response, ir_data):
        handle = command.get_param(0)
        obj_fmt_code = command.get_param(1)
        if handle == 0xffffffff:
            self.delete_all_objects(obj_fmt_code)
        else:
            obj = self.get_object(handle)
            obj.delete(0xffffffff)

    @operation(OperationDataCodes.SendObjectInfo, num_params=1, ir_data_required=True)
    def SendObjectInfo(self, command, response, ir_data):
        '''
        .. todo:: complete !!
        '''
        storage_id = command.get_param(0)
        parent_handle = command.get_param(1)
        if storage_id:
            store = self.get_storage(storage_id)
            if parent_handle:
                parent = store.get_object(parent_handle)
                parent_uid = parent.get_uid()
            else:
                parent = store
                parent_uid = 0xffffffff
            if store.can_write():
                obj_info = MtpObjectInfo.from_buff(ir_data.data)
                obj = MtpObject(None, obj_info, [])
                parent.add_object(obj)
                response.add_param(store.get_uid())
                response.add_param(parent_uid)
                response.add_param(obj.get_uid())
                # next operation MUST be SendObject, otherwise we do NOT keep the object
                # so we need a refrence to it.
                self.last_obj = obj
            else:
                raise MtpProtocolException(ResponseCodes.STORE_READ_ONLY)
        else:
            #
            # This might not be accurate, but I'm willing to play with that for now
            raise MtpProtocolException(ResponseCodes.INVALID_STORAGE_ID)

    @operation(OperationDataCodes.SendObject, num_params=0, ir_data_required=True)
    def SendObject(self, command, response, ir_data):
        if not self.last_obj:
            raise MtpProtocolException(ResponseCodes.NO_VALID_OBJECT_INFO)
        self.last_obj.set_data(ir_data.data, adhere_size=True)
        self.last_obj = None

    # @operation(OperationDataCodes.InitiateCapture, num_params=0):
    def InitiateCapture(self, command, response, ir_data):
        '''
        .. todo::

            This is part of a complex operation (first time to have events)
            so it is not implemented for now ...
            See appendix D.2.14
        '''
        raise MtpProtocolException(ResponseCodes.OPERATION_NOT_SUPPORTED)

    @operation(OperationDataCodes.FormatStore, num_params=1)
    def FormatStore(self, command, response, ir_data):
        '''
        Current implementation will NOT perform a format
        '''
        storage_id = command.get_param(0)
        self.get_storage(storage_id)
        raise MtpProtocolException(ResponseCodes.PARAMETER_NOT_SUPPORTED)

    @operation(OperationDataCodes.ResetDevice, num_params=0)
    def ResetDevice(self, command, response, ir_data):
        self.session_id = None

    @operation(OperationDataCodes.SelfTest, num_params=0)
    def SelfTest(self, command, response, ir_data):
        test_type = command.get_param(0)
        self.run_self_test(test_type)

    @operation(OperationDataCodes.SetObjectProtection, num_params=2)
    def SetObjectProtection(self, command, response, ir_data):
        handle = command.get_param(0)
        prot_status = command.get_param(1)
        obj = self.get_object(handle)
        obj.set_protection_status(prot_status)

    @operation(OperationDataCodes.PowerDown)
    def PowerDown(self, command, response, ir_data):
        self.session_id = None

    @operation(OperationDataCodes.GetDevicePropDesc, num_params=1)
    def GetDevicePropDesc(self, command, response, ir_data):
        prop_code = command.get_param(0)
        prop = self.get_property(prop_code)
        return prop.get_desc()

    @operation(OperationDataCodes.GetDevicePropValue, num_params=1)
    def GetDevicePropValue(self, command, response, ir_data):
        prop_code = command.get_param(0)
        prop = self.get_property(prop_code)
        return prop.get_value()

    def get_property(self, prop_code):
        if prop_code in self.properties:
            return self.properties[prop_code]
        raise MtpProtocolException(ResponseCodes.DEVICE_PROP_NOT_SUPPORTED)

    def run_self_test(self, test_type):
        pass

    def delete_all_objects(self, obj_fmt_code):
        deleted = False
        undeleted = False
        for store in self.stores.values():
            objects = store.get_objects()
            for obj in objects:
                try:
                    obj.delete(obj_fmt_code)
                    deleted = True
                except MtpProtocolException as ex:
                    if ex.status == ResponseCodes.PARTIAL_DELETION:
                        deleted = True
                    undeleted = True
        if undeleted:
            if deleted:
                raise MtpProtocolException(ResponseCodes.OBJECT_WRITE_PROTECTED)
            else:
                raise MtpProtocolException(ResponseCodes.PARTIAL_DELETION)

    def get_handles_for_store_id(self, storage_id, obj_fmt_code):
        '''
        :param stores: stores to search in
        :param obj_fmt_code: format to filter objects by
        :return: list of handles
        '''
        res = []
        if storage_id == 0xffffffff:
            relevant_store = list(self.stores.values())
        else:
            relevant_store = [self.get_storage(storage_id)]
        for store in relevant_store:
            handles = [h for h in store.get_handles() if store.get_object(h).format_matches(obj_fmt_code)]
            res.extend(handles)
        return res

    def get_object(self, handle):
        '''
        :param handle: handle of the object
        :raises: MtpProtocolException if there is no object with given handle
        :return: MtpObject
        '''
        obj = None
        for store in self.stores.values():
            obj = store.get_object(handle)
            if obj:
                break
        if not obj:
            raise MtpProtocolException(ResponseCodes.INVALID_OBJECT_HANDLE)
        return obj

    def get_storage(self, storage_id):
        '''
        :param storage_id: the storage id to get
        :raises: MtpProtocolException if storage with this id does not exist
        :return: MtpStorage
        '''
        if storage_id not in self.stores:
            raise MtpProtocolException(ResponseCodes.INVALID_STORAGE_ID)
        return self.stores[storage_id]


class MtpDeviceInfo(object):

    def __init__(
        self,
        std_version, mtp_vendor_ext_id, mtp_version, mtp_extensions,
        functional_mode, capture_formats, playback_formats,
        manufacturer, model, device_version, serial_number
    ):
        '''
        :type std_version: 16bit uint
        :param std_version: Standard Version
        :type mtp_vendor_ext_id: 32bit uint
        :param mtp_vendor_ext_id: MTP Vendor Extension ID
        :type mtp_version: 16bit uint
        :param mtp_version: MTP Version
        :type mtp_extensions: str
        :param mtp_extensions: MTP Extensions
        :type functional_mode: 16bit uint
        :param functional_mode: Functional Mode
        :type capture_formats: list of 16bit uint
        :param capture_formats: Capture Formats
        :type playback_formats: list of 16bit uint
        :param playback_formats: Playback Formats
        :type manufacturer: str
        :param manufacturer: Manufacturer
        :type model: str
        :param model: Model
        :type device_version: str
        :param device_version: Device Version
        :type serial_number: str
        :param serial_number: Serial Number
        '''
        self.std_version = UInt16(std_version)
        self.mtp_vendor_ext_id = UInt32(mtp_vendor_ext_id)
        self.mtp_version = UInt16(mtp_version)
        self.mtp_extensions = MStr(mtp_extensions)
        self.functional_mode = UInt16(functional_mode)
        self.operations_supported = MArray(UInt16, [])
        self.events_supported = MArray(UInt16, [])
        self.properties = MArray(UInt16, [])
        self.capture_formats = MArray(UInt16, capture_formats)
        self.playback_formats = MArray(UInt16, playback_formats)
        self.manufacturer = MStr(manufacturer)
        self.model = MStr(model)
        self.device_version = MStr(device_version)
        self.serial_number = MStr(serial_number)
        self.device = None

    def set_device(self, device):
        self.device = device

    def pack(self):
        return (
            self.std_version.pack() +
            self.mtp_vendor_ext_id.pack() +
            self.mtp_version.pack() +
            self.mtp_extensions.pack() +
            self.functional_mode.pack() +
            self.operations_supported.pack() +
            self.events_supported.pack() +
            self.properties.pack() +
            self.capture_formats.pack() +
            self.playback_formats.pack() +
            self.manufacturer.pack() +
            self.model.pack() +
            self.device_version.pack() +
            self.serial_number.pack()
        )
