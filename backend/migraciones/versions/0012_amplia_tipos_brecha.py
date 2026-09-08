"""Amplía la taxonomía de brechas

Los valores existentes no se reclasifican: fueron producidos con el prompt
anterior y conservan esa procedencia. La migración solo permite que los
análisis nuevos guarden las categorías empírica y aplicada.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-07
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TIPOS_V2 = (
    "metodológica", "temática", "teórica", "tecnológica",
    "empírica", "aplicada", "otra",
)
TIPOS_V1 = (
    "metodológica", "temática", "teórica", "tecnológica", "otra",
)


def _enum_sql(valores: tuple[str, ...]) -> str:
    return ",".join("'%s'" % valor.replace("'", "''") for valor in valores)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE resultado_brecha MODIFY COLUMN tipo_brecha "
        "ENUM(%s) NOT NULL" % _enum_sql(TIPOS_V2)
    )


def downgrade() -> None:
    # MySQL no permite reducir un ENUM mientras existan valores que dejarían
    # de ser válidos. En una reversión explícita se preservan esas filas bajo
    # la categoría de respaldo en vez de hacer fallar toda la migración.
    op.execute(
        "UPDATE resultado_brecha SET tipo_brecha = 'otra' "
        "WHERE tipo_brecha IN ('empírica', 'aplicada')"
    )
    op.execute(
        "ALTER TABLE resultado_brecha MODIFY COLUMN tipo_brecha "
        "ENUM(%s) NOT NULL" % _enum_sql(TIPOS_V1)
    )
