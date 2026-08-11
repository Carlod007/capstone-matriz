# app/models/metrica.py
"""
Almacén genérico de métricas.

Se usa formato largo —una fila por métrica medida— en lugar de una columna
por indicador. La capa de medición está en evolución: con columnas fijas,
cada métrica nueva exigiría una migración y cada métrica retirada dejaría una
columna muerta, que es justamente como quedaron `entropia` y `val_score`.

El formato largo además facilita lo que la especificación exige: describir la
distribución de cada métrica, no solo su promedio.
"""

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.sql import func

from app.models.proyecto import Base

# Ámbitos posibles: a qué entidad se refiere la medición.
AMBITO_BRECHA = "brecha"
AMBITO_ARTICULO = "articulo"
AMBITO_RUN = "run"
AMBITO_PROYECTO = "proyecto"


class Metrica(Base):
    __tablename__ = "metrica"

    id = Column(String(36), primary_key=True)
    # `referencia_id` es polimórfico y por eso no admite clave foránea. Se
    # añade el proyecto, que sí la admite, para que al borrar un proyecto
    # desaparezcan sus métricas. Sin esto la tabla acumularía filas huérfanas,
    # que es como quedaron las 120 de resultado_resumen.
    proyecto_id = Column(
        String(36),
        ForeignKey("proyecto.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    ambito = Column(String(16), nullable=False)      # brecha | articulo | run | proyecto
    referencia_id = Column(String(36), nullable=False)
    codigo = Column(String(32), nullable=False)      # N1.2, N3.1, N4.1...
    valor = Column(Float, nullable=True)
    detalle = Column(MySQLJSON, nullable=True)       # contexto del cálculo
    creado_en = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_metrica_ref", "ambito", "referencia_id"),
        Index("idx_metrica_codigo", "codigo"),
        Index("idx_metrica_proyecto", "proyecto_id", "codigo"),
    )
