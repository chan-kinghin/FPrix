from __future__ import annotations

import re
from typing import Optional


def infer_material_from_query(query: str) -> Optional[str]:
    """Infer material (SILICONE/PVC) from free-text query.

    Rules:
    - Keywords: 硅胶/矽膠/silicone -> SILICONE; pvc -> PVC
    - Suffix in an inline code token: ...S -> SILICONE; ...P -> PVC
    """
    q = (query or "").strip()
    uq = q.upper()

    if any(k in uq for k in ["硅胶", "矽膠", "矽胶", "SILICONE"]):
        return "SILICONE"
    if "PVC" in uq:
        return "PVC"
    if any(k in uq for k in ["TPE", "包胶", "包膠"]):
        return "TPE"

    # Look for product-like token to infer suffix
    m = re.search(r"([A-Z]{1,3}\s*-?\s*\d{1,4}\s*[SP])\b", uq)
    if m:
        token = re.sub(r"[^A-Z0-9]", "", m.group(1))
        if token.endswith("S"):
            return "SILICONE"
        if token.endswith("P"):
            return "PVC"

    return None
