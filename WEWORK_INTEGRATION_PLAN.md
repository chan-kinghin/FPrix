# WeChat Work Integration - Implementation Plan

## Executive Summary

Integrate CostChecker with WeChat Work (企业微信) to enable natural language price queries via enterprise chat interface.

**Goal**: Enable end users to query product prices through WeChat Work chat while maintaining the existing REST API for admin use.

**Key Insight**: The existing system already provides perfectly formatted markdown output in `result_text`. We only need to add the WeChat Work interface layer - no new formatting code required.

**Timeline**: 1-2 weeks (15-20 hours total)

**Risk Level**: Low (purely additive - no modifications to existing code)

---

## Architecture Overview

### System Design

```
┌────────────────────────────────────────────────────────────────┐
│                          User Layer                            │
├──────────────────────────┬─────────────────────────────────────┤
│   WeChat Work Users      │   Admin/API Users                   │
│   - Chat interface       │   - Direct HTTP calls               │
│   - Natural language     │   - Admin dashboard                 │
└────────────┬─────────────┴──────────────┬──────────────────────┘
             │                            │
             ↓                            ↓
┌────────────────────────┐   ┌───────────────────────────────────┐
│  WeChat Work Layer     │   │  REST API Layer (existing)        │
│  (NEW - THIS PROJECT)  │   │  - /api/query                     │
│                        │   │  - /api/confirm                   │
│  - /wework/callback    │   │  - /api/analytics                 │
│  - Encrypt/Decrypt     │   │  - /admin dashboard               │
│  - Timeout handling    │   │                                   │
└────────────┬───────────┘   └───────────────┬───────────────────┘
             │                                │
             └────────────────┬───────────────┘
                              ↓
             ┌────────────────────────────────────────────┐
             │  Query Processing Engine (REUSE AS-IS)     │
             │  - query_processor.py                      │
             │  - wide_search.py                          │
             │  - fuzzy_match.py                          │
             │  - response_formatter.py                   │
             │                                            │
             │  Already returns: result_text (markdown)  │
             └────────────────────────────────────────────┘
```

### Message Flow

```
User sends "比 GT10S 便宜的" in WeChat Work
         ↓
WeChat Work Server encrypts message (XML)
         ↓
POST /wework/callback (encrypted)
         ↓
Decrypt message → Extract text
         ↓
Call existing: process_query(query, db)
         ↓
Get back: result["result_text"] (already formatted!)
         ↓
Fast (<4s)?  ──YES──> Encrypt as XML → Return passive reply
         │
         NO
         ↓
Return 200 empty immediately
         ↓
Background task: Send active message via WeChat API
```

---

## Implementation Stages

### Stage 1: Dependencies & Configuration (2 hours)

#### Tasks
- [ ] Install Python dependencies
- [ ] Download official WeChat Work SDK
- [ ] Create configuration module
- [ ] Update environment files

#### 1.1 Install Dependencies

Add to `requirements.txt`:
```
wechatpy==1.8.18
pycryptodome==3.19.0
xmltodict==0.13.0
```

Run:
```bash
pip install -r requirements.txt
```

#### 1.2 Crypto SDK Choice

Use `wechatpy.crypto.WeChatCrypto` (built-in to `wechatpy`) instead of vendoring the official WXBizMsgCrypt scripts. This keeps dependencies simpler and is functionally equivalent for URL verification, decryption, and encryption.

#### 1.3 Configuration Module

Use central settings in `app/core/config.py` (Pydantic BaseSettings). Added:

```
WEWORK_CORP_ID
WEWORK_AGENT_ID
WEWORK_SECRET
WEWORK_TOKEN
WEWORK_ENCODING_AES_KEY
```

Service validates presence and AES key length at runtime.

#### 1.4 Environment Configuration

`.env.example` already updated ✓

Update local `.env` with test credentials.

**Success Criteria**:
- ✅ All dependencies installed
- ✅ SDK files downloaded and importable
- ✅ Configuration validates correctly

