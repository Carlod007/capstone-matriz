from sqlalchemy import CHAR, Boolean, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Usuario(Base):
    """Cuenta de una persona.

    El correo es la identidad y se guarda normalizado en minusculas: dos altas
    con el mismo correo escrito distinto serian dos cuentas distintas para la
    base y la misma persona para todo el mundo.

    Aqui vive el hash de la contrasena, nunca la contrasena. Ningun esquema de
    salida lo expone; ver app/schemas/usuario.py.
    """

    __tablename__ = "usuario"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    correo: Mapped[str] = mapped_column(String(190), nullable=False)
    # 60 bytes es lo que ocupa un hash de bcrypt; se deja holgura por si algun
    # dia se cambia de algoritmo, porque migrar hashes es caro.
    contrasena_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    # Desactivar en vez de borrar: una cuenta borrada se llevaria por delante
    # sus proyectos, y casi siempre lo que se quiere es cortar el acceso.
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True)

    __table_args__ = (
        # 190 y no 255: con utf8mb4 cada caracter ocupa hasta 4 bytes y el
        # indice de MySQL admite 767 en formatos antiguos. 190 entra siempre.
        UniqueConstraint("correo", name="uq_usuario_correo"),
    )
