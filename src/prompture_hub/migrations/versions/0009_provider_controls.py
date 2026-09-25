"""hub-wide provider pause

Revision ID: a6d3e8f19c52
Revises: f2a9c4b81e56
Create Date: 2026-09-24 23:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "a6d3e8f19c52"
down_revision: str | None = "f2a9c4b81e56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "providercontrol",
        sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("provider"),
    )


def downgrade() -> None:
    op.drop_table("providercontrol")
