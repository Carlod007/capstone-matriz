from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    CHAR, BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, String,
    UniqueConstraint, func,
)
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

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    proyecto_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("proyecto.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    # Al borrar el articulo el archivo sobrevive sin dueno, que es el
    # comportamiento declarado en el esquema desde el principio.
    articulo_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        ForeignKey("articulo.id", ondelete="SET NULL", onupdate="RESTRICT"),
        nullable=True,
    )
    nombre: Mapped[str] = mapped_column(String(300))
    ruta: Mapped[str] = mapped_column(String(500))
    hash_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ocr_aplicado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    estado: Mapped[EstadoArchivo] = mapped_column(
        Enum(EstadoArchivo), default=EstadoArchivo.subido, nullable=True)
    creado_en: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True)

    __table_args__ = (
        # Deduplicacion por contenido: el mismo PDF subido dos veces no crea
        # dos archivos.
        UniqueConstraint("hash_sha256", name="uq_archivo_hash"),
        Index("idx_archivo_proyecto", "proyecto_id"),
        Index("idx_archivo_estado", "estado"),
    )
