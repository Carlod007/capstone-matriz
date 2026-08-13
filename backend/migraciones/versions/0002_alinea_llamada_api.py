"""Alinea llamada_api con el resto del esquema

La tabla se creo con create_all() y sus identificadores quedaron en
VARCHAR(36), mientras el resto del esquema usa CHAR(36). La migracion inicial
declara CHAR, de modo que una instalacion nueva y la existente diferian en esa
tabla: exactamente el tipo de divergencia que Alembic viene a evitar.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE llamada_api MODIFY id CHAR(36) NOT NULL")
    op.execute("ALTER TABLE llamada_api MODIFY proyecto_id CHAR(36) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE llamada_api MODIFY id VARCHAR(36) NOT NULL")
    op.execute("ALTER TABLE llamada_api MODIFY proyecto_id VARCHAR(36) NULL")
