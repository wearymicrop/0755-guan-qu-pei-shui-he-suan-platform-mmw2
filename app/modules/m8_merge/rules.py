"""M8 支渠合并承接。

裁决原则：
- 只认现行线路会改变既有用水资格，只认历史归属会重复计水；本模块以合并变更表为唯一
  承接依据，旧渠权证注销留证、新渠权证承接，保底就高保护，承接关系不明的斗口挂起。
- 已断开支渠的损耗只在迁移前账内核算，不摊入合并后配水账；断流渠历史入流留作上游余量。
- 渠首→支渠→斗口逐级勾稽迁移前后损耗、保底与余水；合并链接按自然键去重，重跑不重复累加。
"""
from collections import defaultdict

from app.evidence import issue, key, rows, timestamp
from app.manifest import sha256
from app.units import integer, liters

CARRIED_STATES = {"carried", "suspended", "current_only"}
BLOCKING_CODES = {"MERGE_PENDING", "MERGE_NO_TARGET", "MERGE_CEILING_CONFLICT",
                  "MERGE_RIGHTS_OVERLAP", "MERGE_CONFLICT", "MERGE_RESERVE_EXCESS"}
LINK_FIELDS = ("change_id", "outlet", "old_channel", "new_channel", "status")


def _active_map(result):
    return {(row["outlet"], row["channel"]): row for row in result["rights"]["active"]}


def _parse_vouchers(windowed, batch):
    """M8 专用权证解析：按 (斗口, 渠段) 建索引，旧渠与新渠各留一权时不互相覆盖。"""
    start, end = timestamp(batch["start"]), timestamp(batch["end"])
    quantum = batch["quantum_l"]
    vouchers, by_outlet = [], defaultdict(list)
    for line, raw in windowed:
        source = {"table": "rights", "line": line, "raw": raw}
        try:
            outlet, channel, version = (key(raw[field]) for field in ("outlet", "channel", "version"))
            begin, finish = timestamp(raw["start"]), timestamp(raw["end"])
            if begin >= finish or not (begin <= start and finish >= end):
                continue
            floor = liters(raw["minimum"], raw["unit"])
            cap = liters(raw["ceiling"], raw["unit"])
            rank, weight = integer(raw["priority"], 1, 99), integer(raw["weight"], 1)
            if cap < floor or floor % quantum or cap % quantum:
                continue
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        record = {"outlet": outlet, "channel": channel, "version": version, "source": source,
                  "minimum_l": floor, "ceiling_l": cap, "priority": rank, "weight": weight}
        vouchers.append(record)
        by_outlet[outlet].append(record)
    indexed = {(row["outlet"], row["channel"]): row for row in vouchers}
    same_channel_overlap = defaultdict(list)
    for outlet, records in by_outlet.items():
        seen = defaultdict(list)
        for record in records:
            seen[record["channel"]].append(record)
        for channel, records in seen.items():
            if len(records) > 1:
                same_channel_overlap[(outlet, channel)] = records
    return indexed, same_channel_overlap


def _window(row, start, end):
    begin, finish = timestamp(row["start"]), timestamp(row["end"])
    return begin < end and finish > start


