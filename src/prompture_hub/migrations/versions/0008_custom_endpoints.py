"""custom OpenAI-compatible endpoints

Revision ID: f2a9c4b81e56
Revises: e5c8d2a17f40
Create Date: 2026-09-24 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "f2a9c4b81e56"
down_revision: str | None = "e5c8d2a17f40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customendpoint",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("base_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("api_key_env", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("models", sa.JSON(), nullable=True),
        sa.Column("last_status", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("last_latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("customendpoint", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_customendpoint_name"), ["name"], unique=True)
        batch_op.create_index(batch_op.f("ix_customendpoint_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("customendpoint")
