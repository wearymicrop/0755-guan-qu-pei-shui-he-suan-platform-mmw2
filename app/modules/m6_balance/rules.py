from collections import defaultdict

from app.evidence import issue


def run(_data, previous):
    supply = previous["batches"]["supply_l"]
    channels = previous["channels"]
    issues = [warning for section in previous.values() for warning in section["issues"]]
    by_channel, by_outlet = defaultdict(int), defaultdict(list)
    for row in previous["tail"]["allocations"]:
        by_channel[row["channel"]] += row["allocated_l"]
        by_outlet[row["outlet"]].append(row["source"])
    for sources in by_outlet.values():
        if len(sources) > 1:
            issues.append(issue("DUPLICATE_OUTLET", *sources))
    ledgers, held = [], channels["held_at_head_l"]
    for row in channels["channels"]:
        allocation = by_channel.pop(row["channel"], 0)
        remainder = row["usable_l"] - allocation
        if remainder < 0:
            issues.append(issue("CHANNEL_UNBALANCED", row["source"]))
        ledgers.append({**row, "allocated_l": allocation, "remainder_l": remainder + row["held_l"]})
        held += remainder + row["held_l"]
    if by_channel:
        issues.append(issue("CHANNEL_UNBALANCED"))
    losses = channels["loss_l"]
    allocated = previous["tail"]["allocated_l"]
    difference = supply - losses - allocated - held
    return {"status": "DIFFERENCE" if difference or by_channel or any(row["usable_l"] < row["allocated_l"] for row in ledgers)
            else "REVIEW" if issues else "MATCHED", "supply_l": supply, "loss_l": losses, "allocated_l": allocated,
            "remaining_l": held, "difference_l": difference, "ledgers": ledgers, "issues": issues}
