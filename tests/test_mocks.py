from __future__ import annotations

import asyncio
import httpx
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Product, PricingTier
from app.services.query_processor import process_query
from app.services.deepseek import DeepSeekClient
from app.core.database import get_db
from app.main import app


def setup_mem_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    return db


def seed_products(db):
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
    db.add_all([
        PricingTier(product_id=p_s.product_id, tier="C级", color_type="标准色", price=0.9),
        PricingTier(product_id=p_s.product_id, tier="C级", color_type="定制色", price=1.1),
        PricingTier(product_id=p_p.product_id, tier="C级", color_type="标准色", price=0.7),
    ])
    db.commit()
    return p_s, p_p


def test_process_query_uses_mocked_deepseek_api(monkeypatch):
    db = setup_mem_db()
    seed_products(db)

    def fake_call(self, query: str, timeout: float = 8.0):
        return {
            "product_code": "GT10S",
            "tier": "C级",
            "color_type": "标准色",
            "material": "SILICONE",
        }

    monkeypatch.setattr(DeepSeekClient, "_call_api", fake_call)
    r = process_query("随便说点啥", db)
    assert r["status"] == "success"
    assert r["data"]["product_code"] == "GT10S"
    assert r["data"]["tier"] == "C级"
    assert r["data"]["color_type"] == "标准色"


def test_fuzzy_match_path_forces_confirmation(monkeypatch):
    db = setup_mem_db()
    p_s, p_p = seed_products(db)

    # Return fuzzy matches regardless of input
    from app.services import query_processor as qp
    from app.services.deepseek import DeepSeekClient

    def fake_fuzzy(db_session, norm_code: str, threshold: float = 0.85):
        return [(p_s, 0.92), (p_p, 0.88)]

    monkeypatch.setattr(qp, "fuzzy_string_match", fake_fuzzy)
    # Ensure a product_code is present to avoid early missing_product_code error
    monkeypatch.setattr(DeepSeekClient, "extract_query_params", lambda self, q: {"product_code": "AB12"})
    r = process_query("AB12", db)
    assert r["status"] == "needs_confirmation"
    codes = {o.get("product_code") for o in r.get("options", [])}
    assert {"GT10S", "GT10P"}.issubset(codes)


def make_sqlite_session(tmp_name: str):
    engine = create_engine(f"sqlite:///{tmp_name}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return Session


def override_dep(Session):
    def _override() -> Iterator:
        db = Session()
        try:
            yield db
        finally:
            db.close()
    return _override


def seed_basic(Session):
    db = Session()
    try:
        seed_products(db)
    finally:
        db.close()


def test_api_logs_ignore_errors(monkeypatch, tmp_path):
    # Prepare DB and override dependency
    db_file = tmp_path / "mock_api.sqlite"
    Session = make_sqlite_session(str(db_file))
    seed_basic(Session)
    app.dependency_overrides[get_db] = override_dep(Session)

    # Monkeypatch the imported log_query symbol inside the route module
    import app.api.routes.query as query_mod

    def fake_log_query(db, data):
        raise RuntimeError("log failed")

    monkeypatch.setattr(query_mod, "log_query", fake_log_query)

    transport = httpx.ASGITransport(app=app)

    async def _run():
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/query", json={"query": "GT10S C级 标准色"})
            return resp

    resp = asyncio.get_event_loop().run_until_complete(_run())
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_analytics_requires_basic_auth(tmp_path):
    db_file = tmp_path / "mock_api2.sqlite"
    Session = make_sqlite_session(str(db_file))
    seed_basic(Session)
    app.dependency_overrides[get_db] = override_dep(Session)
    transport = httpx.ASGITransport(app=app)

    async def _req():
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/analytics/queries")

    resp = asyncio.get_event_loop().run_until_complete(_req())
    assert resp.status_code == 401