---

### Stage 2: Core WeChat Work Service (3-4 hours)

#### Tasks
- [ ] Create WeChat Work service with encryption
- [ ] Create message deduplication cache
- [ ] Test encryption/decryption

#### 2.1 WeChat Work Service

Create `app/services/wework_service.py`:

```python
import logging
from wechatpy.enterprise import WeChatClient
from wechatpy.crypto import WeChatCrypto, PrpCrypto
from wechatpy.exceptions import WeChatException
from app.core.config import settings

logger = logging.getLogger(__name__)


class WeWorkService:
    """WeChat Work service for message encryption and API calls."""

    def __init__(self):
        wework_config.validate()

        # Encryption handler
        self.crypto = WeChatCrypto(
            token=settings.WEWORK_TOKEN,
            encoding_aes_key=settings.WEWORK_ENCODING_AES_KEY,
            app_id=settings.WEWORK_CORP_ID,
        )

        # API client for active messages
        self.client = WeChatClient(
            settings.WEWORK_CORP_ID,
            settings.WEWORK_SECRET,
        )

        logger.info("WeWorkService initialized")

    def verify_url(self, msg_signature: str, timestamp: str,
                   nonce: str, echostr: str) -> str:
        """Verify callback URL (GET request)."""
        # Use internal signature checker
        reply = self.crypto._check_signature(msg_signature, timestamp, nonce, echostr, PrpCrypto)
        return reply.decode("utf-8")

    def decrypt_message(self, post_data: bytes, msg_signature: str,
                       timestamp: str, nonce: str) -> str:
        """Decrypt incoming message."""
        decrypted_xml = self.crypto.decrypt_message(post_data, msg_signature, timestamp, nonce)
        return decrypted_xml.decode('utf-8') if isinstance(decrypted_xml, (bytes, bytearray)) else decrypted_xml

    def encrypt_reply(self, reply_xml: str, timestamp: str,
                     nonce: str) -> str:
        """Encrypt passive reply."""
        return self.crypto.encrypt_message(reply_xml, nonce, timestamp)

    def send_markdown_message(self, user_id: str, content: str) -> dict:
        """Send active markdown message."""
        try:
            response = self.client.message.send_markdown(
                agent_id=wework_config.AGENT_ID,
                user_ids=user_id,
                content=content
            )
            logger.info(f"Message sent to {user_id}")
            return response
        except WeChatException as e:
            logger.error(f"Failed to send message: {e}")
            raise


# Singleton
wework_service = WeWorkService()
```

#### 2.2 Message Cache

Create `app/utils/message_cache.py`:

```python
from datetime import datetime, timedelta
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class MessageCache:
    """In-memory cache for message deduplication."""

    def __init__(self, ttl_seconds: int = 60):
        self._cache: Dict[str, datetime] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def is_duplicate(self, msg_id: str) -> bool:
        """Check if message was processed recently."""
        self._cleanup_expired()

        if msg_id in self._cache:
            logger.info(f"Duplicate: {msg_id}")
            return True

        return False

    def mark_processed(self, msg_id: str):
        """Mark message as processed."""
        self._cache[msg_id] = datetime.now()

    def _cleanup_expired(self):
        """Remove expired entries."""
        now = datetime.now()
        expired = [k for k, v in self._cache.items() if now - v > self._ttl]
        for k in expired:
            del self._cache[k]


# Singleton
message_cache = MessageCache()
```

**Success Criteria**:
- ✅ Service initializes without errors
- ✅ Encryption/decryption methods implemented
- ✅ Message cache works correctly

---

### Stage 3: Callback Endpoints (3-4 hours)

#### Tasks
- [ ] Create WeChat Work router
- [ ] Implement GET verification endpoint
- [ ] Implement POST callback with timeout handling
- [ ] Register router in main app

#### 3.1 WeChat Work Router

