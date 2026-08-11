# app/routers/metricas_v2.py
"""
Endpoints de la capa de medición v2.

Sustituyen a /metrics/resumen, que leía las columnas retiradas y por eso
devuelve ceros: la interfaz mostraba entropía, similitud y val_score en 0,
dando la impresión de estar rota cuando en realidad esas métricas ya no se
calculan.

Se sirven distribuciones completas, no solo promedios. Una media de 0.86 con
un rango intercuartílico de 0.02 y otra con 0.40 dicen cosas muy distintas, y
presentarlas igual fue lo que oculto el problema original.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.articulo import Articulo
from app.models.estado_arte import EstadoDelArte
from app.models.metrica import Metrica
from app.models.proyecto import Proyecto
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run import Run, EstadoRun
from app.models.run_item import RunItem
from app.services.metricas import distribucion as D
from app.services.metricas.catalogo import CATALOGO, ficha

router = APIRouter(prefix="/proyectos", tags=["metricas-v2"])


def _ultimo_run(db: Session, proyecto_id: str) -> Run | None:
    # MySQL no admite NULLS LAST y tampoco hace falta: en orden descendente
    # coloca los nulos al final, que es justo lo que se busca.
    return (db.query(Run)
            .filter(Run.proyecto_id == proyecto_id)
            .order_by(Run.iniciado_en.desc(), Run.id)
            .first())


@router.get("/{proyecto_id}/metricas")
def metricas_proyecto(proyecto_id: str, db: Session = Depends(get_db)):
    """Distribuciones de cada métrica del último análisis del proyecto."""
    pr = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    run = _ultimo_run(db, proyecto_id)
    if not run:
        return {"proyecto_id": proyecto_id, "run": None, "metricas": [],
                "aviso": "El proyecto todavía no se ha analizado."}

    # Identificadores del último run: las métricas de ejecuciones anteriores
    # se conservan, pero mezclarlas falsearía las distribuciones.
    ids_brecha = [r[0] for r in
                  db.query(ResultadoBrecha.id)
                  .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
                  .filter(RunItem.run_id == run.id).all()]
    ids_articulo = [r[0] for r in
                    db.query(RunItem.articulo_id).filter(RunItem.run_id == run.id).all()]
    referencias = set(ids_brecha) | set(ids_articulo) | {run.id}

    # Una métrica de ámbito artículo conserva el mismo `referencia_id` entre
    # ejecuciones, así que filtrar solo por referencia mezclaría el análisis
    # actual con los anteriores. Se conserva la medición más reciente de cada
    # par (entidad, código), que es el valor vigente.
    ultima: dict[tuple[str, str], Metrica] = {}
    for m in (db.query(Metrica)
              .filter(Metrica.proyecto_id == proyecto_id)
              .order_by(Metrica.creado_en.asc()).all()):
        if m.referencia_id in referencias:
            ultima[(m.referencia_id, m.codigo)] = m

    valores: dict[str, list] = {}
    for m in ultima.values():
        valores.setdefault(m.codigo, []).append(m.valor)

    salida = []
    for codigo in sorted(valores):
        d = D.describir(codigo, valores[codigo])
        f = ficha(codigo)
        salida.append({
            **d.dict(),
            "nombre": f.nombre if f else codigo,
            "nivel": f.nivel if f else "",
            "ambito": f.ambito if f else "",
            "mejor": f.mejor if f else "neutro",
            "rango": f.rango if f else "",
            "descripcion": f.descripcion if f else "",
            "interpretacion": f.interpretacion if f else "",
        })

    estados = {}
    for (e,) in (db.query(ResultadoBrecha.estado_validacion)
                 .filter(ResultadoBrecha.id.in_(ids_brecha or ["-"])).all()):
        estados[e or ""] = estados.get(e or "", 0) + 1

    ea = (db.query(EstadoDelArte)
          .filter(EstadoDelArte.proyecto_id == proyecto_id)
          .order_by(EstadoDelArte.version.desc()).first())

    return {
        "proyecto_id": proyecto_id,
        "run": {
            "id": run.id,
            "estado": run.estado.value if hasattr(run.estado, "value") else str(run.estado),
            "finalizado_en": str(run.finalizado_en) if run.finalizado_en else None,
            "n_items_total": run.n_items_total,
            "n_items_ok": run.n_items_ok,
            "tokens_in": run.tokens_in or 0,
            "tokens_out": run.tokens_out or 0,
        },
        "conteos": {
            "articulos": len(set(ids_articulo)),
            "brechas": len(ids_brecha),
            "por_estado_validacion": estados,
        },
        "estado_arte": ({"version": ea.version, "fecha": str(ea.created_at),
                         "caracteres": len((ea.texto or "").strip())} if ea else None),
        "metricas": salida,
        # La validación automática está desactivada a propósito hasta
        # calibrarla; conviene que la interfaz lo diga en vez de mostrar
        # "pendiente" sin explicación.
        "validacion_calibrada": False,
    }


@router.get("/{proyecto_id}/metricas/por_articulo")
def metricas_por_articulo(proyecto_id: str, db: Session = Depends(get_db)):
    """Valor de cada métrica para cada artículo del último análisis."""
    run = _ultimo_run(db, proyecto_id)
    if not run:
        return {"run": None, "articulos": []}

    filas = (db.query(ResultadoBrecha, RunItem, Articulo)
             .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
             .join(Articulo, Articulo.id == RunItem.articulo_id)
             .filter(RunItem.run_id == run.id).all())

    # Igual que arriba: se toma la medición más reciente de cada par.
    por_referencia: dict[str, dict] = {}
    for m in (db.query(Metrica)
              .filter(Metrica.proyecto_id == proyecto_id)
              .order_by(Metrica.creado_en.asc()).all()):
        por_referencia.setdefault(m.referencia_id, {})[m.codigo] = m.valor

    articulos = []
    for rb, ri, art in filas:
        metricas = dict(por_referencia.get(rb.id, {}))
        metricas.update(por_referencia.get(art.id, {}))
        articulos.append({
            "articulo_id": art.id,
            "titulo": art.titulo,
            "doi": art.doi,
            "brecha_id": rb.id,
            "tipo_brecha": rb.tipo_brecha,
            "estado_validacion": rb.estado_validacion,
            "metricas": {c: v for c, v in sorted(metricas.items())},
        })

    return {
        "run": {"id": run.id},
        "catalogo": {c: f.dict() for c, f in CATALOGO.items()},
        "articulos": articulos,
    }


@router.get("/{proyecto_id}/consumo")
def consumo(proyecto_id: str, db: Session = Depends(get_db)):
    """Consumo de API estimado, para no chocar con la cuota sin avisar.

    El nivel gratuito permite 20 generaciones al día. Cada análisis gasta una
    por artículo más una para la síntesis, de modo que un proyecto de cinco
    artículos consume seis. Sin este recuento, el límite se descubre a mitad
    de una ejecución y el trabajo se pierde.

    Es una estimación a partir de lo registrado en la base: no consulta al
    proveedor, así que no cuenta lo consumido por otras aplicaciones que usen
    la misma clave.
    """
    desde = datetime.utcnow() - timedelta(hours=24)

    brechas_hoy = (db.query(ResultadoBrecha)
                   .filter(ResultadoBrecha.created_at >= desde).count())
    sintesis_hoy = (db.query(EstadoDelArte)
                    .filter(EstadoDelArte.created_at >= desde).count())
    generaciones = brechas_hoy + sintesis_hoy

    LIMITE_DIARIO = 20
    n_articulos = db.query(Articulo).filter(Articulo.proyecto_id == proyecto_id).count()
    coste_ejecucion = n_articulos + 1

    tokens_in = sum(r.tokens_in or 0 for r in
                    db.query(Run).filter(Run.proyecto_id == proyecto_id).all())
    tokens_out = sum(r.tokens_out or 0 for r in
                     db.query(Run).filter(Run.proyecto_id == proyecto_id).all())

    restantes = max(0, LIMITE_DIARIO - generaciones)
    return {
        "ventana": "ultimas 24 horas",
        "generaciones_estimadas": generaciones,
        "limite_diario_nivel_gratuito": LIMITE_DIARIO,
        "restantes_estimadas": restantes,
        "coste_de_una_ejecucion": coste_ejecucion,
        "alcanza_para_otra_ejecucion": restantes >= coste_ejecucion,
        "tokens_acumulados": {"entrada": tokens_in, "salida": tokens_out},
        "nota": ("Estimacion a partir de los resultados guardados. No incluye "
                 "llamadas fallidas ni consumo de otras aplicaciones que usen "
                 "la misma clave. Consulta oficial en ai.dev/rate-limit"),
    }
