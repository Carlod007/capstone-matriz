from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    CHAR, BigInteger, DateTime, Enum, ForeignKey, Index, Integer, Text, func,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from app.models.proyecto import Base
import enum


class EstadoRunItem(str, enum.Enum):
    pendiente = "pendiente"
    # Tomado por un trabajador y todavia sin terminar. Sin este estado, dos
    # trabajadores podrian coger el mismo articulo, y un trabajador caido
    # dejaria el suyo en "pendiente" para siempre sin que nadie sepa que ya
    # se intento.
    en_proceso = "en_proceso"
    extraido = "extraido"
    ocr = "ocr"
    enriquecido = "enriquecido"
    analizado = "analizado"
    guardado = "guardado"
    fallido = "fallido"


class RunItem(Base):
    __tablename__ = "run_item"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("run.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    articulo_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("articulo.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    estado: Mapped[EstadoRunItem] = mapped_column(
        Enum(EstadoRunItem), default=EstadoRunItem.pendiente, nullable=True)
    duracion_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cuantas veces se ha intentado. Un fallo de red o un limite de cuota son
    # transitorios y merecen otra oportunidad; un PDF sin texto, no. Sin
    # contarlos, reintentar es indistinguible de un bucle infinito.
    intentos: Mapped[int] = mapped_column(Integer, default=0, nullable=False,
                                          server_default=text("0"))
    # Cuando lo tomo un trabajador. Si pasa demasiado tiempo, se da por caido
    # y otro puede recogerlo: sin esta marca, un trabajador que muere a mitad
    # deja el articulo bloqueado indefinidamente.
    tomado_en: Mapped[DateTime | None] = mapped_column(DATETIME(6), nullable=True)
    creado_en: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True)

    __table_args__ = (
        Index("idx_run_item_run_estado", "run_id", "estado"),
        Index("idx_run_item_articulo", "articulo_id"),
    )
