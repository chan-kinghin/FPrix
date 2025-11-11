from __future__ import annotations

from typing import Any, Dict
from sqlalchemy.orm import Session

from app.models import QueryLog


def log_query(db: Session, query_data: Dict[str, Any]) -> int:
    log = QueryLog(
        query_text=query_data.get("query_text", ""),
        normalized_query=query_data.get("normalized_query"),
        query_classification=query_data.get("query_classification"),
        fuzzy_matches=query_data.get("fuzzy_matches"),
        selected_product=query_data.get("selected_product"),
        confirmation_required=query_data.get("confirmation_required", False),
        user_confirmed=query_data.get("user_confirmed", False),
        sql_generated=query_data.get("sql_generated"),
        result_text=query_data.get("result_text"),
        result_data=query_data.get("result_data"),
        screenshot_url=query_data.get("screenshot_url"),
        confidence_score=query_data.get("confidence_score"),
        execution_time_ms=query_data.get("execution_time_ms"),
        success=query_data.get("success", True),
        error_message=query_data.get("error_message"),
        user_session=query_data.get("user_session"),
        ip_address=query_data.get("ip_address"),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log.query_id

