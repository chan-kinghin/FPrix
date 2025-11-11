from app.utils.inference import infer_material_from_query


def test_infer_material_keywords():
    assert infer_material_from_query("GT10 硅胶") == "SILICONE"
    assert infer_material_from_query("GT10 silicone") == "SILICONE"
    assert infer_material_from_query("GT10 PVC") == "PVC"


def test_infer_from_suffix_in_text():
    assert infer_material_from_query("我要查 GT10S 的价格") == "SILICONE"
    assert infer_material_from_query("看一下 GT10P 价格") == "PVC"


def test_infer_mixed_chinese():
    assert infer_material_from_query("GT10硅胶版") == "SILICONE"

