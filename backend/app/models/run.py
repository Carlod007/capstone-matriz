from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    CHAR, BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, Text,
    text,
)
from sqlalchemy.dialects.mysql import DECIMAL as MySQLDECIMAL
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from app.models.proyecto import Base
import enum


class EstadoRun(str, enum.Enum):
    creado = "creado"
    en_progreso = "en_progreso"
    completado = "completado"
    fallido = "fallido"


class Run(Base):
    __tablename__ = "run"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    proyecto_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("proyecto.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    estado: Mapped[EstadoRun] = mapped_column(Enum(EstadoRun), default=EstadoRun.creado, nullable=True)
    iniciado_en: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    finalizado_en: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    n_items_total: Mapped[int] = mapped_column(Integer, default=0, nullable=True)
    n_items_ok: Mapped[int] = mapped_column(Integer, default=0, nullable=True)
    tokens_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=True)
    tokens_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=True)
    # DECIMAL y no float: es dinero, y el tipo estaba sin declarar en el
    # modelo aunque la base ya lo definia asi.
    costo_estimado: Mapped[float] = mapped_column(
        MySQLDECIMAL(10, 2), nullable=True, default=0.0)
    # Si al terminar todos los articulos hay que sintetizar el estado del
    # arte. Lo pide quien encola; el trabajador no puede adivinarlo, y hacerlo
    # siempre gastaria una generacion en ejecuciones parciales.
    genera_estado_arte: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=text("0"))
    # Motivo por el que la ejecucion entera se dio por perdida. Los fallos de
    # un articulo suelto van en run_item.error_msg; este es para lo que impide
    # continuar, como quedarse sin cuota diaria a mitad del lote.
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fotografia tecnica del pipeline en el momento de crear la ejecucion.
    # Es nullable a proposito: las ejecuciones anteriores a la migracion no
    # tienen procedencia demostrable y no debe inventarse retrospectivamente.
    procedencia: Mapped[dict | None] = mapped_column(MySQLJSON, nullable=True)

    __table_args__ = (
        Index("idx_run_proy_estado", "proyecto_id", "estado"),
    )
