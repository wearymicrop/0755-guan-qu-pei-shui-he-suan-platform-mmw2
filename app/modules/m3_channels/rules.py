from collections import defaultdict, deque

from app.evidence import issue, key, rows
from app.units import liters


def read_channels(data):
    grouped, issues = defaultdict(list), []
    for row, source in rows(data, "channels"):
        try:
            name = key(row["channel"])
            parent = None if row["parent"] is None else key(row["parent"])
        except (KeyError, TypeError, ValueError):
            issues.append(issue("BAD_CHANNEL", source))
            continue
        grouped[name].append((parent, row, source))
    by_name = {}
    for name, candidates in sorted(grouped.items()):
        if len(candidates) > 1:
            issues.append(issue("DUPLICATE_CHANNEL", *(item[2] for item in candidates)))
            continue
        parent, row, source = candidates[0]
        try:
            inflow, loss = liters(row["inflow"], row["unit"]), liters(row["loss"], row["unit"])
            if loss > inflow:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            issues.append(issue("BAD_CHANNEL", source))
            continue
        by_name[name] = {"channel": name, "parent": parent, "inflow_l": inflow, "loss_l": loss, "source": source}
    return by_name, issues


def run(data, previous):
    batch = previous["batches"]
    root, supply, gates = batch["root"], batch["supply_l"], batch["gates"]
    by_name, issues = read_channels(data)
    children = defaultdict(list)
    for entry in by_name.values():
        if entry["channel"] != root:
            children[entry["parent"]].append(entry)
    gate_sources = {row["channel"]: row["sources"] for row in batch["records"] if row["state"] != "outside"}
    for channel in sorted(gate_sources.keys() - by_name.keys()):
        issues.append(issue("UNKNOWN_GATE", *gate_sources[channel]))
    head = by_name.get(root)
    ready, seen = [], set()
    queue = deque()
    if not head or head["parent"] is not None or head["inflow_l"] != supply:
        issues.append(issue("ROOT_MISMATCH", *([head["source"]] if head else [])))
    elif gates.get(root) != "open":
        issues.append(issue("GATE_BLOCKED", head["source"], *gate_sources.get(root, [])))
    else:
        queue.append(head)
    while queue:
        entry = queue.popleft()
        name = entry["channel"]
        seen.add(name)
        net = entry["inflow_l"] - entry["loss_l"]
        passing = []
        for child in children[name]:
            code = "GATE_BLOCKED" if child["inflow_l"] else None
            if gates.get(child["channel"]) == "open":
                passing.append(child)
            elif code:
                issues.append(issue(code, child["source"], *gate_sources.get(child["channel"], [])))
        declared = sum(child["inflow_l"] for child in passing)
        if declared > net:
            issues.append(issue("CHILD_FLOW_EXCESS", entry["source"], *(row["source"] for row in passing)))
            passing, declared = [], 0
            local = 0
        else:
            local = net - declared
        ready.append({**entry, "child_inflow_l": declared, "usable_l": local, "held_l": net - declared - local})
        queue.extend(passing)
    for name in sorted(by_name.keys() - seen - {root}):
        entry = by_name[name]
        parent = entry["parent"]
        lineage = {name, root}
        while parent is not None and parent not in lineage and parent in by_name:
            lineage.add(parent)
            parent = by_name[parent]["parent"]
        if parent != root:
            issues.append(issue("CHANNEL_DISCONNECTED", entry["source"]))
        elif entry["inflow_l"] and (entry["parent"] not in seen or gates.get(name) == "open"):
            issues.append(issue("UPSTREAM_BLOCKED", entry["source"], *gate_sources.get(entry["parent"], [])))
    return {"channels": ready, "loss_l": sum(row["loss_l"] for row in ready),
            "held_at_head_l": supply if not ready else 0, "issues": issues}
