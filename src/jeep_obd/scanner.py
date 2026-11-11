"""Read-only vehicle access through an ELM327/STN adapter (e.g. OBDLink EX).

Reads engine + transmission module codes, a live sensor snapshot, and an
optional fast drive log. Sends ONLY read requests: OBD-II modes 01/03/07/09
and UDS 0x19 ReadDTCInformation. Nothing here clears codes or writes to
any module.
"""
from __future__ import annotations

import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import obd
import serial.tools.list_ports
from obd import OBDCommand
from obd.protocols import ECU

try:
    from obd.codes import DTC as DTC_DESC
except Exception:  # descriptions are a nice-to-have
    DTC_DESC = {}
try:
    import msvcrt  # Windows keypress for symptom marks
except ImportError:
    msvcrt = None

# USB adapter chips: OBDLink EX (FTDI/STN) plus common ELM327-clone USB chips.
# Bluetooth COM ports are deliberately NOT matched (probing them can hang).
ADAPTER_HINTS = ("obdlink", "stn", "ftdi", "usb serial", "usb-serial", "ch340", "pl2303", "cp210", "elm327")

# Read every loop (shift analysis needs these fast) / every SLOW_EVERY loops
CORE_PIDS = ["RPM", "SPEED", "ACCELERATOR_POS_D", "THROTTLE_POS", "ENGINE_LOAD"]
SLOW_PIDS = ["COOLANT_TEMP", "INTAKE_TEMP", "TIMING_ADVANCE", "MAF", "INTAKE_PRESSURE",
             "SHORT_FUEL_TRIM_1", "LONG_FUEL_TRIM_1", "SHORT_FUEL_TRIM_2", "LONG_FUEL_TRIM_2",
             "CONTROL_MODULE_VOLTAGE", "CATALYST_TEMP_B1S1", "OIL_TEMP", "FUEL_LEVEL"]
SLOW_EVERY = 8

# Physical CAN addresses (standard OBD addressing on this platform)
MODULES = {"ECM (engine)": b"7E0", "TCM (transmission)": b"7E1"}
UDS_STATUS_BITS = {0: "testFailed", 2: "pending", 3: "confirmed", 7: "warningLamp"}


def list_ports() -> None:
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        print(f"  {p.device:8} {p.description}")
    if not ports:
        print("  (no serial ports found: is the adapter plugged in?)")


def pick_port(explicit: str | None) -> str:
    if explicit:
        return explicit
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        if any(h in (p.description or "").lower() for h in ADAPTER_HINTS):
            return p.device
    print("No USB OBD adapter found.")
    print("  - Is the adapter's USB cable plugged into this laptop?")
    print("  - Serial ports on this laptop right now:")
    list_ports()
    print("  If your adapter is one of these, run again with --port COMx (e.g. jeep-obd scan --port COM7).")
    sys.exit(2)


def status_dict(v) -> dict:
    out = {"mil_on": bool(getattr(v, "MIL", False)),
           "dtc_count": getattr(v, "DTC_count", None),
           "ignition_type": str(getattr(v, "ignition_type", "")),
           "monitors": {}}
    for name, t in vars(v).items():
        if hasattr(t, "available") and hasattr(t, "complete") and t.available:
            out["monitors"][name] = "complete" if t.complete else "incomplete"
    return out


def val(resp) -> object:
    if resp is None or resp.is_null():
        return None
    v = resp.value
    if isinstance(v, (bytes, bytearray)):
        return v.decode(errors="ignore").strip("\x00 ")
    if hasattr(v, "MIL"):
        return status_dict(v)
    if isinstance(v, list):
        return [list(x) if isinstance(x, tuple) else str(x) for x in v]
    if hasattr(v, "magnitude"):  # pint quantity
        return {"value": round(float(v.magnitude), 3), "unit": str(v.units)}
    return str(v)


def num(resp):
    if resp is None or resp.is_null():
        return ""
    v = resp.value
    return round(float(v.magnitude), 3) if hasattr(v, "magnitude") else ""


# ---------- raw read-only requests to a specific module ----------

def raw(conn: obd.OBD, req: bytes, header: bytes) -> list:
    cmd = OBDCommand(f"RAW_{req.decode()}_{header.decode()}", "raw read", req, 0,
                     lambda msgs: msgs, ECU.ALL, False, header=header)
    r = conn.query(cmd, force=True)
    return list(r.value) if (r is not None and r.value) else []


def dtc_str(b1: int, b2: int) -> str:
    return "PCBU"[b1 >> 6] + str((b1 >> 4) & 3) + f"{b1 & 0xF:X}{b2 >> 4:X}{b2 & 0xF:X}"


def decode_obd_dtcs(msgs: list, resp_mode: int) -> list:
    codes = []
    for m in msgs:
        d = bytes(m.data)
        if not d or d[0] != resp_mode:
            continue
        rest = d[1:]
        if len(rest) % 2 == 1:  # CAN responses carry a leading count byte
            rest = rest[1:]
        for i in range(0, len(rest) - 1, 2):
            if rest[i] == 0 and rest[i + 1] == 0:
                continue
            c = dtc_str(rest[i], rest[i + 1])
            codes.append([c, DTC_DESC.get(c, "")])
    return codes