def _parse_links(data, previous):
    """解析合并变更表，按 (变更号, 斗口) 自然键去重，坏行、重复登记与承接冲突全部留证。"""
    start = timestamp(previous["batches"]["start"])
    end = timestamp(previous["batches"]["end"])
    raw_links, issues = [], []
    for row, source in rows(data, "merges"):
        try:
            change = key(row["change_id"])
            outlet = key(row["outlet"])
            old_channel = key(row["old_channel"])
            new_channel = key(row["new_channel"])
            status = key(row["status"])
            if status not in ("confirmed", "pending"):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            issues.append(issue("MERGE_BAD", source))
            continue
        raw_links.append({"change_id": change, "outlet": outlet, "old_channel": old_channel,
                          "new_channel": new_channel, "status": status, "source": source,
                          "duplicate": False, "conflicting": False})
    indexed = defaultdict(list)
    for link in raw_links:
        indexed[(link["change_id"], link["outlet"])].append(link)
    conflicts = []
    for (change, outlet), links in indexed.items():
        routes = {(link["old_channel"], link["new_channel"], link["status"]) for link in links}
        if len(routes) == 1 and len(links) > 1:
            # 同一承接关系重复登记：留证并去重，重跑不重复累加。
            for link in links[1:]:
                link["duplicate"] = True
                issues.append(issue("MERGE_DUPLICATE", link["source"]))
        elif len(routes) > 1:
            # 同一斗口指向不同承接线路：承接关系冲突，全部挂起。
            conflicts.append((change, outlet))
            for link in links:
                link["conflicting"] = True
                issues.append(issue("MERGE_CONFLICT", link["source"]))
    windowed = []
    for line, raw in enumerate(data["rights"], 1):
        try:
            if _window(raw, start, end):
                windowed.append((line, raw))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return raw_links, windowed, issues, set(conflicts)


def _scenario_inputs(data, windowed, raw_links):
    """构造迁移前（旧渠通水）与合并后两套输入；衍生输入剥离 merges 以终止嵌套计算。"""
    distinct = [link for link in raw_links if not link["duplicate"]]
    valid = [link for link in distinct if not link["conflicting"]]
    old_channels = {link["old_channel"] for link in valid}
    before_gates = [{**row, "state": "open" if key(row["channel"]) in old_channels else row["state"]}
                    for row in data["gates"]]
    carried = {(link["outlet"], link["new_channel"]): link for link in valid}
    before_rights = []
    for _line, raw in windowed:
        outlet, channel = key(raw["outlet"]), key(raw["channel"])
        if (outlet, channel) in carried:
            # 迁移前承接斗口只保留旧渠权证，避免同一斗口双权重叠。
            continue
        before_rights.append(raw)
    common = {k: v for k, v in data.items() if k != "merges"}
    before = {**common, "gates": before_gates, "rights": before_rights}
    return before, distinct, old_channels


def _suspend(base, code, issues, sources, legacy, target=None):
    issues.append(issue(code, *sources))
    reserved = legacy["minimum_l"] if legacy else (target["minimum_l"] if target else 0)
    return {**base, "state": "suspended", "reason_code": code,
            "legacy_minimum_l": legacy["minimum_l"] if legacy else None,
            "carried_minimum_l": None, "reserved_l": reserved}


def _adjudicate(link, before_result, voucher_index, same_channel_overlap, issues):
    """对一条合并链接裁决承接方式，返回承接台账行。"""
    outlet, old_channel, new_channel = link["outlet"], link["old_channel"], link["new_channel"]
    base = {"change_id": link["change_id"], "outlet": outlet,
            "old_channel": old_channel, "new_channel": new_channel, "source": link["source"]}
    legacy = _active_map(before_result).get((outlet, old_channel))
    target = voucher_index.get((outlet, new_channel))
    if link["status"] == "pending":
        return _suspend(base, "MERGE_PENDING", issues, [link["source"]], legacy, target)
    if target is None:
        return _suspend(base, "MERGE_NO_TARGET", issues, [link["source"]], legacy)
    if (outlet, new_channel) in same_channel_overlap:
        overlap_sources = [record["source"] for record in same_channel_overlap[(outlet, new_channel)]]
        return _suspend(base, "MERGE_RIGHTS_OVERLAP", issues, overlap_sources, legacy, target)
    if legacy is None:
        # 只有新渠权证、查不到历史归属：资格保留但标记待复核，不重复计水。
        issues.append(issue("MERGE_NO_LEGACY", link["source"], target["source"]))
        return {**base, "state": "current_only", "reason_code": "MERGE_NO_LEGACY",
                "legacy_minimum_l": None, "carried_minimum_l": target["minimum_l"],
                "reserved_l": 0, "target_source": target["source"]}
    lifted = max(legacy["minimum_l"], target["minimum_l"])
    if lifted > target["ceiling_l"]:
        return _suspend(base, "MERGE_CEILING_CONFLICT", issues,
                        [legacy["source"], target["source"]], legacy, target)
    if lifted > target["minimum_l"]:
        issues.append(issue("MERGE_MIN_LIFTED", legacy["source"], target["source"]))
    if (target["ceiling_l"] != legacy["ceiling_l"]
            or target["priority"] != legacy["priority"]
            or target["weight"] != legacy["weight"]):
        issues.append(issue("MERGE_TERMS_REVIEW", legacy["source"], target["source"]))
    return {**base, "state": "carried", "reason_code": None,
            "legacy_minimum_l": legacy["minimum_l"], "carried_minimum_l": lifted,
            "reserved_l": 0, "target_source": target["source"]}


