"""Regression tests for the community-derived EcoNet frame implementation."""

from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path
from types import ModuleType


def _load_protocol_module() -> ModuleType:
    """Load the protocol without importing the HA-dependent integration setup."""
    repo_root = Path(__file__).resolve().parents[1]
    component_path = repo_root / "custom_components" / "rheem_econet"
    package_name = "_rheem_econet_test"
    package = ModuleType(package_name)
    package.__path__ = [str(component_path)]
    sys.modules[package_name] = package

    for module_name in ("const", "protocol"):
        qualified_name = f"{package_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(
            qualified_name, component_path / f"{module_name}.py"
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load {qualified_name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified_name] = module
        spec.loader.exec_module(module)

    return sys.modules[f"{package_name}.protocol"]


protocol = _load_protocol_module()


class EcoNetProtocolTests(unittest.TestCase):
    """Test protocol helpers using synthetic frames, not physical hardware."""

    def test_crc16_reference_vector(self) -> None:
        self.assertEqual(protocol.crc16(b"123456789"), 0xBB3D)

    def test_read_payload_encodes_object_names(self) -> None:
        self.assertEqual(
            protocol.build_read_payload(("WHTRSETP",)),
            b"\x02\x01\x00\x00WHTRSETP",
        )

    def test_frame_contains_addresses_command_and_valid_crc(self) -> None:
        frame = protocol.build_frame(0x1040, 0x340, protocol.ACK, b"abc")
        self.assertEqual(frame[:5], b"\x80\x00\x10\x40\x00")
        self.assertEqual(frame[5:10], b"\x80\x00\x03\x40\x00")
        self.assertEqual(frame[13], protocol.ACK)
        self.assertEqual(
            frame[-2:], struct.pack("<H", protocol.crc16(frame[:-2]))
        )

    def test_decodes_float_and_enum_values(self) -> None:
        float_item = b"\x00\x80\x00" + struct.pack(">f", 125.0)
        enum_item = b"\x02\x80\x00\x01\x04HEAT"
        payload = bytes((len(float_item),)) + float_item
        payload += bytes((len(enum_item),)) + enum_item
        frame = protocol.build_frame(0x340, 0x1040, protocol.ACK, payload)

        self.assertEqual(
            protocol.decode_values(frame, ("WHTRSETP", "WHTRENAB")),
            {"WHTRSETP": 125.0, "WHTRENAB": 1, "WHTRENAB_text": "HEAT"},
        )

    def test_rejects_corrupt_crc(self) -> None:
        frame = bytearray(protocol.build_frame(0x340, 0x1040, protocol.ACK, b""))
        frame[-1] ^= 0xFF
        with self.assertRaisesRegex(protocol.EcoNetProtocolError, "CRC"):
            protocol.decode_values(bytes(frame), ())

    def test_rejects_oversized_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "255 bytes"):
            protocol.build_frame(0x1040, 0x340, protocol.ACK, b"x" * 256)


if __name__ == "__main__":
    unittest.main()
