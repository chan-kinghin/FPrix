from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Optional, List


class QueryRequest(BaseModel):
    query: str
    user_session: Optional[str] = None
    language: str = "zh"


class QueryResponse(BaseModel):
    status: str = Field(default="success")
    result_text: str
    result_markdown: str
    screenshot_url: Optional[str] = None
    data: dict[str, Any]
    confidence: float
    execution_time_ms: int


class ConfirmationOption(BaseModel):
    id: str
    product_code: str
    material: Optional[str] = None
    category: Optional[str] = None
    confidence: float
    match_reason: Optional[str] = None


class ConfirmationResponse(BaseModel):
    status: str = Field(default="needs_confirmation")
    message: str
    options: List[ConfirmationOption]
    confirmation_id: str
    execution_time_ms: int


class ErrorResponse(BaseModel):
    status: str = Field(default="error")
    error_type: str
    message: str
    suggestions: Optional[List[str]] = None
    execution_time_ms: int

