"""Build dashboard.html from scans/*.json, scans/drivelog-*.csv and notes.json.

Tabs: Overview, Transmission, Drive log, Codes (glossary). Every trouble
code anywhere on the page gets a hover explanation and links to its
glossary entry. Health checks are deterministic rules; notes.json holds an
optional written diagnosis / next steps (by you, a mechanic, or an AI
assistant) shown on the Overview tab.
"""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from . import glossary, trans_analysis

E = html.escape
GENERIC: dict = {}
VIN_YEARS = dict(zip("ABCDEFGHJKLMNPRSTVWXY", range(2010, 2031)))


def vehicle_title(vin) -> str:
    vin = str(vin or "")
    year = VIN_YEARS.get(vin[9]) if len(vin) == 17 else None
    if vin.startswith("1C4R"):
        return f"{year or ''} Jeep Grand Cherokee".strip()
    return f"{year} vehicle" if year else "Vehicle health"


def c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


# ---------- code links / tooltips ----------

def code_link(code: str, ftb: str | None = None) -> str:
    tip = glossary.tip_text(code, GENERIC, ftb)
    label = code + (f"-{ftb}" if ftb else "")
    return f'<a class="code" href="#code-{code}" data-tip="{E(tip)}">{label}</a>'


def lk(text) -> str:
    """Escape text and turn every trouble code in it into a tooltip link."""
    return glossary.CODE_RE.sub(lambda m: code_link(m.group(1), m.group(2)), E(str(text)))


# ---------- data loading ----------

def live_num(scan: dict, name: str) -> float | None:
    v = (scan.get("live_snapshot") or {}).get(name)
    return v.get("value") if isinstance(v, dict) else None


def fmt_live(v) -> str:
    if isinstance(v, dict):
        unit = v.get("unit", "")
        if "Celsius" in unit:
            return f"{c_to_f(v['value']):.0f} °F"
        if unit == "kilometer_per_hour":
            return f"{v['value'] * 0.621371:.0f} mph"
        unit = (unit.replace("revolutions_per_minute", "rpm").replace("percent", "%")
                    .replace("volt", "V").replace("kilopascal", "kPa")
                    .replace("gram / second", "g/s").replace("degree", "°")
                    .replace("dimensionless", ""))
        return f"{v['value']:g} {unit}".strip()
    return str(v)


def load(scans_dir: Path):
    scans = []
    for p in sorted(scans_dir.glob("scan-*.json")):
        try:
            d = json.loads(p.read_text())
            d["_file"] = p.name
            scans.append(d)
        except Exception as e:  # loud, not silent
            print(f"WARNING: skipped unreadable {p.name}: {e}")
    logs = sorted(scans_dir.glob("drivelog-*.csv"))
    return scans, (logs[-1] if logs else None)


def read_log(path: Path) -> dict:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    cols: dict[str, list] = {}
    for r in rows:
        for k, v in r.items():
            try:
                x = float(v)
                if "TEMP" in k:
                    x = round(c_to_f(x), 1)
                elif k == "SPEED":
                    x = round(x * 0.621371, 1)  # km/h -> mph
            except (TypeError, ValueError):
                x = None
            cols.setdefault(k, []).append(x)
    return cols


def scan_codes(scan: dict) -> list[dict]:
    """Every code in one scan: [{code, ftb, module, kind, flags, desc}] (deduped)."""
    out, seen = [], set()

    def put(code, ftb, module, kind, flags=(), desc=""):
        key = (code, module)
        if key in seen:
            return
        seen.add(key)
        out.append({"code": code, "ftb": ftb, "module": module, "kind": kind, "flags": list(flags), "desc": desc})

    for name, m in (scan.get("modules") or {}).items():
        for d in m.get("uds_dtcs") or []:
            kind = "Confirmed" if "confirmed" in d["flags"] else "Pending" if "pending" in d["flags"] else "History"
            put(d["code"], d["ftb"], name, kind, d["flags"], d.get("desc", ""))
        for c, desc in m.get("obd_stored") or []:
            put(c, None, name, "Stored", (), desc)
        for c, desc in m.get("obd_pending") or []:
            put(c, None, name, "Pending", (), desc)
    have = {c["code"] for c in out}
    for c, desc in scan.get("stored_dtcs") or []:
        if c not in have:
            put(c, None, "Engine (generic OBD)", "Stored", (), desc)
    for c, desc in scan.get("pending_dtcs") or []:
        if c not in have:
            put(c, None, "Engine (generic OBD)", "Pending", (), desc)
    return out


