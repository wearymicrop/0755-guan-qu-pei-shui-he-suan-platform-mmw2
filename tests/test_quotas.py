from app.pipeline import calculate


def test_weighted_fraction(clean):
    assert clean["quotas"]["quotas"][0]["target_units"] == "50/3"


def test_floor_before_extras(clean):
    row = next(r for r in clean["quotas"]["quotas"] if r["outlet"] == "004")
    assert row["priority"] == 2 and row["target_units"] == "10"


def test_cap_redistribution(clean):
    rows = {r["outlet"]:r["target_units"] for r in clean["quotas"]["quotas"]}
    assert (rows["011"], rows["012"]) == ("30", "20")


def test_without_route(dirty):
    assert {i["sources"][0]["raw"]["outlet"] for i in dirty["quotas"]["issues"]} == {"011", "012", "031", "032", "041", "042"}


def test_minimum_shortage(clean_data):
    clean_data["channels"][3]["inflow"] = "0.37"
    result = calculate(clean_data)["quotas"]
    assert [r["target_units"] for r in result["quotas"] if r["channel"] == "北斗渠"] == ["3/2", "3/2"]
    assert sum(i["code"] == "MINIMUM_SHORTAGE" for i in result["issues"]) == 2


def test_exhausted_caps(clean):
    row = next(r for r in clean["quotas"]["quotas"] if r["outlet"] == "020")
    assert row["target_l"] == "2000"
