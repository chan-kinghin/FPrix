from __future__ import annotations

from typing import Any, Dict

from app.models import Product, PricingTier
from pathlib import Path
from typing import Optional

try:  # optional dependency for computing highlight on-the-fly
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover
    pdfplumber = None  # type: ignore


def format_success_response(
    product: Product,
    pricing: PricingTier | None,
    screenshot_url: str | None,
    all_pricing: list[PricingTier] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    title = f"**产品：{product.product_code} {product.product_name_cn or ''} {product.material_type}**".strip()
    price_line = "价格：未知"
    data: Dict[str, Any] = {
        "product_code": product.product_code,
        "material": product.material_type,
        "category": product.category,
        "subcategory": product.subcategory,
        "tier": None,
        "color_type": None,
        "price": None,
        "source": {
            "pdf": product.source_pdf,
            "page": product.source_page,
        },
    }
    checks: Dict[str, Any] = {
        "code_found": False,
        "row_located": False,
        "cost_anchor": False,
        "column_ordinal": False,
        "fallback_nearest": False,
        "value_match": False,
    }
    if pricing is not None:
        data.update({
            "tier": pricing.tier,
            "color_type": pricing.color_type,
            "price": float(pricing.price),
        })
        price_line = f"价格：${float(pricing.price):.2f} USD ({pricing.tier}{pricing.color_type})"
    elif all_pricing:
        # Build a compact table for all tiers/colors
        rows = []
        for p in sorted(all_pricing, key=lambda x: (x.tier, x.color_type)):
            try:
                rows.append(f"- {p.tier}{p.color_type}: ${float(p.price):.2f} USD")
            except Exception:
                continue
        price_line = "\n".join(["价格一览:"] + rows) if rows else "价格：未知"
        # expose structured list in data
        data["prices"] = [
            {
                "tier": p.tier,
                "color_type": p.color_type,
                "price": float(p.price),
            }
            for p in all_pricing
        ]

    source_line = f"来源：{product.source_pdf} (第{product.source_page}页)"
    # include highlight metadata if available in notes JSON
    code_highlight: Optional[dict] = None
    try:
        import json as _json
        if product.notes:
            j = _json.loads(product.notes)
            code_highlight = j.get("highlight") if isinstance(j, dict) else None
    except Exception:
        code_highlight = None
    if code_highlight is None:
        # Fallback: compute highlight from PDF on-the-fly for product_code/base_code
        try:
            if pdfplumber is not None and product.source_pdf and product.source_page:
                pdf_path = Path("data/pdfs") / product.source_pdf
                if pdf_path.exists():
                    with pdfplumber.open(str(pdf_path)) as doc:
                        page = doc.pages[max(0, int(product.source_page) - 1)]
                        def _norm(s: str) -> str:
                            return "".join(ch for ch in (s or "").upper() if ch.isalnum())
                        cands = []
                        if product.product_code:
                            cands.append(_norm(product.product_code))
                        if getattr(product, "base_code", None):
                            cands.append(_norm(product.base_code))
                        box: Optional[dict] = None
                        words = page.extract_words() or []
                        for cand in cands:
                            for w in words:
                                if _norm(w.get("text", "")) == cand:
                                    x0, y0, x1, y1 = w["x0"], w["top"], w["x1"], w["bottom"]
                                    scale = 300.0 / 72.0
                                    x, y, width, height = int(x0 * scale), int(y0 * scale), int((x1 - x0) * scale), int((y1 - y0) * scale)
                                    box = {"x": x, "y": y, "w": width, "h": height, "page": int(product.source_page)}
                                    break
                            if box:
                                break
                        code_highlight = box
        except Exception:
            code_highlight = None
    if code_highlight:
        checks["code_found"] = True
    # Try to compute price highlight if pricing value present
    price_highlight: Optional[dict] = None
    try:
        if pdfplumber is not None and pricing is not None and product.source_pdf and product.source_page:
            pdf_path = Path("data/pdfs") / product.source_pdf
            if pdf_path.exists():
                with pdfplumber.open(str(pdf_path)) as doc:
                    page = doc.pages[max(0, int(product.source_page) - 1)]
                    words = page.extract_words() or []
                    def _normnum(s: str) -> Optional[float]:
                        try:
                            t = "".join(ch for ch in s if (ch.isdigit() or ch == '.'))
                            if not t:
                                return None
                            if t.endswith('.'):
                                t = t[:-1]
                            return float(t)
                        except Exception:
                            return None
                    price_val = float(pricing.price)
                    # Determine row by code highlight
                    code_y = None
                    if code_highlight:
                        code_y = code_highlight.get("y") + (code_highlight.get("h") or 0) / 2
                    # Build row tokens near code_y
                    row = []
                    if code_y is not None:
                        for w in words:
                            y0, y1 = w.get("top", 0.0), w.get("bottom", 0.0)
                            cy = (y0 + y1) / 2.0
                            # Tolerance ~ 10 px at 300 DPI in image space -> in PDF points scale back
                            # Since we scaled to 300 DPI for boxes, here just compare in PDF space; allow 3 points
                            if abs(cy - (code_y / (300.0/72.0))) <= 3.5:
                                row.append(w)
                        if row:
                            checks["row_located"] = True
                    # Choose by row ordinal if possible
                    chosen = None
                    chosen_val: Optional[float] = None
                    if row:
                        row_num = []
                        for w in row:
                            val = _normnum(w.get("text", ""))
                            if val is None:
                                continue
                            if 0.05 <= val <= 10.0:
                                row_num.append(w)
                        row_num.sort(key=lambda w: w.get("x0", 0.0))
                        # Map ordinal by tier/color after cost
                        tier_map = {"A级": 1, "B级": 2, "C级": 3, "D级": 4}
                        ord_after_cost = tier_map.get(pricing.tier or "", 0)
                        if (pricing.color_type or "") == "定制色":
                            ord_after_cost += 4
                        # find cost index by matching base_cost if present
                        cost_idx = 0
                        try:
                            base_cost = float(product.base_cost or 0)
                            for i, w in enumerate(row_num):
                                v = _normnum(w.get("text", ""))
                                if v is not None and abs(v - base_cost) < 1e-6:
                                    cost_idx = i
                                    checks["cost_anchor"] = True
                                    break
                        except Exception:
                            pass
                        target_idx = cost_idx + ord_after_cost
                        if 0 <= target_idx < len(row_num):
                            w = row_num[target_idx]
                            v = _normnum(w.get("text", ""))
                            if v is not None:
                                x0, y0, x1, y1 = w["x0"], w["top"], w["x1"], w["bottom"]
                                scale = 300.0 / 72.0
                                x, y, width, height = int(x0 * scale), int(y0 * scale), int((x1 - x0) * scale), int((y1 - y0) * scale)
                                chosen = {"x": x, "y": y, "w": width, "h": height, "page": int(product.source_page)}
                                chosen_val = v
                                checks["column_ordinal"] = True
                    # Fallback to nearest by value and row proximity
                    if chosen is None:
                        best = None
                        best_pen = 1e9
                        for w in words:
                            val = _normnum(w.get("text", ""))
                            if val is None:
                                continue
                            if abs(val - price_val) < 1e-6:
                                x0, y0, x1, y1 = w["x0"], w["top"], w["x1"], w["bottom"]
                                scale = 300.0 / 72.0
                                x, y, width, height = int(x0 * scale), int(y0 * scale), int((x1 - x0) * scale), int((y1 - y0) * scale)
                                pen = 0.0
                                if code_y is not None:
                                    cy = y + height / 2
                                    pen += abs(cy - code_y)
                                # prefer more rightward values slightly to avoid cost match
                                pen += (x * 0.0001)
                                if pen < best_pen:
                                    best_pen = pen
                                    best = {"x": x, "y": y, "w": width, "h": height, "page": int(product.source_page)}
                                    chosen_val = val
                        chosen = best
                        if chosen is not None:
                            checks["fallback_nearest"] = True
                    price_highlight = chosen
                    if chosen_val is not None and abs(chosen_val - price_val) < 1e-6:
                        checks["value_match"] = True
    except Exception:
        price_highlight = None

    if code_highlight or price_highlight:
        # primary 'highlight' prefers price if available
        primary = price_highlight or code_highlight
        if primary:
            data["highlight"] = {"filename": screenshot_url, **primary}
        # also include a list of highlights for consumers: [code, price]
        hs = []
        if code_highlight:
            hs.append({"type": "code", "filename": screenshot_url, **code_highlight})
        if price_highlight:
            hs.append({"type": "price", "filename": screenshot_url, **price_highlight})
        if hs:
            data["highlights"] = hs

    # Attach checks for QA/debugging
    data["checks"] = checks

    md = f"{title}\n\n{price_line}\n\n来源：{product.source_pdf} (第{product.source_page}页)"
    return md, md, data


def format_confirmation_response(matches: list[dict], confirmation_id: str) -> dict:
    return {
        "status": "needs_confirmation",
        "message": "找到多个匹配产品，请确认您要查询的是哪一个：",
        "options": matches,
        "confirmation_id": confirmation_id,
    }


def format_error_response(error_type: str, message: str, suggestions: list[str] | None, ms: int) -> dict:
    return {
        "status": "error",
        "error_type": error_type,
        "message": message,
        "suggestions": suggestions,
        "execution_time_ms": ms,
    }
