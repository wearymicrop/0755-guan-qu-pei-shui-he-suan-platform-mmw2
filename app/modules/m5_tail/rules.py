from collections import defaultdict
from fractions import Fraction


def distribute(items):
    targets = [Fraction(row["target_units"]) for row in items]
    floors = [int(target) for target in targets]
    remainder = [target - floor for target, floor in zip(targets, floors)]
    ranked = sorted(range(len(items)), key=lambda i: (-remainder[i], items[i]["priority"], items[i]["outlet"]))
    count = int(sum(targets)) - sum(floors)
    awarded = set(ranked[:count])
    return [(floor, remainder[index], index in awarded) for index, floor in enumerate(floors)]


def run(_data, previous):
    quota = previous["quotas"]
    quantum = quota["quantum_l"]
    grouped, allocations = defaultdict(list), []
    for row in quota["quotas"]:
        grouped[row["channel"]].append(row)
    for items in grouped.values():
        for row, (floor, remainder, awarded) in zip(items, distribute(items)):
            allocations.append({**row, "floor_l": floor * quantum, "remainder_units": str(remainder),
                                "tail_l": awarded * quantum, "allocated_l": (floor + awarded) * quantum})
    return {"allocations": allocations, "allocated_l": sum(row["allocated_l"] for row in allocations),
            "tail_l": sum(row["tail_l"] for row in allocations), "issues": []}
