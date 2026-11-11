"""Simulated scans and drive logs, so the dashboard can be tried without a car
(and so the tests have a known-healthy and a known-faulty drive to compare).

All values are made up. The VIN is a placeholder, not a real vehicle.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

K = 38.0  # rpm per mph per unit gear ratio (3.45 axle, ~661 tire revs/mile)
GEARS = [4.71, 3.14, 2.10, 1.67, 1.29, 1.00, 0.84, 0.67]
HEADER = ["t", "mark", "RPM", "SPEED", "ACCELERATOR_POS_D", "THROTTLE_POS", "ENGINE_LOAD",
          "COOLANT_TEMP", "TIMING_ADVANCE"]
DEMO_VIN = "DEMO0000000000000"  # 17 chars, deliberately not a valid VIN


def make_drive(symptom: bool) -> list[list]:
    """Rows of a 4 Hz drive log. symptom=True: stuck in 4th from 40-70 mph, one flare,
    symptom marks, and an engine-limited full-throttle pull. symptom=False: normal 8-speed."""
    rows: list[list] = []
    st = {"t": 0.0, "mph": 0.0, "gear": 1}

    def emit(pedal, load, mark=0, rpm=None):
        mph, g = st["mph"], st["gear"]
        if rpm is None:
            rpm = max(750, mph * K * GEARS[g - 1]) if mph >= 8 else 750 + mph * 120
        rows.append([round(st["t"], 2), mark, round(rpm), round(mph / 0.621371, 1),
                     round(15 + pedal * 0.65, 1), round(14 + pedal * 0.8, 1), load])
        st["t"] += 0.25

    def upshift(limit):
        while st["mph"] >= 8 and st["gear"] < 8 and st["mph"] * K * GEARS[st["gear"] - 1] > limit:
            st["gear"] += 1

    while st["mph"] < 65:            # A: accelerate with normal upshifts
        st["mph"] += 0.9
        upshift(1800)
        emit(35, 55)
    for _ in range(240):             # B: cruise
        emit(18, 30)
    while st["mph"] > 40:            # C: slow down, downshifting
        st["mph"] -= 0.5
        while st["gear"] > 5 and st["mph"] * K * GEARS[st["gear"] - 1] < 1300:
            st["gear"] -= 1
        emit(5, 15)
    if symptom:                      # D: kick down to 4th and stay there
        st["gear"], i = 4, 0
        while st["mph"] < 70:
            st["mph"] += 0.35
            i += 1
            if i == 40:              # failed upshift attempt: RPM flares, speed doesn't
                base = st["mph"] * K * GEARS[3]
                for k in range(4):
                    emit(45, 60, rpm=base + 150 * (k + 1))
                continue
            emit(45, 60, mark=1 if i in (60, 61) else 0)
        for j in range(200):         # E: highway cruise still in 4th
            emit(25, 45, mark=1 if j == 100 else 0)
        for _ in range(16):          # F: full throttle, engine-limited
            st["mph"] += 0.3
            emit(95, 58)
    else:
        st["gear"] = 4
        while st["mph"] < 70:
            st["mph"] += 0.35
            upshift(2500)
            emit(45, 60)
        upshift(1800)
        for _ in range(200):
            emit(25, 45)
        st["gear"] = 5               # kickdown for the full-throttle pull
        for _ in range(16):
            st["mph"] += 0.6
            emit(95, 92)
    for n, r in enumerate(rows):     # slow sensors only every 8th sample, like the real logger
        r.extend([90, 12] if n % 8 == 0 else ["", ""])
    return rows


def write_drive(path: Path, symptom: bool) -> Path:
    with Path(path).open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(make_drive(symptom))
    return Path(path)


def make_scan(symptom: bool) -> dict:
    q = lambda v, u: {"value": v, "unit": u}  # noqa: E731
    live = {"RPM": q(720, "revolutions_per_minute"), "COOLANT_TEMP": q(92, "degree_Celsius"),
            "SHORT_FUEL_TRIM_1": q(2.3, "percent"), "LONG_FUEL_TRIM_1": q(3.1, "percent"),
            "SHORT_FUEL_TRIM_2": q(1.7, "percent"), "LONG_FUEL_TRIM_2": q(2.5, "percent"),
            "SPEED": q(0, "kilometer_per_hour"), "ENGINE_LOAD": q(21, "percent")}
    tcm_uds = [{"code": "P0730", "ftb": "00", "status": "09", "flags": ["testFailed", "confirmed"], "desc": ""},
               {"code": "P0868", "ftb": "92", "status": "04", "flags": ["pending"], "desc": ""}] if symptom else []
    return {"timestamp": "2026-01-01T12:00:00", "protocol": "ISO 15765-4 (CAN 11/500)", "port": "DEMO",
            "vin": DEMO_VIN, "elm_voltage": q(14.0, "volt"), "freeze_frame_dtc": None,
            "status": {"mil_on": symptom, "dtc_count": int(symptom), "ignition_type": "spark",
                       "monitors": {"MISFIRE_MONITORING": "complete", "CATALYST_MONITORING": "complete"}},
            "stored_dtcs": [["P0700", "Transmission Control System (MIL Request)"]] if symptom else [],
            "pending_dtcs": [], "live_snapshot": live, "snapshot_failed": [],
            "modules": {"ECM (engine)": {"address": "7E0", "obd_stored": [["P0700", ""]] if symptom else [],
                                         "obd_pending": [], "uds_dtcs": [], "uds_error": None, "responded": True},
                        "TCM (transmission)": {"address": "7E1", "obd_stored": [["P0730", ""]] if symptom else [],
                                               "obd_pending": [], "uds_dtcs": tcm_uds, "uds_error": None,
                                               "responded": True}}}


DEMO_NOTES = {
    "updated": "demo",
    "summary": "DEMO DATA (simulated). This is where a written diagnosis goes. Here: the TCM has P0730 "
               "(incorrect gear ratio) confirmed and P0868 (low fluid pressure) pending, and the drive log "
               "shows the transmission holding 4th gear at highway speed. Together that points to transmission "
               "limp mode, most likely from low fluid pressure.",
    "next_steps": [
        {"priority": "high", "text": "Have the transmission fluid level and condition checked (shop procedure on the 8-speed)."},
        {"priority": "medium", "text": "Ask a dealer to check for transmission software updates by VIN."},
    ],
}


def write_demo(folder: Path, symptom: bool = True) -> Path:
    """Create folder/scans with one demo scan + drive log and folder/notes.json."""
    folder = Path(folder)
    scans = folder / "scans"
    scans.mkdir(parents=True, exist_ok=True)
    for old in scans.glob("*"):
        old.unlink()
    (scans / "scan-20260101-120000.json").write_text(json.dumps(make_scan(symptom), indent=2))
    write_drive(scans / "drivelog-20260101-120000.csv", symptom)
    (folder / "notes.json").write_text(json.dumps(DEMO_NOTES if symptom else {}, indent=2))
    return folder
