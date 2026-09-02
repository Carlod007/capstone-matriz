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

from sqlalchemy import CHAR, Column, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.mysql import DATETIME as MySQLDATETIME
from sqlalchemy.dialects.mysql import JSON as MySQLJSON

from app.models.proyecto import Base

# Ámbitos posibles: a qué entidad se refiere la medición.
AMBITO_BRECHA = "brecha"
AMBITO_ARTICULO = "articulo"
AMBITO_RUN = "run"
AMBITO_PROYECTO = "proyecto"


class Metrica(Base):
    __tablename__ = "metrica"

    id = Column(CHAR(36), primary_key=True)
    # `referencia_id` es polimórfico y por eso no admite clave foránea. Se
    # añade el proyecto, que sí la admite, para que al borrar un proyecto
    # desaparezcan sus métricas. Sin esto la tabla acumularía filas huérfanas,
    # que es como quedaron las 120 de resultado_resumen.
    proyecto_id = Column(
        CHAR(36),
        ForeignKey("proyecto.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    ambito = Column(String(16), nullable=False)  # brecha | articulo | run | proyecto
    referencia_id = Column(CHAR(36), nullable=False)
    codigo = Column(String(32), nullable=False)  # N1.2, N3.1, N4.1c...
    # Una misma etiqueta deja de ser comparable si cambia su formula. Las
    # filas antiguas quedan en NULL (legado/desconocido), sin atribuirles una
    # version que no se registro cuando se calcularon.
    version_formula = Column(Integer, nullable=True)
    valor = Column(Float, nullable=True)
    detalle = Column(MySQLJSON, nullable=True)  # contexto del cálculo
    # La verificacion y la sintesis pueden ejecutarse despues del run, incluso
    # bajo otro despliegue. Por eso cada medicion conserva su propia fotografia
    # ademas de la fotografia general de la ejecucion.
    procedencia = Column(MySQLJSON, nullable=True)
    # Con resolución de segundos, dos mediciones escritas en el mismo segundo
    # empatan y ordenar por fecha no decide cuál es la vigente. Al verificar
    # una brecha por segunda vez eso hacía que se mostrara indistintamente la
    # medición nueva o la anterior. Microsegundos rompen el empate.
    creado_en = Column(MySQLDATETIME(fsp=6),
                       server_default=text("CURRENT_TIMESTAMP(6)"))

    __table_args__ = (
        Index("idx_metrica_ref", "ambito", "referencia_id"),
        Index("idx_metrica_codigo", "codigo"),
        Index("idx_metrica_codigo_version", "codigo", "version_formula"),
        Index("idx_metrica_proyecto", "proyecto_id", "codigo"),
    )
