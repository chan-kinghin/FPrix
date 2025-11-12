from __future__ import annotations

import asyncio
import time
import logging
from typing import Any

from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
import xmltodict

from app.core.database import SessionLocal
from app.services.query_processor import process_query
from app.services.wework_service import get_wework_service
from app.utils.message_cache import message_cache


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wework", tags=["WeChat Work"])


@router.get("/callback")
async def wework_verify(msg_signature: str, timestamp: str, nonce: str, echostr: str):
    """WeChat Work URL verification."""
    try:
        service = get_wework_service()
        reply = service.verify_url(msg_signature, timestamp, nonce, echostr)
        # Must return plain text echo
        return PlainTextResponse(content=reply)
    except Exception as e:
        logger.error("WeWork verify failed: %s", e)
        raise HTTPException(status_code=400, detail="verification failed")


@router.post("/callback")
async def wework_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str,
    timestamp: str,
    nonce: str,
):
    """WeChat Work message callback.

    - Fast (< 4s): passive reply (encrypted XML)
    - Slow (>= 4s): return 200 immediately and send active markdown message
    """
    try:
        body = await request.body()
        service = get_wework_service()
        decrypted_xml = service.decrypt_message(body, msg_signature, timestamp, nonce)
        msg_dict = xmltodict.parse(decrypted_xml)["xml"]

        msg_id = msg_dict.get("MsgId") or msg_dict.get("MsgID")
        if msg_id and message_cache.is_duplicate(str(msg_id)):
            return PlainTextResponse(content="")
        if msg_id:
            message_cache.mark_processed(str(msg_id))

        msg_type = msg_dict.get("MsgType", "").lower()
        if msg_type != "text":
            # ignore non-text
            return PlainTextResponse(content="")

        query_text = (msg_dict.get("Content") or "").strip()
        if not query_text:
            return PlainTextResponse(content="")

        from_user = msg_dict.get("FromUserName")
        to_user = msg_dict.get("ToUserName")
        create_time = msg_dict.get("CreateTime", str(int(time.time())))

        logger.info("WeWork query from %s: %s", from_user, query_text)

        try:
            # Run query with 4s timeout in threadpool using its own DB session
            result_text = await asyncio.wait_for(_process_query_in_thread(query_text), timeout=4.0)

            reply_xml = _build_reply_xml(from_user, to_user, result_text, create_time)
            encrypted = service.encrypt_reply(reply_xml, timestamp, nonce)
            return Response(content=encrypted, media_type="text/xml")
        except asyncio.TimeoutError:
            # schedule active message and return immediately
            background_tasks.add_task(_send_active_result, from_user, query_text)
            return PlainTextResponse(content="")
    except Exception as e:
        # Always 200 to avoid retries; log for debugging
        logger.error("WeWork callback error: %s", e, exc_info=True)
        return PlainTextResponse(content="", status_code=200)


def _build_reply_xml(to_user: str, from_user: str, content: str, create_time: str) -> str:
    return (
        f"<xml>"
        f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{create_time}</CreateTime>"
        f"<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{content}]]></Content>"
        f"</xml>"
    )


async def _process_query_in_thread(query: str) -> str:
    """Run process_query in a worker thread with its own DB session."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _process_query_blocking, query)


def _process_query_blocking(query: str) -> str:
    db: Session = SessionLocal()
    try:
        result: dict[str, Any] = process_query(query, db)
        if result.get("status") == "success":
            return result.get("result_text") or "查询成功"
        elif result.get("status") == "needs_confirmation":
            # For chat UX, show options briefly
            opts = result.get("options") or []
            lines = ["需要确认，请选择以下产品："]
            for o in opts:
                lines.append(f"{o.get('id')}. {o.get('product_code')}（{o.get('material','')}）")
            return "\n".join(lines)
        else:
            return f"❌ 查询失败\n\n{result.get('message', '未知错误')}"
    finally:
        db.close()


def _send_active_result(user_id: str, query: str) -> None:
    service = get_wework_service()
    text = _process_query_blocking(query)
    service.send_markdown_message(user_id, text)

