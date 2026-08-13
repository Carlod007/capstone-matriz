# app/models/rag_log.py
"""Registro de qué fragmentos se recuperaron en cada análisis.

La tabla existía en el esquema desde el principio pero no tenía modelo ni
llegó a usarse nunca (C-08). Es la base de la trazabilidad: permite responder
a "¿en qué se apoyó el sistema para afirmar esta brecha?".
"""

from sqlalchemy import CHAR, Column, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.mysql import JSON as MySQLJSON

from app.models.proyecto import Base


class RagLog(Base):
    __tablename__ = "rag_log"

    id = Column(CHAR(36), primary_key=True)
    # run_id y articulo_id son opcionales por diseño y no llevan clave
    # foránea. Se guarda el proyecto, que sí la lleva, para que el registro
    # se borre con él y la tabla no acumule filas huérfanas.
    proyecto_id = Column(
        CHAR(36),
        ForeignKey("proyecto.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    run_id = Column(CHAR(36), nullable=True)
    articulo_id = Column(CHAR(36), nullable=True)
    consulta = Column(Text, nullable=True)
    top_k = Column(Integer, default=5)
    scores = Column(MySQLJSON, nullable=True)
    creado_en = Column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        Index("idx_rag_articulo", "articulo_id"),
        Index("idx_rag_run", "run_id"),
    )
