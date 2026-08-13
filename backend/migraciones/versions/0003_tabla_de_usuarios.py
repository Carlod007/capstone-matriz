"""Tabla de usuarios

Primer paso de la Fase 2. Hasta aqui no habia usuarios: cualquiera que
alcanzara el backend veia y modificaba todos los proyectos.

Esta revision solo crea la tabla. La propiedad de los datos —anadir el dueno
a cada proyecto y filtrar por el en cada consulta— es la revision siguiente,
para que este cambio se pueda deshacer sin tocar los datos existentes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'usuario',
        sa.Column('id', sa.CHAR(length=36), nullable=False),
        sa.Column('correo', sa.String(length=190), nullable=False),
        sa.Column('contrasena_hash', sa.String(length=255), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('creado_en', sa.DateTime(),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('correo', name='uq_usuario_correo'),
        # Se fijan explicitamente, como las trece tablas de la revision 0001.
        # Sin esto la tabla hereda la colacion de la base, que depende de como
        # la creara cada cual, y MySQL rechaza una clave foranea entre columnas
        # de colaciones distintas: la revision 0004 fallaba con
        # "Referencing column and referenced column are incompatible" segun la
        # maquina donde se aplicara.
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_0900_ai_ci',
    )


def downgrade() -> None:
    op.drop_table('usuario')
