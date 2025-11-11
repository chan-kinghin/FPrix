from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Date,
    DECIMAL,
    ForeignKey,
    Boolean,
    JSON,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from .base import Base


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    base_code: Mapped[str] = mapped_column(String(20), nullable=False)
    product_name_cn: Mapped[Optional[str]] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    subcategory: Mapped[Optional[str]] = mapped_column(String(100))
    material_type: Mapped[str] = mapped_column(String(20), nullable=False)
    base_cost: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    net_weight_grams: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="active")
    source_pdf: Mapped[str] = mapped_column(String(200), nullable=False)
    source_page: Mapped[int] = mapped_column(Integer, nullable=False)
    screenshot_url: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    pricing_tiers: Mapped[list["PricingTier"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    sizes: Mapped[list["ProductSize"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


Index("idx_product_code", Product.product_code)
Index("idx_base_code", Product.base_code)
Index("idx_category", Product.category)
Index("idx_material", Product.material_type)


class PricingTier(Base):
    __tablename__ = "pricing_tiers"

    pricing_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"))
    tier: Mapped[str] = mapped_column(String(10), nullable=False)
    color_type: Mapped[str] = mapped_column(String(20), nullable=False)
    price: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, default=date.today)

    __table_args__ = (
        UniqueConstraint("product_id", "tier", "color_type", "effective_date"),
    )

    product: Mapped[Product] = relationship(back_populates="pricing_tiers")

    
class ProductSize(Base):
    __tablename__ = "product_sizes"

    size_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"))
    size_code: Mapped[str] = mapped_column(String(10), nullable=False)
    size_range: Mapped[Optional[str]] = mapped_column(String(20))
    cost_adjustment: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0)

    __table_args__ = (
        UniqueConstraint("product_id", "size_code"),
    )

    product: Mapped[Product] = relationship(back_populates="sizes")


class QueryLog(Base):
    __tablename__ = "query_logs"

    query_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_query: Mapped[Optional[str]] = mapped_column(Text)
    query_classification: Mapped[Optional[str]] = mapped_column(String(50))
    fuzzy_matches: Mapped[Optional[dict]] = mapped_column(JSON)
    selected_product: Mapped[Optional[str]] = mapped_column(String(20))
    confirmation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    sql_generated: Mapped[Optional[str]] = mapped_column(Text)
    result_text: Mapped[Optional[str]] = mapped_column(Text)
    result_data: Mapped[Optional[dict]] = mapped_column(JSON)
    screenshot_url: Mapped[Optional[str]] = mapped_column(Text)
    confidence_score: Mapped[Optional[float]] = mapped_column(DECIMAL(3, 2))
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    user_session: Mapped[Optional[str]] = mapped_column(String(100))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_query_timestamp", "timestamp"),
        Index("idx_query_product", "selected_product"),
        Index("idx_query_session", "user_session"),
    )


class DailyMetric(Base):
    __tablename__ = "daily_metrics"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    total_queries: Mapped[int] = mapped_column(Integer, default=0)
    successful_queries: Mapped[int] = mapped_column(Integer, default=0)
    failed_queries: Mapped[int] = mapped_column(Integer, default=0)
    avg_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    confirmation_rate: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 2))
    unique_users: Mapped[int] = mapped_column(Integer, default=0)
    top_products: Mapped[Optional[dict]] = mapped_column(JSON)


class PricingHistory(Base):
    __tablename__ = "pricing_history"

    history_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.product_id"))
    tier: Mapped[Optional[str]] = mapped_column(String(10))
    color_type: Mapped[Optional[str]] = mapped_column(String(20))
    old_price: Mapped[Optional[float]] = mapped_column(DECIMAL(10, 2))
    new_price: Mapped[Optional[float]] = mapped_column(DECIMAL(10, 2))
    change_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    change_reason: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("idx_history_product", "product_id"),
        Index("idx_history_date", "change_date"),
    )


class ConfirmationSessionDB(Base):
    __tablename__ = "confirmation_sessions"

    confirmation_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_session: Mapped[Optional[str]] = mapped_column(String(100))
    matches: Mapped[Optional[dict]] = mapped_column(JSON)
    params: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
