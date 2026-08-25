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
    """Bitmask for the ``access_capability`` field of a property descriptor."""

    READ = 0x0001
    WRITE = 0x0002


class FormFlag(IntEnum):
    """Bitmask for the ``form_flag`` field of a property descriptor."""

    DEFAULT = 0x0001
    RANGE = 0x0002
    ENUMERATION = 0x0004
    TEXT = 0x0008


@dataclass
class PropertyDesc:
    """Parsed ``GetDevicePropDesc`` dataset describing one device property."""

    code: int
    data_type: int
    access: int
    form_flag: int = 0
    data_size: int = 0
    default_value: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    step: int | None = None
    enumeration: list[int] = field(default_factory=list)
    text: str = ""

    @property
    def readable(self) -> bool:
        return bool(self.access & AccessCapability.READ)

    @property
    def writable(self) -> bool:
        return bool(self.access & AccessCapability.WRITE)

    @classmethod
    def parse(cls, data: bytes) -> PropertyDesc:
        u = Unpacker(data)
        desc = cls(
            code=u.uint16(),
            data_type=u.uint16(),
            access=u.uint16(),
            form_flag=u.uint32(),
            data_size=u.uint32(),
        )
        if desc.form_flag & FormFlag.DEFAULT:
            desc.default_value = u.uint32()
        if desc.form_flag & FormFlag.RANGE:
            desc.minimum = u.uint32()
            desc.maximum = u.uint32()
            desc.step = u.uint32()
        if desc.form_flag & FormFlag.ENUMERATION:
            count = u.uint32()
            desc.enumeration = [u.uint32() for _ in range(count)]
        if desc.form_flag & FormFlag.TEXT and u.remaining > 0:
            desc.text = u.string()
        return desc

    def pack(self) -> bytes:
        form = self.form_flag
        size = 0
        if form & FormFlag.DEFAULT:
            size += 4
        if form & FormFlag.RANGE:
            size += 12
        if form & FormFlag.ENUMERATION:
            size += 4 + 4 * len(self.enumeration)
        if form & FormFlag.TEXT:
            size += len(pack_string(self.text))
        out = struct.pack("<HHHI", self.code, self.data_type, self.access, form)
        out += struct.pack("<I", size)
        if form & FormFlag.DEFAULT:
            out += struct.pack("<I", self.default_value or 0)
        if form & FormFlag.RANGE:
            out += struct.pack("<III", self.minimum or 0, self.maximum or 0, self.step or 0)
        if form & FormFlag.ENUMERATION:
            out += struct.pack("<I", len(self.enumeration))
            out += b"".join(struct.pack("<I", v) for v in self.enumeration)
        if form & FormFlag.TEXT:
            out += pack_string(self.text)
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
