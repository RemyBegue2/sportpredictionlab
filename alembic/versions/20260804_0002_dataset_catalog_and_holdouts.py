"""Add immutable dataset catalog and holdout generations.

Revision ID: 20260804_0002
Revises: 20260804_0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "20260804_0002"
down_revision: Union[str, None] = "20260804_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "dataset_catalog" not in tables:
        op.create_table(
            "dataset_catalog",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("dataset_id", sa.String(length=120), nullable=False),
            sa.Column("sport", sa.String(length=40), nullable=False),
            sa.Column("source", sa.String(length=200), nullable=False),
            sa.Column("license_status", sa.String(length=40), nullable=False),
            sa.Column("cutoff_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("distinct_dates", sa.Integer(), nullable=False),
            sa.Column("quality_status", sa.String(length=40), nullable=False),
            sa.Column("dataset_sha256", sa.String(length=64), nullable=False),
            sa.Column("supersedes_dataset_id", sa.String(length=120), nullable=True),
            sa.Column("catalog", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("dataset_id", name="uq_dataset_catalog_dataset_id"),
        )
        op.create_index("ix_dataset_catalog_dataset_id", "dataset_catalog", ["dataset_id"], unique=True)
        op.create_index("ix_dataset_catalog_sport", "dataset_catalog", ["sport"], unique=False)
        op.create_index("ix_dataset_catalog_quality_status", "dataset_catalog", ["quality_status"], unique=False)
        op.create_index("ix_dataset_catalog_dataset_sha256", "dataset_catalog", ["dataset_sha256"], unique=False)
    inspector = inspect(op.get_bind())
    if "holdout_generations" not in set(inspector.get_table_names()):
        op.create_table(
            "holdout_generations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("generation_id", sa.String(length=120), nullable=False),
            sa.Column("dataset_id", sa.String(length=120), nullable=False),
            sa.Column("sport", sa.String(length=40), nullable=False),
            sa.Column("generation", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("train_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("calibration_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("holdout_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("holdout_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("consulted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("generation_manifest", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("generation_id", name="uq_holdout_generation_id"),
        )
        op.create_index("ix_holdout_generations_generation_id", "holdout_generations", ["generation_id"], unique=True)
        op.create_index("ix_holdout_generations_dataset_id", "holdout_generations", ["dataset_id"], unique=False)
        op.create_index("ix_holdout_generations_sport", "holdout_generations", ["sport"], unique=False)
        op.create_index("ix_holdout_generations_status", "holdout_generations", ["status"], unique=False)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "holdout_generations" in set(inspector.get_table_names()):
        op.drop_table("holdout_generations")
    inspector = inspect(op.get_bind())
    if "dataset_catalog" in set(inspector.get_table_names()):
        op.drop_table("dataset_catalog")
