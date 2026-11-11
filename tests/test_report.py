"""Dashboard output: every code must link to a glossary anchor that exists, and the
health verdict must differ between a faulty and a healthy vehicle."""
import re

from jeep_obd import demo, report


def build(tmp_path, symptom):
    folder = demo.write_demo(tmp_path / ("bad" if symptom else "good"), symptom=symptom)
    return report.build(folder / "scans", folder / "dashboard.html", folder / "notes.json").read_text(encoding="utf-8")


def test_every_code_link_has_a_glossary_anchor(tmp_path):
    html = build(tmp_path, symptom=True)
    links = set(re.findall(r'class="code" href="#code-([A-Z0-9]+)"', html))
    anchors = set(re.findall(r'id="code-([A-Z0-9]+)"', html))
    assert {"P0700", "P0730", "P0868"} <= links
    assert links <= anchors, f"links without glossary entry: {links - anchors}"


def test_tooltip_carries_plain_english_explanation(tmp_path):
    html = build(tmp_path, symptom=True)
    tip = re.search(r'href="#code-P0730" data-tip="([^"]+)"', html).group(1)
    assert "Incorrect Gear Ratio" in tip and "slipping" in tip


def test_verdict_differs_between_faulty_and_healthy(tmp_path):
    assert "Problems found" in build(tmp_path, symptom=True)
    good = build(tmp_path, symptom=False)
    assert "Problems found" not in good and "Healthy" in good


def test_manufacturer_code_is_marked_unknown_not_invented():
    from jeep_obd import glossary
    d = glossary.lookup("P1D72", {})
    assert d["source"] == "unknown" and "manufacturer-specific" in d["title"]


def test_vehicle_title_from_vin():
    assert report.vehicle_title("1C4RJFAG5FC000000") == "2015 Jeep Grand Cherokee"
    assert report.vehicle_title(None) == "Vehicle health"
