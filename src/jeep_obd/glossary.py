"""Plain-English trouble-code notes for the dashboard glossary (stdlib only).

CURATED: hand-written explanations for codes relevant to this Jeep's symptoms.
Titles are the standard SAE J2012 definitions; 'plain' and 'check' are
general guidance, not a diagnosis. Everything else falls back to the
generic SAE table that ships with python-OBD.
"""
from __future__ import annotations

import re

CODE_RE = re.compile(r"\b([PCBU][0-3][0-9A-F]{3})(?:-([0-9A-F]{2}))?\b")

_T = "Transmission"
CURATED: dict[str, dict] = {
    "P0700": {"sys": _T, "title": "Transmission Control System (MIL Request)",
              "plain": "The transmission computer (TCM) has a fault stored and asked the engine computer to turn on the check engine light. P0700 itself says nothing about what's wrong.",
              "check": "Read the TCM's own codes. This scanner does that automatically (Transmission tab)."},
    "P0705": {"sys": _T, "title": "Transmission Range Sensor Circuit Malfunction (PRNDL Input)",
              "plain": "The TCM isn't sure which gear position the shifter is in.",
              "check": "Shifter/range sensor wiring and connector; can cause no-shift or limp mode."},
    "P0711": {"sys": _T, "title": "Transmission Fluid Temperature Sensor A Circuit Range/Performance",
              "plain": "The transmission temperature reading doesn't make sense (e.g. not warming up as expected).",
              "check": "Sensor/wiring; fluid condition."},
    "P0712": {"sys": _T, "title": "Transmission Fluid Temperature Sensor A Circuit Low", "plain": "Temperature sensor signal too low (usually a short).", "check": "Sensor wiring."},
    "P0713": {"sys": _T, "title": "Transmission Fluid Temperature Sensor A Circuit High", "plain": "Temperature sensor signal too high (usually an open circuit).", "check": "Sensor wiring/connector."},
    "P0715": {"sys": _T, "title": "Input/Turbine Speed Sensor A Circuit",
              "plain": "The TCM lost or distrusts the signal measuring how fast the transmission's input is spinning. Without it the TCM can't judge shifts and often goes into limp mode.",
              "check": "Speed sensor and wiring; inside the transmission on this unit (shop job)."},
    "P0720": {"sys": _T, "title": "Output Speed Sensor Circuit",
              "plain": "The signal for transmission output speed is missing or wrong. Leads to erratic or no shifting.",
              "check": "Output speed sensor and wiring."},
    "P0729": {"sys": _T, "title": "Gear 6 Incorrect Ratio", "plain": "In 6th gear, input vs output speed didn't match 6th's ratio: something slipped.", "check": "Fluid level/condition, clutch wear, TCM software update."},
    "P0730": {"sys": _T, "title": "Incorrect Gear Ratio",
              "plain": "The TCM measured input vs output speed and it didn't match the gear it commanded, i.e. slipping. Often triggers limp mode (stuck in one gear, weak acceleration).",
              "check": "Fluid level and condition first (the 8-speed has no dipstick, so this is a shop check), then TCM software update, then internal clutch/solenoid diagnosis."},
    "P0731": {"sys": _T, "title": "Gear 1 Incorrect Ratio", "plain": "Slip detected in 1st gear.", "check": "Fluid level/condition, then internal diagnosis."},
    "P0732": {"sys": _T, "title": "Gear 2 Incorrect Ratio", "plain": "Slip detected in 2nd gear.", "check": "Fluid level/condition, then internal diagnosis."},
    "P0733": {"sys": _T, "title": "Gear 3 Incorrect Ratio", "plain": "Slip detected in 3rd gear.", "check": "Fluid level/condition, then internal diagnosis."},
    "P0734": {"sys": _T, "title": "Gear 4 Incorrect Ratio", "plain": "Slip detected in 4th gear.", "check": "Fluid level/condition, then internal diagnosis."},
    "P0735": {"sys": _T, "title": "Gear 5 Incorrect Ratio", "plain": "Slip detected in 5th gear.", "check": "Fluid level/condition, then internal diagnosis."},
    "P0736": {"sys": _T, "title": "Reverse Incorrect Ratio", "plain": "Slip detected in reverse.", "check": "Fluid level/condition, then internal diagnosis."},
    "P0740": {"sys": _T, "title": "Torque Converter Clutch Circuit Malfunction", "plain": "Electrical fault in the circuit that locks the torque converter at cruise.", "check": "Solenoid/wiring; hurts fuel economy and can cause shudder."},
    "P0741": {"sys": _T, "title": "Torque Converter Clutch Circuit Performance or Stuck Off",
              "plain": "The torque converter clutch was told to lock but RPM shows it slipping. Feels like RPM sitting a bit high at cruise or a shudder.",
              "check": "Fluid condition, TCM software, converter clutch."},
    "P0742": {"sys": _T, "title": "Torque Converter Clutch Circuit Stuck On", "plain": "Converter stays locked when it shouldn't; can stall or buck at stops.", "check": "Solenoid/valve body."},
    "P0750": {"sys": _T, "title": "Shift Solenoid A Malfunction", "plain": "A solenoid that controls a clutch for shifting has an electrical fault.", "check": "Solenoid/valve body wiring; often causes limp mode."},
    "P0755": {"sys": _T, "title": "Shift Solenoid B Malfunction", "plain": "Shift solenoid B electrical fault.", "check": "Solenoid/valve body wiring."},
    "P0760": {"sys": _T, "title": "Shift Solenoid C Malfunction", "plain": "Shift solenoid C electrical fault.", "check": "Solenoid/valve body wiring."},
    "P0765": {"sys": _T, "title": "Shift Solenoid D Malfunction", "plain": "Shift solenoid D electrical fault.", "check": "Solenoid/valve body wiring."},
    "P0770": {"sys": _T, "title": "Shift Solenoid E Malfunction", "plain": "Shift solenoid E electrical fault.", "check": "Solenoid/valve body wiring."},
    "P0868": {"sys": _T, "title": "Transmission Fluid Pressure Low",
              "plain": "Hydraulic pressure is below what the TCM expects. Low pressure means clutches slip, which feels like flare, no-shift and lost power.",
              "check": "Fluid level first (low fluid from a leak is the most common cause), then pump/filter."},
    "P0869": {"sys": _T, "title": "Transmission Fluid Pressure High", "plain": "Pressure higher than expected; harsh shifts.", "check": "Pressure control solenoid/valve body."},
    "P0218": {"sys": _T, "title": "Transmission Fluid Over Temperature Condition",
              "plain": "The transmission got too hot. The TCM may change shifting to protect itself.",
              "check": "Fluid level/condition, cooler lines, towing load."},
    "P0841": {"sys": _T, "title": "Transmission Fluid Pressure Sensor/Switch A Circuit Range/Performance", "plain": "Pressure sensor reading doesn't make sense.", "check": "Sensor/wiring; fluid level."},
    "P0500": {"sys": "Speed", "title": "Vehicle Speed Sensor A Malfunction", "plain": "Vehicle speed signal missing or wrong. Shifting depends on it.", "check": "Wheel speed sensors / ABS module."},
    "P0171": {"sys": "Engine", "title": "System Too Lean (Bank 1)", "plain": "The engine is getting more air than fuel on one side and the computer is adding fuel to compensate.", "check": "Vacuum leaks (intake, PCV), MAF sensor, fuel pressure."},
    "P0174": {"sys": "Engine", "title": "System Too Lean (Bank 2)", "plain": "Same as P0171 on the other cylinder bank. Lean on both banks points to something shared (MAF, fuel pressure, big vacuum leak).", "check": "Vacuum leaks, MAF sensor, fuel pressure."},
    "P0172": {"sys": "Engine", "title": "System Too Rich (Bank 1)", "plain": "Too much fuel; the computer is removing fuel.", "check": "MAF, leaking injector, fuel pressure regulator."},
    "P0175": {"sys": "Engine", "title": "System Too Rich (Bank 2)", "plain": "Same as P0172 on bank 2.", "check": "MAF, injectors, fuel pressure."},
    "P0300": {"sys": "Engine", "title": "Random/Multiple Cylinder Misfire Detected", "plain": "Misfires across several cylinders. Felt as stumbling and power loss.", "check": "Plugs, coils, vacuum leak, fuel delivery."},
    **{f"P030{n}": {"sys": "Engine", "title": f"Cylinder {n} Misfire Detected", "plain": f"Cylinder {n} isn't firing properly: rough running and power loss.", "check": "Swap that cylinder's coil/plug with a neighbor and see if the misfire follows."} for n in range(1, 9)},
    "P0420": {"sys": "Engine", "title": "Catalyst System Efficiency Below Threshold (Bank 1)", "plain": "The catalytic converter isn't cleaning exhaust well. A badly clogged cat can also choke power at higher speed.", "check": "Upstream causes first (misfire/rich), then cat condition/back-pressure."},
    "P0430": {"sys": "Engine", "title": "Catalyst System Efficiency Below Threshold (Bank 2)", "plain": "Same as P0420 on bank 2.", "check": "See P0420."},
    "P0101": {"sys": "Engine", "title": "Mass Air Flow Circuit Range/Performance", "plain": "The airflow sensor's reading doesn't make sense versus other sensors. A bad MAF causes hesitation and low power.", "check": "Clean/replace MAF; check for air leaks after it."},
    "P0121": {"sys": "Engine", "title": "Throttle Position Sensor A Circuit Range/Performance", "plain": "Throttle position signals disagree. Can trigger reduced-power mode.", "check": "Throttle body sensor/wiring."},
    "P2101": {"sys": "Engine", "title": "Throttle Actuator Control Motor Circuit Range/Performance", "plain": "The electronic throttle motor isn't doing what it's told. The engine often limits power ('limp home').", "check": "Throttle body (clean or replace), connector."},
    "P0016": {"sys": "Engine", "title": "Crankshaft/Camshaft Position Correlation (Bank 1 Sensor A)", "plain": "Cam and crank timing don't line up as expected.", "check": "Oil level/condition, cam phaser/solenoid, timing chain."},
    "P0128": {"sys": "Engine", "title": "Coolant Thermostat Below Regulating Temperature", "plain": "Engine warms up too slowly, usually a thermostat stuck open.", "check": "Thermostat."},
    "P0455": {"sys": "Emissions", "title": "EVAP System Large Leak Detected", "plain": "Fuel vapor system leak. Often a loose gas cap.", "check": "Gas cap, EVAP hoses/purge valve."},
    "P0456": {"sys": "Emissions", "title": "EVAP System Small Leak Detected", "plain": "Small fuel vapor leak.", "check": "Gas cap seal, EVAP lines (smoke test)."},
    "P0562": {"sys": "Electrical", "title": "System Voltage Low", "plain": "A computer saw low battery/charging voltage. Low voltage can make the TCM shift erratically.", "check": "Battery load test, alternator, ground straps."},
    "P0563": {"sys": "Electrical", "title": "System Voltage High", "plain": "Charging voltage too high.", "check": "Alternator/regulator."},
    "U0100": {"sys": "Network", "title": "Lost Communication With ECM/PCM A", "plain": "A module stopped hearing the engine computer on the vehicle network.", "check": "Battery voltage, CAN wiring/connectors."},
    "U0101": {"sys": "Network", "title": "Lost Communication With TCM", "plain": "A module stopped hearing the transmission computer. The transmission may go to limp mode.", "check": "Battery voltage, TCM power/ground, CAN wiring."},
    "U0121": {"sys": "Network", "title": "Lost Communication With ABS Module", "plain": "Lost contact with the ABS module, which also supplies wheel speeds used for shifting.", "check": "ABS module power/ground, CAN wiring."},
    "U0140": {"sys": "Network", "title": "Lost Communication With Body Control Module", "plain": "Lost contact with the body computer.", "check": "BCM power/ground, CAN wiring."},
}

