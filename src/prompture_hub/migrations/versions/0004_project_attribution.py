"""project attribution on usage and a per-key default project

Revision ID: b4e2a91c7d10
Revises: 9c1f4b7a2d63
Create Date: 2026-09-24 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "b4e2a91c7d10"
down_revision: str | None = "9c1f4b7a2d63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("hubkey", schema=None) as batch_op:
        batch_op.add_column(sa.Column("default_project", sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    with op.batch_alter_table("usagerecord", schema=None) as batch_op:
        batch_op.add_column(sa.Column("project", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.create_index(batch_op.f("ix_usagerecord_project"), ["project"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("usagerecord", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_usagerecord_project"))
        batch_op.drop_column("project")

    with op.batch_alter_table("hubkey", schema=None) as batch_op:
        batch_op.drop_column("default_project")
