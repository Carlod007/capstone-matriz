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
    creado_en = Column(DateTime, server_default=func.now())
