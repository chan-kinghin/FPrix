from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import httpx


SYSTEM_PROMPT = """你是一个专业的价格查询助手。用户会用中文提问产品价格。

产品代码规则:
- 后缀 "S" 表示 SILICONE (硅胶款)
- 后缀 "P" 表示 PVC 款
- 无后缀可能表示两个版本都存在

定价层级:
- A级: 最优客户
- B级: 二级客户 (红线)
- C级: 一般客户
- D级: 四级客户

颜色类型:
- 标准色: 常规颜色
- 定制色: 客户定制颜色 (价格更高)

任务:
请严格输出JSON，字段如下：
{
  "product_code": "GT10S | GT10P | GT10",
  "tier": "A级 | B级 | C级 | D级 | null",
  "color_type": "标准色 | 定制色 | null",
  "material": "SILICONE | PVC | null"
}
仅返回JSON，不要额外解释。
"""


def _heuristic_extract(query: str) -> Dict[str, Any]:
    q = (query or "").upper()
    result: Dict[str, Any] = {
        "product_code": None,
        "tier": None,
        "color_type": None,
        "material": None,
    }
    m = re.search(r"[A-Z]{1,3}\s*-?\s*\d{1,4}[SP]?", q)
    if m:
        code = re.sub(r"[^A-Z0-9]", "", m.group(0))
        result["product_code"] = code
    if any(k in q for k in ["A级", "A类", " A "]):
        result["tier"] = "A级"
    elif any(k in q for k in ["B级", "B类", " B "]):
        result["tier"] = "B级"
    elif any(k in q for k in ["C级", "C类", " C "]):
        result["tier"] = "C级"
    elif any(k in q for k in ["D级", "D类", " D "]):
        result["tier"] = "D级"
    if any(k in q for k in ["定制", "定制色", "CUSTOM"]):
        result["color_type"] = "定制色"
    elif any(k in q for k in ["标准", "标准色", "STANDARD"]):
        result["color_type"] = "标准色"
    if any(k in q for k in ["硅胶", "SILICONE", "矽膠", "矽胶"]):
        result["material"] = "SILICONE"
    elif "PVC" in q:
        result["material"] = "PVC"
    return result


def _normalize_tier(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().upper()
    mapping = {
        "A": "A级",
        "A级": "A级",
        "B": "B级",
        "B级": "B级",
        "C": "C级",
        "C级": "C级",
        "D": "D级",
        "D级": "D级",
    }
    return mapping.get(v, None)


def _normalize_color(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().upper()
    if any(k in v for k in ["定制", "CUSTOM"]):
        return "定制色"
    if any(k in v for k in ["标准", "STANDARD"]):
        return "标准色"
    return None


def _parse_json_from_text(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


class DeepSeekClient:
    """DeepSeek API client. Falls back to heuristics if API key missing or request fails."""

    def __init__(self, api_key: str | None, base_url: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or None
        if self.api_key and self.api_key.lower() in {"your_deepseek_api_key_here", "changeme", "none"}:
            self.api_key = None
        self.base_url = (base_url or "https://api.deepseek.com/v1").rstrip("/")
        self.model = model or "deepseek-chat"

    def _call_api(self, query: str, timeout: float = 8.0) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            "temperature": 0.0,
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                return None
            data = resp.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            parsed = _parse_json_from_text(content)
            if not isinstance(parsed, dict):
                return None
            out: Dict[str, Any] = {
                "product_code": parsed.get("product_code"),
                "tier": _normalize_tier(parsed.get("tier")),
                "color_type": _normalize_color(parsed.get("color_type")),
                "material": None,
            }
            mat = parsed.get("material")
            if isinstance(mat, str):
                mu = mat.strip().upper()
                if "SILICONE" in mu or "硅" in mu or "矽" in mu:
                    out["material"] = "SILICONE"
                elif "PVC" in mu:
                    out["material"] = "PVC"
            if isinstance(out.get("product_code"), str):
                out["product_code"] = re.sub(r"[^A-Z0-9]", "", str(out["product_code"]).upper())
            return out
        except Exception:
            return None

    def extract_query_params(self, query: str) -> Dict[str, Any]:
        api_result = self._call_api(query)
        if api_result:
            if not api_result.get("product_code"):
                h = _heuristic_extract(query)
                if h.get("product_code"):
                    api_result["product_code"] = h.get("product_code")
            return api_result
        return _heuristic_extract(query)