def decode_uds_dtcs(msgs: list) -> tuple[list, str | None]:
    out, err = [], None
    for m in msgs:
        d = bytes(m.data)
        if len(d) >= 3 and d[0] == 0x7F:
            err = f"negative response NRC 0x{d[2]:02X}"
            continue
        if len(d) < 3 or d[0] != 0x59:
            continue
        rec = d[3:]
        for i in range(0, len(rec) - 3, 4):
            b1, b2, ftb, st = rec[i:i + 4]
            if b1 == b2 == ftb == 0:
                continue
            c = dtc_str(b1, b2)
            out.append({"code": c, "ftb": f"{ftb:02X}", "status": f"{st:02X}",
                        "flags": [n for b, n in UDS_STATUS_BITS.items() if st >> b & 1],
                        "desc": DTC_DESC.get(c, "")})
    return out, err


def read_modules(conn: obd.OBD) -> dict:
    res = {}
    for name, hdr in MODULES.items():
        m: dict = {"address": hdr.decode()}
        try:
            r03, r07, r19 = raw(conn, b"03", hdr), raw(conn, b"07", hdr), raw(conn, b"1902FF", hdr)
            m["obd_stored"] = decode_obd_dtcs(r03, 0x43)
            m["obd_pending"] = decode_obd_dtcs(r07, 0x47)
            m["uds_dtcs"], m["uds_error"] = decode_uds_dtcs(r19)
            m["responded"] = bool(r03 or r07 or r19)
        except Exception as e:  # loud: recorded in report and printed
            m["responded"], m["error"] = False, f"{type(e).__name__}: {e}"
        res[name] = m
    return res


# ---------- scan + drive log ----------

def connect(port: str | None) -> obd.OBD:
    print(f"Connecting on {port or 'auto-detect'} ...")
    conn = obd.OBD(portstr=port, fast=False, timeout=1.0)
    if not conn.is_connected():
        print(f"FAILED to connect. Status: {conn.status()}")
        print("Check: ignition ON, adapter seated, correct COM port (--list-ports).")
        sys.exit(2)
    print(f"Connected. Protocol: {conn.protocol_name()}  Port: {conn.port_name()}")
    return conn


def scan(conn: obd.OBD) -> dict:
    c = obd.commands
    report: dict = {"timestamp": datetime.now().isoformat(timespec="seconds"),
                    "protocol": conn.protocol_name(), "port": conn.port_name()}
    for name in ("ELM_VOLTAGE", "VIN", "STATUS"):
        cmd = getattr(c, name, None)
        report[name.lower()] = val(conn.query(cmd)) if cmd else None
    report["stored_dtcs"] = val(conn.query(c.GET_DTC)) or []
    report["pending_dtcs"] = val(conn.query(c.GET_CURRENT_DTC)) or []
    report["freeze_frame_dtc"] = val(conn.query(c.FREEZE_DTC))

    live, failed = {}, []
    mode1 = sorted((x for x in conn.supported_commands if x.command[:2] == b"01"),
                   key=lambda x: x.command)
    for cmd in mode1:
        if cmd.name.startswith("PIDS_"):
            continue
        r = val(conn.query(cmd))
        (failed.append(cmd.name) if r is None else live.__setitem__(cmd.name, r))
    report["live_snapshot"], report["snapshot_failed"] = live, failed
    report["modules"] = read_modules(conn)
    return report


def drive_log(conn: obd.OBD, seconds: int, path: Path) -> None:
    def have(n):
        cmd = getattr(obd.commands, n, None)
        return cmd if cmd is not None and conn.supports(cmd) else None
    core = [x for x in map(have, CORE_PIDS) if x]
    slow = [x for x in map(have, SLOW_PIDS) if x]
    names = [x.name for x in core + slow]
    print(f"Logging {len(core)} fast + {len(slow)} slow PIDs "
          f"{'until Ctrl+C' if seconds <= 0 else f'for {seconds}s'} -> {path}")
    if msvcrt:
        print("PASSENGER: press M on the laptop the moment the symptom happens.")
    end = time.time() + seconds if seconds > 0 else float("inf")
    rows = marks = 0
    t0 = time.time()
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "mark"] + names)
        try:
            while time.time() < end:
                row = {"t": round(time.time() - t0, 2)}
                for cmd in core + (slow if rows % SLOW_EVERY == 0 else []):
                    row[cmd.name] = num(conn.query(cmd))
                mark = 0
                while msvcrt and msvcrt.kbhit():
                    if msvcrt.getwch().lower() == "m":
                        mark = 1
                if mark:
                    marks += 1
                    print(f"  symptom marked at {row['t']}s")
                w.writerow([row["t"], mark] + [row.get(n, "") for n in names])
                rows += 1
                if rows % 20 == 0:
                    f.flush()
        except KeyboardInterrupt:
            print("Stopped by Ctrl+C.")
    el = max(time.time() - t0, 1e-6)
    print(f"Logged {rows} samples over {el:.0f}s ({rows / el:.1f}/s), {marks} symptom mark(s).")
    if rows / el < 2:
        print("WARNING: under 2 samples/s; shift analysis will be coarse.")
