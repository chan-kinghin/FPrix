from app.services.wide_search import detect_wide_query


def P(q: str):
    w = detect_wide_query(q)
    assert w is not None, f"should detect mode for: {q}"
    return w


def test_top_desc_with_category_and_limit():
    w = P("最贵的 泳镜 前5")
    assert w.mode == "top_desc"
    assert w.category == "泳镜"
    assert w.limit == 5


def test_top_asc_default_limit():
    w = P("最便宜 泳镜")
    assert w.mode == "top_asc"
    assert w.limit == 10  # default


def test_compare_gt_with_code():
    w = P("比 2323S 贵 的 泳镜 前3")
    assert w.mode == "compare_gt"
    assert w.ref_code == "2323S"
    assert w.category == "泳镜"
    assert w.limit == 3


def test_compare_lt_with_base_number():
    w = P("比 2323 便宜 的 泳镜")
    assert w.mode == "compare_lt"
    assert w.ref_code == "2323"


def test_range_detection_with_dash():
    w = P("泳镜 0.8-1.0 美元")
    assert w.mode == "range"
    assert abs(w.min_price - 0.8) < 1e-9
    assert abs(w.max_price - 1.0) < 1e-9


def test_range_detection_with_tilde():
    w = P("潜水镜 1.2~1.5 之间")
    assert w.mode == "range"
    assert w.category == "潜水镜"
    assert abs(w.min_price - 1.2) < 1e-9
    assert abs(w.max_price - 1.5) < 1e-9


def test_top_desc_without_category():
    w = P("最贵的 前7")
    assert w.mode == "top_desc"
    assert w.category is None
    assert w.limit == 7

