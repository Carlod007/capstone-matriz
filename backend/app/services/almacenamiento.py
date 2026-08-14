# app/services/almacenamiento.py
"""
Acceso a los PDF guardados, detras de una interfaz.

Hasta ahora `STORAGE_DIR` se leia en el router de subida y la ruta absoluta
del archivo se guardaba en `archivo.ruta`, de modo que el resto del codigo
abria ficheros del disco directamente. Mientras todo corra en una maquina eso
funciona; en cuanto haya dos —un servidor web y un trabajador en otro sitio—,
o el disco sea efimero, deja de funcionar y hay que buscar rutas por todo el
codigo.

Aqui se guarda una *clave* relativa, no una ruta: `<usuario>/<uuid>.pdf`. La
clave no dice donde vive el archivo, solo como se llama, y eso es lo que
permite cambiar el donde sin tocar a quien la usa.

Solo hay implementacion local. No es un olvido: mientras el sistema viva en
una maquina con disco persistente, el almacenamiento de objetos no aporta
nada y anadirlo seria pagar complejidad por adelantado. Lo que si hacia falta
era que anadirlo fuera escribir una implementacion en este archivo en lugar
de rastrear `open()` por el proyecto.

La carpeta por usuario no es organizacion: es que el aislamiento entre
cuentas valga tambien en el disco. Con todos los PDF en el mismo directorio,
un error al construir un nombre podia servir el archivo de otra persona.
"""

from __future__ import annotations

import os
import re
import uuid

from app.config import STORAGE_DIR

# Solo lo que puede aparecer en una clave legitima. Se comprueba en lugar de
# confiar: una clave con `..` permitiria leer cualquier fichero de la maquina,
# y las claves vienen de la base, que a su vez se alimenta de lo que sube el
# usuario.
CLAVE_VALIDA = re.compile(r"^[0-9a-fA-F-]{36}/[0-9a-fA-F-]{36}\.pdf$")


class ClaveInvalida(ValueError):
    """La clave no tiene la forma esperada y no se va a tocar el disco."""


def _raiz() -> str:
    return os.path.abspath(STORAGE_DIR)


def nueva_clave(usuario_id: str) -> str:
    """Una clave para un archivo nuevo de ese usuario."""
    return "%s/%s.pdf" % (usuario_id, uuid.uuid4())


def guardar(clave: str, datos: bytes) -> str:
    """Escribe el archivo y devuelve la clave con la que recuperarlo."""
    if not CLAVE_VALIDA.match(clave):
        raise ClaveInvalida("Clave con formato inesperado: %r" % clave)

    destino = os.path.join(_raiz(), *clave.split("/"))
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "wb") as f:
        f.write(datos)
    return clave


def ruta_local(clave_o_ruta: str) -> str:
    """Un camino del sistema de ficheros que se puede abrir.

    Acepta tambien las rutas absolutas que quedaron guardadas antes de que
    existieran las claves. Convertirlas exigiria mover los archivos y
    reescribir la base, y no aporta nada: seguir aceptandolas cuesta tres
    lineas y evita que los proyectos ya cargados dejen de abrirse.

    Cuando haya almacenamiento remoto, esta funcion sera la que descargue el
    archivo a un temporal y devuelva su ruta; los extractores no tendran que
    enterarse.
    """
    if not clave_o_ruta:
        raise ClaveInvalida("Referencia de archivo vacia.")

    # Forma antigua: una ruta del disco tal cual.
    if os.path.isabs(clave_o_ruta) or os.path.exists(clave_o_ruta):
        return clave_o_ruta

    if not CLAVE_VALIDA.match(clave_o_ruta):
        raise ClaveInvalida("Clave con formato inesperado: %r" % clave_o_ruta)

    destino = os.path.join(_raiz(), *clave_o_ruta.split("/"))

    # Cinturon y tirantes: aunque la expresion regular ya excluye `..`, se
    # confirma que el resultado no se sale de la carpeta de almacenamiento.
    if not os.path.abspath(destino).startswith(_raiz() + os.sep):
        raise ClaveInvalida("La clave apunta fuera del almacenamiento.")
    return destino


def existe(clave_o_ruta: str) -> bool:
    try:
        return os.path.exists(ruta_local(clave_o_ruta))
    except ClaveInvalida:
        return False


def borrar(clave_o_ruta: str) -> bool:
    """Borra el archivo. Devuelve si habia algo que borrar."""
    try:
        ruta = ruta_local(clave_o_ruta)
    except ClaveInvalida:
        return False
    if not os.path.exists(ruta):
        return False
    os.remove(ruta)
    return True
