#!/usr/bin/env python
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


def load_scenarios(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list), "scenario file must be a JSON array"
    return data


def post_json(client: httpx.Client, url: str, payload: dict) -> Dict[str, Any]:
    r = client.post(url, json=payload, timeout=30)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"raw": r.text}


def write_header(fh, title: str):
    fh.write(f"# {title}\n\n")
    fh.write(f"时间: {datetime.now().isoformat()}\n\n")


def run(api_base: str, scenarios: List[Dict[str, Any]], out_path: Path, auto_confirm: bool = True) -> None:
    api_query = api_base.rstrip("/") + "/api/query"
    api_confirm = api_base.rstrip("/") + "/api/confirm"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        write_header(fh, "场景测试结果（扩展）")

        with httpx.Client() as client:
            for idx, sc in enumerate(scenarios, start=1):
                title = sc.get("title") or f"用例 {idx}"
                query = sc.get("query") or ""
                confirm_choice: Optional[int] = sc.get("confirm_choice")
                fh.write(f"## {idx}) {title}\n")
                fh.write(f"- 请求: `{query}`\n")

                try:
                    resp = post_json(client, api_query, {"query": query})
                except Exception as e:
                    fh.write(f"- 状态: request_failed ({e})\n\n")
                    continue

                status = resp.get("status")
                et = resp.get("error_type")
                fh.write(f"- 状态: {status}{(' ('+et+')') if et else ''}\n\n")
                fh.write("```json\n")
                fh.write(json.dumps(resp, ensure_ascii=False))
                fh.write("\n````\n".replace("````,", "```\n"))

                rt = resp.get("result_text")
                if isinstance(rt, str) and rt:
                    fh.write("\n**result_text（前若干行）**\n\n")
                    for line in rt.splitlines()[:20]:
                        fh.write("    " + line + "\n")
                    fh.write("\n")

                if status == "needs_confirmation" and auto_confirm:
                    opts = resp.get("options") or []
                    conf_id = resp.get("confirmation_id")
                    if opts and conf_id:
                        sel = confirm_choice or 1
                        fh.write(f"- 自动确认选项: {sel}\n\n")
                        try:
                            final = post_json(client, api_confirm, {"confirmation_id": conf_id, "selected_option": sel})
                            fh.write("```json\n")
                            fh.write(json.dumps(final, ensure_ascii=False))
                            fh.write("\n```\n\n")
                            final_rt = final.get("result_text")
                            if isinstance(final_rt, str) and final_rt:
                                fh.write("**确认后 result_text（前若干行）**\n\n")
                                for line in final_rt.splitlines()[:20]:
                                    fh.write("    " + line + "\n")
                                fh.write("\n")
                        except Exception as e:
                            fh.write(f"- 确认失败: {e}\n\n")


if __name__ == "__main__":
    API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
    scenario_file = Path(os.getenv("SCENARIOS", "docs/scenarios_cn.json"))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(f"docs/SCENARIO_TEST_RESULTS_EXT_{ts}.md")
    scs = load_scenarios(scenario_file)
    run(API_BASE, scs, out, auto_confirm=True)
    print(out)

