from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models import Product
from app.services.fuzzy_match import normalize_product_code
from app.services.product_name_matcher import match_product_by_description


DEFAULT_TIER = "C级"
DEFAULT_COLOR = "标准色"

CATEGORY_KEYS = {
    "泳镜": "泳镜",
    "潜水镜": "潜水镜",
    "呼吸管": "呼吸管",
    "蛙鞋": "蛙鞋",
    "帽子": "帽子配件",
}


class WideQueryParams:
    def __init__(self) -> None:
        self.mode: str = ""  # compare_gt, compare_lt, top_desc, top_asc
        self.ref_code: Optional[str] = None
        self.ref_products: List[Product] = []  # Multiple reference products (for description-based queries)
        self.description_query: Optional[str] = None  # Original query text for description matching
        self.category: Optional[str] = None
        self.limit: int = 10
        self.tier: str = DEFAULT_TIER
        self.color: str = DEFAULT_COLOR
        self.min_price: Optional[float] = None
        self.max_price: Optional[float] = None


def detect_wide_query(query: str) -> Optional[WideQueryParams]:
    q = (query or "").strip()
    if not q:
        return None
    uq = q.upper()
    params = WideQueryParams()

    # category
    for k, v in CATEGORY_KEYS.items():
        if k in q:
            params.category = v
            break

    # limit
    m = re.search(r"(?:前|TOP)\s*(\d{1,3})", q, re.IGNORECASE)
    if m:
        try:
            params.limit = max(1, min(50, int(m.group(1))))
        except Exception:
            pass

    code_pat = re.compile(r"([A-Z]{1,3})\s*-?\s*(\d{1,4})([SP])?", re.IGNORECASE)
    num_first_pat = re.compile(r"\b(\d{2,6}[SP]?)\b", re.IGNORECASE)
    if "比" in q and ("贵" in q or "便宜" in q):
        # First try to extract product code
        m2 = code_pat.search(uq) or num_first_pat.search(uq)
        if m2:
            g = m2.groups() if hasattr(m2, "groups") else (m2.group(1),)
            code = normalize_product_code("".join([x or "" for x in g]))
            params.ref_code = code
            params.mode = "compare_gt" if ("贵" in q) else "compare_lt"
            return params
        else:
            # No product code found, store query for description-based matching
            # This will be resolved later when we have database access
            params.description_query = q
            params.mode = "compare_gt" if ("贵" in q) else "compare_lt"
            return params

    # price range: 0.8~1.0 or 0.8-1.0
    m_rng = re.search(r"(\d+(?:\.\d+)?)\s*[~-]\s*(\d+(?:\.\d+)?)", q)
    if m_rng:
        try:
            a = float(m_rng.group(1)); b = float(m_rng.group(2))
            params.min_price, params.max_price = (min(a,b), max(a,b))
            params.mode = "range"
            return params
        except Exception:
            pass

    if any(k in q for k in ["最贵", "贵的"]):
        params.mode = "top_desc"
        return params
    if any(k in q for k in ["最便宜", "便宜的"]):
        params.mode = "top_asc"
        return params
    return None


