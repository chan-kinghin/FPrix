from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.wide_search import detect_wide_query, run_wide_search
from app.models import Base


def make_sqlite_session(tmp_name: str = ":memory:"):
    engine = create_engine(f"sqlite:///{tmp_name}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return Session


def test_description_match_not_found_returns_error(tmp_path):
    # Empty DB is fine; description match will fail and return error early
    Session = make_sqlite_session(str(tmp_path / "ws_no_match.sqlite"))
    db = Session()
    try:
        params = detect_wide_query("比 不存在的产品描述 便宜的")
        assert params is not None and params.mode == "compare_lt"
        result = run_wide_search(db, params)
        assert result["status"] == "error"
        assert result["error_type"] == "reference_not_found"
    finally:
        db.close()


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *args, **kwargs):  # sql, params
        return _FakeResult(self._rows)

    def close(self):
        pass


class _FakeEngine:
    def __init__(self, rows):
        self._rows = rows

    def connect(self):
        return _FakeConnection(self._rows)


class _DummyDB:
    def __init__(self, rows):
        self._engine = _FakeEngine(rows)

    def get_bind(self):
        return self._engine


def test_wide_search_top_asc_filters_zero_prices():
    # Provide rows including zero prices; expect zeros to be filtered out
    fake_rows = [
        ("GT33", "泳镜", "PVC", None, 0.0),
        ("GT10S", "泳镜", "SILICONE", None, 0.9),
        ("2322", "泳镜", "PVC", None, 0.0),
    ]
    db = _DummyDB(fake_rows)

    params = detect_wide_query("最便宜 泳镜 前5")
    assert params is not None and params.mode == "top_asc"

    result = run_wide_search(db, params)
    assert result["status"] == "success"
    products = result["data"]["results"]
    # Only the non-zero row should remain
    assert all(p["price"] > 0 for p in products)
    assert any(p["product_code"] == "GT10S" for p in products)
