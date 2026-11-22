from app.pipeline import calculate


def test_mixed_channel_unit(dirty):
    """TRAP-15：脏样例总渠立方米与支渠整升并用。"""
    assert next(r for r in dirty["channels"]["channels"] if r["channel"] == "东支渠")["loss_l"] == 300


def test_cycle_rejected(dirty):
    """TRAP-20：脏样例离线渠道环路。"""
    assert {item["sources"][0]["raw"]["channel"] for item in dirty["channels"]["issues"] if item["code"] == "CHANNEL_DISCONNECTED"} == {"废旧渠", "左叉"}


def test_downstream_blocked(dirty):
    assert "苗圃渠" not in {r["channel"] for r in dirty["channels"]["channels"]}
    assert any(i["code"] == "UPSTREAM_BLOCKED" and i["sources"][0]["raw"]["channel"] == "苗圃渠" for i in dirty["channels"]["issues"])


def test_head_residual(clean):
    assert clean["channels"]["channels"][0]["usable_l"] == 2650


def test_oversubscribed_channel(clean_data):
    clean_data["channels"][1]["inflow"] = "19"
    section = calculate(clean_data)["channels"]
    assert section["channels"][0]["held_l"] == 18600
    assert section["issues"][0]["code"] == "CHILD_FLOW_EXCESS"


def test_wrong_head_reading(clean_data):
    clean_data["channels"][0]["inflow"] = "19"
    section = calculate(clean_data)["channels"]
    assert (section["held_at_head_l"], section["issues"][0]["code"]) == (19750, "ROOT_MISMATCH")
