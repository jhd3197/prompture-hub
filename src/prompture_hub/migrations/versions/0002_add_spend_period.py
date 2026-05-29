"""add spend_period to hubkey

Revision ID: 72f44d69fbc4
Revises: e3e4239796fd
Create Date: 2026-05-29 00:09:51.466137
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "72f44d69fbc4"
down_revision: str | None = "e3e4239796fd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite-friendly: batch_alter_table rebuilds the table for ALTER.
    # server_default="day" backfills every existing row so the NOT NULL
    # constraint passes without a separate UPDATE step.
    with op.batch_alter_table("hubkey", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "spend_period",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="day",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("hubkey", schema=None) as batch_op:
        batch_op.drop_column("spend_period")
