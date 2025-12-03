from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, BigInteger, Boolean, Enum, DateTime, func
from app.models.proyecto import Base
import enum

class EstadoArchivo(str, enum.Enum):
    pendiente = "pendiente"
    subido = "subido"
    extraido = "extraido"
    ocr = "ocr"
    fallido = "fallido"

class Archivo(Base):
    __tablename__ = "archivo"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proyecto_id: Mapped[str] = mapped_column(String(36))
    articulo_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    nombre: Mapped[str] = mapped_column(String(300))
    ruta: Mapped[str] = mapped_column(String(500))
    hash_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ocr_aplicado: Mapped[bool] = mapped_column(Boolean, default=False)
    estado: Mapped[EstadoArchivo] = mapped_column(Enum(EstadoArchivo), default=EstadoArchivo.subido)
    creado_en: Mapped[DateTime] = mapped_column(DateTime, server_default=func.current_timestamp())
