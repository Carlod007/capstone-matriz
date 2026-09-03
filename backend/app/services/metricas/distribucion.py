# app/services/metricas/distribucion.py
"""Descripción estadística de los valores observados de una métrica.

La mediana, los percentiles y el rango intercuartílico resumen la distribución;
no dictaminan por sí solos si una métrica es útil ni si el resultado es bueno.
El umbral universal de IQR que existía aquí mezclaba escalas distintas y no
estaba calibrado contra N6, por lo que se retiró. Cualquier clasificación futura
debe ser específica de cada métrica y validarse con evidencia humana.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Sequence


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


def describir(codigo: str, valores: Sequence[float]) -> Distribucion:
    """Resume los valores válidos sin convertir su dispersión en un juicio."""
    limpios = []
    for v in valores:
        try:
            if v is None:
                continue
            limpios.append(float(v))
        except (TypeError, ValueError):
            continue

    if not limpios:
        return Distribucion(codigo=codigo, n=0)

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
    return d


def tabla(distribuciones: Sequence[Distribucion]) -> str:
    """Representación en texto, apta para consola o informe."""
    if not distribuciones:
        return "(sin métricas)"
    cab = ("%-26s %4s %8s %8s %8s %8s %8s %8s"
           % ("metrica", "n", "min", "P25", "mediana", "P75", "max", "IQR"))
    lineas = [cab, "-" * len(cab)]
    for d in distribuciones:
        if d.n == 0:
            lineas.append("%-26s %4d  (sin datos)" % (d.codigo, 0))
            continue
        lineas.append(
            "%-26s %4d %8.4f %8.4f %8.4f %8.4f %8.4f %8.4f"
            % (d.codigo, d.n, d.minimo, d.p25, d.mediana, d.p75, d.maximo,
               d.iqr))
    return "\n".join(lineas)
