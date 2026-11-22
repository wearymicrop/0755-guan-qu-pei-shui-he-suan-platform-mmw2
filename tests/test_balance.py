from app.pipeline import calculate
from app.modules.m6_balance.rules import run as reconcile


def test_clean_balance(clean):
    assert [clean["balance"][k] for k in ("supply_l","loss_l","allocated_l","remaining_l","difference_l")] == [19750,2320,16700,730,0]


def test_dirty_balance(dirty):
    assert [dirty["balance"][k] for k in ("status","loss_l","allocated_l","remaining_l","difference_l")] == ["REVIEW",1450,11000,7300,0]


def test_edges_count_once(clean):
    ledgers = clean["balance"]["ledgers"]
    assert all(r["inflow_l"] == r["loss_l"] + r["child_inflow_l"] + r["allocated_l"] + r["remainder_l"] for r in ledgers)


def test_head_margin(clean):
    assert next(r for r in clean["balance"]["ledgers"] if r["channel"]=="总干渠")["remainder_l"] == 650


def test_isolated_not_lost(dirty):
    assert dirty["balance"]["supply_l"] == dirty["balance"]["loss_l"] + dirty["balance"]["allocated_l"] + dirty["balance"]["remaining_l"]


def test_impossible_ledger(clean):
    clean["tail"]["allocations"][0]["allocated_l"] += 10000
    assert reconcile(None, clean)["status"] == "DIFFERENCE"
