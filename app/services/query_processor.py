from __future__ import annotations

import time
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Product, PricingTier
from app.services.deepseek import DeepSeekClient
from app.services.fuzzy_match import (
    normalize_product_code,
    exact_match,
    base_code_match,
    fuzzy_string_match,
)
from app.services.response_formatter import (
    format_success_response,
)
from app.services.wide_search import detect_wide_query, run_wide_search
from app.services.confirmation import (
    generate_confirmation_id,
    save_confirmation,
    needs_confirmation,
)
from app.utils.inference import infer_material_from_query


def process_query(query: str, db: Session) -> Dict[str, Any]:
    t0 = time.time()
    # 1) Wide-search detection (more expensive/cheaper/top-N)
    w = detect_wide_query(query)
    if w is not None:
        result = run_wide_search(db, w)
        result["execution_time_ms"] = int((time.time() - t0) * 1000)
        return result
    ds = DeepSeekClient(settings.DEEPSEEK_API_KEY)
    params = ds.extract_query_params(query)
    if not params.get("material"):
        inferred = infer_material_from_query(query)
        if inferred:
            params["material"] = inferred

    code = params.get("product_code")
    if not code:
        ms = int((time.time() - t0) * 1000)
        return {
            "status": "error",
            "error_type": "missing_product_code",
            "message": "未检测到产品代码，请提供产品代码再试。",
            "execution_time_ms": ms,
        }

    norm = normalize_product_code(code)
    # level 1
    matches, conf = exact_match(db, norm)
    # If exact match is a base code without suffix and there are variants, require confirmation
    if matches and len(matches) == 1:
        m = matches[0]
        if not (m.product_code.endswith("S") or m.product_code.endswith("P")):
            base_variants, _ = base_code_match(db, norm)
            # filter variants that are not the base code itself
            variants = [p for p in base_variants if p.product_code != m.product_code]
            if variants:
                matches = variants
                conf = 0.95
    if not matches:
        # level 2: base code
        matches, conf = base_code_match(db, norm)
    need_confirm = False
    selected = None
    confidence = conf
    if len(matches) == 1 and conf == 1.0:
        selected = matches[0]
    elif needs_confirmation(len(matches), conf):
        need_confirm = True
    else:
        # fuzzy
        fuzzy = fuzzy_string_match(db, norm)
        if fuzzy:
            need_confirm = True
            matches = [p for p, _ in fuzzy]
            confidence = fuzzy[0][1]
        else:
            ms = int((time.time() - t0) * 1000)
            return {
                "status": "error",
                "error_type": "product_not_found",
                "message": "未找到匹配的产品。请检查产品代码是否正确。",
                "suggestions": [],
                "execution_time_ms": ms,
            }

    if need_confirm:
        # filter by material if inferred
        material = params.get("material")
        if material:
            filtered = [p for p in matches if p.material_type == material]
            if filtered:
                matches = filtered
        opts = []
        for i, p in enumerate(matches, start=1):
            opts.append(
                {
                    "id": str(i),
                    "product_code": p.product_code,
                    "material": p.material_type,
                    "category": p.category,
                    "confidence": confidence,
                    "match_reason": "模糊匹配" if confidence < 1.0 else "找到基础代码的多个版本",
                }
            )
        conf_id = generate_confirmation_id()
        # persist confirmation options; fall back to in-memory if DB commit fails
        try:
            save_confirmation(conf_id, opts[:5], params, db)
        except Exception:
            save_confirmation(conf_id, opts[:5], params, None)
        ms = int((time.time() - t0) * 1000)
        return {
            "status": "needs_confirmation",
            "message": "找到多个匹配产品，请确认您要查询的是哪一个：",
            "options": opts[:5],
            "confirmation_id": conf_id,
            "execution_time_ms": ms,
        }

    # Direct match
    product = selected
    tier = params.get("tier")
    color = params.get("color_type") or "标准色"
    pricing: PricingTier | None = None
    all_prices: list[PricingTier] | None = None
    # resolve pricing with sensible defaults and fallback
    if tier:
        try_colors = [color] if color else ["标准色", "定制色"]
        if "标准" not in "".join(try_colors) and "定制" not in "".join(try_colors):
            try_colors = ["标准色", "定制色"]
        for c in try_colors:
            rec = (
                db.query(PricingTier)
                .filter(
                    PricingTier.product_id == product.product_id,
                    PricingTier.tier == tier,
                    PricingTier.color_type == c,
                )
                .order_by(PricingTier.effective_date.desc())
                .first()
            )
            if rec is not None:
                pricing = rec
                color = c
                break
    else:
        # Ambiguous query (no tier provided): return full price list
        all_prices = (
            db.query(PricingTier)
            .filter(PricingTier.product_id == product.product_id)
            .order_by(PricingTier.tier, PricingTier.color_type)
            .all()
        )

    md_text, md_markdown, data = format_success_response(product, pricing, product.screenshot_url, all_prices)
    ms = int((time.time() - t0) * 1000)
    return {
        "status": "success",
        "result_text": md_text,
        "result_markdown": md_markdown,
        "screenshot_url": product.screenshot_url,
        "data": data,
        "confidence": confidence,
        "execution_time_ms": ms,
    }
