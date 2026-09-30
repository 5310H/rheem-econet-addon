"""Minimal EcoNet serial protocol client based on the ESPHome EcoNet profile."""

from __future__ import annotations

import logging
import struct
import threading
import time

import serial

from .const import BAUD_RATE, READ_DATAPOINTS

_LOGGER = logging.getLogger(__name__)
HEADER_SIZE = 14
ACK = 0x06
READ_COMMAND = 0x1E
WRITE_COMMAND = 0x1F
MAX_PAYLOAD = 255


class EcoNetProtocolError(Exception):
    """Serial or frame error."""


def crc16(data: bytes, crc: int = 0) -> int:
    """ESPHome's CRC-16/A001 variant, with the EcoNet initial value of zero."""
    for byte in data:
        # The upstream implementation stores this intermediate in uint8_t.
        combo = (crc ^ byte) & 0xFF
        crc = (crc >> 8) ^ _CRC16_LOW[combo & 0x0F] ^ _CRC16_HIGH[combo >> 4]
    return crc & 0xFFFF


_CRC16_LOW = (
    0x0000,
    0xC0C1,
    0xC181,
    0x0140,
    0xC301,
    0x03C0,
    0x0280,
    0xC241,
    0xC601,
    0x06C0,
    0x0780,
    0xC741,
    0x0500,
    0xC5C1,
    0xC481,
    0x0440,
)
_CRC16_HIGH = (
    0x0000,
    0xCC01,
    0xD801,
    0x1400,
    0xF001,
    0x3C00,
    0x2800,
    0xE401,
    0xA001,
    0x6C00,
    0x7800,
    0xB401,
    0x5000,
    0x9C01,
    0x8801,
    0x4400,
)


def _address_bytes(address: int) -> bytes:
    if not 0 <= address <= 0xFFFFFF:
        raise ValueError("EcoNet address must fit in 24 bits")
    return bytes(
        (0x80, (address >> 16) & 0xFF, (address >> 8) & 0xFF, address & 0xFF, 0)
    )


def build_frame(destination: int, source: int, command: int, payload: bytes) -> bytes:
    """Build a complete EcoNet frame."""
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("EcoNet payload exceeds 255 bytes")
    body = (
        _address_bytes(destination)
        + _address_bytes(source)
        + bytes((len(payload), 0, 0, command))
        + payload
    )
    checksum = crc16(body)
    return body + struct.pack("<H", checksum)


def build_read_payload(datapoints: tuple[str, ...] = READ_DATAPOINTS) -> bytes:
    """Build a class 2/property 1 request for multiple datapoints."""
    payload = bytearray((2, 1))
    for name in datapoints:
        encoded = name.encode("ascii")
        if len(encoded) > 8:
            raise ValueError(f"EcoNet object name too long: {name}")
        payload.extend(b"\x00\x00" + encoded.ljust(8, b"\x00"))
    return bytes(payload)


def _validate_frame(frame: bytes) -> None:
    """Check ACK command, declared length, and frame CRC."""
    if len(frame) < HEADER_SIZE + 2:
        raise EcoNetProtocolError("Short EcoNet frame")
    payload_len = frame[10]
    if frame[13] != ACK or len(frame) != HEADER_SIZE + payload_len + 2:
        raise EcoNetProtocolError("Unexpected EcoNet response frame")
    body = frame[:-2]
    expected_crc = struct.unpack("<H", frame[-2:])[0]
    if crc16(body) != expected_crc:
        raise EcoNetProtocolError("EcoNet response CRC mismatch")


def decode_values(
    frame: bytes, requested: tuple[str, ...]
) -> dict[str, float | int | str]:
    """Decode a class 2 ACK payload into datapoint values."""
    _validate_frame(frame)

    payload = frame[HEADER_SIZE:-2]
    values: dict[str, float | int | str] = {}
    offset = 0
    for name in requested:
        if offset >= len(payload):
            break
        item_len = payload[offset]
        offset += 1
        if item_len == 0 or offset + item_len > len(payload):
            raise EcoNetProtocolError("Malformed EcoNet datapoint response")
        item = payload[offset : offset + item_len]
        offset += item_len
        kind = item[0] & 0x7F
        # Upstream handle_response_ advances three bytes from the type field
        # before reading the value: type + two metadata bytes + value.
        if kind == 0 and item_len == 7 and item[1:3] == b"\x80\x00":
            values[name] = struct.unpack(">f", item[3:7])[0]
        elif kind == 2 and item_len >= 5 and item[1:3] == b"\x80\x00":
            enum_value = item[3]
            text_len = item[4]
            if len(item) != 5 + text_len:
                raise EcoNetProtocolError(f"Malformed enum response for {name}")
            text = item[5:].decode("ascii", errors="replace").strip(" \x00")
            values[name] = enum_value
            if text:
                values[f"{name}_text"] = text
        elif kind == 1 and item_len >= 3 and item[1:3] == b"\x80\x00":
            values[name] = item[3:].decode("ascii", errors="replace").strip(" \x00")
        else:
            _LOGGER.debug(
                "Ignoring unsupported EcoNet value type %d for %s", kind, name
            )
    return values


