# app/services/metricas/distribucion.py
"""
Descripción de la distribución de una métrica.

Todo el reporte anterior del sistema se construía con promedios, lo que
ocultaba exactamente el problema que tenía: una media de 0.86 con rango
intercuartílico de 0.02 y otra con rango de 0.40 se presentaban igual, aunque
la primera indica una métrica muerta y la segunda una que discrimina.

El criterio operativo es el principio 2 de la especificación: una métrica cuyo
rango intercuartílico no llega a 0.05 sobre datos reales no está midiendo nada
y debe retirarse.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Sequence

IQR_MINIMO = 0.05


@dataclass
class Distribucion:
    codigo: str
    n: int
    minimo: float = 0.0
    p25: float = 0.0
    mediana: float = 0.0
    p75: float = 0.0
    maximo: float = 0.0
    media: float = 0.0
    iqr: float = 0.0
    rango: float = 0.0
    discrimina: bool = False
    veredicto: str = ""

    def dict(self) -> dict:
        return asdict(self)


def percentil(ordenados: Sequence[float], p: float) -> float:
    """Percentil por interpolación lineal."""
    if not ordenados:
        return 0.0
    if len(ordenados) == 1:
        return float(ordenados[0])
    k = (len(ordenados) - 1) * p
    f = int(k)
    if f + 1 >= len(ordenados):
        return float(ordenados[-1])
    return float(ordenados[f] + (k - f) * (ordenados[f + 1] - ordenados[f]))


def describir(codigo: str, valores: Sequence[float], iqr_minimo: float = IQR_MINIMO
              ) -> Distribucion:
    """Resume una métrica y dictamina si discrimina."""
    limpios = []
    for v in valores:
        try:
            if v is None:
                continue
            limpios.append(float(v))
        except (TypeError, ValueError):
            continue

    if not limpios:
        return Distribucion(codigo=codigo, n=0, veredicto="sin datos")

    limpios.sort()
    d = Distribucion(
        codigo=codigo,
        n=len(limpios),
        minimo=round(limpios[0], 4),
        p25=round(percentil(limpios, 0.25), 4),
        mediana=round(percentil(limpios, 0.50), 4),
        p75=round(percentil(limpios, 0.75), 4),
        maximo=round(limpios[-1], 4),
        media=round(sum(limpios) / len(limpios), 4),
    )
    d.iqr = round(d.p75 - d.p25, 4)
    d.rango = round(d.maximo - d.minimo, 4)

    if len(limpios) < 5:
        d.veredicto = "muestra insuficiente (%d valores)" % len(limpios)
        d.discrimina = False
    elif d.iqr < iqr_minimo:
        d.veredicto = ("cuasi-constante: IQR %.4f por debajo de %.2f; "
                       "candidata a retirarse" % (d.iqr, iqr_minimo))
        d.discrimina = False
    else:
        d.veredicto = "discrimina (IQR %.4f)" % d.iqr
        d.discrimina = True
    return d


def tabla(distribuciones: Sequence[Distribucion]) -> str:
    """Representación en texto, apta para consola o informe."""
    if not distribuciones:
        return "(sin métricas)"
    cab = ("%-26s %4s %8s %8s %8s %8s %8s %8s  %s"
           % ("metrica", "n", "min", "P25", "mediana", "P75", "max", "IQR", "veredicto"))
    lineas = [cab, "-" * len(cab)]
    for d in distribuciones:
        if d.n == 0:
            lineas.append("%-26s %4d %s" % (d.codigo, 0, " " * 50 + d.veredicto))
            continue
        lineas.append(
            "%-26s %4d %8.4f %8.4f %8.4f %8.4f %8.4f %8.4f  %s"
            % (d.codigo, d.n, d.minimo, d.p25, d.mediana, d.p75, d.maximo,
               d.iqr, d.veredicto))
    return "\n".join(lineas)
