from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import verify_admin
from app.models import QueryLog


router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(verify_admin)])


@router.get("/queries")
def get_queries(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(QueryLog)
    if start_date:
        q = q.filter(QueryLog.timestamp >= start_date)
    if end_date:
        q = q.filter(QueryLog.timestamp <= end_date)
    if status == "success":
        q = q.filter(QueryLog.success.is_(True))
    elif status == "error":
        q = q.filter(QueryLog.success.is_(False))
    total = q.count()
    rows = (
        q.order_by(QueryLog.timestamp.desc()).offset(offset).limit(limit).all()
    )
    return {
        "total": total,
        "queries": [
            {
                "query_id": r.query_id,
                "query_text": r.query_text,
                "selected_product": r.selected_product,
                "execution_time_ms": r.execution_time_ms,
                "success": r.success,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ],
    }


@router.get("/stats")
def get_stats(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(QueryLog).filter(QueryLog.timestamp >= since)
    total = q.count()
    success_count = q.filter(QueryLog.success.is_(True)).count()
    confirm_count = q.filter(QueryLog.confirmation_required.is_(True)).count()

    # average execution time
    times = [
        t[0]
        for t in db.query(QueryLog.execution_time_ms).filter(QueryLog.timestamp >= since).all()
        if t[0] is not None
    ]
    avg_ms = int(sum(times) / len(times)) if times else 0

    # top products
    top_rows = (
        db.query(QueryLog.selected_product, func.count(1))
        .filter(QueryLog.timestamp >= since, QueryLog.selected_product.isnot(None))
        .group_by(QueryLog.selected_product)
        .order_by(func.count(1).desc())
        .limit(10)
        .all()
    )
    top_products = [
        {"product_code": r[0], "count": int(r[1])} for r in top_rows if r[0]
    ]

    # common errors
    err_rows = (
        db.query(QueryLog.error_message, func.count(1))
        .filter(QueryLog.timestamp >= since, QueryLog.success.is_(False), QueryLog.error_message.isnot(None))
        .group_by(QueryLog.error_message)
        .order_by(func.count(1).desc())
        .limit(10)
        .all()
    )
    common_errors = [
        {"error": r[0], "count": int(r[1])} for r in err_rows if r[0]
    ]

    return {
        "period": f"last_{days}_days",
        "total_queries": total,
        "success_rate": (success_count / total) if total else 0.0,
        "avg_response_time_ms": avg_ms,
        "confirmation_rate": (confirm_count / total) if total else 0.0,
        "top_products": top_products,
        "common_errors": common_errors,
    }


@router.get("/data_quality")
def data_quality(db: Session = Depends(get_db)):
    from app.models import Product

    total = db.query(func.count(1)).select_from(Product).scalar() or 0
    with_shot = db.query(func.count(1)).select_from(Product).filter(Product.screenshot_url.isnot(None)).scalar() or 0
    # per-category counts
    rows = db.query(Product.category, func.count(1)).group_by(Product.category).all()
    categories = [{"category": r[0] or "", "count": int(r[1])} for r in rows]
    return {
        "last_updated": None,
        "total_products": int(total),
        "products_with_screenshots": int(with_shot),
        "categories": categories,
    }
