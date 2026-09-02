"""Unico punto de escritura para métricas versionadas."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.metrica import Metrica
from app.services.metricas.catalogo import ficha
from app.services.procedencia import capturar_procedencia


def registrar_metrica(
    db: Session,
    proyecto_id: str,
    ambito: str,
    referencia_id: str,
    codigo: str,
    valor: float | None,
    detalle: dict | None = None,
) -> Metrica:
    """Añade una medición y fija la versión declarada por su catálogo.

    Un código fuera del catálogo queda con versión nula: asignarle v1 por
    defecto ocultaría un error de registro y fabricaría procedencia.
    """
    definicion = ficha(codigo)
    registro = Metrica(
        id=str(uuid.uuid4()),
        proyecto_id=proyecto_id,
        ambito=ambito,
        referencia_id=referencia_id,
        codigo=codigo,
        version_formula=(definicion.version_formula if definicion else None),
        valor=None if valor is None else float(valor),
        detalle=detalle,
        procedencia=capturar_procedencia(),
    )
    db.add(registro)
    return registro
