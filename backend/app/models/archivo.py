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
        # Deduplicacion por contenido, acotada al proyecto: el mismo PDF subido
        # dos veces al mismo proyecto no crea dos archivos.
        #
        # El alcance importa. La restriccion era global sobre el hash, y eso
        # significaba que un PDF solo podia existir una vez en todo el sistema:
        # subir a un proyecto nuevo un articulo que ya estaba en otro fallaba
        # con un 500, y entre cuentas distintas era ademas una fuga —el error
        # delataba que alguien mas habia subido ese mismo articulo—.
        #
        # `archivos.py` ya deduplicaba por proyecto, pero la base seguia
        # exigiendo unicidad global. La consulta previa no encontraba nada y el
        # INSERT chocaba contra el indice: la correccion estaba aplicada en el
        # codigo y no en el esquema, que es la unica forma de que un mismo
        # arreglo pase las pruebas y rompa en produccion.
        UniqueConstraint("proyecto_id", "hash_sha256",
                         name="uq_archivo_proyecto_hash"),
        Index("idx_archivo_proyecto", "proyecto_id"),
        Index("idx_archivo_estado", "estado"),
    )
