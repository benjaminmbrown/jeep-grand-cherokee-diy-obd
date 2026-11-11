"""`jeep-obd` command line. Run `jeep-obd --help` for usage."""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from . import __version__

DEFAULT_DIR = Path.home() / "JeepOBD"


def data_dir(arg: str | None) -> Path:
    d = Path(arg or os.environ.get("JEEP_OBD_DIR") or DEFAULT_DIR)
    (d / "scans").mkdir(parents=True, exist_ok=True)
    return d


def rebuild(folder: Path, open_it: bool, title: str | None = None) -> Path:
    from .report import build
    out = build(folder / "scans", folder / "dashboard.html", folder / "notes.json", title=title)
    print(f"\nDashboard: {out}")
    if open_it:
        webbrowser.open(out.resolve().as_uri())
    return out


def print_summary(report: dict) -> None:
    print(f"\nBattery (at the adapter): {report['elm_voltage']}")
    print(f"VIN: {report['vin']}")
    print(f"Engine codes (generic) stored: {report['stored_dtcs'] or 'none'}  "
          f"pending: {report['pending_dtcs'] or 'none'}")
    for name, m in report["modules"].items():
        if not m.get("responded"):
            print(f"{name}: NO RESPONSE {m.get('error') or m.get('uds_error') or ''}")
            continue
        codes = [d["code"] + "-" + d["ftb"] for d in m["uds_dtcs"]] + \
                [c for c, _ in m["obd_stored"] + m["obd_pending"]]
        print(f"{name}: {', '.join(dict.fromkeys(codes)) or 'no codes'}"
              + (f"  (extended read: {m['uds_error']})" if m.get("uds_error") else ""))
    print(f"Live sensors read: {len(report['live_snapshot'])}, unreadable: {len(report['snapshot_failed'])}")


def run_scan(args, drive_seconds: int | None) -> None:
    from . import scanner
    folder = data_dir(args.data_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    conn = scanner.connect(scanner.pick_port(args.port))
    try:
        report = scanner.scan(conn)
        out = folder / "scans" / f"scan-{stamp}.json"
        out.write_text(json.dumps(report, indent=2))
        print_summary(report)
        print(f"Saved: {out}")
        if drive_seconds is not None:
            scanner.drive_log(conn, drive_seconds, folder / "scans" / f"drivelog-{stamp}.csv")
    finally:
        conn.close()
    rebuild(folder, not args.no_open)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="jeep-obd",
        description="Read-only OBD-II diagnostics + dashboard for the Jeep Grand Cherokee (WK2). "
                    "Never clears codes or writes to the vehicle.")
    ap.add_argument("--version", action="version", version=f"jeep-obd {__version__}")
    ap.add_argument("--data-dir", help=f"where scans and the dashboard are saved (default {DEFAULT_DIR}, "
                                       "or set JEEP_OBD_DIR)")
    sub = ap.add_subparsers(dest="cmd", metavar="COMMAND")

    def with_port(p):
        p.add_argument("--port", help="adapter COM port, e.g. COM7 (default: auto-detect)")
        p.add_argument("--no-open", action="store_true", help="don't open the dashboard in a browser")
        return p

    sub.add_parser("ports", help="list serial ports, to find the adapter")
    with_port(sub.add_parser("scan", help="read codes + sensors (ignition ON), save, open dashboard"))
    d = with_port(sub.add_parser("drive", help="scan, then record a drive log until Ctrl+C (press M to mark a symptom)"))
    d.add_argument("--seconds", type=int, default=0, help="stop after N seconds (default: run until Ctrl+C)")
    r = sub.add_parser("report", help="rebuild and open the dashboard from saved scans")
    r.add_argument("--no-open", action="store_true")
    m = sub.add_parser("demo", help="build a dashboard from simulated data (no car needed)")
    m.add_argument("--healthy", action="store_true", help="simulate a healthy vehicle instead of a faulty one")
    m.add_argument("--no-open", action="store_true")
    sub.add_parser("where", help="print the data folder location")

    args = ap.parse_args(argv)
    if args.cmd is None:
        ap.print_help()
        return
    if args.cmd == "ports":
        from .scanner import list_ports
        list_ports()
    elif args.cmd == "scan":
        run_scan(args, None)
    elif args.cmd == "drive":
        run_scan(args, args.seconds)
    elif args.cmd == "report":
        rebuild(data_dir(args.data_dir), not args.no_open)
    elif args.cmd == "demo":
        from .demo import write_demo
        folder = write_demo(data_dir(args.data_dir) / "demo", symptom=not args.healthy)
        rebuild(folder, not args.no_open, title="Jeep Grand Cherokee (demo data)")
    elif args.cmd == "where":
        print(data_dir(args.data_dir))


if __name__ == "__main__":
    sys.exit(main())
