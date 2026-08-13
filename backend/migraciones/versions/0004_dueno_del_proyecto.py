"""Dueno del proyecto

Segundo paso de la Fase 2. La revision anterior creo las cuentas; esta las
conecta con los datos.

`usuario_id` admite NULL a proposito. Cuando esta revision se aplica sobre una
base que ya tiene proyectos, puede no existir todavia ninguna cuenta a la que
asignarlos, y una columna NOT NULL obligaria a inventarse un usuario dentro de
la migracion —con que contrasena— o a rechazar la actualizacion.

Un proyecto sin dueno no queda accesible "por defecto": no pertenece a nadie,
asi que ninguna consulta lo devuelve. El fallo es cerrado. `crear_cuenta.py`
los adopta al dar de alta la primera cuenta.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'proyecto',
        sa.Column('usuario_id', sa.CHAR(length=36), nullable=True),
    )
    op.create_index('idx_proyecto_usuario', 'proyecto', ['usuario_id'],
                    unique=False)
    # Con nombre explicito: sin el, MySQL inventa uno y el downgrade no sabria
    # cual borrar. El resto del esquema sigue la misma convencion, fk_<tabla>_
    # <destino>, fijada en la revision 0001.
    op.create_foreign_key(
        'fk_proyecto_usuario', 'proyecto', 'usuario',
        ['usuario_id'], ['id'], onupdate='RESTRICT', ondelete='RESTRICT',
    )


def downgrade() -> None:
    op.drop_constraint('fk_proyecto_usuario', 'proyecto', type_='foreignkey')
    op.drop_index('idx_proyecto_usuario', table_name='proyecto')
    op.drop_column('proyecto', 'usuario_id')
