# app/config.py
"""
Configuracion de la aplicacion, en un solo sitio.

Hasta ahora cada modulo leia sus variables con os.getenv por su cuenta y con
su propio valor por defecto. Eso funciona mientras todo corre en una maquina
conocida; en un servidor, una variable mal escrita no se nota al arrancar,
sino en la primera peticion que la necesita, con un error que no menciona la
variable.

Aqui se leen todas al importar el modulo y las obligatorias se exigen. Es
preferible que la aplicacion no arranque a que arranque mal.
"""

import os
import secrets

from dotenv import load_dotenv

load_dotenv()


def _texto(nombre: str, defecto: str = "") -> str:
    return os.getenv(nombre, defecto).strip()


def _bandera(nombre: str, defecto: bool = False) -> bool:
    v = _texto(nombre).lower()
    if not v:
        return defecto
    return v in ("1", "true", "si", "sí", "yes", "on")


def _entero(nombre: str, defecto: int) -> int:
    v = _texto(nombre)
    try:
        return int(v) if v else defecto
    except ValueError:
        raise RuntimeError(
            "%s debe ser un numero entero; se recibio %r" % (nombre, v)
        ) from None


# ------------------------------------------------------------------ sesion

# Secreto con el que se firman los tokens. Sin valor por defecto a proposito:
# un secreto de relleno es peor que ninguno, porque parece configurado y
# permite a cualquiera que conozca el codigo firmar tokens validos.
JWT_SECRETO = _texto("JWT_SECRETO")

# Ocho horas: lo bastante para una sesion de trabajo sin volver a entrar, y lo
# bastante corto para que un token filtrado no sirva indefinidamente. No hay
# revocacion —eso exige guardar los tokens emitidos—, asi que la caducidad es
# la unica defensa.
JWT_HORAS = _entero("JWT_HORAS", 8)
JWT_ALGORITMO = "HS256"

# El registro se construye completo pero nace cerrado: por ahora la instancia
# es de una sola persona. Abrirlo es cambiar esta variable, no tocar codigo.
REGISTRO_ABIERTO = _bandera("REGISTRO_ABIERTO", False)


def generar_secreto() -> str:
    """Un secreto valido, para pegar en el .env."""
    return secrets.token_urlsafe(48)


def revisar(estricto: bool = True) -> list[str]:
    """Devuelve lo que falta. Con `estricto`, ademas impide arrancar.

    Se llama al arrancar la aplicacion. Las pruebas la usan sin `estricto`
    para comprobar que detecta lo que falta sin tumbar el proceso.
    """
    faltan = []
    if not _texto("MYSQL_URI"):
        faltan.append(
            "MYSQL_URI: direccion de la base de datos."
        )
    if not JWT_SECRETO:
        faltan.append(
            "JWT_SECRETO: secreto para firmar las sesiones. Genera uno con\n"
            "    python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    elif len(JWT_SECRETO) < 32:
        faltan.append(
            "JWT_SECRETO: demasiado corto (%d caracteres, minimo 32). Un "
            "secreto adivinable equivale a no tener ninguno." % len(JWT_SECRETO)
        )

    if estricto and faltan:
        raise RuntimeError(
            "Faltan variables de entorno en backend/.env:\n\n  - %s\n"
            % "\n  - ".join(faltan)
        )
    return faltan
