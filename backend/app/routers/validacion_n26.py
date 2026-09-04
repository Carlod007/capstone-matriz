"""Protocolo ciego para validar N2.6 con datos no usados en su construccion."""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencias import proyecto_propio, usuario_actual
from app.models.articulo import Articulo
from app.models.metrica import AMBITO_BRECHA, Metrica
from app.models.proyecto import Proyecto
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run import EstadoRun, Run
from app.models.run_item import RunItem
from app.models.usuario import Usuario
from app.models.validacion_n26 import (
    ABIERTO, CERRADO, PROTOCOLO_N26_VERSION, ItemValidacionN26,
    LoteValidacionN26,
)
from app.schemas.validacion_n26 import EtiquetaN26In
from app.services.metricas.catalogo import ficha
from app.services.verificacion import PROMPT_VERIFICACION_VERSION

router = APIRouter(prefix="/proyectos", tags=["validacion-n26"])


def _ultimo_run(db: Session, proyecto_id: str) -> Run | None:
    return (db.query(Run).filter(Run.proyecto_id == proyecto_id)
            .order_by(Run.iniciado_en.desc(), Run.id.desc()).first())


def _lote(db: Session, proyecto_id: str, usuario_id: str,
          run_id: str | None = None,
          estado: str | None = None) -> LoteValidacionN26 | None:
    q = db.query(LoteValidacionN26).filter(
        LoteValidacionN26.proyecto_id == proyecto_id,
        LoteValidacionN26.usuario_id == usuario_id,
    )
    if run_id:
        q = q.filter(LoteValidacionN26.run_id == run_id)
    if estado:
        q = q.filter(LoteValidacionN26.estado == estado)
    return q.order_by(LoteValidacionN26.creado_en.desc(),
                      LoteValidacionN26.id.desc()).first()


def _filas_run(db: Session, run_id: str):
    return (db.query(ResultadoBrecha, Articulo)
            .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
            .join(Articulo, Articulo.id == RunItem.articulo_id)
            .filter(RunItem.run_id == run_id)
            .order_by(Articulo.titulo.asc(), ResultadoBrecha.id.asc()).all())


def _metricas_n26(db: Session, proyecto_id: str, ids: list[str]) -> dict[str, Metrica]:
    """Ultima N2.6 de cada brecha; el orden tambien resuelve empates."""
    filas = (db.query(Metrica)
             .filter(Metrica.proyecto_id == proyecto_id,
                     Metrica.ambito == AMBITO_BRECHA,
                     Metrica.referencia_id.in_(ids or ["-"]),
                     Metrica.codigo == "N2.6")
             .order_by(Metrica.creado_en.desc(), Metrica.id.desc()).all())
    resultado = {}
    for metrica in filas:
        resultado.setdefault(metrica.referencia_id, metrica)
    return resultado


def _intervalo_wilson(aciertos: int, total: int) -> dict | None:
    """Intervalo binomial 95 %, util incluso con muestras pequenas."""
    if total <= 0:
        return None
    z = 1.959963984540054
    p = aciertos / total
    divisor = 1 + z * z / total
    centro = (p + z * z / (2 * total)) / divisor
    margen = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / divisor
    return {"valor": round(p, 4), "inferior": round(max(0, centro - margen), 4),
            "superior": round(min(1, centro + margen), 4), "n": total}


def _resultado(items: list[ItemValidacionN26]) -> dict:
    tp = sum(i.prediccion_ya_resuelta and i.etiqueta_humana is True for i in items)
    fp = sum(i.prediccion_ya_resuelta and i.etiqueta_humana is False for i in items)
    fn = sum(not i.prediccion_ya_resuelta and i.etiqueta_humana is True for i in items)
    tn = sum(not i.prediccion_ya_resuelta and i.etiqueta_humana is False for i in items)
    total = tp + fp + fn + tn
    return {
        "matriz": {"verdadero_positivo": tp, "falso_positivo": fp,
                   "falso_negativo": fn, "verdadero_negativo": tn},
        "indicadores": {
            "exactitud": _intervalo_wilson(tp + tn, total),
            "sensibilidad": _intervalo_wilson(tp, tp + fn),
            "especificidad": _intervalo_wilson(tn, tn + fp),
            "precision": _intervalo_wilson(tp, tp + fp),
        },
        "advertencia_muestra": (
            None if total >= 20 else
            "Muestra exploratoria: con menos de 20 brechas los intervalos son "
            "amplios y el resultado no demuestra generalización."
        ),
    }


