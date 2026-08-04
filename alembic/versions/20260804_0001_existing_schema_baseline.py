"""Baseline the schema that existed before Alembic.

Revision ID: 20260804_0001
Revises: None
"""
from typing import Sequence, Union

revision: str = "20260804_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The pre-V4.8 schema is adopted in place. New installations are bootstrapped
    # by scripts.db_migrate before this revision is stamped.
    pass


def downgrade() -> None:
    pass
