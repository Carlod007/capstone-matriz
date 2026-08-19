"""Tabla para el juicio humano sobre cada brecha

N6 pregunta si el sistema ACIERTA, no si es consistente. Todas las metricas
anteriores comparan al sistema consigo mismo; sin una opinion humana no hay
forma de saber si las brechas son correctas.

La tabla es nueva y no una columna en `resultado_brecha` por dos motivos. Alli
ya vive `estado_validacion`, de la validacion automatica desactivada: mezclar
las dos dejaria dos verdades sin poder distinguirlas. Y con una fila por
(brecha, persona) se puede calcular el acuerdo entre jueces el dia que haya mas
de uno, sin volver a migrar.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "validacion_humana",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("brecha_id", sa.CHAR(36), nullable=False),
        sa.Column("usuario_id", sa.CHAR(36), nullable=False),
        sa.Column("veredicto",
                  sa.Enum("correcta", "parcial", "incorrecta",
                          name="veredicto_humano"),
                  nullable=False),
        sa.Column("justificacion", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(),
                  server_default=sa.text("CURRENT_TIMESTAMP"),
                  server_onupdate=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["brecha_id"], ["resultado_brecha.id"],
                                ondelete="CASCADE", onupdate="RESTRICT"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"],
                                ondelete="CASCADE", onupdate="RESTRICT"),
        # Un veredicto vigente por persona y brecha: cambiar de opinion
        # sustituye el propio y no toca el de nadie mas.
        sa.UniqueConstraint("brecha_id", "usuario_id",
                            name="uq_validacion_brecha_usuario"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_validacion_brecha", "validacion_humana", ["brecha_id"])
    op.create_index("idx_validacion_usuario", "validacion_humana",
                    ["usuario_id"])


def downgrade() -> None:
    # Se pierden las anotaciones. No hay donde guardarlas: son el dato que esta
    # tabla existe para tener.
    op.drop_index("idx_validacion_usuario", table_name="validacion_humana")
    op.drop_index("idx_validacion_brecha", table_name="validacion_humana")
    op.drop_table("validacion_humana")
