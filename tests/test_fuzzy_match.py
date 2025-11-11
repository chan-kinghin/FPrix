from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Product
from app.services.fuzzy_match import (
    normalize_product_code,
    exact_match,
    base_code_match,
    fuzzy_string_match,
)


def setup_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    # seed sample products
    samples = [
        Product(
            product_code="GT10S",
            base_code="GT10",
            product_name_cn="儿童分体简易带扣",
            category="泳镜",
            material_type="SILICONE",
            base_cost=0.5,
            source_pdf="2025.10.28 泳镜.pdf",
            source_page=2,
        ),
        Product(
            product_code="GT10P",
            base_code="GT10",
            product_name_cn="儿童分体简易带扣",
            category="泳镜",
            material_type="PVC",
            base_cost=0.4,
            source_pdf="2025.10.28 泳镜.pdf",
            source_page=2,
        ),
        Product(
            product_code="F9970",
            base_code="F9970",
            product_name_cn="蛙鞋",
            category="蛙鞋",
            material_type="",
            base_cost=1.0,
            source_pdf="2025.10.28 蛙鞋.pdf",
            source_page=1,
        ),
        Product(
            product_code="GT20S",
            base_code="GT20",
            product_name_cn="泳镜",
            category="泳镜",
            material_type="SILICONE",
            base_cost=0.6,
            source_pdf="2025.10.28 泳镜.pdf",
            source_page=3,
        ),
        Product(
            product_code="GT30S",
            base_code="GT30",
            product_name_cn="泳镜",
            category="泳镜",
            material_type="SILICONE",
            base_cost=0.7,
            source_pdf="2025.10.28 泳镜.pdf",
            source_page=4,
        ),
    ]
    db.add_all(samples)
    db.commit()
    return db


def test_normalization_variants():
    assert normalize_product_code("GT10S") == "GT10S"
    assert normalize_product_code("gt10s") == "GT10S"
    assert normalize_product_code("GT-10S") == "GT10S"
    assert normalize_product_code("GT 10 S") == "GT10S"
    assert normalize_product_code("GT!10S") == "GT10S"


def test_exact_and_base_matches():
    db = setup_db()
    # exact
    matches, conf = exact_match(db, "GT10S")
    assert len(matches) == 1 and matches[0].product_code == "GT10S" and conf == 1.0
    # base code
    matches, conf = base_code_match(db, "GT10")
    codes = {m.product_code for m in matches}
    assert {"GT10S", "GT10P"}.issubset(codes)
    assert conf == 0.95


def test_fuzzy_matching_and_thresholds():
    db = setup_db()
    # hyphen/space removal leads to exact when normalized but fuzzy as function
    fuzzy = fuzzy_string_match(db, "GT-10S", threshold=0.85)
    assert any(p.product_code == "GT10S" for p, score in fuzzy)
    # slight typo (0 -> O) should still match with lower threshold
    fuzzy2 = fuzzy_string_match(db, "GT1OS", threshold=0.8)
    assert any(p.product_code in {"GT10S", "GT10P"} for p, score in fuzzy2)
    # no match scenario
    none = fuzzy_string_match(db, "XYZ999", threshold=0.8)
    assert none == []
    # below threshold should not match
    none2 = fuzzy_string_match(db, "GT99", threshold=0.95)
    assert none2 == []


def test_no_suffix_product_present():
    db = setup_db()
    matches, _ = exact_match(db, "F9970")
    assert len(matches) == 1 and matches[0].product_code == "F9970"
