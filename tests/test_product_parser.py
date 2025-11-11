from app.utils.product_parser import extract_base_code, determine_material


def test_extract_base_code_variants():
    assert extract_base_code("GT10S") == ("GT10", "S")
    assert extract_base_code("GT-10S") == ("GT10", "S")
    assert extract_base_code("GT 10 S") == ("GT10", "S")
    assert extract_base_code("F9970") == ("F9970", None)


def test_determine_material_from_suffix():
    assert determine_material("GT10S", None) == "SILICONE"
    assert determine_material("GT10P", None) == "PVC"


def test_determine_material_from_column():
    assert determine_material("GT10", "硅胶") == "SILICONE"
    assert determine_material("GT10", "PVC") == "PVC"
    assert determine_material("GT10", None) is None

