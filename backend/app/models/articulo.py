from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import CHAR, DateTime, ForeignKey, Index, String, UniqueConstraint, func

from app.models.proyecto import Base  # usa el mismo Base


class Articulo(Base):
    __tablename__ = "articulo"

    # CHAR y no String: la base usa CHAR(36) para los identificadores, y
    # declararlo distinto hacia que Alembic viera una diferencia inexistente y
    # propusiera alterar todas las columnas.
    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    # La clave foranea se declara aqui, no solo en la base: sin ella
    # SQLAlchemy desconoce la dependencia y ordena los INSERT de forma
    # arbitraria, lo que hacia fallar la insercion de un articulo y su archivo
    # en la misma transaccion.
    proyecto_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("proyecto.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    titulo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    creado_en: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True)

    __table_args__ = (
        UniqueConstraint("proyecto_id", "doi", name="uq_articulo_proy_doi"),
        Index("idx_articulo_proyecto", "proyecto_id"),
    )