def _minimum_text(value_l, unit):
    """把就高后的整升保底写回权证原单位，保持与同一行上限单位一致。"""
    scale = {"L": 1, "m3": 1000, "m³": 1000}[unit]
    if value_l % scale == 0:
        return str(value_l // scale)
    text = f"{value_l / scale:.3f}".rstrip("0").rstrip(".")
    return text


def _rewrite_final_rights(data, windowed, adjudications):
    """按裁决改写合并后输入：承接保底就高、挂起斗口撤出权证、旧渠权证注销留证。"""
    lifted = {(row["outlet"], row["new_channel"]): row["carried_minimum_l"]
              for row in adjudications if row["state"] == "carried"}
    suspended = {(row["outlet"], row["new_channel"])
                 for row in adjudications if row["state"] == "suspended"}
    legacy_pairs = {(row["outlet"], row["old_channel"]) for row in adjudications}
    rewritten = []
    for _line, raw in windowed:
        outlet, channel = key(raw["outlet"]), key(raw["channel"])
        if (outlet, channel) in legacy_pairs:
            continue  # 历史权证注销，不再参与合并后配水。
        if (outlet, channel) in suspended:
            continue  # 挂起斗口本轮不配水，保底以挂账形式保留。
        if (outlet, channel) in lifted:
            rewritten.append({**raw, "minimum": _minimum_text(lifted[(outlet, channel)], raw["unit"])})
        else:
            rewritten.append(raw)
    return {**{k: v for k, v in data.items() if k != "merges"}, "rights": rewritten}


def _channel_reconcile(before_result, post_result, old_channels):
    before_rows = {row["channel"]: row for row in before_result["balance"]["ledgers"]}
    post_rows = {row["channel"]: row for row in post_result["balance"]["ledgers"]}
    records = []
    for channel in sorted(set(before_rows) | set(post_rows)):
        old, new = before_rows.get(channel), post_rows.get(channel)
        records.append({
            "channel": channel, "kind": "disconnected" if channel in old_channels else "active",
            "inflow_before_l": old["inflow_l"] if old else 0,
            "inflow_after_l": new["inflow_l"] if new else 0,
            "child_inflow_before_l": old["child_inflow_l"] if old else 0,
            "child_inflow_after_l": new["child_inflow_l"] if new else 0,
            "loss_before_l": old["loss_l"] if old else 0,
            "loss_after_l": new["loss_l"] if new else 0,
            "allocated_before_l": old["allocated_l"] if old else 0,
            "allocated_after_l": new["allocated_l"] if new else 0,
            "remainder_before_l": old["remainder_l"] if old else 0,
            "remainder_after_l": new["remainder_l"] if new else 0,
        })
    return records


def _outlet_reconcile(before_result, post_result, adjudications):
    before_alloc = {row["outlet"]: row["allocated_l"] for row in before_result["tail"]["allocations"]}
    post_alloc = {row["outlet"]: row["allocated_l"] for row in post_result["tail"]["allocations"]}
    by_outlet = defaultdict(list)
    for row in adjudications:
        by_outlet[row["outlet"]].append(row)
    outlets = sorted(set(before_alloc) | set(post_alloc) | set(by_outlet))
    records = []
    for outlet in outlets:
        links = by_outlet.get(outlet)
        records.append({
            "outlet": outlet,
            "state": links[0]["state"] if links else "unchanged",
            "legacy_minimum_l": links[0]["legacy_minimum_l"] if links else None,
            "carried_minimum_l": links[0]["carried_minimum_l"] if links else None,
            "allocated_before_l": before_alloc.get(outlet, 0),
            "allocated_after_l": post_alloc.get(outlet, 0),
            "reserved_l": links[0]["reserved_l"] if links else 0,
        })
    return records


def run(data, previous):
    from app.pipeline import calculate

    if not data.get("merges"):
        return {"change_id": None, "state": "ready", "adjudications": [], "channel_reconcile": [],
                "outlet_reconcile": [], "subtotals": [], "dispatch_ledger": [], "reserve_l": 0,
                "superseded_loss_l": 0, "difference_l": 0, "verdict": [], "issues": []}
    raw_links, windowed, issues, conflict_keys = _parse_links(data, previous)
    voucher_index, same_channel_overlap = _parse_vouchers(windowed, previous["batches"])
    before_input, distinct, old_channels = _scenario_inputs(data, windowed, raw_links)
    before_result = calculate(before_input)
    adjudications = []
    for link in distinct:
        if (link["change_id"], link["outlet"]) in conflict_keys:
            # MERGE_CONFLICT 已在解析阶段留证，这里只登记挂起承接，不重复发异常。
            legacy = _active_map(before_result).get((link["outlet"], link["old_channel"]))
            target = voucher_index.get((link["outlet"], link["new_channel"]))
            reserved = legacy["minimum_l"] if legacy else (target["minimum_l"] if target else 0)
            adjudications.append({
                "change_id": link["change_id"], "outlet": link["outlet"],
                "old_channel": link["old_channel"], "new_channel": link["new_channel"],
                "state": "suspended", "reason_code": "MERGE_CONFLICT",
                "legacy_minimum_l": legacy["minimum_l"] if legacy else None,
                "carried_minimum_l": None, "reserved_l": reserved, "source": link["source"]})
        else:
            adjudications.append(_adjudicate(
                link, before_result, voucher_index, same_channel_overlap, issues))
    post_input = _rewrite_final_rights(data, windowed, adjudications)
    post_result = calculate(post_input)

    # 挂账保底必须落在承接渠的余量内，否则该渠承接挂起、水量待核实。
    reserves = defaultdict(int)
    reserve_sources = defaultdict(list)
    for row in adjudications:
        if row["state"] == "suspended":
            reserves[row["new_channel"]] += row["reserved_l"]
            reserve_sources[row["new_channel"]].append(row["source"])
    post_remainder = {row["channel"]: row["remainder_l"] for row in post_result["balance"]["ledgers"]}
    for channel, reserved in sorted(reserves.items()):
        if reserved > post_remainder.get(channel, 0):
            issues.append(issue("MERGE_RESERVE_EXCESS", *reserve_sources[channel]))
    reserve_total = sum(reserves.values())

    channel_records = _channel_reconcile(before_result, post_result, old_channels)
    outlet_records = _outlet_reconcile(before_result, post_result, adjudications)
    root = previous["batches"]["root"]
    before_balance, post_balance = before_result["balance"], post_result["balance"]
    subtotals = [{
        "level": "渠首", "name": root,
        "supply_before_l": before_balance["supply_l"], "supply_after_l": post_balance["supply_l"],
        "loss_before_l": before_balance["loss_l"], "loss_after_l": post_balance["loss_l"],
        "allocated_before_l": before_balance["allocated_l"], "allocated_after_l": post_balance["allocated_l"],
        "remaining_before_l": before_balance["remaining_l"], "remaining_after_l": post_balance["remaining_l"],
    }]
    for record in channel_records:
        if record["kind"] == "disconnected":
            subtotals.append({"level": "断开支渠", "name": record["channel"],
                              "loss_before_l": record["loss_before_l"], "loss_after_l": 0,
                              "allocated_before_l": record["allocated_before_l"], "allocated_after_l": 0,
                              "remaining_before_l": record["remainder_before_l"], "remaining_after_l": 0})
    subtotals.append({
        "level": "斗口承接", "name": "合计",
        "carried_count": sum(1 for row in adjudications if row["state"] == "carried"),
        "suspended_count": sum(1 for row in adjudications if row["state"] == "suspended"),
        "current_only_count": sum(1 for row in adjudications if row["state"] == "current_only"),
        "reserved_l": reserve_total})

    superseded_loss = sum(row["loss_l"] for row in before_result["balance"]["ledgers"]
                          if row["channel"] in old_channels)
    conservation = (before_balance["supply_l"] == post_balance["supply_l"]
                    and before_balance["difference_l"] == 0 and post_balance["difference_l"] == 0)
    difference = (post_balance["supply_l"] - post_balance["loss_l"]
                  - post_balance["allocated_l"] - post_balance["remaining_l"])

    routes = {row["channel"]: row["source"] for row in post_result["balance"]["ledgers"]}
    dispatch_ledger = []
    for row in post_result["tail"]["allocations"]:
        if not row["allocated_l"]:
            continue
        dispatch_ledger.append({
            "receipt": f"{previous['batches']['batch']}/{row['outlet']}",
            "outlet": row["outlet"], "channel": row["channel"],
            "allocated_l": row["allocated_l"], "state": "ready",
            "sources": [row["source"], *([routes[row["channel"]]] if row["channel"] in routes else [])]})
    for row in adjudications:
        if row["state"] == "suspended":
            dispatch_ledger.append({
                "receipt": f"{previous['batches']['batch']}/{row['outlet']}",
                "outlet": row["outlet"], "channel": row["new_channel"],
                "allocated_l": 0, "state": "suspended", "reserved_l": row["reserved_l"],
                "reason_code": row["reason_code"], "sources": [row["source"]]})

    blocking = {item["code"] for item in issues} & BLOCKING_CODES
    if difference or not conservation:
        state = "held"
    elif blocking:
        state = "held"
    elif issues:
        state = "review"
    else:
        state = "ready"
    change_id = sha256([{k: link[k] for k in LINK_FIELDS}
                        for link in raw_links if not link["duplicate"]])[:16]
    verdict = [
        "权证承接：confirmed 链接旧权证注销留证、新权证承接，保底就高不就低；条款冲突或承接不明的斗口挂起。",
        "损耗承接：合并后只计现行通水线路损耗，断开支渠损耗仅入迁移前账，历史入流保留为上游余量。",
        "挂起斗口本轮不配水，历史保底作为挂账水量保留在承接渠余量，待人工确认后再结转。",
        "重跑同一合并变更按 (变更号, 斗口) 去重，承接权证与水量只计一次；守恒差额为零方可下发。",
    ]
    post_issues = [item for section in post_result.values()
                   if isinstance(section, dict) and "issues" in section for item in section["issues"]]
    seen = {(item["code"], tuple(sorted((src["table"], src["line"]) for src in item["sources"])))
            for item in issues}
    for item in post_issues:
        marker = (item["code"], tuple(sorted((src["table"], src["line"]) for src in item["sources"])))
        if marker not in seen:
            seen.add(marker)
            issues.append(item)
    return {
        "change_id": change_id, "state": state, "adjudications": adjudications,
        "channel_reconcile": channel_records, "outlet_reconcile": outlet_records,
        "subtotals": subtotals, "dispatch_ledger": dispatch_ledger,
        "reserve_l": reserve_total, "superseded_loss_l": superseded_loss,
        "difference_l": difference, "verdict": verdict, "issues": issues,
    }
