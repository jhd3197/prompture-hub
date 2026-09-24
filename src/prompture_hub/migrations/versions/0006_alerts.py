"""alert rules and fired alert events

Revision ID: d91b6e2f4a37
Revises: c7a3f05e9b21
Create Date: 2026-09-24 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "d91b6e2f4a37"
down_revision: str | None = "c7a3f05e9b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alertrule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("key_id", sa.Integer(), nullable=True),
        sa.Column("target", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("webhook_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("ntfy_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["key_id"], ["hubkey.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("alertrule", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_alertrule_kind"), ["kind"], unique=False)
        batch_op.create_index(batch_op.f("ix_alertrule_enabled"), ["enabled"], unique=False)
        batch_op.create_index(batch_op.f("ix_alertrule_user_id"), ["user_id"], unique=False)

    op.create_table(
        "alertevent",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("subject", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("message", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("key_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["rule_id"], ["alertrule.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("alertevent", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_alertevent_rule_id"), ["rule_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_alertevent_subject"), ["subject"], unique=False)
        batch_op.create_index(batch_op.f("ix_alertevent_key_id"), ["key_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_alertevent_created_at"), ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("alertevent")
    op.drop_table("alertrule")
