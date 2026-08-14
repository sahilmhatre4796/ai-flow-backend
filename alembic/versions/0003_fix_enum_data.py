"""fix existing data to use lowercase enum values

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-14
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    pass  # No-op: data already has correct lowercase values


def downgrade() -> None:
    pass
