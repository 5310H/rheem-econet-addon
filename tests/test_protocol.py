"""Regression tests for the community-derived EcoNet frame implementation."""

from __future__ import annotations

import struct
import unittest

from custom_components.rheem_econet.protocol import (
    ACK,
    EcoNetProtocolError,
    build_frame,
    build_read_payload,
    crc16,
    decode_values,
)


class EcoNetProtocolTests(unittest.TestCase):
    """Test protocol helpers using synthetic frames, not physical hardware."""

    def test_crc16_reference_vector(self) -> None:
        self.assertEqual(crc16(b"123456789"), 0xBB3D)

    def test_read_payload_encodes_object_names(self) -> None:
        self.assertEqual(
            build_read_payload(("WHTRSETP",)),
            b"\x02\x01\x00\x00WHTRSETP",
        )

    def test_frame_contains_addresses_command_and_valid_crc(self) -> None:
        frame = build_frame(0x1040, 0x340, ACK, b"abc")
        self.assertEqual(frame[:5], b"\x80\x00\x10\x40\x00")
        self.assertEqual(frame[5:10], b"\x80\x00\x03\x40\x00")
        self.assertEqual(frame[13], ACK)
        self.assertEqual(frame[-2:], struct.pack("<H", crc16(frame[:-2])))

    def test_decodes_float_and_enum_values(self) -> None:
        float_item = b"\x00\x80\x00" + struct.pack(">f", 125.0)
        enum_item = b"\x02\x80\x00\x01\x04HEAT"
        payload = bytes((len(float_item),)) + float_item
        payload += bytes((len(enum_item),)) + enum_item
        frame = build_frame(0x340, 0x1040, ACK, payload)

        self.assertEqual(
            decode_values(frame, ("WHTRSETP", "WHTRENAB")),
            {"WHTRSETP": 125.0, "WHTRENAB": 1, "WHTRENAB_text": "HEAT"},
        )

    def test_rejects_corrupt_crc(self) -> None:
        frame = bytearray(build_frame(0x340, 0x1040, ACK, b""))
        frame[-1] ^= 0xFF
        with self.assertRaisesRegex(EcoNetProtocolError, "CRC"):
            decode_values(bytes(frame), ())

    def test_rejects_oversized_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "255 bytes"):
            build_frame(0x1040, 0x340, ACK, b"x" * 256)


if __name__ == "__main__":
    unittest.main()
