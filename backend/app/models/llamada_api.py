# app/models/llamada_api.py
"""
Registro de cada llamada al modelo, exitosa o no.

El recuento de consumo se estimaba contando los resultados guardados, lo que
dejaba fuera precisamente lo que mas engana: las llamadas que fallan tambien
gastan cuota. Tras varios 429 la estimacion se quedaba corta en dos o tres
intentos, y un contador que se muestra como si fuera exacto y no lo es acaba
haciendo tomar decisiones equivocadas.

Aqui se anota el intento en si, con independencia de su resultado.
"""

from sqlalchemy import CHAR, Boolean, Column, DateTime, Index, Integer, String, Text, func

from app.models.proyecto import Base

# Operaciones registradas.
OP_ANALISIS = "analisis"
OP_SINTESIS = "sintesis"
OP_VERIFICACION = "verificacion"
OP_EMBEDDING = "embedding"
OP_OTRA = "otra"


class LlamadaAPI(Base):
    __tablename__ = "llamada_api"

    id = Column(CHAR(36), primary_key=True)
    # No lleva clave foranea al proyecto: interesa el consumo de la clave en
    # conjunto, incluidas las llamadas hechas fuera de un proyecto concreto,
    # y el registro debe sobrevivir al borrado de un proyecto porque la cuota
    # consumida no se recupera al borrarlo.
    proyecto_id = Column(CHAR(36), nullable=True)
    operacion = Column(String(16), nullable=False)
    modelo = Column(String(64), nullable=True)
    unidades = Column(Integer, default=1)  # textos embebidos por llamada
    exito = Column(Boolean, default=True)
    motivo = Column(Text, nullable=True)  # detalle cuando falla
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    creado_en = Column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        Index("ix_llamada_api_proyecto_id", "proyecto_id"),
        Index("ix_llamada_api_creado_en", "creado_en"),
    )
