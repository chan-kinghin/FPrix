from __future__ import annotations

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import QueryRequest
from app.core.database import get_db
from app.services.query_processor import process_query
from app.services.logger import log_query
from app.services.confirmation import get_confirmation, pop_confirmation
from app.services.response_formatter import format_success_response
from app.models import Product, PricingTier


router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query")
def query_endpoint(req: QueryRequest, request: Request, db: Session = Depends(get_db)):
    result = process_query(req.query, db)
    # fire-and-forget logging (synchronous here, but errors ignored)
    try:
        query_data = {
            "query_text": req.query,
            "result_text": result.get("result_text"),
            "result_data": result.get("data"),
            "screenshot_url": result.get("screenshot_url"),
            "execution_time_ms": result.get("execution_time_ms"),
            "success": result.get("status") == "success",
            "user_session": req.user_session,
            "ip_address": request.client.host if request.client else None,
            "confirmation_required": result.get("status") == "needs_confirmation",
        }
        log_query(db, query_data)
    except Exception:
        # do not block response on logging errors
        pass

    return result


@router.post("/confirm")
def confirm_endpoint(payload: dict, db: Session = Depends(get_db)):
    conf_id = payload.get("confirmation_id")
    selected = payload.get("selected_option")
    if not conf_id or not selected:
        raise HTTPException(status_code=400, detail="Missing confirmation_id or selected_option")

    session = pop_confirmation(conf_id, db)
    if not session:
        raise HTTPException(status_code=404, detail="Confirmation not found or expired")

    try:
        opt = next(o for o in session.options if o.get("id") == str(selected))
    except StopIteration:
        raise HTTPException(status_code=400, detail="Invalid selected_option")

    code = opt.get("product_code")
    product = db.query(Product).filter(Product.product_code == code).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    tier = session.params.get("tier")
    color = session.params.get("color_type")
    pricing = None
    if tier and color:
        pricing = (
            db.query(PricingTier)
            .filter(
                PricingTier.product_id == product.product_id,
                PricingTier.tier == tier,
                PricingTier.color_type == color,
            )
            .order_by(PricingTier.effective_date.desc())
            .first()
        )

    md_text, md_markdown, data = format_success_response(product, pricing, product.screenshot_url)
    return {
        "status": "success",
        "result_text": md_text,
        "result_markdown": md_markdown,
        "screenshot_url": product.screenshot_url,
        "data": data,
        "confidence": opt.get("confidence", 1.0),
        "execution_time_ms": 0,
    }
