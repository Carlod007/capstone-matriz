# app/services/limitador.py
"""
Control de ritmo y reintentos frente a la API del modelo.

El nivel gratuito de Gemini limita las peticiones por minuto y **cuenta cada
texto embebido por separado**, aunque el SDK los agrupe en una sola llamada
HTTP. Sin control de ritmo, indexar cinco artículos agota la cuota a mitad
del segundo y el lote entero se pierde con un error 500.

Aquí viven dos piezas complementarias:

- `Limitador`: cubo de fichas que reparte el permiso de emitir peticiones a
  lo largo del minuto en lugar de dispararlas en ráfaga.
- `con_reintentos`: envuelve una llamada y reintenta ante errores
  recuperables, respetando el `retryDelay` que devuelve el propio servicio.
"""

from __future__ import annotations

import os
import random
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable, TypeVar

T = TypeVar("T")

# Límites del nivel gratuito, comprobados en el panel de AI Studio:
#
#   gemini-2.5-flash      5 peticiones/min     20 al día
#   gemini-embedding-001  100 peticiones/min   1000 al día
#
# Se deja margen por dos motivos: el contador vive en el proceso y se pierde
# al reiniciar el servidor, de modo que puede quedar consumo reciente sin
# registrar; y la ventana del servicio no tiene por qué alinearse con la
# nuestra. Configurables porque un plan de pago los amplía.
#
# La generación estaba fijada en 8 por minuto cuando el tope real son 5, y el
# panel lo reflejaba en rojo: 6 de 5. Un limitador por encima del límite no
# limita nada.
LIMITE_EMBEDDINGS_MIN = int(os.getenv("LIMITE_EMBEDDINGS_MIN", "70"))
LIMITE_GENERACION_MIN = int(os.getenv("LIMITE_GENERACION_MIN", "4"))

# Cuotas diarias, para poder avisar antes de agotarlas.
LIMITE_GENERACION_DIA = int(os.getenv("LIMITE_GENERACION_DIA", "20"))
LIMITE_EMBEDDINGS_DIA = int(os.getenv("LIMITE_EMBEDDINGS_DIA", "1000"))

# Huso en el que el proveedor reinicia sus cuotas diarias. El panel de AI
# Studio rotula sus gráficas en UTC-8, de modo que el corte es la medianoche
# de ese huso y no la del servidor donde corre esto.
HUSO_REINICIO = int(os.getenv("HUSO_REINICIO_UTC", "-8"))
MAX_REINTENTOS = int(os.getenv("MAX_REINTENTOS", "5"))
ESPERA_MAXIMA = float(os.getenv("ESPERA_MAXIMA_SEG", "70"))


VENTANA = 60.0  # segundos


class Limitador:
    """Ventana deslizante de peticiones, segura entre hilos.

    Se registra la marca de tiempo de cada petición emitida y se garantiza
    que en ningún intervalo de 60 segundos haya más de `por_minuto`.

    La primera versión usaba un cubo de fichas que arrancaba lleno. Eso
    permitía una ráfaga inicial de `por_minuto` peticiones y, mientras
    seguía reponiendo, podía llegar a emitir casi el doble dentro del primer
    minuto: exactamente lo que volvió a agotar la cuota. Un cubo de fichas
    limita el caudal medio; el servicio limita el conteo dentro de una
    ventana, que no es lo mismo.
    """

    def __init__(self, por_minuto: int, nombre: str = ""):
        self.por_minuto = max(1, por_minuto)
        self.nombre = nombre
        self._marcas: deque[float] = deque()
        self._cerrojo = threading.Lock()

    def _purgar(self, ahora: float) -> None:
        limite = ahora - VENTANA
        while self._marcas and self._marcas[0] <= limite:
            self._marcas.popleft()

    def usadas(self) -> int:
        """Peticiones emitidas en los últimos 60 segundos."""
        with self._cerrojo:
            self._purgar(time.monotonic())
            return len(self._marcas)

    def adquirir(self, n: int = 1) -> float:
        """Espera lo necesario para emitir n peticiones. Devuelve la espera.

        Si n supera la capacidad de la ventana se consume por tramos, en vez
        de bloquear indefinidamente a la espera de un hueco imposible.
        """
        n = max(1, n)
        esperado = 0.0
        restantes = n

        while restantes > 0:
            with self._cerrojo:
                ahora = time.monotonic()
                self._purgar(ahora)
                hueco = self.por_minuto - len(self._marcas)
                if hueco > 0:
                    toma = min(hueco, restantes)
                    self._marcas.extend([ahora] * toma)
                    restantes -= toma
                    if restantes == 0:
                        return esperado
                # Quede hueco o no, para seguir hay que aguardar a que la
                # marca más antigua salga de la ventana. Calcularlo siempre
                # desde esa marca evita esperas cortas arbitrarias, que
                # desplazaban las emisiones y hacían que dos grupos cayeran
                # dentro del mismo minuto.
                espera = self._marcas[0] + VENTANA - ahora
            time.sleep(max(0.0, min(espera, 5.0)))
            esperado += max(0.0, min(espera, 5.0))
        return esperado


