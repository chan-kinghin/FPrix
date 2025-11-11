"""Add latest_pricing view + pick_price() and helpful indexes

Revision ID: 0003_wide_search_sql
Revises: 0002_confirmation_sessions
Create Date: 2025-11-10
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0003_wide_search_sql"
down_revision = "0002_confirmation_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite index to accelerate tier lookups
    op.execute(
        """
        DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'ix_pricing_tiers_pid_tier_color_date' AND n.nspname = 'public'
        ) THEN
            CREATE INDEX ix_pricing_tiers_pid_tier_color_date
            ON pricing_tiers (product_id, tier, color_type, effective_date DESC);
        END IF;
        END $$;
        """
    )

    # View with latest price per (product_id, tier, color)
    op.execute(
        """
        CREATE OR REPLACE VIEW latest_pricing AS
        WITH lp AS (
            SELECT pt.*, ROW_NUMBER() OVER (
                PARTITION BY product_id, tier, color_type
                ORDER BY effective_date DESC, pricing_id DESC
            ) AS rn
            FROM pricing_tiers pt
        )
        SELECT pricing_id, product_id, tier, color_type, price, effective_date
        FROM lp WHERE rn = 1;
        """
    )

    # Helper function to choose a representative price given preferences
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pick_price(pid INT, pref_tier TEXT, pref_color TEXT)
        RETURNS NUMERIC LANGUAGE SQL STABLE AS $$
        WITH lp AS (
            SELECT * FROM latest_pricing WHERE product_id = pid
        ),
        pref AS (
            SELECT price FROM lp WHERE tier = pref_tier AND color_type = pref_color
            UNION ALL
            SELECT price FROM lp WHERE tier = pref_tier AND color_type = (CASE WHEN pref_color = '标准色' THEN '定制色' ELSE '标准色' END)
            UNION ALL
            SELECT price FROM (
                SELECT price,
                       CASE tier WHEN 'B级' THEN 1 WHEN 'A级' THEN 2 WHEN 'D级' THEN 3 ELSE 9 END AS ord
                FROM lp
                WHERE color_type = pref_color AND tier IN ('B级','A级','D级')
                ORDER BY ord
                LIMIT 1
            ) s
        )
        SELECT (SELECT price FROM pref LIMIT 1);
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS pick_price(INT, TEXT, TEXT);")
    op.execute("DROP VIEW IF EXISTS latest_pricing;")
    op.execute("DROP INDEX IF EXISTS ix_pricing_tiers_pid_tier_color_date;")
