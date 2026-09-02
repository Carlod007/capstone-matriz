"""Procedencia de ejecuciones y version de formulas

Las filas existentes quedan nulas deliberadamente. Atribuirles la version
actual seria mezclar datos historicos con una procedencia que no se registro
cuando fueron producidos.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("run", sa.Column("procedencia", sa.JSON(), nullable=True))
    op.add_column(
        "metrica", sa.Column("version_formula", sa.Integer(), nullable=True)
    )
    op.add_column("metrica", sa.Column("procedencia", sa.JSON(), nullable=True))
    op.create_index(
        "idx_metrica_codigo_version",
        "metrica",
        ["codigo", "version_formula"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_metrica_codigo_version", table_name="metrica")
    op.drop_column("metrica", "procedencia")
    op.drop_column("metrica", "version_formula")
    op.drop_column("run", "procedencia")