Create `app/api/routes/wework.py`:

```python
import asyncio
import time
import logging
from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
import xmltodict

from app.services.wework_service import wework_service
from app.utils.message_cache import message_cache
from app.services.query_processor import process_query
from app.core.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wework", tags=["WeChat Work"])


@router.get("/callback")
async def wework_verify(
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str
):
    """Verify callback URL (GET request from WeChat Work)."""
    try:
        reply = wework_service.verify_url(msg_signature, timestamp, nonce, echostr)
        return PlainTextResponse(content=reply)
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/callback")
async def wework_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    db: Session = Depends(get_db)
):
    """
    Receive and process messages (POST request from WeChat Work).

    Implements 4-second timeout rule:
    - Fast queries (< 4s): Return encrypted passive reply
    - Slow queries (≥ 4s): Return 200 empty, send active message
    """
    try:
        # 1. Decrypt
        post_data = await request.body()
        decrypted_xml = wework_service.decrypt_message(
            post_data, msg_signature, timestamp, nonce
        )

        # 2. Parse XML
        msg_dict = xmltodict.parse(decrypted_xml)
        msg_content = msg_dict['xml']

        # 3. Check duplicate
        msg_id = msg_content.get('MsgId')
        if msg_id and message_cache.is_duplicate(msg_id):
            return PlainTextResponse(content="")

        if msg_id:
            message_cache.mark_processed(msg_id)

        # 4. Extract info
        from_user = msg_content['FromUserName']
        to_user = msg_content['ToUserName']
        msg_type = msg_content.get('MsgType', '')
        create_time = msg_content.get('CreateTime', str(int(time.time())))

        # 5. Handle only text messages
        if msg_type != 'text':
            return PlainTextResponse(content="")

        query_text = msg_content.get('Content', '').strip()
        if not query_text:
            return PlainTextResponse(content="")

        logger.info(f"Query from {from_user}: {query_text}")

        # 6. Process with 4-second timeout
        try:
            result_text = await asyncio.wait_for(
                process_query_async(query_text, db),
                timeout=4.0
            )

            # Fast response - passive reply
            reply_xml = build_reply_xml(from_user, to_user, result_text, create_time)
            encrypted = wework_service.encrypt_reply(reply_xml, timestamp, nonce)

            logger.info("Fast query completed")
            return Response(content=encrypted, media_type="text/xml")

        except asyncio.TimeoutError:
            # Slow query - active message
            logger.info("Timeout - using active message")
            background_tasks.add_task(
                send_active_result, from_user, query_text, db
            )
            return PlainTextResponse(content="")

    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        return PlainTextResponse(content="", status_code=200)


def build_reply_xml(to_user: str, from_user: str,
                   content: str, create_time: str) -> str:
    """Build passive reply XML."""
    return f"""<xml>
        <ToUserName><![CDATA[{to_user}]]></ToUserName>
        <FromUserName><![CDATA[{from_user}]]></FromUserName>
        <CreateTime>{create_time}</CreateTime>
        <MsgType><![CDATA[text]]></MsgType>
        <Content><![CDATA[{content}]]></Content>
    </xml>"""


async def process_query_async(query: str, db: Session) -> str:
    """
    Process query using existing engine.

    IMPORTANT: No additional formatting needed!
    The existing query_processor already returns markdown-formatted
    text in result_text that works perfectly with WeChat Work.
    """
    result = process_query(query, db)

    if result.get("status") == "success":
        # Use existing formatted text as-is
        return result.get("result_text", "查询成功")
    else:
        return f"❌ 查询失败\n\n{result.get('message', '未知错误')}"


async def send_active_result(user_id: str, query: str, db: Session):
    """Background task for slow queries."""
    try:
        result_text = await process_query_async(query, db)
        wework_service.send_markdown_message(user_id, result_text)
        logger.info("Active message sent")
    except Exception as e:
        logger.error(f"Background task error: {e}")
```

