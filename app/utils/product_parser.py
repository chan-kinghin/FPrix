import re
from typing import Tuple, Optional


_CODE_RE = re.compile(r"^\s*([A-Za-z]+)\s*-?\s*(\d+)\s*([A-Za-z]?)\s*$")


def extract_base_code(product_code: str) -> Tuple[str, Optional[str]]:
    """Extract base code and suffix from a product code.

    Examples:
    - "GT10S" -> ("GT10", "S")
    - "GT-10S" -> ("GT10", "S")
    - "GT 10 S" -> ("GT10", "S")
    - "F9970" -> ("F9970", None)
    """
    if not product_code:
        return "", None

    m = _CODE_RE.match(product_code)
    if not m:
        # Fallback: compact everything and attempt simple logic
        compact = re.sub(r"[^A-Za-z0-9]", "", product_code).upper()
        # S or P suffix
        suffix = None
        if compact.endswith("S") or compact.endswith("P"):
            suffix = compact[-1]
            compact = compact[:-1]
        return compact, suffix

    prefix, digits, suffix = m.groups()
    base = f"{prefix.upper()}{digits}"
    suffix = suffix.upper() or None
    return base, suffix


def determine_material(product_code: str, material_column: Optional[str]) -> Optional[str]:
    """Determine material type from code suffix or fallback to material column.

    - S suffix => SILICONE
    - P suffix => PVC
    - else use material_column (normalized)
    """
    base, suffix = extract_base_code(product_code)
    if suffix == "S":
        return "SILICONE"
    if suffix == "P":
        return "PVC"

    if not material_column:
        return None

    material_norm = material_column.strip().upper()
    if any(k in material_norm for k in ["SILICONE", "硅胶", "矽膠", "硅膠"]):
        return "SILICONE"
    if "PVC" in material_norm:
        return "PVC"
    # TPE / 包胶款 inference
    if any(k in material_norm for k in ["TPE", "包胶", "包膠"]):
        return "TPE"
    return None
