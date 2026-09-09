"""Estado de completitud de la comprobación de fidelidad.

Este módulo responde una pregunta operativa: qué brechas ya tienen todas las
mediciones N2 necesarias. No agrega sus valores ni compara fórmulas. Las
distribuciones técnicas sí deben separarse por versión y procedencia, pero esa
separación no puede convertir cinco brechas completas en una sola.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models.metrica import Metrica


CODIGOS_N2_COMPLETOS = {
    "N2.1",
    "N2.2",
    "N2.4",
    "N2.5",
    "N2.6",
    "N2.verificada",
}


def brechas_verificadas_completas(
    db: Session,
    proyecto_id: str,
    referencia_ids: Iterable[str] | None = None,
) -> set[str]:
    """Devuelve los identificadores con una comprobación N2 completa vigente.

    Se toma la medición más reciente de cada código. La revisión del código y
    la versión de fórmula se conservan en cada fila para auditoría, pero no
    dividen este conteo: completar la fidelidad es un estado por brecha.
    """
    referencias = set(referencia_ids) if referencia_ids is not None else None
    if referencias == set():
        return set()

    consulta = (
        db.query(Metrica)
        .filter(
            Metrica.proyecto_id == proyecto_id,
            Metrica.codigo.in_(CODIGOS_N2_COMPLETOS),
        )
        .order_by(Metrica.creado_en.asc(), Metrica.id.asc())
    )
    if referencias is not None:
        consulta = consulta.filter(Metrica.referencia_id.in_(referencias))

    vigentes: dict[tuple[str, str], Metrica] = {}
    for metrica in consulta.all():
        vigentes[(metrica.referencia_id, metrica.codigo)] = metrica

    codigos_por_brecha: dict[str, set[str]] = {}
    for referencia_id, codigo in vigentes:
        codigos_por_brecha.setdefault(referencia_id, set()).add(codigo)

    completas = set()
    for referencia_id, codigos in codigos_por_brecha.items():
        realizada = vigentes.get((referencia_id, "N2.verificada"))
        if (
            CODIGOS_N2_COMPLETOS <= codigos
            and realizada is not None
            and realizada.valor == 1.0
        ):
            completas.add(referencia_id)
    return completas
