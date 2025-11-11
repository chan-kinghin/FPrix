from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.models import ConfirmationSessionDB


TTL_SECONDS = 300  # 5 minutes


@dataclass
class ConfirmationSession:
    created_at: float
    options: List[Dict[str, Any]]
    params: Dict[str, Any]


_STORE: Dict[str, ConfirmationSession] = {}


def needs_confirmation(count: int, top_confidence: float) -> bool:
    if count <= 0:
        return False
    if count == 1 and top_confidence >= 1.0:
        return False
    return True


def generate_confirmation_id(user_session: Optional[str] = None) -> str:
    ts = int(time.time())
    suffix = user_session or "anon"
    return f"conf_{suffix}_{ts}"


def _cleanup_expired() -> None:
    now = time.time()
    expired = [k for k, v in _STORE.items() if now - v.created_at > TTL_SECONDS]
    for k in expired:
        _STORE.pop(k, None)


def save_confirmation(confirmation_id: str, options: List[Dict[str, Any]], params: Dict[str, Any], db: Optional[Session] = None, user_session: Optional[str] = None, ttl_seconds: int = TTL_SECONDS) -> None:
    if db is None:
        _cleanup_expired()
        _STORE[confirmation_id] = ConfirmationSession(created_at=time.time(), options=options, params=params)
        return
    expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    rec = ConfirmationSessionDB(
        confirmation_id=confirmation_id,
        user_session=user_session,
        matches=options,
        params=params,
        expires_at=expires_at,
    )
    db.merge(rec)
    db.commit()


def get_confirmation(confirmation_id: str, db: Optional[Session] = None) -> Optional[ConfirmationSession]:
    if db is None:
        _cleanup_expired()
        return _STORE.get(confirmation_id)
    rec = db.get(ConfirmationSessionDB, confirmation_id)
    if not rec:
        return None
    # Check expiry
    if rec.expires_at and rec.expires_at < datetime.utcnow():
        try:
            db.delete(rec)
            db.commit()
        finally:
            return None
    return ConfirmationSession(created_at=(rec.created_at or datetime.utcnow()).timestamp(), options=rec.matches or [], params=rec.params or {})


def pop_confirmation(confirmation_id: str, db: Optional[Session] = None) -> Optional[ConfirmationSession]:
    if db is None:
        _cleanup_expired()
        return _STORE.pop(confirmation_id, None)
    rec = db.get(ConfirmationSessionDB, confirmation_id)
    if not rec:
        return None
    session = ConfirmationSession(created_at=(rec.created_at or datetime.utcnow()).timestamp(), options=rec.matches or [], params=rec.params or {})
    db.delete(rec)
    db.commit()
    return session