# ---------- rule-based checks ----------

def health_checks(scan: dict, codes: list[dict], ta: dict | None) -> list[dict]:
    out = []

    def add(level, title, detail, action=""):
        out.append({"level": level, "title": title, "detail": detail, "action": action})

    st = scan.get("status") if isinstance(scan.get("status"), dict) else {}
    rpm = live_num(scan, "RPM") or 0
    running = rpm > 400

    if st.get("mil_on"):
        add("fail", "Check engine light is ON", "The engine computer has commanded the MIL.",
            "Diagnose the codes below before long drives.")
    for c in codes:
        lvl = "fail" if c["kind"] in ("Confirmed", "Stored") else "warn" if c["kind"] == "Pending" else "info"
        tag = c["code"] + (f"-{c['ftb']}" if c["ftb"] else "")
        add(lvl, f"{c['module']}: {c['kind'].lower()} code {tag}", glossary.lookup(c["code"], GENERIC)["title"],
            glossary.CURATED.get(c["code"], {}).get("check", f"Look up {c['code']} in the Codes tab."))
    for name, m in (scan.get("modules") or {}).items():
        if not m.get("responded"):
            add("warn", f"{name} did not answer the code request",
                m.get("error") or "No response at its address.", "Re-scan with the engine running.")
    if not codes and not st.get("mil_on"):
        add("ok", "No trouble codes", "No codes in the engine or transmission computers.")

    v = (scan.get("elm_voltage") or {}).get("value") if isinstance(scan.get("elm_voltage"), dict) else None
    if v is not None:
        if running:
            if v < 13.2:
                add("warn", f"Charging voltage low ({v:.1f} V)", "Running voltage should be ~13.5-14.8 V.",
                    "Have the alternator and battery load-tested.")
            elif v > 15.0:
                add("fail", f"Charging voltage high ({v:.1f} V)", "Overcharging can damage battery and modules.",
                    "Check alternator/voltage regulation.")
            else:
                add("ok", f"Charging voltage {v:.1f} V", "Alternator output in normal range.")
        else:
            if v < 11.8:
                add("fail", f"Battery very low ({v:.1f} V, engine off)", "Healthy resting battery: ~12.4-12.7 V.",
                    "Charge and load-test the battery; check for parasitic drain.")
            elif v < 12.2:
                add("warn", f"Battery low ({v:.1f} V, engine off)", "Partially discharged; low voltage can upset the TCM.",
                    "Charge the battery; re-test after it sits overnight.")
            else:
                add("ok", f"Battery {v:.1f} V (engine off)", "Resting voltage looks healthy.")

    for bank in ("1", "2"):
        lt = live_num(scan, f"LONG_FUEL_TRIM_{bank}")
        stt = live_num(scan, f"SHORT_FUEL_TRIM_{bank}") or 0
        if lt is None or not running:
            continue
        total = lt + stt
        if abs(lt) > 20 or abs(total) > 25:
            add("fail", f"Fuel trim bank {bank} extreme ({total:+.0f}%)",
                "Positive = lean (vacuum leak, weak fuel delivery, MAF); negative = rich.",
                "Smoke-test for vacuum leaks; check MAF and fuel pressure.")
        elif abs(lt) > 10 or abs(total) > 15:
            add("warn", f"Fuel trim bank {bank} elevated ({total:+.0f}%)",
                "Engine is compensating beyond the normal ±10%.", "Watch it on the next drive log; check for vacuum leaks.")
        else:
            add("ok", f"Fuel trim bank {bank} {total:+.0f}%", "Within normal range.")

    mons = st.get("monitors") or {}
    inc = [m for m, s in mons.items() if s == "incomplete"]
    if inc:
        add("info", f"{len(inc)} readiness monitor(s) incomplete", ", ".join(sorted(inc)),
            "Normal after a battery disconnect or code clear; needs a mixed drive cycle.")
    failed = scan.get("snapshot_failed") or []
    if failed:
        add("info", f"{len(failed)} sensor value(s) unreadable", ", ".join(failed[:12]),
            "Usually harmless (PID advertised but not answered).")
    if ta and ta.get("ok"):
        for f in ta["findings"]:
            out.append(dict(f, title="Transmission: " + f["title"]))
    return out


