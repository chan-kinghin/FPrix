"""Initial schema

Revision ID: 0001_init_schema
Revises: 
Create Date: 2025-11-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_init_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # products
    op.create_table(
        "products",
        sa.Column("product_id", sa.Integer(), primary_key=True),
        sa.Column("product_code", sa.String(length=20), nullable=False, unique=True),
        sa.Column("base_code", sa.String(length=20), nullable=False),
        sa.Column("product_name_cn", sa.String(length=200), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("subcategory", sa.String(length=100), nullable=True),
        sa.Column("material_type", sa.String(length=20), nullable=False),
        sa.Column("base_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("net_weight_grams", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=True),
        sa.Column("source_pdf", sa.String(length=200), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=False),
        sa.Column("screenshot_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_product_code", "products", ["product_code"]) 
    op.create_index("idx_base_code", "products", ["base_code"]) 
    op.create_index("idx_category", "products", ["category"]) 
    op.create_index("idx_material", "products", ["material_type"]) 

    # pricing_tiers
    op.create_table(
        "pricing_tiers",
        sa.Column("pricing_id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.product_id", ondelete="CASCADE")),
        sa.Column("tier", sa.String(length=10), nullable=False),
        sa.Column("color_type", sa.String(length=20), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("effective_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=True),
        sa.UniqueConstraint("product_id", "tier", "color_type", "effective_date"),
    )
    op.create_index("idx_pricing_product", "pricing_tiers", ["product_id"]) 

    # product_sizes
    op.create_table(
        "product_sizes",
        sa.Column("size_id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.product_id", ondelete="CASCADE")),
        sa.Column("size_code", sa.String(length=10), nullable=False),
        sa.Column("size_range", sa.String(length=20), nullable=True),
        sa.Column("cost_adjustment", sa.Numeric(10, 2), server_default="0", nullable=True),
        sa.UniqueConstraint("product_id", "size_code"),
    )

    # query_logs
    op.create_table(
        "query_logs",
        sa.Column("query_id", sa.Integer(), primary_key=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("normalized_query", sa.Text(), nullable=True),
        sa.Column("query_classification", sa.String(length=50), nullable=True),
        sa.Column("fuzzy_matches", sa.JSON(), nullable=True),
        sa.Column("selected_product", sa.String(length=20), nullable=True),
        sa.Column("confirmation_required", sa.Boolean(), server_default=sa.text("false"), nullable=True),
        sa.Column("user_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=True),
        sa.Column("sql_generated", sa.Text(), nullable=True),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("result_data", sa.JSON(), nullable=True),
        sa.Column("screenshot_url", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), server_default=sa.text("true"), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("user_session", sa.String(length=100), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_query_timestamp", "query_logs", ["timestamp"]) 
    op.create_index("idx_query_product", "query_logs", ["selected_product"]) 
    op.create_index("idx_query_session", "query_logs", ["user_session"]) 

    # daily_metrics
    op.create_table(
        "daily_metrics",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("total_queries", sa.Integer(), server_default="0", nullable=True),
        sa.Column("successful_queries", sa.Integer(), server_default="0", nullable=True),
        sa.Column("failed_queries", sa.Integer(), server_default="0", nullable=True),
        sa.Column("avg_response_time_ms", sa.Integer(), nullable=True),
        sa.Column("confirmation_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("unique_users", sa.Integer(), server_default="0", nullable=True),
        sa.Column("top_products", sa.JSON(), nullable=True),
    )

    # pricing_history
    op.create_table(
        "pricing_history",
        sa.Column("history_id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.product_id"), nullable=True),
        sa.Column("tier", sa.String(length=10), nullable=True),
        sa.Column("color_type", sa.String(length=20), nullable=True),
        sa.Column("old_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("new_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("change_date", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
    )
    op.create_index("idx_history_product", "pricing_history", ["product_id"]) 
    op.create_index("idx_history_date", "pricing_history", ["change_date"]) 


def downgrade() -> None:
    op.drop_index("idx_history_date", table_name="pricing_history")
    op.drop_index("idx_history_product", table_name="pricing_history")
    op.drop_table("pricing_history")

    op.drop_table("daily_metrics")

    op.drop_index("idx_query_session", table_name="query_logs")
    op.drop_index("idx_query_product", table_name="query_logs")
    op.drop_index("idx_query_timestamp", table_name="query_logs")
    op.drop_table("query_logs")

    op.drop_table("product_sizes")

    op.drop_index("idx_pricing_product", table_name="pricing_tiers")
    op.drop_table("pricing_tiers")

    op.drop_index("idx_material", table_name="products")
    op.drop_index("idx_category", table_name="products")
    op.drop_index("idx_base_code", table_name="products")
    op.drop_index("idx_product_code", table_name="products")
    op.drop_table("products")

