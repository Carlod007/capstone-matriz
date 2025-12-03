from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Integer, Boolean, DateTime, func

class Base(DeclarativeBase): pass

class Proyecto(Base):
    __tablename__ = "proyecto"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tema_principal: Mapped[str] = mapped_column(String(200))
    objetivo: Mapped[str] = mapped_column(Text)
    metodologia_txt: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sector_txt: Mapped[str | None] = mapped_column(String(150), nullable=True)
    n_articulos_objetivo: Mapped[int] = mapped_column(Integer)
    estado_arte_generado: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[DateTime] = mapped_column(DateTime, server_default=func.current_timestamp())
