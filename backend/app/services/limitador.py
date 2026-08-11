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
from typing import Callable, TypeVar

T = TypeVar("T")

# Límites del nivel gratuito. Se dejan configurables porque un plan de pago
# los amplía y no tendría sentido frenar de más.
LIMITE_EMBEDDINGS_MIN = int(os.getenv("LIMITE_EMBEDDINGS_MIN", "90"))
LIMITE_GENERACION_MIN = int(os.getenv("LIMITE_GENERACION_MIN", "10"))
MAX_REINTENTOS = int(os.getenv("MAX_REINTENTOS", "5"))
ESPERA_MAXIMA = float(os.getenv("ESPERA_MAXIMA_SEG", "70"))


class Limitador:
    """Cubo de fichas sencillo, seguro entre hilos.

    Se reponen `por_minuto` fichas de forma continua. `adquirir(n)` bloquea
    hasta que haya n fichas disponibles, de modo que las peticiones se
    reparten en el tiempo en lugar de agotar la cuota de golpe.
    """

    def __init__(self, por_minuto: int, nombre: str = ""):
        self.por_minuto = max(1, por_minuto)
        self.nombre = nombre
        self._fichas = float(self.por_minuto)
        self._ultimo = time.monotonic()
        self._cerrojo = threading.Lock()

    def _reponer(self) -> None:
        ahora = time.monotonic()
        transcurrido = ahora - self._ultimo
        self._ultimo = ahora
        self._fichas = min(
            float(self.por_minuto),
            self._fichas + transcurrido * (self.por_minuto / 60.0),
        )

    def adquirir(self, n: int = 1) -> float:
        """Espera lo necesario para consumir n fichas. Devuelve la espera."""
        n = max(1, n)
        esperado = 0.0
        while True:
            with self._cerrojo:
                self._reponer()
                if self._fichas >= n or n > self.por_minuto:
                    # Si n supera la capacidad total no se puede satisfacer
                    # nunca por completo: se consume lo que haya y se sigue,
                    # dejando que el reintento absorba el exceso.
                    self._fichas = max(0.0, self._fichas - n)
                    return esperado
                faltan = n - self._fichas
                espera = faltan / (self.por_minuto / 60.0)
            espera = min(espera, 5.0)
            time.sleep(espera)
            esperado += espera


limitador_embeddings = Limitador(LIMITE_EMBEDDINGS_MIN, "embeddings")
limitador_generacion = Limitador(LIMITE_GENERACION_MIN, "generacion")


# ---------------------------------------------------------------- reintentos
_RE_RETRY = re.compile(r"'?retryDelay'?\s*:\s*'?(\d+(?:\.\d+)?)s", re.IGNORECASE)


def es_recuperable(exc: Exception) -> bool:
    """Distingue un fallo transitorio de uno definitivo.

    Reintentar un 400 por petición mal formada solo gasta tiempo; reintentar
    un 429 o un 503 casi siempre funciona.
    """
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
            if intento >= intentos or not es_recuperable(exc):
                raise
            espera = espera_sugerida(exc)
            if espera is None:
                espera = min(2.0 ** intento + random.uniform(0, 1.0), ESPERA_MAXIMA)
            time.sleep(espera)
    if ultimo:
        raise ultimo
    raise RuntimeError("con_reintentos terminó sin resultado: " + descripcion)
