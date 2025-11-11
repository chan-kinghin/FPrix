from __future__ import annotations

import base64
from pathlib import Path
from typing import Iterator

import asyncio
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import get_db
from app.models import Base, Product, PricingTier


def make_sqlite_session(tmp_name: str = "test_api.sqlite"):
    db_url = f"sqlite:///{tmp_name}"
    engine = create_engine(db_url)
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
    finally:
        db.close()


def test_query_success_via_api(tmp_path):
    db_file = tmp_path / "api1.sqlite"
    Session = make_sqlite_session(str(db_file))
    seed_basic(Session)
    app.dependency_overrides[get_db] = override_dep(Session)
    transport = httpx.ASGITransport(app=app)
    async def _run():
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/query", json={"query": "GT10S C级 标准色"})
            assert resp.status_code == 200
            return resp.json()
    data = asyncio.get_event_loop().run_until_complete(_run())
    assert data["status"] == "success"
    assert data["data"]["product_code"] == "GT10S"
    assert data["data"]["tier"] == "C级"
    assert data["data"]["color_type"] == "标准色"


def test_query_needs_confirm_and_confirm_flow(tmp_path):
    db_file = tmp_path / "api2.sqlite"
    Session = make_sqlite_session(str(db_file))
    seed_basic(Session)
    app.dependency_overrides[get_db] = override_dep(Session)
    transport = httpx.ASGITransport(app=app)
    async def _flow():
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.post("/api/query", json={"query": "查 GT10 C级 标准色"})
            assert r1.status_code == 200
            return r1.json()
    j1 = asyncio.get_event_loop().run_until_complete(_flow())
    assert j1["status"] == "needs_confirmation"
    cid = j1["confirmation_id"]
    opt = (j1.get("options") or [])[0]

    async def _confirm():
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r2 = await client.post("/api/confirm", json={"confirmation_id": cid, "selected_option": opt["id"]})
            assert r2.status_code == 200
            return r2.json()
    j2 = asyncio.get_event_loop().run_until_complete(_confirm())
    assert j2["status"] == "success"
    assert j2["data"]["product_code"] in ("GT10S", "GT10P")


def test_wide_search_via_mock(monkeypatch, tmp_path):
    # Prepare DB (not used by mock but required by dependency)
    db_file = tmp_path / "api3.sqlite"
    Session = make_sqlite_session(str(db_file))
    seed_basic(Session)
    app.dependency_overrides[get_db] = override_dep(Session)
    transport = httpx.ASGITransport(app=app)

    # Mock run_wide_search to avoid DB-specific SQL function dependency
    from app.services import query_processor as qp
    def _fake_run(db, params):
        rows = [
            {"product_code": "GT10S", "category": "泳镜", "material": "SILICONE", "screenshot_url": None, "price": 0.9, "tier": "C级", "color_type": "标准色"},
            {"product_code": "GT10P", "category": "泳镜", "material": "PVC", "screenshot_url": None, "price": 0.7, "tier": "C级", "color_type": "标准色"},
        ]
        return {
            "status": "success",
            "result_text": "查询结果\n1. GT10S — $0.90 [泳镜]\n2. GT10P — $0.70 [泳镜]",
            "result_markdown": "",
            "screenshot_url": None,
            "data": {"results": rows, "mode": params.mode, "tier": params.tier, "color_type": params.color, "category": params.category, "limit": params.limit},
            "confidence": 0.75,
            "execution_time_ms": 1,
        }
    monkeypatch.setattr(qp, "run_wide_search", _fake_run)

    async def _ws():
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/api/query", json={"query": "最贵的 泳镜 前2"})
            assert r.status_code == 200
            return r.json()
    j = asyncio.get_event_loop().run_until_complete(_ws())
    assert j["status"] == "success"
    assert len(j["data"]["results"]) == 2


def test_screenshot_endpoint(tmp_path):
    # Write a small PNG file
    png_path = Path("data/screenshots/test_api.png")
    png_path.parent.mkdir(parents=True, exist_ok=True)
    if not png_path.exists():
        png_bytes = base64.b64decode(
            b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGAAAAAEAAH3o7sSAAAAAElFTkSuQmCC"
        )
        png_path.write_bytes(png_bytes)

    Session = make_sqlite_session(str(tmp_path / "api4.sqlite"))
    app.dependency_overrides[get_db] = override_dep(Session)
    transport = httpx.ASGITransport(app=app)
    async def _shot():
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/screenshot/test_api.png")
            assert r.status_code == 200
            return r
    r = asyncio.get_event_loop().run_until_complete(_shot())
    assert r.headers.get("content-type") == "image/png"


def test_analytics_endpoints_basic_auth(tmp_path):
    db_file = tmp_path / "api5.sqlite"
    Session = make_sqlite_session(str(db_file))
    seed_basic(Session)
    app.dependency_overrides[get_db] = override_dep(Session)
    transport = httpx.ASGITransport(app=app)
    async def _produce_and_fetch():
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/query", json={"query": "GT10S C级 标准色"})
            await client.post("/api/query", json={"query": "GT10 C级 标准色"})
            auth = httpx.BasicAuth("admin", "change-me")
            r1 = await client.get("/api/analytics/queries", auth=auth)
            r2 = await client.get("/api/analytics/stats", auth=auth)
            r3 = await client.get("/api/analytics/data_quality", auth=auth)
            return r1, r2, r3
    r1, r2, r3 = asyncio.get_event_loop().run_until_complete(_produce_and_fetch())
    assert r1.status_code == 200
    j1 = r1.json()
    assert isinstance(j1.get("total"), int)
    assert isinstance(j1.get("queries"), list)
    assert r2.status_code == 200
    j2 = r2.json()
    assert "total_queries" in j2 and "success_rate" in j2
    assert r3.status_code == 200
    j3 = r3.json()
    assert "total_products" in j3
