from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Product, PricingTier
from app.services.query_processor import process_query


def setup_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    # Seed products
    p_s = Product(
        product_code="GT10S",
        base_code="GT10",
        product_name_cn="儿童分体简易带扣",
        category="泳镜",
        material_type="SILICONE",
        base_cost=0.5,
        source_pdf="2025.10.28 泳镜.pdf",
        source_page=2,
        screenshot_url="screenshots/GT10S.png",
    )
    p_p = Product(
        product_code="GT10P",
        base_code="GT10",
        product_name_cn="儿童分体简易带扣",
        category="泳镜",
        material_type="PVC",
        base_cost=0.4,
        source_pdf="2025.10.28 泳镜.pdf",
        source_page=2,
        screenshot_url="screenshots/GT10P.png",
    )
    db.add_all([p_s, p_p])
    db.commit()
    # Prices
    db.add_all([
        PricingTier(product_id=p_s.product_id, tier="C级", color_type="标准色", price=0.9),
        PricingTier(product_id=p_s.product_id, tier="C级", color_type="定制色", price=1.1),
        PricingTier(product_id=p_p.product_id, tier="C级", color_type="标准色", price=0.7),
    ])
    db.commit()
    return db


def test_success_with_tier_and_color():
    db = setup_db()
    r = process_query("查询 GT10S C级 标准色", db)
    assert r["status"] == "success"
    assert r["data"]["product_code"] == "GT10S"
    assert r["data"]["tier"] == "C级"
    assert r["data"]["color_type"] == "标准色"
    assert abs(float(r["data"]["price"]) - 0.9) < 1e-9


def test_all_pricing_returned_when_no_tier():
    db = setup_db()
    r = process_query("查一下 GT10S 价格", db)
    assert r["status"] == "success"
    assert r["data"]["product_code"] == "GT10S"
    prices = r["data"].get("prices")
    assert isinstance(prices, list) and len(prices) >= 2


def test_needs_confirmation_for_base_code_variants():
    db = setup_db()
    r = process_query("GT10", db)
    assert r["status"] == "needs_confirmation"
    opts = r.get("options") or []
    codes = {o.get("product_code") for o in opts}
    assert {"GT10S", "GT10P"}.issubset(codes)


def test_product_not_found_error():
    db = setup_db()
    r = process_query("XYZ999", db)
    assert r["status"] == "error"
    assert r["error_type"] == "product_not_found"


def test_missing_product_code_error():
    db = setup_db()
    r = process_query("查一下 价格", db)
    assert r["status"] == "error"
    assert r["error_type"] == "missing_product_code"

