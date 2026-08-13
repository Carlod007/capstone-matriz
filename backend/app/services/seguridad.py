# app/services/seguridad.py
"""
Contrasenas y tokens de sesion.

Se apoya en bcrypt directamente en vez de en passlib: passlib lleva anos sin
version nueva y arrastra un choque conocido con bcrypt 4 y posteriores. La
interfaz que hace falta aqui son dos funciones, no vale la pena una capa mas.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import JWT_ALGORITMO, JWT_HORAS, JWT_SECRETO

# bcrypt trunca silenciosamente lo que pase de 72 bytes: una contrasena larga
# valdria lo mismo que sus primeros 72 caracteres, y dos distintas con igual
# prefijo abririan la misma cuenta. Se rechaza en vez de truncar.
LIMITE_BCRYPT = 72
MINIMO_CONTRASENA = 8


class ContrasenaInvalida(ValueError):
    """La contrasena no cumple los requisitos minimos."""


class TokenInvalido(Exception):
    """El token no se puede verificar: alterado, caducado o mal formado."""


def revisar_contrasena(contrasena: str) -> None:
    """Levanta ContrasenaInvalida si no sirve. No mide 'fortaleza'.

    Exigir mayusculas y simbolos empuja a la gente hacia contrasenas cortas y
    predecibles; la longitud es lo que de verdad cuesta de romper.
    """
    if len(contrasena) < MINIMO_CONTRASENA:
        raise ContrasenaInvalida(
            "La contrasena debe tener al menos %d caracteres." % MINIMO_CONTRASENA)
    if len(contrasena.encode("utf-8")) > LIMITE_BCRYPT:
        raise ContrasenaInvalida(
            "La contrasena no puede pasar de %d bytes." % LIMITE_BCRYPT)


def cifrar(contrasena: str) -> str:
    revisar_contrasena(contrasena)
    return bcrypt.hashpw(contrasena.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def comprobar(contrasena: str, hash_guardado: str) -> bool:
    """Compara sin filtrar el motivo del fallo.

    Un hash corrupto en la base devuelve False, no una excepcion: por fuera
    debe verse igual que una contrasena equivocada.
    """
    try:
        return bcrypt.checkpw(
            contrasena.encode("utf-8"), hash_guardado.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def emitir_token(usuario_id: str) -> str:
    ahora = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": usuario_id,
            "iat": ahora,
            "exp": ahora + timedelta(hours=JWT_HORAS),
        },
        JWT_SECRETO,
        algorithm=JWT_ALGORITMO,
    )


def leer_token(token: str) -> str:
    """Devuelve el identificador del usuario. Levanta TokenInvalido si no vale.

    `algorithms` se fija explicitamente. Aceptar el algoritmo que declare el
    propio token es la vulnerabilidad clasica de JWT: basta con enviar uno
    firmado con "none" para entrar sin secreto.
    """
    try:
        datos = jwt.decode(token, JWT_SECRETO, algorithms=[JWT_ALGORITMO])
    except jwt.PyJWTError as exc:
        raise TokenInvalido(str(exc)) from exc

    usuario_id = datos.get("sub")
    if not usuario_id:
        raise TokenInvalido("el token no identifica a ningun usuario")
    return usuario_id
