# app/models/embedding_doc.py
from sqlalchemy import CHAR, Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.dialects.mysql import LONGTEXT

from app.models.proyecto import Base


class EmbeddingDoc(Base):
    __tablename__ = "embedding_doc"

    id = Column(CHAR(36), primary_key=True)
    articulo_id = Column(
        CHAR(36),
        ForeignKey("articulo.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    chunk_orden = Column(Integer, nullable=False)
    texto = Column(LONGTEXT, nullable=False)
    embedding = Column(MySQLJSON, nullable=False)  # lista de floats, no cadena
    # Sección del artículo a la que pertenece el fragmento. Permite exigir
    # cobertura de método, resultados y discusión al recuperar contexto, en
    # lugar de quedarse siempre con la introducción (M-10).
    seccion = Column(String(24), nullable=True)
    char_inicio = Column(Integer, nullable=True)  # trazabilidad hacia el PDF
    char_fin = Column(Integer, nullable=True)
    creado_en = Column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        Index("idx_embedding_articulo", "articulo_id"),
        Index("idx_embedding_seccion", "articulo_id", "seccion"),
    )