def coolant_check(log: dict | None) -> list[dict]:
    if not log or not log.get("COOLANT_TEMP"):
        return []
    temps = [t for t in log["COOLANT_TEMP"] if t is not None]
    secs = max((t for t in log.get("t", []) if t is not None), default=0)
    if not temps:
        return []
    hi = max(temps)
    if hi > 230:
        return [{"level": "fail", "title": f"Coolant hit {hi:.0f} °F", "detail": "Overheating range.",
                 "action": "Check coolant level, fans, thermostat, water pump. Don't drive hot."}]
    if hi > 222:
        return [{"level": "warn", "title": f"Coolant peaked {hi:.0f} °F", "detail": "Upper edge of normal.",
                 "action": "Check coolant level and fans."}]
    if secs > 600 and hi < 180:
        return [{"level": "warn", "title": f"Coolant never passed {hi:.0f} °F", "detail": "Didn't reach operating temp in 10+ min.",
                 "action": "Thermostat may be stuck open."}]
    return [{"level": "ok", "title": f"Coolant peak {hi:.0f} °F", "detail": "Normal operating temperature.", "action": ""}]


# ---------- HTML pieces ----------

def checks_html(checks: list[dict]) -> str:
    if not checks:
        return '<p class="empty">Nothing to report.</p>'
    return "".join(f'<div class="chk"><span class="dot {c["level"]}"></span><div><b>{lk(c["title"])}</b>'
                   f'<div class="d">{lk(c["detail"])}</div>'
                   + (f'<div class="a">→ {lk(c["action"])}</div>' if c["action"] else "") + "</div></div>"
                   for c in checks)


def codes_table(codes: list[dict]) -> str:
    if not codes:
        return '<p class="empty">No trouble codes.</p>'
    rows = "".join(f"<tr><td>{E(c['module'])}</td><td>{E(c['kind'])}</td><td><b>{code_link(c['code'], c['ftb'])}</b></td>"
                   f"<td>{E(glossary.lookup(c['code'], GENERIC)['title'])}</td><td>{E(', '.join(c['flags']))}</td></tr>"
                   for c in codes)
    return f"<table><tr><th>Module</th><th>Type</th><th>Code</th><th>Meaning</th><th>Status flags</th></tr>{rows}</table>"


def table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return '<p class="empty">None.</p>'
    h = "".join(f"<th>{E(x)}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{lk('' if v is None else v)}</td>" for v in r) + "</tr>" for r in rows)
    return f'<div class="tbl"><table><tr>{h}</tr>{b}</table></div>'


def glossary_tab(scans: list[dict]) -> str:
    anchored: set[str] = set()

    def aid(code):
        if code in anchored:
            return ""
        anchored.add(code)
        return f' id="code-{code}"'

    # codes seen on this Jeep, across all scans
    seen: dict[str, dict] = {}
    for s in scans:
        for c in scan_codes(s):
            e = seen.setdefault(c["code"], {"modules": set(), "ftbs": set(), "first": s.get("timestamp", ""), "last": ""})
            e["modules"].add(c["module"])
            if c["ftb"]:
                e["ftbs"].add(c["ftb"])
            e["last"] = s.get("timestamp", "")
    mine = ""
    for code in sorted(seen):
        d, e = glossary.lookup(code, GENERIC), seen[code]
        ftbs = "".join(f"<li><b>-{f}</b>: {E(glossary.FTB.get(f, 'failure type ' + f))}</li>" for f in sorted(e["ftbs"]))
        mine += (f'<div class="gcard"{aid(code)}><h3>{code} <span class="sub">{E(d["sys"])}</span></h3>'
                 f'<b>{E(d["title"])}</b>' + (f"<p>{E(d['plain'])}</p>" if d["plain"] else "")
                 + (f"<p><i>What to check:</i> {E(d['check'])}</p>" if d["check"] else "")
                 + (f"<ul>{ftbs}</ul>" if ftbs else "")
                 + f'<p class="sub">Seen in: {E(", ".join(sorted(e["modules"])))} · first {E(e["first"])} · last {E(e["last"])}'
                 f' · source: {E(glossary.SOURCES.get(d["source"], "no definition on file"))}</p></div>')
    if not mine:
        mine = '<p class="empty">No codes recorded yet. Codes found by a scan appear here with full explanations.</p>'

    cur = "".join(f'<tr class="g"{aid(c)}><td><b>{c}</b></td><td>{E(d.get("sys", ""))}</td><td><b>{E(d["title"])}</b><br>'
                  f'{E(d["plain"])}<br><i>Check:</i> {E(d.get("check", ""))}</td></tr>'
                  for c, d in sorted(glossary.CURATED.items()))
    ftb = "".join(f"<tr class='g'><td><b>-{k}</b></td><td>{E(v)}</td></tr>" for k, v in glossary.FTB.items())
    flags = "".join(f"<tr class='g'><td><b>{E(k)}</b></td><td>{E(v)}</td></tr>" for k, v in glossary.STATUS_FLAGS.items())
    gen = "".join(f'<tr class="g"{aid(c)}><td><b>{c}</b></td><td>{E(t)}</td></tr>' for c, t in GENERIC.items())
    return f"""
<div class="card"><input id="gsearch" type="search" placeholder="Search codes or words, e.g. P0730, slip, solenoid, lean">
<p class="sub">How to read a code: the first letter is the system (P powertrain, C chassis, B body, U network).
A 0 or 2 after it means a generic SAE code; 1 or 3 means manufacturer-specific. A suffix like <b>-77</b>
is the failure type the module reported.</p></div>
<section class="card"><h2>Codes on this Jeep</h2>{mine}</section>
<section class="card"><h2>Plain-English guide ({len(glossary.CURATED)} codes relevant to this vehicle)</h2>
<div class="tbl tall"><table class="gl">{cur}</table></div></section>
<div class="grid two" style="margin-top:14px">
<div class="card"><h2>Failure-type suffixes</h2><table class="gl">{ftb}</table></div>
<div class="card"><h2>Status flags</h2><table class="gl">{flags}</table></div></div>
<section class="card"><h2>All generic codes ({len(GENERIC):,})</h2><p class="sub">{E(glossary.SOURCES['generic'])}</p>
<div class="tbl tall"><table class="gl">{gen}</table></div></section>"""


