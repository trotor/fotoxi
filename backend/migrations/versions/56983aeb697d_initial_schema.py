"""initial schema

Revision ID: 56983aeb697d
Revises:
Create Date: 2026-03-15 08:21:46.271910

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '56983aeb697d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Initial schema - tables already exist via create_all."""
    pass


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('duplicate_group_members')
    op.drop_table('duplicate_groups')
    op.drop_table('settings')
    op.drop_table('images')
