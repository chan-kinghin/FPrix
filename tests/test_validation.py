from app.utils.validation import validate_product


def test_missing_required_fields():
    errs = validate_product({})
    assert "Missing product_code" in errs
    assert "Missing material_type" in errs
    assert "Missing base_cost" in errs


def test_suffix_material_consistency():
    errs = validate_product({"product_code": "GT10S", "material_type": "PVC", "base_cost": 1.0})
    assert any("'S' suffix" in e for e in errs)
    errs = validate_product({"product_code": "GT10P", "material_type": "SILICONE", "base_cost": 1.0})
    assert any("'P' suffix" in e for e in errs)


def test_price_ordering():
    p = {
        "product_code": "GT10S",
        "material_type": "SILICONE",
        "base_cost": 0.5,
        "A级_标准": 0.8,
        "B级_标准": 0.9,
        "C级_标准": 1.0,
        "D级_标准": 1.1,
    }
    assert validate_product(p) == []

    p_bad = {**p, "B级_标准": 0.7}
    errs = validate_product(p_bad)
    assert any("Price ordering violated" in e for e in errs)


def test_custom_color_not_cheaper():
    p = {
        "product_code": "GT10S",
        "material_type": "SILICONE",
        "base_cost": 0.5,
        "A级_标准": 0.8,
        "A级_定制": 0.7,
    }
    errs = validate_product(p)
    assert any("定制色 price should be ≥ 标准色 price" in e for e in errs)

