from app.pipeline import calculate


def test_largest_remainder(clean):
    """TRAP-24：干净样例北斗渠两个 4.5 刻度只能分 9 刻度。"""
    assert [(r["outlet"],r["allocated_l"]) for r in clean["tail"]["allocations"] if r["channel"]=="北斗渠"] == [("031",500),("032",400)]


def test_tail_amount(clean):
    assert clean["tail"]["tail_l"] == 200


def test_winner_on_larger_fraction(clean):
    rows = {r["outlet"]:r["tail_l"] for r in clean["tail"]["allocations"]}
    assert (rows["001"],rows["002"]) == (100,0)


def test_rounding_exact_quanta(clean):
    assert all(row["allocated_l"] % 100 == 0 for row in clean["tail"]["allocations"])
    assert clean["tail"]["allocated_l"] == 16700


def test_reordered_input_stable(clean_data):
    before = {r["outlet"]:r["allocated_l"] for r in calculate(clean_data)["tail"]["allocations"]}
    clean_data["rights"].reverse()
    after = {r["outlet"]:r["allocated_l"] for r in calculate(clean_data)["tail"]["allocations"]}
    assert before == after


def test_empty_tail(clean_data):
    clean_data["rights"] = []
    assert calculate(clean_data)["tail"]["allocated_l"] == 0
