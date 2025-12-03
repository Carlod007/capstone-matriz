# app/routers/pipeline.py
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.proyecto import Proyecto
from app.models.articulo import Articulo
from app.models.embedding_doc import EmbeddingDoc
from app.models.run import Run, EstadoRun
from app.models.run_item import RunItem, EstadoRunItem

from app.services.embedding_service import index_articulo
from app.routers.runs import process_next_item  # usamos la lógica existente
from app.routers.estado_arte import generar_estado_arte  # ya existente

router = APIRouter(prefix="/proyectos", tags=["pipeline"])

def _proj_or_404(db: Session, proyecto_id: str) -> Proyecto:
    pr = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return pr

@router.post("/{proyecto_id}/analizar_todo")
def analizar_todo(proyecto_id: str, db: Session = Depends(get_db)):
    """
    Pipeline 1-clic:
      - Indexa artículos (RAG) si falta
      - Crea Run
      - Ejecuta process_next hasta completar
      - Genera Estado del Arte
    Devuelve resumen.
    """
    _proj_or_404(db, proyecto_id)

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
    while True:
        out = process_next_item(run_id, db)  # reutiliza la función del router
        if out.estado == EstadoRun.completado.value:
            break

    # 4) Generar Estado del Arte
    ea = generar_estado_arte(proyecto_id, db)

    return {
        "proyecto_id": proyecto_id,
        "indexados_nuevos": indexados,
        "run_id": run_id,
        "run_estado": out.estado,
        "n_items_total": out.n_items_total,
        "n_items_ok": out.n_items_ok,
        "estado_arte": getattr(ea, "estado", "generado"),
    }
