"""Validacion externa y ciega de la metrica N2.6.

N6 juzga la calidad global de una brecha. Esta tabla responde otra pregunta,
binaria y mucho mas estrecha: si la brecha presenta como pendiente algo que el
articulo ya hizo. Mezclar ambos juicios haria imposible calcular una matriz de
confusion valida para N2.6.

El lote conserva una fotografia de las predicciones antes de que la persona
las vea. Al cerrarlo, las etiquetas quedan bloqueadas y recien entonces se
revela la comparacion. Esa ceguera es una propiedad del dato, no de la pantalla.
"""

from sqlalchemy import (
    CHAR, Boolean, DateTime, Enum, ForeignKey, Index, Integer, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.proyecto import Base

ABIERTO = "abierto"
CERRADO = "cerrado"
ESTADOS_LOTE = (ABIERTO, CERRADO)
PROTOCOLO_N26_VERSION = 1


class LoteValidacionN26(Base):
    __tablename__ = "lote_validacion_n26"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    proyecto_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("proyecto.id", ondelete="CASCADE",
                            onupdate="RESTRICT"), nullable=False)
    run_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("run.id", ondelete="CASCADE",
                            onupdate="RESTRICT"), nullable=False)
    usuario_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("usuario.id", ondelete="CASCADE",
                            onupdate="RESTRICT"), nullable=False)
    estado: Mapped[str] = mapped_column(
        Enum(*ESTADOS_LOTE, name="estado_lote_n26"),
        default=ABIERTO, nullable=False)
    protocolo_version: Mapped[int] = mapped_column(Integer, nullable=False)
    formula_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Misma fotografia para todo el lote. Si las mediciones no comparten una
    # procedencia, el endpoint se niega a iniciarlo: ya no seria una sola
    # version del verificador sometida a prueba.
    procedencia: Mapped[dict] = mapped_column(MySQLJSON, nullable=False)
    creado_en: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False)
    cerrado_en: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "usuario_id",
                         name="uq_lote_n26_run_usuario"),
        Index("idx_lote_n26_proyecto", "proyecto_id"),
        Index("idx_lote_n26_usuario", "usuario_id"),
    )


class ItemValidacionN26(Base):
    __tablename__ = "item_validacion_n26"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    lote_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("lote_validacion_n26.id", ondelete="CASCADE",
                            onupdate="RESTRICT"), nullable=False)
    brecha_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("resultado_brecha.id", ondelete="CASCADE",
                            onupdate="RESTRICT"), nullable=False)
    metrica_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    # Esta copia es deliberada: aunque N2.6 se recalculase despues, el conjunto
    # validado debe conservar exactamente la prediccion que se etiqueto.
    prediccion_ya_resuelta: Mapped[bool] = mapped_column(Boolean, nullable=False)
    etiqueta_humana: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    justificacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False)
    actualizado_en: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(), nullable=False)

    __table_args__ = (
        UniqueConstraint("lote_id", "brecha_id",
                         name="uq_item_n26_lote_brecha"),
        Index("idx_item_n26_lote", "lote_id"),
        Index("idx_item_n26_brecha", "brecha_id"),
    )
