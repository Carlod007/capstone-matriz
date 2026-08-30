# app/routers/validacion.py
"""
Anotacion humana de las brechas (nivel N6).

Todas las metricas anteriores comparan al sistema consigo mismo: dicen si es
consistente, no si acierta. Para saber lo segundo hace falta que alguien que se
haya leido el articulo diga si la brecha es correcta.

Lo que aporta esta pantalla no es el porcentaje sino la justificacion. Un «esta
mal» sin motivo no permite corregir el sistema ni defender la evaluacion; con
el motivo escrito, cada brecha rechazada es una linea del capitulo de
resultados.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencias import proyecto_propio, usuario_actual
from app.models.articulo import Articulo
from app.models.proyecto import Proyecto
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run import Run
from app.models.run_item import RunItem
from app.models.usuario import Usuario
from app.models.validacion_humana import (
    CORRECTA, INCORRECTA, ORIGENES, PARCIAL, VEREDICTOS, ValidacionHumana,
)
from app.schemas.validacion import ValidacionIn, ValidacionOut

router = APIRouter(prefix="/proyectos", tags=["validacion"])

# Peso de cada veredicto al resumir. «Parcial» vale medio punto: la brecha
# acierta en el problema y falla en un matiz, y contarla como acierto o como
# fallo completo falsea el resultado en direcciones opuestas.
PESOS = {CORRECTA: 1.0, PARCIAL: 0.5, INCORRECTA: 0.0}


def _brecha_del_proyecto(db: Session, proyecto_id: str,
                         brecha_id: str) -> tuple[ResultadoBrecha, str]:
    """El filtro por proyecto no sobra: sin el, conocer el identificador de una
    brecha ajena bastaria para anotarla desde un proyecto propio."""
    fila = (db.query(ResultadoBrecha, Run.id)
            .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
            .join(Run, Run.id == RunItem.run_id)
            .filter(ResultadoBrecha.id == brecha_id,
                    Run.proyecto_id == proyecto_id)
            .first())
    if not fila:
        raise HTTPException(status_code=404, detail="Brecha no encontrada")
    return fila[0], fila[1]


def _ultimo_run(db: Session, proyecto_id: str) -> Run | None:
    return (db.query(Run).filter(Run.proyecto_id == proyecto_id)
            .order_by(Run.iniciado_en.desc(), Run.id).first())


@router.get("/{proyecto_id}/validacion")
def listar_para_validar(proyecto: Proyecto = Depends(proyecto_propio),
                        usuario: Usuario = Depends(usuario_actual),
                        db: Session = Depends(get_db)):
    """Las brechas del ultimo analisis con el veredicto propio, si lo hay."""
    run = _ultimo_run(db, proyecto.id)
    if not run:
        return {"run": None, "brechas": [], "resumen": None}

    filas = (db.query(ResultadoBrecha, Articulo)
             .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
             .join(Articulo, Articulo.id == RunItem.articulo_id)
             .filter(RunItem.run_id == run.id)
             .order_by(Articulo.titulo.asc()).all())

    ids = [rb.id for rb, _ in filas]
    mias = {v.brecha_id: v for v in
            db.query(ValidacionHumana)
              .filter(ValidacionHumana.brecha_id.in_(ids or ["-"]),
                      ValidacionHumana.usuario_id == usuario.id).all()}

    # Cuantas personas han anotado cada brecha, sin decir quienes ni que
    # dijeron: saber el veredicto ajeno antes de emitir el propio arruina la
    # independencia de los jueces, que es lo unico que hace util el acuerdo
    # entre ellos.
    otros = {}
    for bid, in db.query(ValidacionHumana.brecha_id).filter(
            ValidacionHumana.brecha_id.in_(ids or ["-"]),
            ValidacionHumana.usuario_id != usuario.id).all():
        otros[bid] = otros.get(bid, 0) + 1

    brechas = []
    for rb, art in filas:
        v = mias.get(rb.id)
        brechas.append({
            "id": rb.id,
            # Hace falta para abrir el PDF: no se puede juzgar una brecha sin
            # leer el artículo, y hasta ahora había que buscarlo a mano en el
            # ordenador, con el riesgo de revisar una versión distinta de la
            # que el sistema analizó.
            "articulo_id": art.id,
            "articulo": art.titulo or "(sin título)",
            "tipo_brecha": rb.tipo_brecha,
            "brecha": rb.brecha,
            "oportunidad": rb.oportunidad,
            "veredicto": v.veredicto if v else None,
            "justificacion": v.justificacion if v else None,
            "origen": v.origen if v else None,
            "otros_anotadores": otros.get(rb.id, 0),
        })

    return {"run": run.id, "brechas": brechas,
            "resumen": _resumen(db, proyecto.id, usuario.id, run.id)}


@router.put("/{proyecto_id}/validacion/{brecha_id}", response_model=ValidacionOut)
def anotar(brecha_id: str, datos: ValidacionIn,
           proyecto: Proyecto = Depends(proyecto_propio),
           usuario: Usuario = Depends(usuario_actual),
           db: Session = Depends(get_db)):
    """Registra o sustituye el veredicto propio sobre una brecha."""
    if datos.veredicto not in VEREDICTOS:
        raise HTTPException(status_code=422,
                            detail="Veredicto no reconocido: %s" % datos.veredicto)

    justificacion = (datos.justificacion or "").strip() or None

    # Un rechazo sin motivo no sirve para nada: ni corrige el sistema ni
    # sostiene la evaluacion. Marcar «correcta» sin comentario si vale, porque
    # ahi el motivo es que no hay nada que objetar.
    if datos.veredicto in (INCORRECTA, PARCIAL) and not justificacion:
        raise HTTPException(
            status_code=422,
            detail="Explica qué falla: un veredicto negativo sin motivo no "
                   "permite corregir el sistema ni defender la evaluación.")

    _, run_id = _brecha_del_proyecto(db, proyecto.id, brecha_id)

    fila = (db.query(ValidacionHumana)
              .filter(ValidacionHumana.brecha_id == brecha_id,
                      ValidacionHumana.usuario_id == usuario.id)
              .first())
    # Se guarda solo si viene declarado. Suponer uno por defecto inventaría el
    # dato del procedimiento que este campo existe para conservar, y al
    # sustituir un veredicto ya emitido se respeta lo que dijera antes si la
    # pantalla no manda nada.
    origen = datos.origen if datos.origen in ORIGENES else None

    if fila:
        fila.veredicto = datos.veredicto
        fila.justificacion = justificacion
        if origen:
            fila.origen = origen
    else:
        fila = ValidacionHumana(id=str(uuid.uuid4()), brecha_id=brecha_id,
                                usuario_id=usuario.id,
                                veredicto=datos.veredicto,
                                justificacion=justificacion,
                                origen=origen)
        db.add(fila)
    db.commit()
    db.refresh(fila)

    return ValidacionOut(
        brecha_id=fila.brecha_id, veredicto=fila.veredicto,
        justificacion=fila.justificacion, origen=fila.origen,
        resumen=_resumen(db, proyecto.id, usuario.id, run_id))


@router.delete("/{proyecto_id}/validacion/{brecha_id}")
def retirar(brecha_id: str,
            proyecto: Proyecto = Depends(proyecto_propio),
            usuario: Usuario = Depends(usuario_actual),
            db: Session = Depends(get_db)):
    """Retira el veredicto propio. Solo el propio."""
    _, run_id = _brecha_del_proyecto(db, proyecto.id, brecha_id)
    (db.query(ValidacionHumana)
       .filter(ValidacionHumana.brecha_id == brecha_id,
               ValidacionHumana.usuario_id == usuario.id)
       .delete(synchronize_session=False))
    db.commit()
    return {"brecha_id": brecha_id, "veredicto": None,
            "resumen": _resumen(db, proyecto.id, usuario.id, run_id)}


@router.get("/{proyecto_id}/validacion/comparacion")
def comparar_con_el_sistema(proyecto: Proyecto = Depends(proyecto_propio),
                            usuario: Usuario = Depends(usuario_actual),
                            db: Session = Depends(get_db)):
    """El juicio humano junto a lo que midió el sistema, al terminar.

    Se niega mientras queden brechas por revisar. Es el mismo motivo por el que
    el acierto no se sirve antes: ver que una brecha sacó fidelidad 1.000
    predispone a darla por buena, y entonces comparar las dos columnas ya no
    mide el acierto del sistema sino su eco.
    """
    from app.models.metrica import Metrica

    run = _ultimo_run(db, proyecto.id)
    if not run:
        raise HTTPException(status_code=400,
                            detail="El proyecto no se ha analizado.")

    resumen = _resumen(db, proyecto.id, usuario.id, run.id)
    if not resumen["revision_completa"]:
        raise HTTPException(
            status_code=409,
            detail="Faltan %d brechas por revisar. La comparación se muestra "
                   "al terminar, para que el juicio no quede condicionado."
                   % resumen["pendientes"])

    filas = (db.query(ResultadoBrecha, Articulo)
             .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
             .join(Articulo, Articulo.id == RunItem.articulo_id)
             .filter(RunItem.run_id == run.id)
             .order_by(Articulo.titulo.asc()).all())

    ids = [rb.id for rb, _ in filas]
    mias = {v.brecha_id: v for v in
            db.query(ValidacionHumana)
              .filter(ValidacionHumana.brecha_id.in_(ids or ["-"]),
                      ValidacionHumana.usuario_id == usuario.id).all()}

    CODIGOS = ("N2.1", "N2.2", "N2.5", "N2.6")
    metricas: dict[str, dict] = {}
    for m in (db.query(Metrica)
                .filter(Metrica.proyecto_id == proyecto.id,
                        Metrica.referencia_id.in_(ids or ["-"]),
                        Metrica.codigo.in_(CODIGOS)).all()):
        metricas.setdefault(m.referencia_id, {})[m.codigo] = m.valor

    return {
        "resumen": resumen,
        "brechas": [{
            "id": rb.id,
            "articulo": art.titulo or "(sin título)",
            "brecha": rb.brecha,
            "veredicto": mias[rb.id].veredicto if rb.id in mias else None,
            "justificacion": mias[rb.id].justificacion if rb.id in mias else None,
            "metricas": metricas.get(rb.id, {}),
        } for rb, art in filas],
    }


def _resumen(db: Session, proyecto_id: str, usuario_id: str,
             run_id: str) -> dict:
    """Cuanto ha anotado esta persona y, si termino, con que resultado.

    El avance -`anotadas`, `total`, `pendientes`- se sirve siempre; el
    resultado, solo al terminar. Cuanto falta no condiciona el juicio, pero el
    marcador si: ver el porcentaje acumulado empuja a confirmar la racha en vez
    de juzgar cada brecha por separado.
    """
    filas = (db.query(ValidacionHumana.veredicto, ValidacionHumana.origen)
               .join(ResultadoBrecha,
                     ResultadoBrecha.id == ValidacionHumana.brecha_id)
               .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
               .join(Run, Run.id == RunItem.run_id)
               .filter(Run.proyecto_id == proyecto_id,
                       Run.id == run_id,
                       ValidacionHumana.usuario_id == usuario_id).all())

    total_brechas = (db.query(ResultadoBrecha.id)
                       .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
                       .join(Run, Run.id == RunItem.run_id)
                       .filter(Run.proyecto_id == proyecto_id,
                               Run.id == run_id).count())

    anotadores = (db.query(ValidacionHumana.usuario_id)
                    .join(ResultadoBrecha,
                          ResultadoBrecha.id == ValidacionHumana.brecha_id)
                    .join(RunItem,
                          RunItem.id == ResultadoBrecha.run_item_id)
                    .join(Run, Run.id == RunItem.run_id)
                    .filter(Run.proyecto_id == proyecto_id,
                            Run.id == run_id)
                    .distinct()
                    .count())

    conteo = {v: 0 for v in VEREDICTOS}
    # `sin_declarar` incluido a proposito: un procedimiento que no se registro
    # no es lo mismo que uno registrado, y no decirlo lo daria por sabido.
    por_origen = {o: 0 for o in ORIGENES}
    por_origen["sin_declarar"] = 0
    for veredicto, origen in filas:
        conteo[veredicto] = conteo.get(veredicto, 0) + 1
        por_origen[origen if origen in ORIGENES else "sin_declarar"] += 1

    anotadas = len(filas)
    pendientes = max(0, total_brechas - anotadas)
    completa = total_brechas > 0 and pendientes == 0

    # El resultado no se sirve hasta terminar, y la restricción vive aquí y no
    # en la pantalla.
    #
    # Quien anota viendo su porcentaje acumulado deja de juzgar cada brecha por
    # separado: con cuatro correctas seguidas cuesta poner la quinta en duda.
    # El mismo razonamiento que aparta el panel de métricas de la revisión
    # -saber que el sistema se dio un 1.000 predispone a darle la razón- se
    # aplica al propio marcador.
    #
    # Ocultarlo en el frontend no bastaría: el dato habría viajado igual y
    # cualquiera podría leerlo, así que la ceguera dejaría de ser una propiedad
    # del procedimiento para ser una decisión de maquetación.
    acierto = (round(sum(PESOS[v] * n for v, n in conteo.items()) / anotadas, 4)
               if anotadas and completa else None)

    return {
        "anotadas": anotadas,
        "total": total_brechas,
        "pendientes": pendientes,
        # Distingue «no hay nada anotado» de «falta terminar»: sin esto, un
        # acierto nulo no dice cuál de las dos cosas ocurre.
        "revision_completa": completa,
        # Cómo se obtuvieron los veredictos. Las dos formas cuentan igual en el
        # acierto: el desglose describe el procedimiento, no pondera la calidad.
        "por_origen": por_origen,
        # También se reserva: saber que se llevan cuatro «correcta» condiciona
        # la quinta tanto como el porcentaje.
        "por_veredicto": conteo if completa else None,
        # None y no cero: mientras falten brechas no hay resultado que dar, y
        # un cero aquí se leería como «el sistema no acertó ninguna».
        "acierto": acierto,
        # Personas que realmente dejaron al menos un veredicto en este run. No
        # se presupone un anotador por el mero hecho de que exista el proyecto.
        "anotadores": anotadores,
    }
