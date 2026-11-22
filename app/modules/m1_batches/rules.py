from collections import defaultdict

from app.errors import InputError
from app.evidence import interval, issue, key, rows, timestamp
from app.units import integer, liters


def run(data, _previous):
    config = data["config"]
    start, end = interval(config)
    try:
        batch, root = key(config["batch"]), key(config["root"])
        supply = liters(config["supply"], config["unit"])
        quantum = integer(config["quantum_l"], 1, 100000)
    except (KeyError, TypeError, ValueError) as error:
        raise InputError("BAD_BATCH", "批次、渠首水量或最小单位有误") from error
    issues, grouped, records = [], defaultdict(list), []
    for row, source in rows(data, "gates"):
        try:
            channel = key(row["channel"])
            begin, finish = timestamp(row["start"]), timestamp(row["end"])
            state = row["state"]
            if begin >= finish or state not in ("open", "closed"):
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            issues.append(issue("BAD_GATE", source))
            continue
        if finish <= start or begin >= end:
            records.append({"channel": channel, "state": "outside", "sources": [source]})
            continue
        grouped[channel].append((state, begin <= start and finish >= end, source))
    states = {}
    for channel, candidates in sorted(grouped.items()):
        sources = [entry[2] for entry in candidates]
        if len(candidates) > 1:
            state = "blocked"
            issues.append(issue("GATE_OVERLAP", *sources))
        elif not candidates[0][1]:
            state = "blocked"
            issues.append(issue("GATE_PARTIAL", *sources))
        else:
            state = candidates[0][0]
        states[channel] = state
        records.append({"channel": channel, "state": state, "sources": sources})
    return {"batch": batch, "root": root, "start": start.isoformat(), "end": end.isoformat(),
            "supply_l": supply, "quantum_l": quantum, "gates": states, "records": records, "issues": issues}
