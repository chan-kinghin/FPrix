"""Add confirmation_sessions table

Revision ID: 0002_confirmation_sessions
Revises: 0001_init_schema
Create Date: 2025-11-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_confirmation_sessions"
down_revision = "0001_init_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "confirmation_sessions",
        sa.Column("confirmation_id", sa.String(length=100), primary_key=True),
        sa.Column("user_session", sa.String(length=100), nullable=True),
        sa.Column("matches", sa.JSON(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("confirmation_sessions")