# SAE J2012 failure-type byte (the "-XX" suffix on UDS codes); common values
FTB = {
    "00": "No sub-type information",
    "01": "General electrical failure",
    "11": "Circuit short to ground",
    "12": "Circuit short to battery",
    "13": "Circuit open",
    "16": "Circuit voltage below threshold",
    "17": "Circuit voltage above threshold",
    "1C": "Circuit voltage out of range",
    "29": "Signal invalid",
    "31": "No signal",
    "62": "Signal compare failure",
    "64": "Signal plausibility failure",
    "77": "Commanded position not reachable",
    "87": "Missing message",
    "92": "Performance or incorrect operation",
    "96": "Component internal failure",
    "98": "Component or system over temperature",
}

STATUS_FLAGS = {
    "testFailed": "Failing right now (on the most recent test).",
    "pending": "Failed during the current or last drive cycle; not yet confirmed.",
    "confirmed": "Stored/confirmed fault (failed enough times to be latched).",
    "warningLamp": "This fault is requesting a warning light.",
}

SOURCES = {"generic": "SAE J2012 generic definition (python-OBD table)",
           "curated": "Plain-English notes: general guidance, not a diagnosis"}


def load_generic() -> dict:
    """Generic SAE definitions from the installed python-OBD package (not bundled here)."""
    try:
        from obd.codes import DTC
        return {k: v for k, v in sorted(DTC.items()) if isinstance(k, str) and v}
    except Exception as e:  # loud: the glossary still works with curated notes only
        print(f"WARNING: generic code table unavailable ({e}); glossary will show curated codes only")
        return {}


def lookup(code: str, generic: dict) -> dict:
    c = CURATED.get(code)
    if c:
        return {"code": code, "title": c["title"], "plain": c["plain"], "check": c.get("check", ""),
                "sys": c.get("sys", ""), "source": "curated"}
    if code in generic:
        return {"code": code, "title": generic[code], "plain": "", "check": "", "sys": "", "source": "generic"}
    kind = {"P": "Powertrain", "C": "Chassis", "B": "Body", "U": "Network"}[code[0]]
    manuf = code[1] in "13"
    return {"code": code, "title": f"{kind} code" + (" (manufacturer-specific)" if manuf else ""),
            "plain": "Not in the generic table. " + ("Chrysler-specific code: look it up with the VIN in a factory service resource or AlfaOBD." if manuf else ""),
            "check": "", "sys": "", "source": "unknown"}


def tip_text(code: str, generic: dict, ftb: str | None = None) -> str:
    d = lookup(code, generic)
    t = f"{code}: {d['title']}."
    if d["plain"]:
        t += f" {d['plain']}"
    if ftb:
        t += f" [-{ftb}: {FTB.get(ftb, 'failure type ' + ftb)}]"
    return t
