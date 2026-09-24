"""pause and route override on hub keys

Revision ID: e5c8d2a17f40
Revises: d91b6e2f4a37
Create Date: 2026-09-24 21:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "e5c8d2a17f40"
down_revision: str | None = "d91b6e2f4a37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("hubkey", schema=None) as batch_op:
        batch_op.add_column(sa.Column("paused_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("route_override", sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("hubkey", schema=None) as batch_op:
        batch_op.drop_column("route_override")
        batch_op.drop_column("paused_at")
