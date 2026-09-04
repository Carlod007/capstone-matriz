"""Validacion ciega de N2.6

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lote_validacion_n26",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("proyecto_id", sa.CHAR(36), nullable=False),
        sa.Column("run_id", sa.CHAR(36), nullable=False),
        sa.Column("usuario_id", sa.CHAR(36), nullable=False),
        sa.Column("estado", sa.Enum("abierto", "cerrado", name="estado_lote_n26"),
                  nullable=False),
        sa.Column("protocolo_version", sa.Integer(), nullable=False),
        sa.Column("formula_version", sa.Integer(), nullable=False),
        sa.Column("procedencia", sa.JSON(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"),
                  nullable=False),
        sa.Column("cerrado_en", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["proyecto_id"], ["proyecto.id"],
                                ondelete="CASCADE", onupdate="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["run.id"],
                                ondelete="CASCADE", onupdate="RESTRICT"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"],
                                ondelete="CASCADE", onupdate="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "usuario_id",
                            name="uq_lote_n26_run_usuario"),
    )
    op.create_index("idx_lote_n26_proyecto", "lote_validacion_n26",
                    ["proyecto_id"], unique=False)
    op.create_index("idx_lote_n26_usuario", "lote_validacion_n26",
                    ["usuario_id"], unique=False)
    op.create_table(
        "item_validacion_n26",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("lote_id", sa.CHAR(36), nullable=False),
        sa.Column("brecha_id", sa.CHAR(36), nullable=False),
        sa.Column("metrica_id", sa.CHAR(36), nullable=False),
        sa.Column("prediccion_ya_resuelta", sa.Boolean(), nullable=False),
        sa.Column("etiqueta_humana", sa.Boolean(), nullable=True),
        sa.Column("justificacion", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"),
                  nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"),
                  nullable=False),
        sa.ForeignKeyConstraint(["brecha_id"], ["resultado_brecha.id"],
                                ondelete="CASCADE", onupdate="RESTRICT"),
        sa.ForeignKeyConstraint(["lote_id"], ["lote_validacion_n26.id"],
                                ondelete="CASCADE", onupdate="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lote_id", "brecha_id",
                            name="uq_item_n26_lote_brecha"),
    )
    op.create_index("idx_item_n26_lote", "item_validacion_n26", ["lote_id"],
                    unique=False)
    op.create_index("idx_item_n26_brecha", "item_validacion_n26", ["brecha_id"],
                    unique=False)


def downgrade() -> None:
    op.drop_index("idx_item_n26_brecha", table_name="item_validacion_n26")
    op.drop_index("idx_item_n26_lote", table_name="item_validacion_n26")
    op.drop_table("item_validacion_n26")
    op.drop_index("idx_lote_n26_usuario", table_name="lote_validacion_n26")
    op.drop_index("idx_lote_n26_proyecto", table_name="lote_validacion_n26")
    op.drop_table("lote_validacion_n26")