def _serializar(db: Session, lote: LoteValidacionN26) -> dict:
    filas = (db.query(ItemValidacionN26, ResultadoBrecha, Articulo)
             .join(ResultadoBrecha,
                   ResultadoBrecha.id == ItemValidacionN26.brecha_id)
             .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
             .join(Articulo, Articulo.id == RunItem.articulo_id)
             .filter(ItemValidacionN26.lote_id == lote.id)
             .order_by(Articulo.titulo.asc(), ItemValidacionN26.id.asc()).all())
    cerrado = lote.estado == CERRADO
    items = []
    registros = []
    for item, brecha, articulo in filas:
        registros.append(item)
        dato = {
            "id": item.id,
            "brecha_id": brecha.id,
            "articulo_id": articulo.id,
            "articulo": articulo.titulo or "(sin título)",
            "tipo_brecha": brecha.tipo_brecha,
            "brecha": brecha.brecha,
            "oportunidad": brecha.oportunidad,
            "etiqueta_humana": item.etiqueta_humana,
            "justificacion": item.justificacion,
        }
        # La prediccion no viaja mientras el lote esta abierto. Ocultarla solo
        # con CSS dejaria el dato accesible y la revision ya no seria ciega.
        if cerrado:
            dato["prediccion_ya_resuelta"] = item.prediccion_ya_resuelta
        items.append(dato)
    anotados = sum(i.etiqueta_humana is not None for i in registros)
    return {
        "lote": {"id": lote.id, "run_id": lote.run_id, "estado": lote.estado,
                 "protocolo_version": lote.protocolo_version,
                 "formula_version": lote.formula_version,
                 "creado_en": lote.creado_en, "cerrado_en": lote.cerrado_en},
        "progreso": {"anotados": anotados, "total": len(registros),
                     "pendientes": len(registros) - anotados},
        "items": items,
        "resultado": _resultado(registros) if cerrado else None,
    }


@router.get("/{proyecto_id}/validacion-n26")
def ver_validacion_n26(proyecto: Proyecto = Depends(proyecto_propio),
                       usuario: Usuario = Depends(usuario_actual),
                       db: Session = Depends(get_db)):
    # Un lote abierto tiene prioridad incluso si despues se reanalizo el
    # proyecto: la nueva ejecucion no debe dejar inaccesible una evaluacion ya
    # empezada ni cambiar a mitad el conjunto congelado.
    abierto = _lote(db, proyecto.id, usuario.id, estado=ABIERTO)
    if abierto:
        return _serializar(db, abierto)
    run = _ultimo_run(db, proyecto.id)
    if not run:
        return {"lote": None, "puede_iniciar": False,
                "motivo": "Analiza el proyecto antes de validar N2.6."}
    existente = _lote(db, proyecto.id, usuario.id, run.id)
    if existente:
        return _serializar(db, existente)
    filas = _filas_run(db, run.id)
    return {
        "lote": None,
        "run_id": run.id,
        "total": len(filas),
        "puede_iniciar": run.estado == EstadoRun.completado and bool(filas),
        "motivo": (None if run.estado == EstadoRun.completado and filas else
                   "La última ejecución debe estar completa y contener brechas."),
    }


