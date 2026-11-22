from app.pipeline import calculate


def test_normal_release(clean):
    assert clean["dispatch"]["state"] == "ready"
    assert len(clean["dispatch"]["receipts"]) == 11


def test_dirty_hold(dirty):
    assert {row["state"] for row in dirty["dispatch"]["receipts"]} == {"held"}


def test_no_zero_receipt(clean_data):
    clean_data["rights"][0].update(minimum="0", ceiling="0")
    assert "001" not in {r["outlet"] for r in calculate(clean_data)["dispatch"]["receipts"]}


def test_receipt_provenance(clean):
    assert clean["dispatch"]["receipts"][0]["receipt"] == "LG-1120-01/001"
    assert [s["table"] for s in clean["dispatch"]["receipts"][0]["sources"]] == ["rights","channels"]


def test_receipt_total(clean):
    assert clean["dispatch"]["receipt_l"] == 16700


def test_no_receipt_when_source_closed(clean_data):
    clean_data["gates"][0]["state"] = "closed"
    assert calculate(clean_data)["dispatch"]["receipts"] == []
