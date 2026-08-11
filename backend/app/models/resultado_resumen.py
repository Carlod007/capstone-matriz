# app/models/resultado_resumen.py
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func, Float
from app.models.proyecto import Base


class ResultadoResumen(Base):
    __tablename__ = "resultado_resumen"

    id = Column(String(36), primary_key=True)
    # ondelete explícito: sin él la tabla quedó sin integridad referencial y
    # acumuló filas huérfanas al borrarse los artículos (C-07).
    articulo_id = Column(
        String(36),
        ForeignKey("articulo.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    resumen_generado = Column(Text, nullable=False)
    resumen_referencia = Column(Text, nullable=False)

    # opcional: guardar los propios ROUGE para depurar
    rouge1_prec = Column(String(32), nullable=True)
    rouge1_rec = Column(String(32), nullable=True)
    rouge1_f1 = Column(String(32), nullable=True)

    lexical_density = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
