from collections import defaultdict
from fractions import Fraction

from app.evidence import issue


def capped_weights(caps, weights, budget):
    assigned = [Fraction(0) for _ in caps]
    remaining = {index for index, cap in enumerate(caps) if cap > 0}
    budget = min(Fraction(budget), sum(caps))
    while budget and remaining:
        total = sum(weights[index] for index in remaining)
        shares = {index: budget * weights[index] / total for index in remaining}
        saturated = {index for index in remaining if shares[index] >= caps[index]}
        if not saturated:
            for index, value in shares.items():
                assigned[index] = value
            break
        for index in saturated:
            assigned[index] = Fraction(caps[index])
            budget -= caps[index]
        remaining -= saturated
    return assigned


def allocate(rights, available, quantum):
    targets = [Fraction(0) for _ in rights]
    floors = [row["minimum_l"] // quantum for row in rights]
    caps = [row["ceiling_l"] // quantum for row in rights]
    by_rank = defaultdict(list)
    for index, row in enumerate(rights):
        by_rank[row["priority"]].append(index)
    remaining = Fraction(available // quantum)
    for rank in sorted(by_rank):
        group = by_rank[rank]
        need = sum(floors[i] for i in group)
        if need:
            for index in group:
                targets[index] = min(1, remaining / need) * floors[index]
            remaining -= min(remaining, need)
    for rank in sorted(by_rank):
        group = by_rank[rank]
        extra = capped_weights([caps[i] - targets[i] for i in group], [rights[i]["weight"] for i in group], remaining)
        for index, value in zip(group, extra):
            targets[index] += value
            remaining -= value
    return targets


def run(_data, previous):
    quantum = previous["batches"]["quantum_l"]
    channels = {r["channel"]: r["usable_l"] for r in previous["channels"]["channels"]}
    by_channel, issues = defaultdict(list), []
    for row in previous["rights"]["active"]:
        if row["channel"] in channels:
            by_channel[row["channel"]].append(row)
        else:
            issues.append(issue("RIGHT_ROUTE_BLOCKED", row["source"]))
    items = []
    for channel, rights in sorted(by_channel.items()):
        available = channels[channel]
        targets = allocate(rights, available, quantum)
        for row, target in zip(rights, targets):
            if target * quantum < row["minimum_l"]:
                issues.append(issue("MINIMUM_SHORTAGE", row["source"]))
            items.append({**row, "target_units": str(target), "target_l": str(target * quantum)})
    return {"quantum_l": quantum, "quotas": items, "issues": issues}
