# app/models/resultado_resumen.py
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func, Float
from sqlalchemy.dialects.postgresql import UUID  # si usas Postgres; si no, usa String
from app.models.proyecto import Base


class ResultadoResumen(Base):
    __tablename__ = "resultado_resumen"

    id = Column(String(36), primary_key=True)  # o UUID / Integer según uses en el resto
    articulo_id = Column(String(36), ForeignKey("articulo.id"), nullable=False)

    resumen_generado = Column(Text, nullable=False)
    resumen_referencia = Column(Text, nullable=False)

    # opcional: guardar los propios ROUGE para depurar
    rouge1_prec = Column(String(32), nullable=True)
    rouge1_rec = Column(String(32), nullable=True)
    rouge1_f1 = Column(String(32), nullable=True)

    lexical_density = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
