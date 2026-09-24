"""key policies (ip allowlist, expiry) and routing columns on usage

Revision ID: 9c1f4b7a2d63
Revises: 72f44d69fbc4
Create Date: 2026-09-24 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "9c1f4b7a2d63"
down_revision: str | None = "72f44d69fbc4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("hubkey", schema=None) as batch_op:
        batch_op.add_column(sa.Column("allowed_ips", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f("ix_hubkey_expires_at"), ["expires_at"], unique=False)

    with op.batch_alter_table("usagerecord", schema=None) as batch_op:
        batch_op.add_column(sa.Column("served_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("usagerecord", schema=None) as batch_op:
        batch_op.drop_column("attempts")
        batch_op.drop_column("served_by")

    with op.batch_alter_table("hubkey", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_hubkey_expires_at"))
        batch_op.drop_column("expires_at")
        batch_op.drop_column("allowed_ips")
