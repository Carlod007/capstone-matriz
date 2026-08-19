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


def emitir_token(usuario_id: str, inicio_sesion: datetime | None = None) -> str:
    """Emite un token de sesion.

    `inicio_sesion` es el momento en que se escribio la contrasena, y viaja en
    el token como `ini`. No es lo mismo que `iat`: al renovar, `iat` avanza y
    `ini` se conserva, de modo que la sesion puede refrescarse mientras se usa
    pero no vivir para siempre. Sin ese ancla, renovar indefinidamente
    convertiria un token robado en permanente.
    """
    ahora = datetime.now(timezone.utc)
    inicio = inicio_sesion or ahora
    return jwt.encode(
        {
            "sub": usuario_id,
            "iat": ahora,
            "ini": int(inicio.timestamp()),
            "exp": ahora + timedelta(hours=JWT_HORAS),
        },
        JWT_SECRETO,
        algorithm=JWT_ALGORITMO,
    )


def datos_token(token: str) -> dict:
    """Contenido verificado del token. Levanta TokenInvalido si no vale.

    `algorithms` se fija explicitamente. Aceptar el algoritmo que declare el
    propio token es la vulnerabilidad clasica de JWT: basta con enviar uno
    firmado con "none" para entrar sin secreto.
    """
    try:
        datos = jwt.decode(token, JWT_SECRETO, algorithms=[JWT_ALGORITMO])
    except jwt.PyJWTError as exc:
        raise TokenInvalido(str(exc)) from exc

    if not datos.get("sub"):
        raise TokenInvalido("el token no identifica a ningun usuario")
    return datos


def leer_token(token: str) -> str:
    """Devuelve el identificador del usuario."""
    return datos_token(token)["sub"]


def inicio_de_sesion(datos: dict) -> datetime:
    """Cuando se escribio la contrasena por ultima vez.

    Los tokens emitidos antes de que existiera `ini` no lo traen. Se toma su
    `iat` como inicio: es lo mas antiguo que se puede afirmar de ellos, y asi
    una sesion vieja no obtiene un techo mas generoso que una nueva.
    """
    marca = datos.get("ini") or datos.get("iat")
    if not marca:
        raise TokenInvalido("el token no dice cuando empezo la sesion")
    return datetime.fromtimestamp(int(marca), tz=timezone.utc)
