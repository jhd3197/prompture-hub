"""audit log and spend adjustments

Revision ID: b8e41c07d3a9
Revises: a6d3e8f19c52
Create Date: 2026-11-02 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "b8e41c07d3a9"
down_revision: str | None = "a6d3e8f19c52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spendadjustment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key_id", sa.Integer(), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("actor_label", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["key_id"], ["hubkey.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("spendadjustment", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_spendadjustment_key_id"), ["key_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_spendadjustment_created_at"), ["created_at"], unique=False)

    op.create_table(
        "auditlog",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("actor_kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_label", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("action", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("key_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("auditlog", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_auditlog_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_auditlog_key_id"), ["key_id"], unique=False)


def downgrade() -> None:
    op.drop_table("auditlog")
    op.drop_table("spendadjustment")
