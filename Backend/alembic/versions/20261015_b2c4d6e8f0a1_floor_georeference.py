"""floor georeference for map overlay

Revision ID: b2c4d6e8f0a1
Revises: 8eba1746903d
Create Date: 2026-10-15 17:55:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c4d6e8f0a1"
down_revision: str | None = "8eba1746903d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("floors", sa.Column("geo_origin_lat", sa.Float(), nullable=True))
    op.add_column("floors", sa.Column("geo_origin_lon", sa.Float(), nullable=True))
    op.add_column("floors", sa.Column("geo_rotation_deg", sa.Float(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("floors", "geo_rotation_deg")
    op.drop_column("floors", "geo_origin_lon")
    op.drop_column("floors", "geo_origin_lat")
