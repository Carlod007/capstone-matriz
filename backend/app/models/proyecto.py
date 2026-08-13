from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    CHAR, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func,
)

# La base declarativa vive en app/database.py. Se reexporta aquí porque casi
# todos los modelos la importan desde este módulo; lo importante es que sea
# una sola en todo el proyecto (C-14).
from app.database import Base


class Proyecto(Base):
    __tablename__ = "proyecto"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    # El dueño. Todo lo demás —artículos, ejecuciones, brechas, métricas—
    # cuelga del proyecto, así que basta esta columna para separar cuentas.
    #
    # Admite NULL porque al añadirla podía no existir todavía ningún usuario a
    # quien asignar los proyectos ya creados. No es un hueco: un proyecto sin
    # dueño no pertenece a nadie y por tanto no lo ve nadie, que es el fallo
    # seguro. `crear_cuenta.py` los adopta al dar de alta la primera cuenta.
    usuario_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", name="fk_proyecto_usuario",
                   ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=True,
    )
    tema_principal: Mapped[str] = mapped_column(String(200))
    objetivo: Mapped[str] = mapped_column(Text)
    metodologia_txt: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sector_txt: Mapped[str | None] = mapped_column(String(150), nullable=True)
    n_articulos_objetivo: Mapped[int] = mapped_column(Integer)
    estado_arte_generado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    creado_en: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True)

    __table_args__ = (
        Index("idx_proyecto_estado", "estado_arte_generado"),
        Index("idx_proyecto_tema", "tema_principal"),
        # Cada consulta de cada endpoint filtra por dueño; sin índice, todas
        # recorren la tabla entera.
        Index("idx_proyecto_usuario", "usuario_id"),
    )
