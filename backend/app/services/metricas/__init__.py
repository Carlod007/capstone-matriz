# app/services/metricas/__init__.py
"""
Capa de medición, versión 2.

Sustituye a las seis mediciones anteriores, de las que tres resultaron ser
cuasi-constantes por construcción y por tanto incapaces de distinguir una
salida buena de una mala.

Organización por niveles, según la especificación:

    N0  calidad de ingesta          -> app/utils/text_extractor.py
    N1  calidad de la recuperación  -> niveles.py
    N2  fidelidad a la fuente       -> services/verificacion.py
    N3  especificidad               -> niveles.py
    N4  calidad del resumen         -> niveles.py
    N5  tipificación y síntesis     -> metricas/sintesis.py
    N6  anclaje humano              -> routers/validacion.py (piloto 5/5)

Principios que aplica el módulo:

1. Cada métrica mide una sola cosa y se llama como lo que mide.
2. Sin valor no equivale a cero; una medición no aplicable conserva el motivo.
3. La dirección puede ser mayor, menor o descriptiva según el indicador.
4. Los umbrales de calidad requieren calibración contra el anclaje humano N6.
"""

from app.services.metricas import distribucion, niveles, texto  # noqa: F401

__all__ = ["distribucion", "niveles", "texto"]