def trans_tab(scan: dict, codes: list[dict], ta: dict | None, log_name: str | None) -> str:
    tcm = [c for c in codes if c["module"].startswith("TCM")]
    tm = (scan.get("modules") or {}).get("TCM (transmission)")
    if tm is None:
        tcm_html = '<p class="empty">This scan predates transmission-module reading. Re-scan to read the TCM.</p>'
    elif not tm.get("responded"):
        tcm_html = f'<p class="empty">The TCM did not respond ({E(tm.get("error") or "no answer")}).</p>'
    else:
        tcm_html = codes_table(tcm) if tcm else '<p>No codes stored in the transmission computer.</p>'
        if tm.get("uds_error"):
            tcm_html += f'<p class="sub">Extended code read: {E(tm["uds_error"])}</p>'

    howto = """<ol class="steps">
<li>Engine warm, passenger runs the laptop. Run: <code>jeep-obd drive</code></li>
<li>Drive normally to highway speed and cruise for a minute at 55-70 mph.</li>
<li>Reproduce the symptom: accelerate moderately from ~40 mph like you normally would when it fails to shift.</li>
<li>Passenger presses <b>M</b> the moment it won't shift or loses power.</li>
<li>If safe (on-ramp), one firm full-throttle pull for 3-5 seconds.</li>
<li>Press Ctrl+C to stop. The dashboard rebuilds and opens automatically.</li></ol>"""
    if not ta or not ta.get("ok"):
        why = E(ta["reason"]) if ta else "No drive log yet."
        return f"""<div class="grid two"><div class="card"><h2>Transmission computer codes</h2>{tcm_html}</div>
<div class="card"><h2>Capture the symptom</h2><p class="sub">{why}</p>{howto}</div></div>"""

    gt = ta["gear_time"]
    held = table(["Gear", "From mph", "To mph", "Peak RPM", "Median pedal %", "Time (s)"],
                 [[h["gear"], h["mph0"], h["mph1"], h["rpm_peak"], h["pedal_median"], f"{h['t0']:.0f}-{h['t1']:.0f}"] for h in ta["held"]])
    flares = table(["Time (s)", "mph", "RPM from", "RPM to", "Gear before", "Gear after"],
                   [[f["t"], f["mph"], f["rpm_from"], f["rpm_to"], f["gear_before"], f["gear_after"] or "no gear"] for f in ta["flares"]])
    wot = table(["Time (s)", "Secs", "mph", "Accel (mph/s)", "Peak RPM", "Avg load %", "Min timing °"],
                [[w["t"], w["secs"], f"{w['mph0']}→{w['mph1']}", w["accel"], w["rpm_peak"], w["load_avg"], w["timing_min"]] for w in ta["wot"]])
    marks = table(["Time (s)", "mph", "RPM", "Est. gear", "Pedal %"],
                  [[m["t"], m["mph"], m["rpm"], m["gear"] or "between gears", m["pedal"]] for m in ta["marks"]])
    return f"""
<div class="grid kpis">
 <div class="card kpi"><div class="l">Highest gear used</div><div class="v">{ta['max_gear'] or 'n/a'} / 8</div></div>
 <div class="card kpi"><div class="l">Top speed</div><div class="v">{ta['max_mph']} mph</div></div>
 <div class="card kpi"><div class="l">Time in 6th-8th</div><div class="v">{gt[6] + gt[7] + gt[8]:.0f} s</div></div>
 <div class="card kpi"><div class="l">RPM flares</div><div class="v">{len(ta['flares'])}</div></div>
 <div class="card kpi"><div class="l">Symptom marks</div><div class="v">{len(ta['marks'])}</div></div>
</div>
<div class="grid two">
 <div class="card"><h2>Transmission findings</h2>{checks_html(ta['findings'])}</div>
 <div class="card"><h2>Transmission computer codes</h2>{tcm_html}</div>
</div>
<section class="card"><h2>Gear vs. speed</h2>
<p class="sub">Estimated gear from RPM ÷ speed against the 8-speed's ratios (fitted axle×tire constant {ta['k']}, implies ~{ta['implied_axle']} axle).
Gaps = shifting, slipping or torque converter unlocked. Red dots = your symptom marks. Log: {E(log_name or '')}</p>
<div class="chart tallc"><canvas id="gearline"></canvas></div></section>
<div class="grid two" style="margin-top:14px">
 <div class="card"><h2>Time in each gear</h2><div class="chart"><canvas id="geartime"></canvas></div></div>
 <div class="card"><h2>Symptom marks</h2>{marks}</div>
</div>
<section class="card"><h2>Held gear events</h2>{held}</section>
<section class="card"><h2>RPM flares (possible slip)</h2>{flares}</section>
<section class="card"><h2>Full-throttle pulls (power check)</h2>{wot}</section>
<section class="card"><h2>Capture another drive</h2>{howto}</section>"""


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1b1f24;--mut:#5f6b7a;--line:#e3e7ec;--hl:#fff6d6;
--ok:#1f8a4c;--warn:#b7791f;--fail:#c53030;--info:#2b6cb0;--acc:#2b6cb0}
@media (prefers-color-scheme:dark){:root{--bg:#0f1216;--card:#171b21;--fg:#e6e9ee;--hl:#3a3320;
--mut:#97a3b2;--line:#28303a;--ok:#48bb78;--warn:#ecc94b;--fail:#fc8181;--info:#63b3ed;--acc:#63b3ed}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:24px;margin:0}h2{font-size:17px;margin:0 0 12px}h3{margin:0 0 4px;font-size:16px}
.sub{color:var(--mut);font-size:13px}code{font-size:13px}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:14px}
.pill{padding:4px 12px;border-radius:999px;font-weight:600;font-size:13px;color:#fff}
.pill.ok{background:var(--ok)}.pill.warn{background:var(--warn)}.pill.fail{background:var(--fail)}
nav{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:16px;overflow-x:auto}
nav button{background:none;border:0;border-bottom:3px solid transparent;color:var(--mut);font:600 14px system-ui;
padding:10px 14px;cursor:pointer;white-space:nowrap}nav button.on{color:var(--fg);border-color:var(--acc)}
.panel{display:none}.panel.on{display:block}
.grid{display:grid;gap:14px}.kpis{grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin-bottom:14px}
.two{grid-template-columns:1fr 1fr}@media(max-width:820px){.two{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0}
.kpi .v{font-size:26px;font-weight:700}.kpi .l{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.chk{display:flex;gap:10px;padding:10px 0;border-top:1px solid var(--line)}.chk:first-of-type{border-top:0}
.dot{flex:none;width:10px;height:10px;border-radius:50%;margin-top:7px}
.dot.ok{background:var(--ok)}.dot.warn{background:var(--warn)}.dot.fail{background:var(--fail)}.dot.info{background:var(--info)}
.chk b{display:block}.chk .d{color:var(--mut);font-size:13px}.chk .a{font-size:13px;margin-top:2px}
ol.steps{margin:0;padding-left:20px}ol.steps li{margin:6px 0}
.tag{font-size:11px;font-weight:700;text-transform:uppercase;margin-right:6px}
.tag.high{color:var(--fail)}.tag.medium{color:var(--warn)}.tag.low{color:var(--info)}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{text-align:left;padding:6px 8px;border-top:1px solid var(--line);vertical-align:top}th{color:var(--mut);font-weight:600}
.tbl{max-height:420px;overflow:auto}.tbl.tall{max-height:560px}.chart{position:relative;height:240px}.chart.tallc{height:320px}
.empty{color:var(--mut);font-style:italic}section{margin-top:14px}
a.code{color:var(--acc);text-decoration:none;border-bottom:1px dotted var(--acc);font-weight:600;cursor:help;white-space:nowrap}
#tip{position:fixed;z-index:50;max-width:340px;background:#1b1f24;color:#f1f3f6;font-size:13px;line-height:1.45;
padding:9px 11px;border-radius:8px;box-shadow:0 6px 24px rgba(0,0,0,.25);pointer-events:none;display:none}
#tip i{color:#9fb3c8;font-size:12px}
.gcard{padding:12px 0;border-top:1px solid var(--line)}.gcard:first-of-type{border-top:0}.gcard p{margin:6px 0}
.flash{animation:fl 2.2s ease}@keyframes fl{0%,40%{background:var(--hl)}100%{background:transparent}}
#gsearch{width:100%;padding:10px 12px;font-size:15px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg)}
"""


def build(scans_dir: Path, out: Path, notes_path: Path | None = None, title: str | None = None) -> Path:
    global GENERIC
    GENERIC = glossary.load_generic()
    scans_dir, out = Path(scans_dir), Path(out)
    notes_path = Path(notes_path) if notes_path else out.parent / "notes.json"
    scans, log_path = load(scans_dir)
    log = read_log(log_path) if log_path else None
    ta = trans_analysis.analyze(trans_analysis.load_rows(log_path)) if log_path else None
    notes = json.loads(notes_path.read_text()) if notes_path.exists() else {}

    s = scans[-1] if scans else {}
    codes = scan_codes(s) if s else []
    checks = (health_checks(s, codes, ta) + coolant_check(log)) if s else []
    worst = "fail" if any(c["level"] == "fail" for c in checks) else \
            "warn" if any(c["level"] == "warn" for c in checks) else "ok"
    label = {"ok": "Healthy", "warn": "Needs attention", "fail": "Problems found"}[worst] if s else "No scans yet"
    st = s.get("status") if isinstance(s.get("status"), dict) else {}
    mons = st.get("monitors") or {}
    done = sum(1 for x in mons.values() if x == "complete")
    volt = s.get("elm_voltage")
    tcm_n = sum(1 for c in codes if c["module"].startswith("TCM"))

    # next steps: written notes first, then rule-generated actions
    steps = list(notes.get("next_steps") or [])
    for c in checks:
        if c["level"] in ("fail", "warn") and c["action"]:
            steps.append({"priority": "high" if c["level"] == "fail" else "medium", "text": c["action"]})
    if not steps:
        steps = [{"priority": "low", "text": "Nothing urgent. Re-scan monthly or whenever a warning light appears."}]
    seen_t, uniq = set(), []
    for x in steps:
        if x["text"] not in seen_t:
            seen_t.add(x["text"])
            uniq.append(x)
    steps_html = "".join(f'<li><span class="tag {E(x.get("priority", "low"))}">{E(x.get("priority", "low"))}</span>{lk(x["text"])}</li>'
                         for x in uniq)
    summary = ""
    if notes.get("summary"):
        summary = f'<p>{lk(notes["summary"])}</p><p class="sub">Diagnosis notes updated {E(notes.get("updated", ""))}</p>'

    if s:
        kpis = [("Check engine light", "ON" if st.get("mil_on") else "Off"), ("Codes (all modules)", len(codes)),
                ("Transmission codes", tcm_n if "modules" in s else "n/a"),
                ("Battery", f"{volt['value']:.1f} V" if isinstance(volt, dict) else "n/a"),
                ("Monitors ready", f"{done}/{len(mons)}" if mons else "n/a"),
                ("Sensors read", len(s.get("live_snapshot") or {}))]
        kpi_html = "".join(f'<div class="card kpi"><div class="l">{E(l)}</div><div class="v">{E(str(v))}</div></div>' for l, v in kpis)
        live_rows = "".join(f"<tr><td>{E(k)}</td><td>{E(fmt_live(v))}</td></tr>"
                            for k, v in sorted((s.get("live_snapshot") or {}).items()))
        hist_rows = "".join(f"<tr><td>{E(x.get('timestamp', ''))}</td><td>{len(scan_codes(x))}</td>"
                            f"<td>{' '.join(code_link(c['code'], c['ftb']) for c in scan_codes(x)) or '-'}</td></tr>"
                            for x in reversed(scans))
        overview = f"""
<div class="grid kpis">{kpi_html}</div>
<div class="grid two">
 <div class="card"><h2>Next steps</h2>{summary}<ol class="steps">{steps_html}</ol></div>
 <div class="card"><h2>Health checks</h2>{checks_html(checks)}</div>
</div>
<section class="card"><h2>Trouble codes (all modules)</h2>{codes_table(codes)}</section>
<div class="grid two" style="margin-top:14px">
 <div class="card"><h2>Scan history</h2><div class="chart"><canvas id="hist"></canvas></div>
  <div class="tbl"><table><tr><th>Scan</th><th>Codes</th><th>Which</th></tr>{hist_rows}</table></div></div>
 <div class="card"><h2>Live snapshot (last scan)</h2><div class="tbl"><table>{live_rows}</table></div></div>
</div>"""
    else:
        overview = (f'<div class="grid two"><div class="card"><h2>Next steps</h2>{summary}<ol class="steps">{steps_html}</ol></div>'
                    '<div class="card empty">No scans yet. Run <code>jeep-obd scan</code> with the ignition on.</div></div>')

    log_note = f"Latest drive log: {E(log_path.name)}" if log_path else \
        "No drive log yet. Run <code>jeep-obd drive</code> during a drive (Ctrl+C to stop)."
    drive = f'<section class="card"><h2>Drive log</h2><p class="sub">{log_note}</p><div class="grid two" id="logcharts"></div></section>'

    data = {
        "history": {"labels": [x.get("timestamp", "")[:16].replace("T", " ") for x in scans],
                    "codes": [len(scan_codes(x)) for x in scans]},
        "log": log or {},
        "trans": ({"series": ta["series"], "gear_time": ta["gear_time"]} if ta and ta.get("ok") else None),
    }
    body = f"""
<header><div><h1>{E(title or vehicle_title(s.get('vin')))}</h1>
<div class="sub">VIN {E(str(s.get('vin') or 'n/a'))} · Last scan {E(s.get('timestamp', 'none'))} · {len(scans)} scan(s) · read-only</div></div>
<span class="pill {worst if s else 'warn'}">{label}</span></header>
<nav><button data-tab="overview">Overview</button><button data-tab="trans">Transmission</button>
<button data-tab="drive">Drive log</button><button data-tab="codes">Codes</button></nav>
<div class="panel" id="tab-overview">{overview}</div>
<div class="panel" id="tab-trans">{trans_tab(s, codes, ta, log_path.name if log_path else None)}</div>
<div class="panel" id="tab-drive">{drive}</div>
<div class="panel" id="tab-codes">{glossary_tab(scans)}</div>
<div id="tip"></div>"""
    out.write_text(page(body, json.dumps(data).replace("</", "<\\/")), encoding="utf-8")
    return out


JS = r"""
// ---- tabs (hash-driven so code links can jump into the glossary) ----
const tabs=[...document.querySelectorAll('nav button')];
function show(name){tabs.forEach(b=>b.classList.toggle('on',b.dataset.tab===name));
 document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on',p.id==='tab-'+name));
 try{localStorage.setItem('jeepTab',name)}catch(e){}}
function route(){const h=location.hash.slice(1);
 if(h.startsWith('code-')){show('codes');const el=document.getElementById(h);
  if(el){el.scrollIntoView({block:'center'});el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash');}
  else{const q=document.getElementById('gsearch');q.value=h.slice(5);filter();}return;}
 if(h.startsWith('tab-')){show(h.slice(4));return;}
 let t='overview';try{t=localStorage.getItem('jeepTab')||t}catch(e){}show(t);}
tabs.forEach(b=>b.onclick=()=>{history.replaceState(null,'','#tab-'+b.dataset.tab);show(b.dataset.tab)});
window.addEventListener('hashchange',route);
// ---- tooltips ----
const tip=document.getElementById('tip');
function place(a){const r=a.getBoundingClientRect();tip.style.display='block';
 let x=Math.min(r.left,innerWidth-tip.offsetWidth-12),y=r.bottom+8;
 if(y+tip.offsetHeight>innerHeight-8)y=r.top-tip.offsetHeight-8;
 tip.style.left=Math.max(8,x)+'px';tip.style.top=y+'px';}
function on(e){const a=e.target.closest&&e.target.closest('a.code');if(!a)return;
 tip.textContent=a.dataset.tip;const i=document.createElement('i');i.textContent='  Click for the glossary entry.';
 tip.appendChild(document.createElement('br'));tip.appendChild(i);place(a);}
function off(e){if(e.target.closest&&e.target.closest('a.code'))tip.style.display='none';}
document.addEventListener('mouseover',on);document.addEventListener('focusin',on);
document.addEventListener('mouseout',off);document.addEventListener('focusout',off);
document.addEventListener('click',e=>{if(e.target.closest('a.code'))tip.style.display='none'});
// ---- glossary search ----
const rows=[...document.querySelectorAll('#tab-codes tr.g, #tab-codes .gcard')];
function filter(){const q=(document.getElementById('gsearch').value||'').toLowerCase().trim();
 rows.forEach(r=>r.style.display=!q||r.textContent.toLowerCase().includes(q)?'':'none');}
document.getElementById('gsearch').addEventListener('input',filter);
route();
// ---- charts ----
if(window.Chart){
 const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
 Chart.defaults.color=css('--mut');Chart.defaults.borderColor=css('--line');
 const pal=['#2b6cb0','#c05621','#2f855a','#9b2c2c','#6b46c1','#b7791f'];
 const H=document.getElementById('hist');
 if(H)new Chart(H,{type:'bar',data:{labels:D.history.labels,datasets:[{label:'Codes found',data:D.history.codes,backgroundColor:css('--fail')}]},
  options:{maintainAspectRatio:false,scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
 if(D.trans){const S=D.trans.series;
  new Chart(document.getElementById('gearline'),{type:'line',data:{labels:S.t.map(x=>Math.round(x)+'s'),datasets:[
   {label:'Est. gear',data:S.gear,stepped:true,borderColor:pal[0],borderWidth:2,pointRadius:0,yAxisID:'y'},
   {label:'Speed (mph)',data:S.mph,borderColor:pal[1],borderWidth:1.2,pointRadius:0,yAxisID:'y2'},
   {label:'Symptom mark',data:S.mark.map(m=>m?8.6:null),showLine:false,pointRadius:6,pointBackgroundColor:css('--fail'),borderColor:css('--fail'),yAxisID:'y'}]},
   options:{maintainAspectRatio:false,spanGaps:false,interaction:{mode:'index',intersect:false},
    scales:{x:{ticks:{maxTicksLimit:10}},y:{min:0,max:9,ticks:{stepSize:1},title:{display:true,text:'gear'}},
     y2:{position:'right',grid:{display:false},title:{display:true,text:'mph'}}}}});
  const g=D.trans.gear_time;
  new Chart(document.getElementById('geartime'),{type:'bar',data:{labels:Object.keys(g).map(k=>'Gear '+k),
   datasets:[{label:'Seconds',data:Object.values(g),backgroundColor:Object.keys(g).map(k=>k>=6?css('--ok'):pal[0])}]},
   options:{maintainAspectRatio:false,plugins:{legend:{display:false}}}});}
 const L=D.log,t=L.t||[];
 const groups=[['RPM & speed (mph)',['RPM','SPEED']],['Temperatures (°F)',['COOLANT_TEMP','OIL_TEMP','INTAKE_TEMP']],
  ['Fuel trims (%)',['SHORT_FUEL_TRIM_1','LONG_FUEL_TRIM_1','SHORT_FUEL_TRIM_2','LONG_FUEL_TRIM_2']],
  ['Pedal, throttle & load (%)',['ACCELERATOR_POS_D','THROTTLE_POS','ENGINE_LOAD']],
  ['Module voltage (V)',['CONTROL_MODULE_VOLTAGE']],['Airflow (g/s)',['MAF']],['Timing advance (°)',['TIMING_ADVANCE']]];
 const box=document.getElementById('logcharts');
 for(const [name,keys] of groups){const ks=keys.filter(k=>L[k]&&L[k].some(v=>v!==null));if(!ks.length)continue;
  const c=document.createElement('div');c.innerHTML='<h2>'+name+'</h2><div class="chart"><canvas></canvas></div>';box.appendChild(c);
  new Chart(c.querySelector('canvas'),{type:'line',data:{labels:t.map(x=>Math.round(x)+'s'),
   datasets:ks.map((k,i)=>({label:k,data:L[k],borderColor:pal[i],pointRadius:0,borderWidth:1.5,tension:.2,spanGaps:true,
   yAxisID:(k==='SPEED')?'y2':'y'}))},
   options:{maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
   scales:{x:{ticks:{maxTicksLimit:8}},y2:{display:ks.includes('SPEED'),position:'right',grid:{display:false}}}}});}
}
"""


def page(body: str, data_json: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jeep Health Dashboard</title><style>{CSS}</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
</head><body><div class="wrap">{body}</div>
<script>const D={data_json};{JS}</script></body></html>"""