class EcoNetSerialClient:
    """Synchronous, serialized RS-485 requests for executor use."""

    def __init__(
        self, port: str, source_address: str | int, destination_address: str | int
    ):
        self.port = port
        self.source_address = _parse_address(source_address)
        self.destination_address = _parse_address(destination_address)
        self._lock = threading.Lock()

    def _read_frame(self, connection: serial.Serial, timeout: float = 2.0) -> bytes:
        deadline = time.monotonic() + timeout
        buffer = bytearray()
        while time.monotonic() < deadline:
            chunk = connection.read(1)
            if not chunk:
                continue
            buffer.extend(chunk)
            if len(buffer) == 1 and buffer[0] != 0x80:
                buffer.clear()
                continue
            if len(buffer) == 10 and buffer[5] != 0x80:
                buffer.clear()
                continue
            if len(buffer) >= 11:
                expected = HEADER_SIZE + buffer[10] + 2
                if len(buffer) == expected:
                    return bytes(buffer)
                if len(buffer) > expected:
                    buffer.clear()
        raise EcoNetProtocolError("Timed out waiting for EcoNet response")

    def poll(self) -> dict[str, float | int | str]:
        """Request the tankless datapoints and return the response values."""
        with self._lock:
            try:
                with serial.Serial(
                    self.port,
                    baudrate=BAUD_RATE,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.1,
                    write_timeout=1.0,
                ) as connection:
                    connection.reset_input_buffer()
                    request = build_frame(
                        self.destination_address,
                        self.source_address,
                        READ_COMMAND,
                        build_read_payload(),
                    )
                    connection.write(request)
                    connection.flush()
                    response = self._read_frame(connection)
                    if response[0:5] != _address_bytes(self.source_address):
                        raise EcoNetProtocolError(
                            "EcoNet response addressed to a different source"
                        )
                    if response[5:10] != _address_bytes(self.destination_address):
                        raise EcoNetProtocolError(
                            "EcoNet response came from an unexpected device"
                        )
                    return decode_values(response, READ_DATAPOINTS)
            except (serial.SerialException, OSError, ValueError) as err:
                raise EcoNetProtocolError(
                    f"EcoNet serial request failed: {err}"
                ) from err

    def write_float(self, datapoint: str, value: float) -> None:
        """Write a floating-point datapoint using the EcoNet class 1 format."""
        self._write_value(datapoint, struct.pack(">f", value), data_type=0)

    def write_enum(self, datapoint: str, value: int) -> None:
        """Write an enum datapoint using the EcoNet class 1 format."""
        if not 0 <= value <= 0xFF:
            raise ValueError("EcoNet enum must fit in one byte")
        self._write_value(datapoint, struct.pack(">f", float(value)), data_type=2)

    def _write_value(self, datapoint: str, value: bytes, data_type: int) -> None:
        """Send one class 1 EcoNet write.

        The upstream ESPHome implementation transmits writes without waiting
        for an ACK. The integration therefore confirms state only by polling
        the datapoint again after the write.
        """
        encoded = datapoint.encode("ascii")
        if len(encoded) > 8:
            raise ValueError("EcoNet datapoint name must be at most 8 characters")
        payload = bytes((1, 1, data_type, 1, 0, 0)) + encoded.ljust(8, b"\x00") + value
        with self._lock:
            try:
                with serial.Serial(
                    self.port,
                    baudrate=BAUD_RATE,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.1,
                    write_timeout=1.0,
                ) as connection:
                    connection.reset_input_buffer()
                    connection.write(
                        build_frame(
                            self.destination_address,
                            self.source_address,
                            WRITE_COMMAND,
                            payload,
                        )
                    )
                    connection.flush()
            except (serial.SerialException, OSError, ValueError) as err:
                raise EcoNetProtocolError(f"EcoNet write failed: {err}") from err


def _parse_address(value: str | int) -> int:
    """Parse decimal or hexadecimal address input."""
    return value if isinstance(value, int) else int(value, 0)
