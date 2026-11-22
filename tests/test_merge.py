import copy

import pytest

from app.errors import InputError
from app.pipeline import calculate, validate


def _merge(data):
    return calculate(data)["merge"]


def test_merged_sample_loads(merged):
    section = merged["merge"]
    assert section["change_id"]
    assert len(section["adjudications"]) == 3


def test_carried_right_supersedes_legacy_and_lifts_minimum(merged):
    """confirmed 链接：旧权证注销留证，承接保底就高（900 > 新权证 800/700）。"""
    section = merged["merge"]
    by_outlet = {row["outlet"]: row for row in section["adjudications"]}
    assert by_outlet["011"]["state"] == "carried"
    assert by_outlet["011"]["legacy_minimum_l"] == 900
    assert by_outlet["011"]["carried_minimum_l"] == 900
    assert by_outlet["012"]["carried_minimum_l"] == 900
    codes = {item["code"] for item in section["issues"]}
    assert "MERGE_MIN_LIFTED" in codes
    lifted = next(item for item in section["issues"] if item["code"] == "MERGE_MIN_LIFTED")
    # 证据指回原始权证行：旧线第 10 行、新线第 11 行。
    assert sorted(src["line"] for src in lifted["sources"]) == [10, 11]
    # 合并后配水账只出现一次新渠行，旧渠权证不再扣账。
    rows = [d for d in section["dispatch_ledger"] if d["outlet"] in ("011", "012")]
    assert {row["channel"] for row in rows} == {"西支渠"}
    assert len(rows) == 2


def test_pending_outlet_suspended_with_reserved_minimum(merged):
    """承接关系未确认的 013 挂起，本轮不配水，保底 500 L 挂账留在新渠余量。"""
    section = merged["merge"]
    suspended = next(d for d in section["dispatch_ledger"] if d["outlet"] == "013")
    assert suspended["state"] == "suspended" and suspended["allocated_l"] == 0
    assert suspended["reserved_l"] == 500
    assert any(item["code"] == "MERGE_PENDING" for item in section["issues"])
    assert section["state"] == "held"


def test_superseded_branch_loss_not_charged_after(merged):
    """断开支渠损耗只在迁移前账内，合并后损耗不摊入新账。"""
    section = merged["merge"]
    old = next(c for c in section["channel_reconcile"] if c["channel"] == "西支渠旧线")
    assert old["kind"] == "disconnected"
    assert (old["loss_before_l"], old["loss_after_l"]) == (200, 0)
    assert (old["allocated_after_l"], old["inflow_after_l"]) == (0, 0)
    assert section["superseded_loss_l"] == 200
    head = section["subtotals"][0]
    assert head["loss_before_l"] - head["loss_after_l"] == 200


def test_conservation_level_by_level(merged):
    """渠首供水迁移前后一致，损耗+实配+余水守恒，差额为零。"""
    head = merged["merge"]["subtotals"][0]
    assert head["supply_before_l"] == head["supply_after_l"] == 28600
    assert head["supply_after_l"] == (
        head["loss_after_l"] + head["allocated_after_l"] + head["remaining_after_l"])
    assert merged["merge"]["difference_l"] == 0
    for channel in merged["merge"]["channel_reconcile"]:
        assert channel["inflow_after_l"] == (
            channel["loss_after_l"] + channel["child_inflow_after_l"]
            + channel["allocated_after_l"] + channel["remainder_after_l"])


def test_outlet_reconcile_before_after(merged):
    section = merged["merge"]
    row = next(o for o in section["outlet_reconcile"] if o["outlet"] == "011")
    assert row["allocated_before_l"] < row["allocated_after_l"]
    assert row["state"] == "carried"
    unchanged = next(o for o in section["outlet_reconcile"] if o["outlet"] == "001")
    assert unchanged["state"] == "unchanged"
    assert unchanged["allocated_before_l"] == unchanged["allocated_after_l"]


def test_idempotent_on_duplicate_merge_rows(merged_data):
    """重跑同一合并变更：重复登记行去重，承接权证与水量不重复累加。"""
    baseline = _merge(merged_data)
    doubled = copy.deepcopy(merged_data)
    doubled["merges"].extend(copy.deepcopy(merged_data["merges"]))
    again = _merge(doubled)
    assert any(item["code"] == "MERGE_DUPLICATE" for item in again["issues"])
    assert len(again["adjudications"]) == len(baseline["adjudications"])
    assert again["dispatch_ledger"] == baseline["dispatch_ledger"]
    assert again["change_id"] == baseline["change_id"]


