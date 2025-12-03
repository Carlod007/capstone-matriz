from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Enum, BigInteger, DateTime, Text, func
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
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36))
    articulo_id: Mapped[str] = mapped_column(String(36))
    estado: Mapped[EstadoRunItem] = mapped_column(Enum(EstadoRunItem), default=EstadoRunItem.pendiente)
    duracion_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[DateTime] = mapped_column(DateTime, server_default=func.current_timestamp())
