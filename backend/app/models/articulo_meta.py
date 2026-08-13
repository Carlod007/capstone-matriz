# app/models/articulo_meta.py
"""
Caché de metadatos bibliográficos externos (Crossref, Scopus).

La tabla existe en el esquema desde el principio pero nunca tuvo modelo ni
llegó a usarse (C-08). Se declara ahora por una razón concreta: sin modelo,
Alembic no la conoce y su primer `autogenerate` proponía borrarla.

Sigue sin escribirse desde ningún punto del código. Cuando se decida si el
enriquecimiento con fuentes externas entra o no en el alcance, se poblará o
se retirará con una migración; mientras tanto, al menos está declarada.
"""

from sqlalchemy import CHAR, Column, DateTime, Enum, ForeignKey, Index, func
from sqlalchemy.dialects.mysql import JSON as MySQLJSON

from app.models.proyecto import Base


class ArticuloMeta(Base):
    __tablename__ = "articulo_meta"

    id = Column(CHAR(36), primary_key=True)
    articulo_id = Column(
        CHAR(36),
        ForeignKey("articulo.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    source = Column(Enum("crossref", "scopus"), nullable=False)
    payload_json = Column(MySQLJSON, nullable=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        Index("idx_meta_articulo_source", "articulo_id", "source"),
    )
