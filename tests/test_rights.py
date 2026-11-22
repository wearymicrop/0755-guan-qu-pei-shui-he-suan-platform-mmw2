from app.pipeline import calculate


def test_end_exclusive(clean):
    """TRAP-23：干净样例旧权证在批次开始时失效。"""
    assert {r["version"]: r["state"] for r in clean["rights"]["records"] if r["outlet"] == "001"} == {"2026-A": "outside", "2026-B": "active"}


def test_leading_zero(clean):
    """TRAP-08：干净样例斗口号保留前导零。"""
    assert clean["rights"]["active"][0]["outlet"] == "001"


def test_overlap_right(dirty):
    """TRAP-25：脏样例重叠权证保留两行。"""
    right = next(i for i in dirty["rights"]["issues"] if i["code"] == "RIGHT_OVERLAP")
    assert [s["line"] for s in right["sources"]] == [1, 13]


def test_missing_minimum(dirty):
    """TRAP-07：脏样例哨兵保底留证。"""
    assert [i["sources"][0]["raw"]["minimum"] for i in dirty["rights"]["issues"] if i["code"] == "BAD_RIGHT"] == ["-"]


def test_partial_right(dirty):
    assert next(r for r in dirty["rights"]["records"] if r["outlet"] == "091")["state"] == "partial"


def test_right_grid(clean_data):
    clean_data["rights"][0]["ceiling"] = "6.01"
    assert calculate(clean_data)["rights"]["issues"][0]["code"] == "BAD_RIGHT"
