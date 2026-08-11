# app/models/embedding_doc.py
from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.sql import func
from app.database import Base

class EmbeddingDoc(Base):
    __tablename__ = "embedding_doc"

    id = Column(String(36), primary_key=True)
    articulo_id = Column(String(36), nullable=False, index=True)
    chunk_orden = Column(Integer, nullable=False)             # <- requerido por el servicio
    texto = Column(Text, nullable=False)
    embedding = Column(MySQLJSON, nullable=False)             # guarda lista de floats (no string)
    # Sección del artículo a la que pertenece el fragmento. Permite exigir
    # cobertura de método, resultados y discusión al recuperar contexto, en
    # lugar de quedarse siempre con la introducción (M-10).
    seccion = Column(String(24), nullable=True, index=True)
    char_inicio = Column(Integer, nullable=True)              # trazabilidad hacia el PDF
    char_fin = Column(Integer, nullable=True)
    creado_en = Column(DateTime, server_default=func.now())