def test_rerun_same_change_does_not_accumulate(client):
    first = client.post("/api/runs", json={"sample": "merged"}).json()
    second = client.post(f"/api/runs/{first['id']}/rerun").json()
    third = client.post("/api/runs", json={"sample": "merged"}).json()
    assert second["reused"] and third["reused"]
    assert first["id"] == second["id"] == third["id"]
    ledger = first["result"]["merge"]["dispatch_ledger"]
    assert second["result"]["merge"]["dispatch_ledger"] == ledger


def test_conflict_links_suspend(merged_data):
    """同一斗口指向不同承接线路时承接关系冲突，斗口挂起。"""
    data = copy.deepcopy(merged_data)
    data["merges"].append({"change_id": "MG-2026-11-01", "outlet": "011",
                           "old_channel": "西支渠旧线", "new_channel": "东支渠", "status": "confirmed"})
    result = _merge(data)
    row = next(a for a in result["adjudications"] if a["outlet"] == "011")
    assert row["state"] == "suspended" and row["reason_code"] == "MERGE_CONFLICT"
    assert result["state"] == "held"


def test_ceiling_conflict_suspends(merged_data):
    """历史保底（900）超出新渠权证上限（800），条款冲突挂起。"""
    data = copy.deepcopy(merged_data)
    target = next(r for r in data["rights"] if r["outlet"] == "011" and r["channel"] == "西支渠")
    target["ceiling"] = "0.8"
    result = _merge(data)
    row = next(a for a in result["adjudications"] if a["outlet"] == "011")
    assert row["state"] == "suspended" and row["reason_code"] == "MERGE_CEILING_CONFLICT"


def test_missing_target_voucher_suspends(merged_data):
    """新渠缺少承接权证时挂起，历史保底仍挂账。"""
    data = copy.deepcopy(merged_data)
    data["rights"] = [r for r in data["rights"]
                      if not (r["outlet"] == "011" and r["channel"] == "西支渠")]
    result = _merge(data)
    row = next(a for a in result["adjudications"] if a["outlet"] == "011")
    assert row["state"] == "suspended" and row["reason_code"] == "MERGE_NO_TARGET"
    assert row["reserved_l"] == 900


def test_current_only_right_kept_with_review(merged_data):
    """只有新渠权证、无历史归属：资格保留并提示待复核，不重复计水。"""
    data = copy.deepcopy(merged_data)
    data["merges"] = [m for m in data["merges"] if m["outlet"] != "013"]
    data["merges"].append({"change_id": "MG-2026-11-01", "outlet": "013",
                           "old_channel": "西支渠旧线", "new_channel": "西支渠", "status": "confirmed"})
    result = _merge(data)
    row = next(a for a in result["adjudications"] if a["outlet"] == "013")
    assert row["state"] == "current_only" and row["reason_code"] == "MERGE_NO_LEGACY"
    assert any(item["code"] == "MERGE_NO_LEGACY" for item in result["issues"])


def test_bad_merge_row_is_evidence(merged_data):
    data = copy.deepcopy(merged_data)
    data["merges"].append({"change_id": "MG-X", "outlet": "099", "old_channel": "西支渠旧线",
                           "new_channel": "西支渠", "status": "unknown"})
    result = _merge(data)
    assert any(item["code"] == "MERGE_BAD" for item in result["issues"])


def test_reserve_exceeding_remainder_blocks(merged_data):
    """挂账保底超出承接渠余量时挂起整账，水量待核实。"""
    data = copy.deepcopy(merged_data)
    data["channels"] = [c for c in data["channels"] if c["channel"] != "西支渠"]
    data["channels"].append({"channel": "西支渠", "parent": "总干渠", "inflow": "6.4",
                             "loss": "0.4", "unit": "m³"})
    result = _merge(data)
    assert any(item["code"] == "MERGE_RESERVE_EXCESS" for item in result["issues"])
    assert result["state"] == "held"


def test_empty_merges_section_is_neutral(clean_data, dirty_data):
    """无合并变更的样例 M8 返回空账，不影响原有七个阶段与下发状态。"""
    for data in (clean_data, dirty_data):
        section = _merge(data)
        assert section["adjudications"] == [] and section["issues"] == []
        assert section["state"] == "ready"


def test_change_id_stable_across_runs(merged_data):
    assert _merge(merged_data)["change_id"] == _merge(copy.deepcopy(merged_data))["change_id"]


def test_merges_table_is_optional_but_unknown_tables_reject(merged_data, clean_data):
    validate(clean_data)
    validate(merged_data)
    with pytest.raises(InputError) as exc:
        validate({**merged_data, "stray": []})
    assert exc.value.code == "INPUT_TABLES"
