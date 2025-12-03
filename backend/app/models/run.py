from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Enum, Integer, BigInteger, DateTime, func
from app.models.proyecto import Base
from sqlalchemy import nullslast
import enum

class EstadoRun(str, enum.Enum):
    creado = "creado"
    en_progreso = "en_progreso"
    completado = "completado"
    fallido = "fallido"

class Run(Base):
    __tablename__ = "run"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proyecto_id: Mapped[str] = mapped_column(String(36))
    estado: Mapped[EstadoRun] = mapped_column(Enum(EstadoRun), default=EstadoRun.creado)
    iniciado_en: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    finalizado_en: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    n_items_total: Mapped[int] = mapped_column(Integer, default=0)
    n_items_ok: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(BigInteger, default=0)
    tokens_out: Mapped[int] = mapped_column(BigInteger, default=0)
    costo_estimado: Mapped[float] = mapped_column(nullable=False, default=0.0)
