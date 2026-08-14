# app/services/cola.py
"""
Cola de trabajos sobre las tablas que ya existian.

`run` y `run_item` llevaban desde el principio el estado de cada articulo:
pendiente, analizado, fallido. Eso ya es una cola, y el frontend ya consultaba
su avance. Anadir Redis y Celery habria supuesto reimplementar ese modelo en
otro sitio, mantener los dos en acuerdo y sostener un servicio mas.

Lo que faltaba no era la cola, sino tres cosas que esta capa aporta:

1. Que dos trabajadores no cojan el mismo articulo.
2. Que un trabajador caido no bloquee el suyo para siempre.
3. Que un fallo transitorio se reintente y uno definitivo no.

Todo se apoya en `SELECT ... FOR UPDATE SKIP LOCKED`, que es exactamente la
herramienta que MySQL ofrece para esto: el que llega segundo no espera al
primero, se lleva otra fila.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.run import EstadoRun, Run
from app.models.run_item import EstadoRunItem, RunItem

log = logging.getLogger("trabajador")

# Cuantas veces se reintenta un articulo antes de darlo por fallido. Tres es
# suficiente para cubrir un corte de red o un limite de frecuencia; mas seria
# insistir en algo que no va a cambiar.
MAX_INTENTOS = 3

# Cuanto se espera antes de dar por caido a un trabajador y recuperar lo que
# tenia tomado. Ha de ser mayor que lo que tarda un articulo, o se recogeria
# trabajo que sigue en curso: un analisis con el limitador de por medio puede
# pasar del minuto.
ABANDONO = timedelta(minutes=15)

ESTADOS_TERMINADOS = (EstadoRunItem.analizado, EstadoRunItem.guardado,
                      EstadoRunItem.fallido)


def tomar_pendiente(db: Session, run_id: str | None = None) -> RunItem | None:
    """Reserva un articulo y lo devuelve, o None si no hay ninguno.

    La reserva se confirma antes de empezar a trabajar: si se dejara abierta
    durante el analisis, la transaccion duraria minutos y bloquearia la fila
    todo ese tiempo. Aqui la fila se marca, se confirma y se suelta; lo que
    protege el trabajo en curso es el estado `en_proceso`, no el candado.
    """
    limite = datetime.now() - ABANDONO

    condiciones = or_(
        RunItem.estado == EstadoRunItem.pendiente,
        # Tomado por alguien que no ha vuelto: se considera abandonado.
        (RunItem.estado == EstadoRunItem.en_proceso)
        & (RunItem.tomado_en < limite),
    )

    consulta = (
        select(RunItem)
        .where(condiciones, RunItem.intentos < MAX_INTENTOS)
        .order_by(RunItem.creado_en.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if run_id:
        consulta = consulta.where(RunItem.run_id == run_id)

    item = db.execute(consulta).scalars().first()
    if item is None:
        db.rollback()
        return None

    reintento = item.estado == EstadoRunItem.en_proceso
    item.estado = EstadoRunItem.en_proceso
    item.tomado_en = datetime.now()
    item.intentos = (item.intentos or 0) + 1
    db.commit()

    if reintento:
        log.warning("Recuperado el articulo %s, abandonado por otro trabajador "
                    "(intento %d)", item.id, item.intentos)
    return item


def devolver(db: Session, item: RunItem, motivo: str) -> None:
    """Deja el articulo listo para otro intento, o lo da por fallido.

    Se usa con lo que puede salir bien mas tarde: un corte de red, un limite
    de frecuencia. Agotados los intentos, se marca como fallido con el ultimo
    motivo, para que quede dicho por que se dejo de intentar.
    """
    if (item.intentos or 0) >= MAX_INTENTOS:
        item.estado = EstadoRunItem.fallido
        item.error_msg = ("Se agotaron los %d intentos. Ultimo error: %s"
                          % (MAX_INTENTOS, motivo))[:2000]
        log.error("Articulo %s descartado tras %d intentos: %s",
                  item.id, item.intentos, motivo)
    else:
        item.estado = EstadoRunItem.pendiente
        item.tomado_en = None
        item.error_msg = motivo[:2000]
        log.warning("Articulo %s devuelto a la cola (intento %d de %d): %s",
                    item.id, item.intentos, MAX_INTENTOS, motivo)
    db.commit()


def quedan_pendientes(db: Session, run_id: str) -> bool:
    """Si la ejecucion tiene algo por hacer todavia.

    Un articulo `en_proceso` cuenta como pendiente: alguien lo esta mirando,
    y cerrar la ejecucion sin el daria por completo un lote que no lo esta.
    """
    return db.query(RunItem.id).filter(
        RunItem.run_id == run_id,
        RunItem.estado.notin_(ESTADOS_TERMINADOS),
    ).first() is not None


def hay_trabajo(db: Session) -> bool:
    """Si queda algo por tomar en cualquier ejecucion."""
    limite = datetime.now() - ABANDONO
    return db.query(RunItem.id).filter(
        or_(RunItem.estado == EstadoRunItem.pendiente,
            (RunItem.estado == EstadoRunItem.en_proceso)
            & (RunItem.tomado_en < limite)),
        RunItem.intentos < MAX_INTENTOS,
    ).first() is not None


def runs_por_cerrar(db: Session) -> list[Run]:
    """Ejecuciones sin articulos por hacer que siguen sin darse por cerradas.

    Se buscan aparte en lugar de cerrar la ejecucion desde el trabajador que
    termina el ultimo articulo: si ese trabajador muere justo despues de
    guardarlo, nadie mas cerraria la ejecucion y quedaria en progreso para
    siempre.
    """
    sin_terminar = (
        select(RunItem.run_id)
        .where(RunItem.estado.notin_(ESTADOS_TERMINADOS))
        .distinct()
    )
    return (db.query(Run)
              .filter(Run.estado.in_((EstadoRun.creado, EstadoRun.en_progreso)),
                      Run.id.notin_(sin_terminar))
              .all())


def marcar_en_progreso(db: Session, run: Run) -> None:
    if run.estado == EstadoRun.creado:
        run.estado = EstadoRun.en_progreso
        run.iniciado_en = datetime.now()
        db.commit()


def contar_ok(db: Session, run_id: str) -> int:
    """Articulos analizados, contados en la base y no acumulados en memoria.

    `run.n_items_ok` se incrementaba con `+= 1` desde el proceso que analizaba.
    Con un solo proceso funcionaba; con varios, dos incrementos simultaneos
    leen el mismo valor y uno de los dos se pierde.
    """
    return db.query(func.count(RunItem.id)).filter(
        RunItem.run_id == run_id,
        RunItem.estado.in_((EstadoRunItem.analizado, EstadoRunItem.guardado)),
    ).scalar() or 0