#### 3.2 Register Router

In `app/main.py`:
```python
from app.routers import wework

app.include_router(wework.router)
```

**Success Criteria**:
- ✅ GET /wework/callback verifies URL
- ✅ POST /wework/callback handles fast queries
- ✅ POST /wework/callback handles slow queries
- ✅ Duplicates detected and ignored
- ✅ Non-text messages ignored

---

### Stage 4: Testing & Documentation (6-8 hours)

#### Tasks
- [ ] Unit tests for WeChat Work service
- [ ] Integration tests for callbacks
- [ ] Manual testing guide
- [ ] Deployment documentation

#### 4.1 Unit Tests

Create `tests/test_wework_service.py`:

```python
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.services.wework_service import WeWorkService


@pytest.fixture
def mock_config():
    with patch('app.services.wework_service.wework_config') as mock:
        mock.CORP_ID = "test_corp"
        mock.AGENT_ID = 1000001
        mock.SECRET = "test_secret"
        mock.TOKEN = "test_token"
        mock.ENCODING_AES_KEY = "a" * 43
        mock.validate = Mock(return_value=True)
        yield mock


@pytest.fixture
def mock_wxcpt():
    with patch('app.services.wework_service.WXBizMsgCrypt') as MockWXCpt:
        mock_instance = MagicMock()
        MockWXCpt.return_value = mock_instance
        yield mock_instance


def test_verify_url_success(mock_config, mock_wxcpt):
    mock_wxcpt.VerifyURL.return_value = (0, b"decrypted")

    service = WeWorkService()
    result = service.verify_url("sig", "ts", "nonce", "encrypted")

    assert result == "decrypted"


def test_decrypt_message_success(mock_config, mock_wxcpt):
    mock_wxcpt.DecryptMsg.return_value = (0, b"<xml>test</xml>")

    service = WeWorkService()
    result = service.decrypt_message(b"encrypted", "sig", "ts", "nonce")

    assert result == "<xml>test</xml>"


def test_encrypt_reply_success(mock_config, mock_wxcpt):
    mock_wxcpt.EncryptMsg.return_value = (0, b"<xml>encrypted</xml>")

    service = WeWorkService()
    result = service.encrypt_reply("<xml>plain</xml>", "ts", "nonce")

    assert result == "<xml>encrypted</xml>"
```

#### 4.2 Integration Tests

Create `tests/test_wework_callback.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_service():
    with patch('app.routers.wework.wework_service') as mock:
        yield mock


def test_verify_callback(client, mock_service):
    mock_service.verify_url.return_value = "decrypted"

    response = client.get(
        "/wework/callback",
        params={"msg_signature": "sig", "timestamp": "123",
                "nonce": "nonce", "echostr": "encrypted"}
    )

    assert response.status_code == 200
    assert response.text == "decrypted"


def test_message_callback_fast_query(client, mock_service):
    decrypted_xml = """<xml>
        <ToUserName><![CDATA[toUser]]></ToUserName>
        <FromUserName><![CDATA[fromUser]]></FromUserName>
        <CreateTime>1234567890</CreateTime>
        <MsgType><![CDATA[text]]></MsgType>
        <Content><![CDATA[GT10S]]></Content>
        <MsgId>12345</MsgId>
    </xml>"""

    mock_service.decrypt_message.return_value = decrypted_xml
    mock_service.encrypt_reply.return_value = "<xml>encrypted</xml>"

    response = client.post(
        "/wework/callback",
        params={"msg_signature": "sig", "timestamp": "123", "nonce": "nonce"},
        content=b"encrypted"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/xml; charset=utf-8"
```

#### 4.3 Manual Testing

Create `docs/WEWORK_MANUAL_TESTING.md`:

