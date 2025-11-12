from __future__ import annotations

import logging
from typing import Optional

from wechatpy.crypto import WeChatCrypto, PrpCrypto
from wechatpy.enterprise import WeChatClient
from wechatpy.exceptions import WeChatException

from app.core.config import settings


logger = logging.getLogger(__name__)


class WeWorkService:
    """WeChat Work helpers: crypto + API client.

    Lazily initialized based on env settings. Raises ValueError if required
    config is missing when methods are used.
    """

    def __init__(self) -> None:
        self._crypto: Optional[WeChatCrypto] = None
        self._client: Optional[WeChatClient] = None

    def _ensure_config(self) -> None:
        required = {
            "WEWORK_CORP_ID": settings.WEWORK_CORP_ID,
            "WEWORK_AGENT_ID": settings.WEWORK_AGENT_ID,
            "WEWORK_SECRET": settings.WEWORK_SECRET,
            "WEWORK_TOKEN": settings.WEWORK_TOKEN,
            "WEWORK_ENCODING_AES_KEY": settings.WEWORK_ENCODING_AES_KEY,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(
                "Missing WeChat Work configuration: " + ", ".join(missing)
            )

        aes = settings.WEWORK_ENCODING_AES_KEY or ""
        if len(aes) != 43:
            raise ValueError("WEWORK_ENCODING_AES_KEY must be 43 characters long")

    @property
    def crypto(self) -> WeChatCrypto:
        if self._crypto is None:
            self._ensure_config()
            self._crypto = WeChatCrypto(
                token=settings.WEWORK_TOKEN,  # type: ignore[arg-type]
                encoding_aes_key=settings.WEWORK_ENCODING_AES_KEY,  # type: ignore[arg-type]
                app_id=settings.WEWORK_CORP_ID,  # type: ignore[arg-type]
            )
        return self._crypto

    @property
    def client(self) -> WeChatClient:
        if self._client is None:
            self._ensure_config()
            self._client = WeChatClient(  # enterprise client
                settings.WEWORK_CORP_ID or "",
                settings.WEWORK_SECRET or "",
            )
            logger.info("WeWork client initialized")
        return self._client

    # --- Crypto helpers ---
    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        """Verify callback URL and decrypt echo string.

        Uses internal signature checker consistent with official SDK.
        """
        try:
            # wechatpy doesn't expose check_signature, use base helper
            decrypted = self.crypto._check_signature(  # type: ignore[attr-defined]
                msg_signature, timestamp, nonce, echostr, PrpCrypto
            )
            return decrypted.decode("utf-8")
        except Exception as e:
            logger.error("URL verification failed: %s", e)
            raise

    def decrypt_message(self, post_data: bytes, msg_signature: str, timestamp: str, nonce: str) -> str:
        try:
            xml = self.crypto.decrypt_message(post_data, msg_signature, timestamp, nonce)
            return xml.decode("utf-8") if isinstance(xml, (bytes, bytearray)) else xml
        except Exception as e:
            logger.error("Decrypt failed: %s", e)
            raise

    def encrypt_reply(self, reply_xml: str, timestamp: str, nonce: str) -> str:
        try:
            enc = self.crypto.encrypt_message(reply_xml, nonce, timestamp)
            return enc
        except Exception as e:
            logger.error("Encrypt failed: %s", e)
            raise

    # --- Active message ---
    def send_markdown_message(self, user_id: str, content: str) -> dict:
        try:
            resp = self.client.message.send_markdown(
                agent_id=str(settings.WEWORK_AGENT_ID or ""),
                user_ids=user_id,
                content=content,
            )
            return resp
        except WeChatException as e:
            logger.error("WeWork send_markdown failed: %s", e)
            raise


# Singleton-like accessor
_instance: Optional[WeWorkService] = None


def get_wework_service() -> WeWorkService:
    global _instance
    if _instance is None:
        _instance = WeWorkService()
    return _instance

