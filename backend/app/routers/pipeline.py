# app/routers/pipeline.py
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencias import proyecto_propio
from app.models.proyecto import Proyecto
from app.models.articulo import Articulo
from app.models.embedding_doc import EmbeddingDoc
from app.models.run import Run, EstadoRun
from app.models.run_item import RunItem, EstadoRunItem

from app.services.embedding_service import index_articulo
from app.routers.runs import process_next_item  # usamos la lógica existente
from app.routers.estado_arte import generar_estado_arte  # ya existente

router = APIRouter(prefix="/proyectos", tags=["pipeline"])

@router.post("/{proyecto_id}/analizar_todo")
def analizar_todo(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    """
    Pipeline 1-clic:
      - Indexa artículos (RAG) si falta
      - Crea Run
      - Ejecuta process_next hasta completar
      - Genera Estado del Arte
    Devuelve resumen.

    `_proj_or_404` desapareció de aquí: buscaba el proyecto sin mirar de quién
    era, y ahora eso lo resuelve la dependencia `proyecto_propio`.
    """
    proyecto_id = proyecto.id

    arts = db.query(Articulo).filter(Articulo.proyecto_id == proyecto_id).all()
    if not arts:
        raise HTTPException(status_code=400, detail="El proyecto no tiene artículos")

    # 1) Indexación previa si falta
    indexados = 0
    for a in arts:
        ya = db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id == a.id).first()
        if not ya:
            n = index_articulo(db, a.id)
            if n > 0:
                indexados += 1

    # 2) Crear run
    run_id = str(uuid.uuid4())
    run = Run(
        id=run_id,
        proyecto_id=proyecto_id,
        estado=EstadoRun.creado,
        n_items_total=len(arts),
        n_items_ok=0,
    )
    db.add(run)
    db.flush()

    for a in arts:
        db.add(RunItem(
            id=str(uuid.uuid4()),
            run_id=run_id,
            articulo_id=a.id,
            estado=EstadoRunItem.pendiente
        ))
    db.commit()

    # 3) Ejecutar hasta completar
    #
    # Se les pasan los objetos ya resueltos, no los identificadores: las dos
    # funciones esperan ahora una ejecución y un proyecto cuya propiedad ya se
    # comprobó, y así no se repite la consulta en cada vuelta del bucle.
    while True:
        out = process_next_item(run, db)  # reutiliza la función del router
        if out.estado == EstadoRun.completado.value:
            break

    # 4) Generar Estado del Arte
    ea = generar_estado_arte(proyecto, db)

    return {
        "proyecto_id": proyecto_id,
        "indexados_nuevos": indexados,
        "run_id": run_id,
        "run_estado": out.estado,
        "n_items_total": out.n_items_total,
        "n_items_ok": out.n_items_ok,
        "estado_arte": getattr(ea, "estado", "generado"),
    }
