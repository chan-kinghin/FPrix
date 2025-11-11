from __future__ import annotations

from app.services.deepseek import _heuristic_extract, DeepSeekClient


def test_heuristic_extract_parses_all_fields():
    q = "查 GT-10S A级 标准色 硅胶 价格"
    r = _heuristic_extract(q)
    assert r["product_code"] == "GT10S"
    assert r["tier"] == "A级"
    assert r["color_type"] == "标准色"
    assert r["material"] == "SILICONE"


def test_client_extract_params_without_api_key_falls_back():
    client = DeepSeekClient(api_key=None)
    q = "看看 gt10 B 定制"
    r = client.extract_query_params(q)
    assert r["product_code"] == "GT10"
    assert r["tier"] == "B级"
    assert r["color_type"] == "定制色"
    # material not present here -> None
    assert r.get("material") in (None, "PVC")
