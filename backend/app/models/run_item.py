from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import CHAR, BigInteger, DateTime, Enum, ForeignKey, Index, Text, func
from app.models.proyecto import Base
import enum


class EstadoRunItem(str, enum.Enum):
    pendiente = "pendiente"
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
    creado_en: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True)

    __table_args__ = (
        Index("idx_run_item_run_estado", "run_id", "estado"),
        Index("idx_run_item_articulo", "articulo_id"),
    )
