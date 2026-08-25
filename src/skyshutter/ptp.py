"""PTP (ISO 15740) constants and dataset parsing.

Only the parts that are actually needed to talk to a Nikon camera are
implemented.  Everything vendor specific lives in :mod:`skyshutter.nikon`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum


class OperationCode(IntEnum):
    """Standard PTP operations (0x1xxx)."""

    GET_DEVICE_INFO = 0x1001
    OPEN_SESSION = 0x1002
    CLOSE_SESSION = 0x1003
    GET_STORAGE_IDS = 0x1004
    GET_STORAGE_INFO = 0x1005
    GET_NUM_OBJECTS = 0x1006
    GET_OBJECT_HANDLES = 0x1007
    GET_OBJECT_INFO = 0x1008
    GET_OBJECT = 0x1009
    GET_THUMB = 0x100A
    DELETE_OBJECT = 0x100B
    INITIATE_CAPTURE = 0x100E
    GET_DEVICE_PROP_DESC = 0x1014
    GET_DEVICE_PROP_VALUE = 0x1015
    SET_DEVICE_PROP_VALUE = 0x1016
    GET_PARTIAL_OBJECT = 0x101B
    INITIATE_OPEN_CAPTURE = 0x101C


class ResponseCode(IntEnum):
    """Standard PTP response codes (0x2xxx)."""

    UNDEFINED = 0x2000
    OK = 0x2001
    GENERAL_ERROR = 0x2002
    SESSION_NOT_OPEN = 0x2003
    INVALID_TRANSACTION_ID = 0x2004
    OPERATION_NOT_SUPPORTED = 0x2005
    PARAMETER_NOT_SUPPORTED = 0x2006
    INCOMPLETE_TRANSFER = 0x2007
    INVALID_STORAGE_ID = 0x2008
    INVALID_OBJECT_HANDLE = 0x2009
    DEVICE_PROP_NOT_SUPPORTED = 0x200A
    INVALID_OBJECT_FORMAT_CODE = 0x200B
    STORE_FULL = 0x200C
    OBJECT_WRITE_PROTECTED = 0x200D
    STORE_READ_ONLY = 0x200E
    ACCESS_DENIED = 0x200F
    NO_THUMBNAIL_PRESENT = 0x2010
    SELF_TEST_FAILED = 0x2011
    PARTIAL_DELETION = 0x2012
    STORE_NOT_AVAILABLE = 0x2013
    SPECIFICATION_BY_FORMAT_UNSUPPORTED = 0x2014
    NO_VALID_OBJECT_INFO = 0x2015
    INVALID_CODE_FORMAT = 0x2016
    UNKNOWN_VENDOR_CODE = 0x2017
    CAPTURE_ALREADY_TERMINATED = 0x2018
    DEVICE_BUSY = 0x2019
    INVALID_PARENT_OBJECT = 0x201A
    INVALID_DEVICE_PROP_FORMAT = 0x201B
    INVALID_DEVICE_PROP_VALUE = 0x201C
    INVALID_PARAMETER = 0x201D
    SESSION_ALREADY_OPEN = 0x201E
    TRANSACTION_CANCELLED = 0x201F
    SPECIFICATION_OF_DESTINATION_UNSUPPORTED = 0x2020


class VendorExtension(IntEnum):
    EASTMAN_KODAK = 0x00000001
    MICROSOFT = 0x00000006
    NIKON = 0x0000000A
    CANON = 0x0000000B
    SONY = 0x00000011
    FUJI = 0x0000000C


def code_name(value: int, enum_cls: type[IntEnum]) -> str:
    """Human readable name for ``value``, falling back to hex."""
    try:
        return enum_cls(value).name
    except ValueError:
        return f"0x{value:04X}"


class PtpError(RuntimeError):
    """A PTP operation answered with a response code other than OK."""

    def __init__(self, code: int, operation: int | None = None) -> None:
        self.code = code
        self.operation = operation
        name = code_name(code, ResponseCode)
        where = f" (operation 0x{operation:04X})" if operation is not None else ""
        super().__init__(f"PTP response {name} [0x{code:04X}]{where}")


class Unpacker:
    """Little endian reader for PTP datasets."""

    def __init__(self, data: bytes, offset: int = 0) -> None:
        self.data = data
        self.offset = offset

    @property
    def remaining(self) -> int:
        return len(self.data) - self.offset

    def _take(self, size: int) -> bytes:
        if self.remaining < size:
            raise ValueError(
                f"truncated PTP dataset: need {size} bytes at offset {self.offset}, "
                f"have {self.remaining}"
            )
        chunk = self.data[self.offset : self.offset + size]
        self.offset += size
        return chunk

    def uint8(self) -> int:
        return self._take(1)[0]

    def uint16(self) -> int:
        return struct.unpack("<H", self._take(2))[0]

    def uint32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def uint64(self) -> int:
        return struct.unpack("<Q", self._take(8))[0]

    def string(self) -> str:
        """PTP string: length in *characters* (incl. terminator) + UTF-16LE."""
        length = self.uint8()
        if length == 0:
            return ""
        raw = self._take(length * 2)
        return raw.decode("utf-16-le").rstrip("\x00")

    def array(self, item: str = "uint16") -> list[int]:
        """PTP array: uint32 element count followed by the elements."""
        count = self.uint32()
        sizes = {"uint8": 1, "uint16": 2, "uint32": 4, "uint64": 8}
        item_size = sizes.get(item, 2)
        if count * item_size > self.remaining:
            raise ValueError(
                f"array size {count} of {item} exceeds remaining data ({self.remaining} bytes)"
            )
        reader = getattr(self, item)
        return [reader() for _ in range(count)]


def pack_string(value: str) -> bytes:
    """Encode a PTP string (used for the PTP/IP friendly name)."""
    if not value:
        return b"\x00"
    encoded = (value + "\x00").encode("utf-16-le")
    return bytes([len(value) + 1]) + encoded


@dataclass
class DeviceInfo:
    """Parsed ``GetDeviceInfo`` dataset."""

    standard_version: int = 0
    vendor_extension_id: int = 0
    vendor_extension_version: int = 0
    vendor_extension_desc: str = ""
    functional_mode: int = 0
    operations_supported: list[int] = field(default_factory=list)
    events_supported: list[int] = field(default_factory=list)
    device_properties_supported: list[int] = field(default_factory=list)
    capture_formats: list[int] = field(default_factory=list)
    image_formats: list[int] = field(default_factory=list)
    manufacturer: str = ""
    model: str = ""
    device_version: str = ""
    serial_number: str = ""

    @classmethod
    def parse(cls, data: bytes) -> DeviceInfo:
        u = Unpacker(data)
        info = cls(
            standard_version=u.uint16(),
            vendor_extension_id=u.uint32(),
            vendor_extension_version=u.uint16(),
            vendor_extension_desc=u.string(),
            functional_mode=u.uint16(),
            operations_supported=u.array(),
            events_supported=u.array(),
            device_properties_supported=u.array(),
            capture_formats=u.array(),
            image_formats=u.array(),
        )
        # Nikon firmware has been seen truncating the tail of the dataset on
        # some models, so the string block is parsed best effort.
        for attr in ("manufacturer", "model", "device_version", "serial_number"):
            if u.remaining <= 0:
                break
            setattr(info, attr, u.string())
        return info

    def pack(self) -> bytes:
        """Inverse of :meth:`parse` (used by tests and the simulator)."""
        out = struct.pack(
            "<HIH", self.standard_version, self.vendor_extension_id, self.vendor_extension_version
        )
        out += pack_string(self.vendor_extension_desc)
        out += struct.pack("<H", self.functional_mode)
        for array in (
            self.operations_supported,
            self.events_supported,
            self.device_properties_supported,
            self.capture_formats,
            self.image_formats,
        ):
            out += struct.pack("<I", len(array))
            out += b"".join(struct.pack("<H", item) for item in array)
        for text in (self.manufacturer, self.model, self.device_version, self.serial_number):
            out += pack_string(text)
        return out

    @property
    def is_nikon(self) -> bool:
        return self.vendor_extension_id == VendorExtension.NIKON

    def supports(self, opcode: int) -> bool:
        return opcode in self.operations_supported


class DataType(IntEnum):
    """PTP device-property data types (ISO 15740 §5.8)."""

    UINT8 = 0x0001
    INT8 = 0x0002
    UINT16 = 0x0003
    INT16 = 0x0004
    UINT32 = 0x0005
    INT32 = 0x0006
    UINT64 = 0x0007
    INT64 = 0x0008
    IEC60529 = 0x0009
    FIXED = 0x000A
    FLOAT = 0x000B
    STRING = 0x000C
    DATE_TIME = 0x000D
    CONTAINER = 0x000E
    UUID = 0x000F
    URI = 0x0010
    UNDEFINED = 0x0011


class AccessCapability(IntEnum):
    """GetSet capability of a property descriptor (ISO 15740)."""

    GET = 0x00
    GET_SET = 0x01


class FormFlag(IntEnum):
    """Form flag of a property descriptor (ISO 15740)."""

    NONE = 0x00
    RANGE = 0x01
    ENUMERATION = 0x02


def _read_val(u: Unpacker, dtype: int) -> int | str:
    if dtype in (DataType.UINT8, DataType.INT8):
        return u.uint8()
    if dtype in (DataType.UINT16, DataType.INT16):
        return u.uint16()
    if dtype in (DataType.UINT32, DataType.INT32):
        return u.uint32()
    if dtype in (DataType.UINT64, DataType.INT64):
        return u.uint64()
    if dtype == DataType.STRING:
        return u.string()
    return 0


def _pack_val(dtype: int, val: int | str) -> bytes:
    if dtype in (DataType.UINT8, DataType.INT8):
        return struct.pack("<B", val)
    if dtype in (DataType.UINT16, DataType.INT16):
        return struct.pack("<H", val)
    if dtype in (DataType.UINT32, DataType.INT32):
        return struct.pack("<I", val)
    if dtype in (DataType.UINT64, DataType.INT64):
        return struct.pack("<Q", val)
    if dtype == DataType.STRING:
        return pack_string(val)  # type: ignore[arg-type]
    return b""


@dataclass
class PropertyDesc:
    """Parsed ``GetDevicePropDesc`` dataset describing one device property."""

    code: int
    data_type: int
    access: int
    form_flag: int = 0
    default_value: int | str = 0
    current_value: int | str = 0
    minimum: int | str = 0
    maximum: int | str = 0
    step: int | str = 0
    enumeration: list[int | str] = field(default_factory=list)

    @property
    def readable(self) -> bool:
        return True

    @property
    def writable(self) -> bool:
        return self.access == AccessCapability.GET_SET

    @classmethod
    def parse(cls, data: bytes) -> PropertyDesc:
        u = Unpacker(data)
        code = u.uint16()
        dtype = u.uint16()
        access = u.uint8()
        default_val = _read_val(u, dtype)
        current_val = _read_val(u, dtype)
        form_flag = u.uint8()

        desc = cls(
            code=code,
            data_type=dtype,
            access=access,
            form_flag=form_flag,
            default_value=default_val,
            current_value=current_val,
        )
        if form_flag == FormFlag.RANGE:
            desc.minimum = _read_val(u, dtype)
            desc.maximum = _read_val(u, dtype)
            desc.step = _read_val(u, dtype)
        elif form_flag == FormFlag.ENUMERATION:
            count = u.uint16()
            desc.enumeration = [_read_val(u, dtype) for _ in range(count)]
        return desc

    def pack(self) -> bytes:
        out = struct.pack("<HHB", self.code, self.data_type, self.access)
        out += _pack_val(self.data_type, self.default_value)
        out += _pack_val(self.data_type, self.current_value)
        out += struct.pack("<B", self.form_flag)
        if self.form_flag == FormFlag.RANGE:
            out += _pack_val(self.data_type, self.minimum)
            out += _pack_val(self.data_type, self.maximum)
            out += _pack_val(self.data_type, self.step)
        elif self.form_flag == FormFlag.ENUMERATION:
            out += struct.pack("<H", len(self.enumeration))
            out += b"".join(_pack_val(self.data_type, v) for v in self.enumeration)
        return out


@dataclass
class StorageInfo:
    """Parsed ``GetStorageInfo`` dataset for one storage medium."""

    storage_id: int
    storage_type: int
    access_capability: int
    max_capacity: int
    free_space_bytes: int
    free_space_objects: int

    @classmethod
    def parse(cls, data: bytes) -> StorageInfo:
        u = Unpacker(data)
        return cls(
            storage_id=u.uint32(),
            storage_type=u.uint16(),
            access_capability=u.uint16(),
            max_capacity=u.uint64(),
            free_space_bytes=u.uint64(),
            free_space_objects=u.uint64(),
        )

    def pack(self) -> bytes:
        """Inverse of :meth:`parse` (used by tests and the simulator)."""
        return struct.pack(
            "<IHHQQQ",
            self.storage_id,
            self.storage_type,
            self.access_capability,
            self.max_capacity,
            self.free_space_bytes,
            self.free_space_objects,
        )
