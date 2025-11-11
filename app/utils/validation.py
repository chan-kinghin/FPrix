from typing import Dict, List


def validate_product(product: Dict) -> List[str]:
    """Validate product data and return a list of error messages."""
    errors: List[str] = []

    # Required fields
    if not product.get("product_code"):
        errors.append("Missing product_code")
    if not product.get("material_type"):
        errors.append("Missing material_type")
    if product.get("base_cost") in (None, ""):
        errors.append("Missing base_cost")

    # Suffix vs material consistency
    code = (product.get("product_code") or "").upper()
    material = (product.get("material_type") or "").upper()
    if code.endswith("S") and material and material != "SILICONE":
        errors.append(f"{code}: 'S' suffix but material {material}")
    if code.endswith("P") and material and material != "PVC":
        errors.append(f"{code}: 'P' suffix but material {material}")

    # Price ordering (if present)
    keys = ["base_cost", "A级_标准", "B级_标准", "C级_标准", "D级_标准"]
    values = []
    for k in keys:
        v = product.get(k)
        if v is None:
            values.append(None)
        else:
            try:
                values.append(float(v))
            except Exception:
                errors.append(f"Invalid price for {k}: {v}")
                values.append(None)

    # Only check ordering if all present
    if all(v is not None for v in values):
        ordered = sorted(values)
        if values != ordered:
            errors.append(f"Price ordering violated: {values}")

    # Custom vs standard color
    a_std = product.get("A级_标准")
    a_custom = product.get("A级_定制")
    try:
        if a_std is not None and a_custom is not None:
            if float(a_custom) < float(a_std):
                errors.append("A级: 定制色 price should be ≥ 标准色 price")
    except Exception:
        pass

    return errors

