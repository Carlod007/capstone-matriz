# app/services/metricas/__init__.py
"""
Capa de medición, versión 2.

Sustituye a las seis mediciones anteriores, de las que tres resultaron ser
cuasi-constantes por construcción y por tanto incapaces de distinguir una
salida buena de una mala.

Organización por niveles, según la especificación:

    N0  calidad de ingesta          -> app/utils/text_extractor.py
    N1  calidad de la recuperación  -> niveles.py
    N2  fidelidad a la fuente       -> pendiente (requiere juez)
    N3  especificidad               -> niveles.py
    N4  calidad del resumen         -> niveles.py
    N5  tipificación y síntesis     -> pendiente
    N6  anclaje humano              -> pendiente (campaña de anotación)

Principios que aplica el módulo:

1. Cada métrica mide una sola cosa y se llama como lo que mide.
2. Ninguna métrica puede ser cuasi-constante: `distribucion.describir`
   dictamina si discrimina sobre datos reales.
3. Los umbrales se calibran sobre la distribución observada, no se inventan.
"""

from app.services.metricas import distribucion, niveles, texto  # noqa: F401

__all__ = ["distribucion", "niveles", "texto"]
