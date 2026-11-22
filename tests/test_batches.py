from app.pipeline import calculate


def test_batch_volume(clean):
    assert clean["batches"]["supply_l"] == 19750


def test_unit_normalized(dirty):
    """TRAP-06：脏样例全角千位水量。"""
    assert dirty["batches"]["supply_l"] == 19750


def test_overlap_blocks_gate(dirty):
    """TRAP-19：脏样例两条北斗渠闸令。"""
    assert dirty["batches"]["gates"]["北斗渠"] == "blocked"


def test_utc_start(clean):
    assert clean["batches"]["start"] == "2026-11-20T00:00:00+00:00"


def test_partial_gate(clean_data):
    clean_data["gates"][0]["start"] = "2026-11-20T08:15:00+08:00"
    assert calculate(clean_data)["batches"]["issues"][0]["code"] == "GATE_PARTIAL"


def test_bad_window(clean_data, client):
    clean_data["config"]["end"] = clean_data["config"]["start"]
    response = client.post("/api/runs", json={"data": clean_data})
    assert (response.status_code, response.json()["code"]) == (422, "INVALID_WINDOW")
