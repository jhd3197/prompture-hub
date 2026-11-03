"""rename hubkey.daily_spend_cap_usd to spend_cap_usd

Revision ID: c3f7a92d5e18
Revises: b8e41c07d3a9
Create Date: 2026-11-02 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f7a92d5e18"
down_revision: str | None = "b8e41c07d3a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("hubkey", schema=None) as batch_op:
        batch_op.alter_column(
            "daily_spend_cap_usd", new_column_name="spend_cap_usd", existing_type=sa.Float(), existing_nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("hubkey", schema=None) as batch_op:
        batch_op.alter_column(
            "spend_cap_usd", new_column_name="daily_spend_cap_usd", existing_type=sa.Float(), existing_nullable=False
        )
