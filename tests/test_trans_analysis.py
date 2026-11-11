"""Transmission analysis must flag the 'won't upshift, loses power' pattern AND stay
quiet on a healthy drive. The healthy control is what makes the fault test meaningful:
an analyzer that flags everything would pass the fault test alone."""
from jeep_obd import demo, trans_analysis


def run(tmp_path, symptom):
    p = demo.write_drive(tmp_path / "log.csv", symptom)
    return trans_analysis.analyze(trans_analysis.load_rows(p))


def levels(r):
    return {f["level"] for f in r["findings"]}


def test_healthy_drive_reaches_8th_and_has_no_failures(tmp_path):
    r = run(tmp_path, symptom=False)
    assert r["ok"] and r["max_gear"] == 8
    assert "fail" not in levels(r), r["findings"]
    assert r["flares"] == [] and r["held"] == []


def test_faulty_drive_flags_held_gear_low_gear_cruise_and_flare(tmp_path):
    r = run(tmp_path, symptom=True)
    titles = " | ".join(f["title"] for f in r["findings"])
    assert any(h["gear"] == 4 and h["rpm_peak"] >= 4000 for h in r["held"]), titles
    assert "Cruised" in titles and "gear 4" in titles
    assert len(r["flares"]) == 1
    assert "Low engine load at full throttle" in titles


def test_symptom_marks_are_located_in_the_stuck_gear(tmp_path):
    r = run(tmp_path, symptom=True)
    assert len(r["marks"]) == 3
    assert all(m["gear"] == 4 for m in r["marks"])


def test_axle_constant_is_recovered(tmp_path):
    """Gear labels depend on fitting the axle x tire constant; demo data uses 38."""
    assert abs(run(tmp_path, symptom=True)["k"] - 38.0) < 0.5


def test_too_little_data_is_reported_not_guessed():
    r = trans_analysis.analyze([{"t": 0.0, "RPM": 800.0, "SPEED": 0.0}])
    assert r["ok"] is False and "samples" in r["reason"]
