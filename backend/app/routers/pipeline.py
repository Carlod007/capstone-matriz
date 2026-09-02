# app/routers/pipeline.py
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencias import proyecto_propio
from app.models.proyecto import Proyecto
from app.models.articulo import Articulo
from app.models.run import Run, EstadoRun
from app.models.run_item import RunItem, EstadoRunItem
from app.services.procedencia import capturar_procedencia

router = APIRouter(prefix="/proyectos", tags=["pipeline"])


@router.post("/{proyecto_id}/analizar_todo")
def analizar_todo(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    """Encola el análisis del proyecto y responde de inmediato.

    Antes esta función hacía el trabajo entero dentro de la petición: indexar,
    analizar artículo por artículo y sintetizar el estado del arte. Con cinco
    artículos y el limitador en cuatro generaciones por minuto son varios
    minutos con la petición abierta; con diez, el doble. Cualquier proxy corta
    a los treinta o sesenta segundos, así que en un servidor no fallaría a
    veces: fallaría siempre, y además gastando cuota en un trabajo cuyo
    resultado nadie recibe.

    Ahora solo se apunta lo que hay que hacer. `trabajador.py` lo va sacando,
    y el avance se consulta en `GET /proyectos/runs/{run_id}`. Quien lanza el
    análisis puede cerrar el navegador.

    La indexación también se movió al trabajador: es la otra parte lenta, y
    dejarla aquí habría mantenido el problema a medias.
    """
    arts = db.query(Articulo).filter(Articulo.proyecto_id == proyecto.id).all()
    if not arts:
        raise HTTPException(status_code=400, detail="El proyecto no tiene artículos")

    en_curso = (db.query(Run)
                  .filter(Run.proyecto_id == proyecto.id,
                          Run.estado.in_((EstadoRun.creado, EstadoRun.en_progreso)))
                  .first())
    if en_curso:
        # Encolar dos veces lo mismo duplicaría el gasto de cuota sin dar nada
        # a cambio. Se devuelve la que ya está en marcha.
        raise HTTPException(
            status_code=409,
            detail={
                "mensaje": "Este proyecto ya tiene un análisis en curso.",
                "run_id": en_curso.id,
            },
        )

    run_id = str(uuid.uuid4())
    run = Run(
        id=run_id,
        proyecto_id=proyecto.id,
        estado=EstadoRun.creado,
        n_items_total=len(arts),
        n_items_ok=0,
        genera_estado_arte=True,
        procedencia=capturar_procedencia(),
    )
    db.add(run)
    db.flush()

    for a in arts:
        db.add(RunItem(
            id=str(uuid.uuid4()),
            run_id=run_id,
            articulo_id=a.id,
            estado=EstadoRunItem.pendiente,
        ))
    db.commit()

    return {
        "proyecto_id": proyecto.id,
        "run_id": run_id,
        "estado": EstadoRun.creado.value,
        "n_items_total": len(arts),
        "n_items_ok": 0,
        "procedencia": run.procedencia,
        "aviso": (
            "El análisis quedó en cola. Puedes cerrar esta página; consulta el "
            "avance en /proyectos/runs/%s." % run_id
        ),
    }