```markdown
# Manual Testing Guide

## Prerequisites
- WeChat Work admin access
- Custom application created
- HTTPS endpoint deployed
- Environment variables configured

## Test Scenarios

### 1. URL Verification
1. Go to WeChat Work admin
2. Navigate to application → 接收消息 → 设置API接收
3. Enter callback URL: `https://yourdomain.com/wework/callback`
4. Enter Token and AESKey from `.env`
5. Click 保存

Expected: Green checkmark ✓

### 2. Simple Query (Fast)
Send: `GT10S A级标准色`

Expected:
- Response within 1-2 seconds
- Shows product info with price

### 3. Comparison Query (Fast)
Send: `比 GT10S 便宜的`

Expected:
- Response within 2-3 seconds
- Lists cheaper products

### 4. Complex Query (Slow - Active Message)
Send: `最便宜的前20个`

Expected:
- Empty immediate response
- Active message arrives within 5-10 seconds
- Shows top 20 products

### 5. Error Handling
Send: `不存在的产品ABC123`

Expected:
- Error message with suggestion
```

#### 4.4 Deployment Guide

Create `docs/WEWORK_DEPLOYMENT.md`:

```markdown
# Deployment Guide

## Pre-Deployment Checklist
- [ ] All tests passing
- [ ] Environment variables set
- [ ] HTTPS certificate valid
- [ ] Database accessible

## WeChat Work Configuration
1. Create custom application in admin console
2. Get credentials:
   - Corp ID
   - Agent ID
   - Secret
   - Generate Token (random string)
   - Generate AESKey (43 characters)
3. Configure callback URL
4. Test URL verification

## Production Deployment
1. Deploy code to production
2. Set environment variables
3. Restart application
4. Verify health endpoint
5. Test callback endpoint
6. Send test message via WeChat Work

## Monitoring
- Check server logs
- Monitor response times
- Track error rates
- Verify message delivery
```

**Success Criteria**:
- ✅ All unit tests pass
- ✅ All integration tests pass
- ✅ Manual testing completed
- ✅ Documentation complete

---

## Timeline Summary

| Stage | Description | Duration |
|-------|-------------|----------|
| 1 | Dependencies & Config | 2 hours |
| 2 | Core Service | 3-4 hours |
| 3 | Callback Endpoints | 3-4 hours |
| 4 | Testing & Docs | 6-8 hours |
| **Total** | | **15-20 hours** |

---

## Key Technical Points

### Why No Formatting Stage?

The existing system already provides perfectly formatted markdown output:
- `query_processor.py` returns `result_text` with markdown
- `wide_search.py` returns formatted comparison results
- `response_formatter.py` handles product formatting

**We only need to**:
1. Add encryption/decryption layer
2. Add callback endpoints
3. Call existing `process_query()`
4. Use existing `result_text` as-is

### Timeout Handling (Critical)

WeChat Work enforces 5-second timeout with 3 retries. We use 4-second threshold:
- **< 4s**: Passive reply (encrypted XML)
- **≥ 4s**: Return 200 empty + active message

This prevents retry storms.

### Idempotency

Use message cache to detect duplicates by `msgid`. TTL = 60 seconds.

### Error Handling

Always return 200 to prevent WeChat Work from retrying. Log errors for debugging.

---

## Success Metrics

### Technical
- URL verification: 100% success
- Fast query response: < 3s average
- Active message delivery: < 8s
- Error rate: < 1%
- Duplicate detection: 100%

### User
- Query success rate: > 95%
- User satisfaction: Positive feedback
- Daily active users: Growing

---

## Rollback Plan

If issues occur:
1. Disable callback in WeChat Work admin
2. Check logs
3. Revert code if needed
4. Re-enable after fix

---

## Next Steps After Completion

### Enhancements (Optional)
- Rich media responses (images)
- Interactive message cards
- Voice message support

### Optimization
- Cache common queries
- Database query optimization
- Pre-compute popular comparisons

---

*Document Version*: 2.0 (Simplified)
*Last Updated*: 2025-01-11
*Total Effort*: 15-20 hours (~1-2 weeks)
