from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from app.main import app


class StubService:
    def __init__(self):
        self._verify_reply = "OK"
        self.sent_messages: list[tuple[str, str]] = []

    # Router expects these methods
    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        return self._verify_reply

    def decrypt_message(self, post_data: bytes, msg_signature: str, timestamp: str, nonce: str) -> str:
        # Default: return text message xml
        return (
            "<xml>"
            "<ToUserName><![CDATA[toUser]]></ToUserName>"
            "<FromUserName><![CDATA[user1]]></FromUserName>"
            "<CreateTime>1699999999</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[GT10S 价格]]></Content>"
            "<MsgId>1234567890</MsgId>"
            "</xml>"
        )

    def encrypt_reply(self, reply_xml: str, timestamp: str, nonce: str) -> str:
        # Echo a stub encrypted payload
        return "<encrypted>ok</encrypted>"

    def send_markdown_message(self, user_id: str, content: str) -> dict:
        self.sent_messages.append((user_id, content))
        return {"errcode": 0, "errmsg": "ok"}


def test_wework_verify_ok(monkeypatch):
    # Patch service factory
    from app.api.routes import wework as r

    stub = StubService()
    monkeypatch.setattr(r, "get_wework_service", lambda: stub)

    client = TestClient(app)
    resp = client.get(
        "/wework/callback",
        params={
            "msg_signature": "sig",
            "timestamp": "1",
            "nonce": "n",
            "echostr": "e",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "OK"


def test_wework_post_fast_path(monkeypatch):
    from app.api.routes import wework as r

    stub = StubService()
    monkeypatch.setattr(r, "get_wework_service", lambda: stub)

    # Force fast result
    async def _fast(query: str) -> str:
        return "RESULT"

    monkeypatch.setattr(r, "_process_query_in_thread", _fast)

    client = TestClient(app)
    resp = client.post(
        "/wework/callback?msg_signature=s&timestamp=1&nonce=n",
        data=b"ignored",
        headers={"Content-Type": "text/xml"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/xml")
    assert resp.text == "<encrypted>ok</encrypted>"


def test_wework_post_timeout_active(monkeypatch):
    from app.api.routes import wework as r

    stub = StubService()
    monkeypatch.setattr(r, "get_wework_service", lambda: stub)

    # Make wait_for raise TimeoutError to exercise active path
    def _raise_timeout(awaitable, timeout):  # signature matches asyncio.wait_for
        # Prevent un-awaited coroutine warnings
        try:
            awaitable.close()  # type: ignore[attr-defined]
        except Exception:
            pass
        raise asyncio.TimeoutError()

    monkeypatch.setattr(r.asyncio, "wait_for", _raise_timeout)

    # Replace background task target with a stub that records invocation
    calls: list[tuple[str, str]] = []

    def _bg(user_id: str, query: str) -> None:
        calls.append((user_id, query))

    monkeypatch.setattr(r, "_send_active_result", _bg)

    # Execute background tasks immediately for deterministic testing
    import starlette.background

    orig_add_task = starlette.background.BackgroundTasks.add_task

    def _immediate(self, func, *args, **kwargs):
        func(*args, **kwargs)

    monkeypatch.setattr(starlette.background.BackgroundTasks, "add_task", _immediate)

    # Ensure not treated as duplicate by cache
    class _NoDup:
        def is_duplicate(self, msg_id: str) -> bool:
            return False

        def mark_processed(self, msg_id: str) -> None:
            pass

    monkeypatch.setattr(r, "message_cache", _NoDup())

    client = TestClient(app)
    resp = client.post(
        "/wework/callback?msg_signature=s&timestamp=1&nonce=n",
        data=b"ignored",
        headers={"Content-Type": "text/xml"},
    )
    assert resp.status_code == 200
    # Passive body is empty on timeout path
    assert resp.text == ""
    # Background task executed immediately
    assert calls and calls[0][0] == "user1"


def test_wework_post_non_text_ignored(monkeypatch):
    from app.api.routes import wework as r

    class StubNonText(StubService):
        def decrypt_message(self, post_data: bytes, msg_signature: str, timestamp: str, nonce: str) -> str:
            return (
                "<xml>"
                "<ToUserName><![CDATA[toUser]]></ToUserName>"
                "<FromUserName><![CDATA[user1]]></FromUserName>"
                "<CreateTime>1699999999</CreateTime>"
                "<MsgType><![CDATA[image]]></MsgType>"
                "<PicUrl><![CDATA[url]]></PicUrl>"
                "<MsgId>111</MsgId>"
                "</xml>"
            )

    stub = StubNonText()
    monkeypatch.setattr(r, "get_wework_service", lambda: stub)

    client = TestClient(app)
    resp = client.post(
        "/wework/callback?msg_signature=s&timestamp=1&nonce=n",
        data=b"ignored",
        headers={"Content-Type": "text/xml"},
    )
    assert resp.status_code == 200
    assert resp.text == ""


def test_wework_post_duplicate_ignored(monkeypatch):
    from app.api.routes import wework as r

    stub = StubService()
    monkeypatch.setattr(r, "get_wework_service", lambda: stub)

    class FakeCache:
        def __init__(self):
            self.count = 0

        def is_duplicate(self, msg_id: str) -> bool:
            self.count += 1
            # First call: not dup; Second call: dup
            return self.count >= 2

        def mark_processed(self, msg_id: str) -> None:
            pass

    monkeypatch.setattr(r, "message_cache", FakeCache())

    client = TestClient(app)

    # First request processes normally (fast path forced for determinism)
    async def _fast(query: str) -> str:
        return "RESULT"

    monkeypatch.setattr(r, "_process_query_in_thread", _fast)

    resp1 = client.post(
        "/wework/callback?msg_signature=s&timestamp=1&nonce=n",
        data=b"ignored",
        headers={"Content-Type": "text/xml"},
    )
    assert resp1.status_code == 200

    # Second request treated as duplicate and ignored
    resp2 = client.post(
        "/wework/callback?msg_signature=s&timestamp=1&nonce=n",
        data=b"ignored",
        headers={"Content-Type": "text/xml"},
    )
    assert resp2.status_code == 200
    assert resp2.text == ""