limitador_embeddings = Limitador(LIMITE_EMBEDDINGS_MIN, "embeddings")
limitador_generacion = Limitador(LIMITE_GENERACION_MIN, "generacion")


def proximo_reinicio_diario(ahora_utc: datetime | None = None) -> datetime:
    """Medianoche siguiente en el huso del proveedor, devuelta en UTC.

    A diferencia de la ventana móvil que lleva esta aplicación, esto sí es el
    criterio del proveedor: sus cuotas diarias se reinician de golpe a esa
    hora, no llamada a llamada.
    """
    ahora_utc = ahora_utc or datetime.now(timezone.utc)
    if ahora_utc.tzinfo is None:
        ahora_utc = ahora_utc.replace(tzinfo=timezone.utc)
    huso = timezone(timedelta(hours=HUSO_REINICIO))
    local = ahora_utc.astimezone(huso)
    manana = (local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return manana.astimezone(timezone.utc)


def segundos_hasta_reinicio(ahora_utc: datetime | None = None) -> int:
    ahora_utc = ahora_utc or datetime.now(timezone.utc)
    if ahora_utc.tzinfo is None:
        ahora_utc = ahora_utc.replace(tzinfo=timezone.utc)
    return max(0, int((proximo_reinicio_diario(ahora_utc) - ahora_utc).total_seconds()))


# ---------------------------------------------------------------- reintentos
_RE_RETRY = re.compile(r"'?retryDelay'?\s*:\s*'?(\d+(?:\.\d+)?)s", re.IGNORECASE)


class CuotaDiariaAgotada(RuntimeError):
    """La cuota del día se ha consumido; no se recupera esperando."""


def es_cuota_diaria(exc: Exception) -> bool:
    """Distingue el límite diario del límite por minuto.

    Ambos llegan como 429, pero solo el segundo se resuelve esperando. El
    servicio identifica el diario en `quotaId` con el sufijo `PerDay`, y aun
    así devuelve un `retryDelay` de un minuto: obedecerlo supone encadenar
    reintentos inútiles durante minutos para acabar fallando igual.
    """
    texto = str(exc)
    return "PerDay" in texto or "per day" in texto.lower()


def es_recuperable(exc: Exception) -> bool:
    """Distingue un fallo transitorio de uno definitivo.

    Reintentar un 400 por petición mal formada solo gasta tiempo; reintentar
    un 429 por límite de minuto casi siempre funciona. El límite diario, en
    cambio, es definitivo hasta el día siguiente.
    """
    if es_cuota_diaria(exc):
        return False
    codigo = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if codigo in (429, 500, 502, 503, 504):
        return True
    texto = str(exc)
    return any(m in texto for m in
               ("RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED",
                "INTERNAL", "429", "503"))


def espera_sugerida(exc: Exception) -> float | None:
    """Extrae el `retryDelay` que el servicio indica en la respuesta."""
    m = _RE_RETRY.search(str(exc))
    if not m:
        return None
    try:
        return min(float(m.group(1)) + 1.0, ESPERA_MAXIMA)
    except ValueError:
        return None


def con_reintentos(fn: Callable[[], T], descripcion: str = "llamada",
                   intentos: int = MAX_REINTENTOS) -> T:
    """Ejecuta `fn` reintentando los fallos recuperables.

    Prioriza el `retryDelay` que devuelve el servicio; si no lo indica, aplica
    retroceso exponencial con una pequeña componente aleatoria para no
    sincronizar los reintentos de varias peticiones.
    """
    ultimo: Exception | None = None
    for intento in range(1, max(1, intentos) + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            ultimo = exc
            if es_cuota_diaria(exc):
                # Mensaje accionable en lugar de un volcado de la API.
                raise CuotaDiariaAgotada(
                    "Se ha agotado la cuota diaria del nivel gratuito para %s. "
                    "No se recupera esperando: se restablece al dia siguiente. "
                    "Detalle del servicio: %s" % (descripcion, str(exc)[:300])
                ) from exc
            if intento >= intentos or not es_recuperable(exc):
                raise
            espera = espera_sugerida(exc)
            if espera is None:
                espera = min(2.0 ** intento + random.uniform(0, 1.0), ESPERA_MAXIMA)
            time.sleep(espera)
    if ultimo:
        raise ultimo
    raise RuntimeError("con_reintentos terminó sin resultado: " + descripcion)
