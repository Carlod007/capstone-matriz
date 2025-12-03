from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, func
from app.models.proyecto import Base  # usa el mismo Base

class Articulo(Base):
    __tablename__ = "articulo"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proyecto_id: Mapped[str] = mapped_column(String(36))
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    titulo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    creado_en: Mapped[DateTime] = mapped_column(DateTime, server_default=func.current_timestamp())
