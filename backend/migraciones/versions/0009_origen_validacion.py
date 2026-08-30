"""Como se obtuvo cada veredicto humano

La tabla guardaba el juicio pero no el procedimiento. Un veredicto emitido tras
leer el articulo entero y otro emitido con una herramienta de lectura delante
son dos cosas distintas, las dos legitimas, y quedaban indistinguibles: dentro
de unos meses nadie -incluido quien anoto- podria saber cual fue cual.

Nace nulo y no con un valor por defecto. Suponer que los veredictos ya
guardados se emitieron de una forma concreta seria inventar justo el dato que
esta columna existe para conservar.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "validacion_humana",
        sa.Column("origen",
                  sa.Enum("lectura", "asistida", name="origen_validacion"),
                  nullable=True),
    )


def downgrade() -> None:
    op.drop_column("validacion_humana", "origen")
