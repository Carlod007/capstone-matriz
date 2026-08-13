from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import CHAR, BigInteger, DateTime, Enum, ForeignKey, Index, Integer
from sqlalchemy.dialects.mysql import DECIMAL as MySQLDECIMAL
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

    __table_args__ = (
        Index("idx_run_proy_estado", "proyecto_id", "estado"),
    )
