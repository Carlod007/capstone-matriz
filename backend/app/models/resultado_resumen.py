# app/models/resultado_resumen.py
from sqlalchemy import CHAR, Column, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.mysql import LONGTEXT

from app.models.proyecto import Base


class ResultadoResumen(Base):
    __tablename__ = "resultado_resumen"

    id = Column(CHAR(36), primary_key=True)
    # ondelete explícito: sin él la tabla quedó sin integridad referencial y
    # acumuló filas huérfanas al borrarse los artículos (C-07).
    articulo_id = Column(
        CHAR(36),
        ForeignKey("articulo.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )

    resumen_generado = Column(LONGTEXT, nullable=False)
    # El abstract real del artículo. Antes eran las primeras 180 palabras del
    # PDF —portada y afiliaciones—, con lo que ROUGE medía el solape con la
    # carátula (M-02).
    resumen_referencia = Column(LONGTEXT, nullable=False)

    rouge1_prec = Column(String(32), nullable=True)
    rouge1_rec = Column(String(32), nullable=True)
    rouge1_f1 = Column(String(32), nullable=True)
    lexical_density = Column(Float, nullable=True)

    created_at = Column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (Index("idx_resumen_articulo", "articulo_id"),)