def run_wide_search(db: Session, params: WideQueryParams) -> Dict[str, Any]:
    title = "查询结果"
    bind = db.get_bind()
    where_cat = " AND p.category = :cat" if params.category else ""

    def _format(rows: List[Dict[str, Any]], extra: Dict[str, Any]) -> Dict[str, Any]:
        if not rows:
            return {"status": "error", "error_type": "no_results", "message": "未找到符合条件的产品。"}
        lines = [title]

        # Add reference product info if available
        if "ref_products" in extra:
            lines.append("\n**参考产品：**")
            for ref in extra["ref_products"]:
                ref_name = ref.get("name", "")
                name_str = f" ({ref_name})" if ref_name else ""
                lines.append(f"- {ref['code']}{name_str} — ${ref['price']:.2f}")
            lines.append("")  # Empty line for spacing

        for i, r in enumerate(rows, start=1):
            # Include product name if available (for description-based queries)
            product_name = r.get('product_name_cn', '')
            name_str = f" ({product_name})" if product_name else ""

            # Include delta if available (for comparison queries)
            if 'delta' in r:
                delta_str = f" (节省 ${abs(r['delta']):.2f})" if r['delta'] < 0 else f" (贵 ${r['delta']:.2f})"
            else:
                delta_str = ""

            lines.append(f"{i}. {r['product_code']}{name_str} — ${r['price']:.2f}{delta_str} [{r['category']}]")

        md = "\n".join(lines)
        return {
            "status": "success",
            "result_text": md,
            "result_markdown": md,
            "screenshot_url": None,
            "data": {
                "results": rows,
                "mode": params.mode,
                "tier": params.tier,
                "color_type": params.color,
                "category": params.category,
                "limit": params.limit,
                **extra,
            },
            "confidence": 0.75,
            "execution_time_ms": 0,
        }

    if params.mode in ("compare_gt", "compare_lt"):
        # Handle description-based queries (no product code)
        if params.description_query and not params.ref_code:
            # Find products matching the description
            matches = match_product_by_description(db, params.description_query, threshold=0.70)
            if not matches:
                return {
                    "status": "error",
                    "error_type": "reference_not_found",
                    "message": "未找到匹配描述的产品。请尝试使用产品代码或更具体的描述。"
                }

            # Store matched products for later use
            params.ref_products = [prod for prod, score in matches]

            # Get prices for all reference products
            ref_prices = []
            ref_info = []
            with bind.connect() as conn:
                for ref_prod in params.ref_products:
                    rp = conn.execute(
                        text("SELECT pick_price(:pid, :tier, :color) AS rp"),
                        {"pid": ref_prod.product_id, "tier": params.tier, "color": params.color},
                    ).scalar()
                    if rp is not None:
                        ref_prices.append(float(rp))
                        ref_info.append({"code": ref_prod.product_code, "price": float(rp), "name": ref_prod.product_name_cn})

            if not ref_prices:
                codes = ", ".join([p.product_code for p in params.ref_products])
                return {
                    "status": "error",
                    "error_type": "reference_not_found",
                    "message": f"参考产品 {codes} 价格缺失。"
                }

            # Use the highest reference price for "cheaper" or lowest for "more expensive"
            # This ensures we find products cheaper than ALL references or more expensive than ALL
            rp = max(ref_prices) if params.mode == "compare_lt" else min(ref_prices)

            comp_op = ">" if params.mode == "compare_gt" else "<"
            order_dir = "DESC" if params.mode == "compare_gt" else "ASC"

            sql = f"""
                SELECT p.product_code, p.category, p.material_type, p.screenshot_url, p.product_name_cn,
                       x.price, (x.price - :rp) AS delta
                FROM products p
                CROSS JOIN LATERAL (SELECT pick_price(p.product_id, :tier, :color) AS price) AS x
                WHERE x.price IS NOT NULL{where_cat} AND x.price {comp_op} :rp
                ORDER BY (x.price - :rp) {order_dir}
                LIMIT :limit
            """
            conn = bind.connect()
            try:
                res = conn.execute(text(sql), {"tier": params.tier, "color": params.color, "rp": rp, "limit": params.limit, "cat": params.category})
                rows = [
                    {
                        "product_code": r[0],
                        "category": r[1],
                        "material": r[2],
                        "screenshot_url": r[3],
                        "product_name_cn": r[4],
                        "price": float(r[5]),
                        "delta": float(r[6]),
                        "tier": params.tier,
                        "color_type": params.color,
                    }
                    for r in res.fetchall()
                ]
            finally:
                conn.close()

            # Build title showing all reference products
            ref_codes_str = ", ".join([info["code"] for info in ref_info])
            title = f"比 {ref_codes_str} {'更贵' if params.mode=='compare_gt' else '更便宜'}的{params.category or ''}（{params.tier}{params.color}）".strip()
            return _format(rows, {"ref_products": ref_info})

        # Handle traditional code-based queries
        elif params.ref_code:
            ref_code = params.ref_code
            ref = db.query(Product).filter(Product.product_code == ref_code).first()
            if not ref:
                base = re.sub(r"[SP]$", "", ref_code)
                ref = (
                    db.query(Product)
                    .filter(Product.product_code.in_([base + "S", base + "P", base]))
                    .first()
                )
            if not ref:
                return {"status": "error", "error_type": "reference_not_found", "message": f"参考产品 {ref_code} 未找到。"}
            # SQLAlchemy 2.x: Engine no longer has execute(); use a Connection
            with bind.connect() as conn:
                rp = conn.execute(
                    text("SELECT pick_price(:pid, :tier, :color) AS rp"),
                    {"pid": ref.product_id, "tier": params.tier, "color": params.color},
                ).scalar()
            if rp is None:
                return {"status": "error", "error_type": "reference_not_found", "message": f"参考产品 {ref_code} 价格缺失。"}
            comp_op = ">" if params.mode == "compare_gt" else "<"
            order_dir = "DESC" if params.mode == "compare_gt" else "ASC"
            sql = f"""
                SELECT p.product_code, p.category, p.material_type, p.screenshot_url,
                       x.price, (x.price - :rp) AS delta
                FROM products p
                CROSS JOIN LATERAL (SELECT pick_price(p.product_id, :tier, :color) AS price) AS x
                WHERE x.price IS NOT NULL{where_cat} AND x.price {comp_op} :rp
                ORDER BY (x.price - :rp) {order_dir}
                LIMIT :limit
            """
            conn = bind.connect()
            try:
                res = conn.execute(text(sql), {"tier": params.tier, "color": params.color, "rp": rp, "limit": params.limit, "cat": params.category})
                rows = [
                {
                    "product_code": r[0],
                    "category": r[1],
                    "material": r[2],
                    "screenshot_url": r[3],
                    "price": float(r[4]),
                    "delta": float(r[5]),
                    "tier": params.tier,
                    "color_type": params.color,
                }
                for r in res.fetchall()
            ]
            finally:
                conn.close()
            title = f"比 {ref.product_code} {'更贵' if params.mode=='compare_gt' else '更便宜'}的{params.category or ''}（{params.tier}{params.color}）".strip()
            return _format(rows, {"ref_code": ref.product_code, "ref_price": float(rp)})

    if params.mode in ("top_desc", "top_asc"):
        order_dir = "DESC" if params.mode == "top_desc" else "ASC"
        sql = f"""
            SELECT p.product_code, p.category, p.material_type, p.screenshot_url, x.price
            FROM products p
            CROSS JOIN LATERAL (SELECT pick_price(p.product_id, :tier, :color) AS price) AS x
            WHERE x.price IS NOT NULL{where_cat}
            ORDER BY x.price {order_dir}
            LIMIT :limit
        """
        conn = bind.connect()
        try:
            res = conn.execute(text(sql), {"tier": params.tier, "color": params.color, "limit": params.limit, "cat": params.category})
            rows = [
            {
                "product_code": r[0],
                "category": r[1],
                "material": r[2],
                "screenshot_url": r[3],
                "price": float(r[4]),
                "tier": params.tier,
                "color_type": params.color,
            }
            for r in res.fetchall()
        ]
        finally:
            conn.close()
        title = f"{'最贵' if params.mode=='top_desc' else '最便宜'}的{params.category or ''}（{params.tier}{params.color}）".strip()
        return _format(rows, {})

    if params.mode == "range" and params.min_price is not None and params.max_price is not None:
        sql = f"""
            SELECT p.product_code, p.category, p.material_type, p.screenshot_url, x.price
            FROM products p
            CROSS JOIN LATERAL (SELECT pick_price(p.product_id, :tier, :color) AS price) AS x
            WHERE x.price IS NOT NULL{where_cat} AND x.price BETWEEN :minp AND :maxp
            ORDER BY x.price ASC
            LIMIT :limit
        """
        conn = bind.connect()
        try:
            res = conn.execute(text(sql), {"tier": params.tier, "color": params.color, "limit": params.limit, "cat": params.category, "minp": params.min_price, "maxp": params.max_price})
            rows = [
                {"product_code": r[0], "category": r[1], "material": r[2], "screenshot_url": r[3], "price": float(r[4]), "tier": params.tier, "color_type": params.color}
                for r in res.fetchall()
            ]
        finally:
            conn.close()
        title = f"价格 {params.min_price}-{params.max_price} 的{params.category or ''}（{params.tier}{params.color}）".strip()
        return _format(rows, {})

    return {"status": "error", "error_type": "unsupported_wide_query", "message": "未识别的范围查询表达。"}
