"""Code decoding: a wrong byte-to-code mapping would show the user the wrong fault,
so these pin exact codes from exact response bytes."""
from jeep_obd.scanner import decode_obd_dtcs, decode_uds_dtcs, dtc_str


class Msg:
    def __init__(self, data):
        self.data = bytearray(data)


def test_dtc_str_maps_all_four_systems():
    assert dtc_str(0x07, 0x30) == "P0730"
    assert dtc_str(0x48, 0x01) == "C0801"
    assert dtc_str(0x91, 0x23) == "B1123"
    assert dtc_str(0xC1, 0x01) == "U0101"


def test_obd_mode03_can_response_with_count_byte():
    """CAN mode 03 replies carry a count byte after 0x43; it must not be read as a code."""
    codes = decode_obd_dtcs([Msg([0x43, 0x02, 0x07, 0x30, 0x08, 0x68])], 0x43)
    assert [c for c, _ in codes] == ["P0730", "P0868"]


def test_obd_ignores_other_modes_and_padding():
    assert decode_obd_dtcs([Msg([0x47, 0x01, 0x07, 0x30])], 0x43) == []
    assert decode_obd_dtcs([Msg([0x43, 0x00])], 0x43) == []


def test_uds_dtc_with_failure_type_and_status_flags():
    """59 02 <mask> then 4-byte records: DTC(2) + failure type + status."""
    dtcs, err = decode_uds_dtcs([Msg([0x59, 0x02, 0xFF, 0x07, 0x30, 0x00, 0x09, 0x08, 0x68, 0x92, 0x04])])
    assert err is None
    assert [(d["code"], d["ftb"]) for d in dtcs] == [("P0730", "00"), ("P0868", "92")]
    assert dtcs[0]["flags"] == ["testFailed", "confirmed"]
    assert dtcs[1]["flags"] == ["pending"]


def test_uds_negative_response_is_reported_not_swallowed():
    dtcs, err = decode_uds_dtcs([Msg([0x7F, 0x19, 0x11])])
    assert dtcs == [] and err == "negative response NRC 0x11"
