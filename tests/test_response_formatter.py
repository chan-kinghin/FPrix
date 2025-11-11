from __future__ import annotations

from app.services.response_formatter import format_success_response
from app.models import Product, PricingTier


def _make_product(**overrides):
    defaults = dict(
        product_code="GT10S",
        base_code="GT10",
        product_name_cn="儿童分体简易带扣",
        category="泳镜",
        subcategory=None,
        material_type="SILICONE",
        base_cost=0.5,
        source_pdf="2025.10.28 泳镜.pdf",
        source_page=2,
        screenshot_url="screenshots/GT10S.png",
        notes=None,
    )
    defaults.update(overrides)
    return Product(**defaults)


def _pt(product_id: int = 1, tier: str = "A级", color: str = "标准色", price: float = 0.8, **kw):
    return PricingTier(product_id=product_id, tier=tier, color_type=color, price=price, **kw)


def test_format_with_single_price():
    p = _make_product()
    price = _pt(tier="C级", color="标准色", price=0.9)
    text, md, data = format_success_response(p, price, p.screenshot_url)
    assert "产品：GT10S" in text
    assert "价格：$0.90 USD (C级标准色)" in text
    assert data["product_code"] == "GT10S"
    assert data["material"] == "SILICONE"
    assert data["tier"] == "C级"
    assert data["color_type"] == "标准色"
    assert abs(float(data["price"]) - 0.9) < 1e-9


def test_format_with_all_pricing_list():
    p = _make_product()
    all_prices = [
        _pt(tier="A级", color="标准色", price=0.8),
        _pt(tier="B级", color="定制色", price=1.2),
    ]
    text, md, data = format_success_response(p, None, p.screenshot_url, all_pricing=all_prices)
    assert "价格一览:" in text
    assert "A级标准色: $0.80 USD" in text
    assert "B级定制色: $1.20 USD" in text
    assert isinstance(data.get("prices"), list) and len(data["prices"]) == 2
    # No single price fields populated
    assert data["tier"] is None and data["color_type"] is None and data["price"] is None