@router.post("/{proyecto_id}/validacion-n26/iniciar")
def iniciar_validacion_n26(proyecto: Proyecto = Depends(proyecto_propio),
                           usuario: Usuario = Depends(usuario_actual),
                           db: Session = Depends(get_db)):
    abierto = _lote(db, proyecto.id, usuario.id, estado=ABIERTO)
    if abierto:
        return _serializar(db, abierto)
    run = _ultimo_run(db, proyecto.id)
    if not run or run.estado != EstadoRun.completado:
        raise HTTPException(status_code=409,
                            detail="La última ejecución no está completa.")
    existente = _lote(db, proyecto.id, usuario.id, run.id)
    if existente:
        return _serializar(db, existente)

    filas = _filas_run(db, run.id)
    if not filas:
        raise HTTPException(status_code=409,
                            detail="La ejecución no contiene brechas.")
    ids = [b.id for b, _ in filas]
    metricas = _metricas_n26(db, proyecto.id, ids)
    actual = ficha("N2.6")
    faltan = [bid for bid in ids if bid not in metricas]
    if faltan:
        raise HTTPException(
            status_code=409,
            detail="Verifica la fidelidad de todas las brechas antes de iniciar."
        )

    for metrica in metricas.values():
        prompt_version = ((metrica.procedencia or {}).get("prompts") or {}).get(
            "verificacion")
        if (metrica.valor not in (0, 0.0, 1, 1.0)
                or metrica.version_formula != actual.version_formula
                or not metrica.procedencia
                or not metrica.procedencia.get("revision_codigo")
                or prompt_version != PROMPT_VERIFICACION_VERSION):
            raise HTTPException(
                status_code=409,
                detail="N2.6 no tiene una medición actual y reproducible en todas "
                       "las brechas. Vuelve a verificar la fidelidad."
            )
    firmas = {json.dumps(m.procedencia, sort_keys=True, ensure_ascii=True)
              for m in metricas.values()}
    if len(firmas) != 1:
        raise HTTPException(
            status_code=409,
            detail="Las brechas fueron verificadas con versiones distintas. "
                   "Vuelve a verificarlas juntas antes de iniciar."
        )

    lote = LoteValidacionN26(
        id=str(uuid.uuid4()), proyecto_id=proyecto.id, run_id=run.id,
        usuario_id=usuario.id, estado=ABIERTO,
        protocolo_version=PROTOCOLO_N26_VERSION,
        formula_version=actual.version_formula,
        procedencia=next(iter(metricas.values())).procedencia,
    )
    db.add(lote)
    db.flush()
    for brecha, _ in filas:
        metrica = metricas[brecha.id]
        db.add(ItemValidacionN26(
            id=str(uuid.uuid4()), lote_id=lote.id, brecha_id=brecha.id,
            metrica_id=metrica.id,
            prediccion_ya_resuelta=bool(round(float(metrica.valor))),
        ))
    db.commit()
    db.refresh(lote)
    return _serializar(db, lote)


@router.put("/{proyecto_id}/validacion-n26/{brecha_id}")
def etiquetar_n26(brecha_id: str, datos: EtiquetaN26In,
                  proyecto: Proyecto = Depends(proyecto_propio),
                  usuario: Usuario = Depends(usuario_actual),
                  db: Session = Depends(get_db)):
    lote = (_lote(db, proyecto.id, usuario.id, estado=ABIERTO)
            or _lote(db, proyecto.id, usuario.id))
    if not lote:
        raise HTTPException(status_code=404,
                            detail="No hay una validación N2.6 iniciada.")
    if lote.estado != ABIERTO:
        raise HTTPException(status_code=409,
                            detail="La validación está cerrada y no puede editarse.")
    item = (db.query(ItemValidacionN26)
            .filter(ItemValidacionN26.lote_id == lote.id,
                    ItemValidacionN26.brecha_id == brecha_id).first())
    if not item:
        raise HTTPException(status_code=404, detail="Brecha no encontrada.")
    justificacion = datos.justificacion.strip()
    if not justificacion:
        raise HTTPException(status_code=422,
                            detail="Explica brevemente en qué parte del artículo basas la respuesta.")
    item.etiqueta_humana = datos.ya_resuelta
    item.justificacion = justificacion
    db.commit()
    return _serializar(db, lote)


@router.post("/{proyecto_id}/validacion-n26/cerrar")
def cerrar_validacion_n26(proyecto: Proyecto = Depends(proyecto_propio),
                          usuario: Usuario = Depends(usuario_actual),
                          db: Session = Depends(get_db)):
    lote = (_lote(db, proyecto.id, usuario.id, estado=ABIERTO)
            or _lote(db, proyecto.id, usuario.id))
    if not lote:
        raise HTTPException(status_code=404,
                            detail="No hay una validación N2.6 iniciada.")
    if lote.estado == CERRADO:
        return _serializar(db, lote)
    pendientes = (db.query(ItemValidacionN26)
                  .filter(ItemValidacionN26.lote_id == lote.id,
                          ItemValidacionN26.etiqueta_humana.is_(None)).count())
    if pendientes:
        raise HTTPException(status_code=409,
                            detail="Faltan %d brechas por etiquetar." % pendientes)
    lote.estado = CERRADO
    lote.cerrado_en = datetime.now()
    db.commit()
    db.refresh(lote)
    return _serializar(db, lote)
