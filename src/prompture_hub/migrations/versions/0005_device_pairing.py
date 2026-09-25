"""device tokens and device pairing for companion clients

Revision ID: c7a3f05e9b21
Revises: b4e2a91c7d10
Create Date: 2026-09-24 19:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "c7a3f05e9b21"
down_revision: str | None = "b4e2a91c7d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "devicetoken",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("hashed_secret", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("devicetoken", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_devicetoken_hashed_secret"), ["hashed_secret"], unique=True)
        batch_op.create_index(batch_op.f("ix_devicetoken_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_devicetoken_revoked_at"), ["revoked_at"], unique=False)

    op.create_table(
        "devicepairing",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_code_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("user_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("client_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("requested_scopes", sa.JSON(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("approved_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("approved_scopes", sa.JSON(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("token_id", sa.Integer(), nullable=True),
        sa.Column("interval", sa.Integer(), nullable=False),
        sa.Column("last_poll_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["approved_by"], ["user.id"]),
        sa.ForeignKeyConstraint(["token_id"], ["devicetoken.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("devicepairing", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_devicepairing_device_code_hash"), ["device_code_hash"], unique=True)
        batch_op.create_index(batch_op.f("ix_devicepairing_user_code"), ["user_code"], unique=True)
        batch_op.create_index(batch_op.f("ix_devicepairing_expires_at"), ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_table("devicepairing")
    op.drop_table("devicetoken")
