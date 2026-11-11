"""Transmission behaviour analysis from a drive-log CSV (stdlib only).

Infers the gear from the RPM/speed ratio (the 8-speed's ratios are fixed;
the axle x tire constant K is fitted from the data), then looks for:
not upshifting at cruise, holding a gear while RPM climbs, RPM flares
(slip), RPM that matches no gear under load, and weak/limited power at
wide-open throttle. Gear numbers are ESTIMATES; the TCM's own data is
authoritative.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

GEARS = [4.71, 3.14, 2.10, 1.67, 1.29, 1.00, 0.84, 0.67]  # ZF 8HP45 / 845RE / 8HP70
LOG_GEARS = [math.log(g) for g in GEARS]
KMH_TO_MPH = 0.621371
K_RANGE = (30.0, 45.0)  # WK2 axle 3.09-3.70 x ~640-690 tire revs/mile / 60
K_PRIOR = 38.0          # 3.45 axle, ~661 revs/mile
MATCH_TOL = 0.05        # max |ln(ratio) - ln(K*gear)| to call a gear


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_rows(path) -> list[dict]:
    with Path(path).open(newline="") as f:
        return [{k: _f(v) for k, v in r.items()} for r in csv.DictReader(f)]


def fit_k(log_ratios: list[float]) -> float:
    best_cost, best_k = None, K_PRIOR
    steps = int((K_RANGE[1] - K_RANGE[0]) / 0.05) + 1
    for i in range(steps):
        k = K_RANGE[0] + i * 0.05
        lk = math.log(k)
        cost = sum(min(min(abs(lr - lk - lg) for lg in LOG_GEARS), 0.08) for lr in log_ratios)
        cost += len(log_ratios) * 0.01 * abs(math.log(k / K_PRIOR))
        if best_cost is None or cost < best_cost:
            best_cost, best_k = cost, k
    return best_k


def _segments(s, pred, max_gap=1.5):
    """Yield (start_idx, end_idx) runs where pred holds, bridging gaps <= max_gap s."""
    start = last = None
    for i, x in enumerate(s):
        if pred(x):
            if start is None or x["t"] - s[last]["t"] > max_gap:
                if start is not None:
                    yield start, last
                start = i
            last = i
    if start is not None:
        yield start, last


def analyze(rows: list[dict]) -> dict:
    s = []
    for r in rows:
        t, rpm, spd = r.get("t"), r.get("RPM"), r.get("SPEED")
        if t is None or rpm is None or spd is None:
            continue
        thr = r.get("ACCELERATOR_POS_D")
        if thr is None:
            thr = r.get("THROTTLE_POS")
        s.append({"t": t, "rpm": rpm, "mph": spd * KMH_TO_MPH, "thr": thr,
                  "load": r.get("ENGINE_LOAD"), "timing": r.get("TIMING_ADVANCE"),
                  "mark": bool(r.get("mark"))})
    if len(s) < 40:
        return {"ok": False, "reason": f"only {len(s)} usable samples (need 40+ with RPM and speed)"}

    # pedal normalised to 0-100 (the raw pedal sensor never reads 0 or 100)
    tv = [x["thr"] for x in s if x["thr"] is not None]
    lo, hi = (min(tv), max(tv)) if tv else (0, 100)
    if hi - lo < 30:
        hi = 100
    for x in s:
        x["pedal"] = None if x["thr"] is None else max(0.0, min(100.0, (x["thr"] - lo) / (hi - lo) * 100))
        x["ratio"] = x["rpm"] / x["mph"] if x["mph"] >= 12 and x["rpm"] > 500 else None

    steady = []
    for i in range(1, len(s) - 1):
        a, b, c = s[i - 1]["ratio"], s[i]["ratio"], s[i + 1]["ratio"]
        if a and b and c and abs(a - b) / b < 0.03 and abs(c - b) / b < 0.03:
            steady.append(math.log(b))
    k = fit_k(steady[::max(1, len(steady) // 1500)]) if len(steady) >= 10 else K_PRIOR
    lk = math.log(k)
    for x in s:
        x["gear"] = None
        if x["ratio"]:
            err, g = min((abs(math.log(x["ratio"]) - lk - lg), n + 1) for n, lg in enumerate(LOG_GEARS))
            if err < MATCH_TOL:
                x["gear"] = g

    dt = [min(max(s[i + 1]["t"] - s[i]["t"], 0), 2.0) for i in range(len(s) - 1)] + [0]
    gear_time = {g: 0.0 for g in range(1, 9)}
    for x, d in zip(s, dt):
        if x["gear"]:
            gear_time[x["gear"]] += d
    max_gear = max((x["gear"] for x in s if x["gear"]), default=None)
    max_mph = max(x["mph"] for x in s)
    findings, held, flares, wot = [], [], [], []

    def add(level, title, detail, action=""):
        findings.append({"level": level, "title": title, "detail": detail, "action": action})

    # 1. cruise: light pedal at 50+ mph should be 7th/8th
    cruise = [(x, d) for x, d in zip(s, dt) if x["mph"] >= 50 and x["gear"]
              and x["pedal"] is not None and x["pedal"] < 35]
    ct = sum(d for _, d in cruise)
    low_t = sum(d for x, d in cruise if x["gear"] <= 5)
    # any sustained low-gear cruise is abnormal; a share threshold would hide it behind normal cruising
    if low_t >= 10:
        low_g = sorted({x["gear"] for x, _ in cruise if x["gear"] <= 5})
        add("fail", f"Cruised {low_t:.0f}s at 50+ mph in gear {', '.join(map(str, low_g))} at light throttle",
            "A healthy 8-speed cruises in 7th/8th at these speeds. Holding a low gear is the signature of "
            "transmission limp mode or a shift-control fault.",
            "Read the TCM codes (Transmission tab); if a code is stored, that's the lead. Check fluid level/condition at a shop.")
    elif ct >= 20:
        add("ok", f"Cruise gearing normal ({ct - low_t:.0f}s of 50+ mph cruise in gear 6-8)", "Upshifts reached at highway speed.")
    if max_gear and max_mph >= 50 and max_gear <= 5:
        add("fail", f"Highest gear reached: {max_gear} (top speed {max_mph:.0f} mph)",
            "The transmission never used 6th-8th despite highway speed.", "Classic limp-mode pattern; see TCM codes.")

    # 2. held gear while RPM climbs at part throttle
    for g in range(1, 7):
        for a, b in _segments(s, lambda x, g=g: x["gear"] == g):
            seg = s[a:b + 1]
            rise = seg[-1]["mph"] - seg[0]["mph"]
            peak = max(x["rpm"] for x in seg)
            ped = sorted(x["pedal"] for x in seg if x["pedal"] is not None)
            med = ped[len(ped) // 2] if ped else None
            if rise >= 15 and peak >= 3800 and med is not None and med < 60:
                held.append({"gear": g, "t0": seg[0]["t"], "t1": seg[-1]["t"], "mph0": round(seg[0]["mph"]),
                             "mph1": round(seg[-1]["mph"]), "rpm_peak": round(peak), "pedal_median": round(med)})
    for h in held:
        add("fail", f"Held gear {h['gear']} from {h['mph0']} to {h['mph1']} mph (RPM up to {h['rpm_peak']})",
            f"At only ~{h['pedal_median']}% pedal the transmission should have upshifted well before this RPM "
            f"(t={h['t0']:.0f}-{h['t1']:.0f}s).", "Matches your 'won't shift at higher gears' symptom.")

    # 3. flares: RPM jumps, speed doesn't, and it isn't a clean downshift
    i = 0
    while i < len(s):
        x = s[i]
        if x["mph"] >= 15 and x["gear"]:
            for j in range(i + 1, len(s)):
                y = s[j]
                if y["t"] - x["t"] > 1.5:
                    break
                if y["rpm"] - x["rpm"] >= 400 and y["mph"] - x["mph"] <= 1.0 and \
                        (x["pedal"] is None or y["pedal"] is None or y["pedal"] >= x["pedal"] - 5):
                    after = next((z["gear"] for z in s[j:] if z["gear"] and z["t"] - y["t"] >= 0.5), None)
                    if after is None or after >= x["gear"]:
                        flares.append({"t": x["t"], "mph": round(x["mph"]), "rpm_from": round(x["rpm"]),
                                       "rpm_to": round(y["rpm"]), "gear_before": x["gear"], "gear_after": after})
                        i = j
                    break
        i += 1
    if flares:
        add("fail" if len(flares) >= 3 else "warn", f"{len(flares)} RPM flare(s) without acceleration",
            "Engine RPM jumped 400+ while road speed didn't change and no lower gear engaged: slipping clutch "
            "or torque converter, often from low/degraded fluid or a pressure fault.",
            "Have fluid level and condition checked (the 8-speed needs a shop procedure); read TCM codes.")

    # 4. ratio matches no gear under load
    load_s = [x for x in s if x["mph"] >= 40 and x["ratio"] and x["pedal"] is not None and x["pedal"] >= 30]
    if len(load_s) >= 20:
        um = sum(1 for x in load_s if not x["gear"]) / len(load_s)
        if um > 0.25:
            add("warn", f"RPM matches no gear {um:.0%} of the time under load at 40+ mph",
                "Either slip or the torque converter clutch unlocking under load.", "Compare with TCM codes (P0741-family).")

    # 5. wide-open-throttle pulls
    for a, b in _segments(s, lambda x: x["pedal"] is not None and x["pedal"] >= 70 and x["mph"] >= 15, 1.0):
        seg = s[a:b + 1]
        dur = seg[-1]["t"] - seg[0]["t"]
        if dur < 2:
            continue
        loads = [x["load"] for x in seg if x["load"] is not None]
        tims = [x["timing"] for x in seg if x["timing"] is not None]
        wot.append({"t": seg[0]["t"], "secs": round(dur, 1), "mph0": round(seg[0]["mph"]), "mph1": round(seg[-1]["mph"]),
                    "accel": round((seg[-1]["mph"] - seg[0]["mph"]) / dur, 2), "rpm_peak": round(max(x["rpm"] for x in seg)),
                    "load_avg": round(sum(loads) / len(loads)) if loads else None,
                    "timing_min": min(tims) if tims else None})
    for w in wot:
        if w["load_avg"] is not None and w["load_avg"] < 70:
            add("warn", f"Low engine load at full throttle ({w['load_avg']}% at t={w['t']:.0f}s)",
                "Near-full pedal should give 85-100% calculated load. Low load points to the engine being limited "
                "(throttle-control reduced-power mode, restricted intake/exhaust e.g. clogged cat, MAF).",
                "Engine-side power loss is likely part of the problem, not only the transmission.")
        if w["timing_min"] is not None and w["timing_min"] < 0:
            add("warn", f"Ignition timing pulled to {w['timing_min']}° under full throttle",
                "Knock retard reduces power.", "Check fuel quality/octane, carbon, knock sensors.")
    if not wot:
        add("info", "No full-throttle pull in this log",
            "Power-loss checks need one firm acceleration (pedal 70%+ for 3+ s) on a safe on-ramp.")

    marks = [{"t": x["t"], "mph": round(x["mph"]), "rpm": round(x["rpm"]), "gear": x["gear"],
              "pedal": None if x["pedal"] is None else round(x["pedal"])} for x in s if x["mark"]]

    step = max(1, len(s) // 1500)
    ser = s[::step]
    return {"ok": True, "k": round(k, 2), "implied_axle": round(k * 60 / 661, 2), "samples": len(s),
            "duration": round(s[-1]["t"] - s[0]["t"]), "max_gear": max_gear, "max_mph": round(max_mph),
            "gear_time": {g: round(v, 1) for g, v in gear_time.items()},
            "findings": findings, "held": held, "flares": flares, "wot": wot, "marks": marks,
            "series": {"t": [round(x["t"], 1) for x in ser], "gear": [x["gear"] for x in ser],
                       "mph": [round(x["mph"], 1) for x in ser], "rpm": [round(x["rpm"]) for x in ser],
                       "mark": [x["mark"] for x in ser]}}
