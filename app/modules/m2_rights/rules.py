from collections import defaultdict

from app.evidence import issue, key, rows, timestamp
from app.units import integer, liters


def run(data, previous):
    batch = previous["batches"]
    start, end = timestamp(batch["start"]), timestamp(batch["end"])
    quantum = batch["quantum_l"]
    groups, records, issues = defaultdict(list), [], []
    for row, source in rows(data, "rights"):
        try:
            outlet, channel, version = (key(row[field]) for field in ("outlet", "channel", "version"))
            begin, finish = timestamp(row["start"]), timestamp(row["end"])
            if begin >= finish:
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            issues.append(issue("BAD_RIGHT", source))
            continue
        if finish <= start or begin >= end:
            records.append({"outlet": outlet, "channel": channel, "version": version, "state": "outside", "source": source})
        else:
            groups[outlet].append((row, source, channel, version, begin <= start and finish >= end))
    active = []
    for outlet, candidates in sorted(groups.items()):
        if len(candidates) > 1:
            issues.append(issue("RIGHT_OVERLAP", *(entry[1] for entry in candidates)))
            for _, source, channel, version, _ in candidates:
                records.append({"outlet": outlet, "channel": channel, "version": version, "state": "overlap", "source": source})
            continue
        row, source, channel, version, covers = candidates[0]
        info = {"outlet": outlet, "channel": channel, "version": version, "source": source}
        if not covers:
            issues.append(issue("RIGHT_PARTIAL", source))
            records.append({**info, "state": "partial"})
            continue
        try:
            floor = liters(row["minimum"], row["unit"])
            cap = liters(row["ceiling"], row["unit"])
            rank, weight = integer(row["priority"], 1, 99), integer(row["weight"], 1)
            if cap < floor or floor % quantum or cap % quantum:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            issues.append(issue("BAD_RIGHT", source))
            records.append({**info, "state": "invalid"})
            continue
        record = {**info, "state": "active", "minimum_l": floor, "ceiling_l": cap, "priority": rank, "weight": weight}
        records.append(record)
        active.append(record)
    return {"active": active, "records": records, "issues": issues}
