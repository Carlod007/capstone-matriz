import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.proyecto import Proyecto
from app.models.run import Run, EstadoRun
from app.models.run_item import RunItem
from app.models.resultado_brecha import ResultadoBrecha
from app.models.estado_arte import EstadoDelArte
from app.services.gemini_service import synthesize_estado_arte

router = APIRouter(prefix="/proyectos", tags=["estado_arte"])

@router.post("/{proyecto_id}/estado_arte")
def generar_estado_arte(proyecto_id: str, db: Session = Depends(get_db)):
    # 1) Proyecto
    pr = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    # 2) Último RUN COMPLETADO del proyecto
    run = (
        db.query(Run)
        .filter(Run.proyecto_id == proyecto_id, Run.estado == EstadoRun.completado)
        .order_by(Run.finalizado_en.desc())
        .first()
    )
    if not run:
        raise HTTPException(status_code=400, detail="No hay runs completados para sintetizar estado del arte")

    # 3) Brechas SOLO de ese run
    sub_items = db.query(RunItem.id).filter(RunItem.run_id == run.id).subquery()
    brechas_rows = (
        db.query(ResultadoBrecha)
        .filter(ResultadoBrecha.run_item_id.in_(sub_items))
        .order_by(ResultadoBrecha.created_at.asc())
        .all()
    )
    if not brechas_rows:
        raise HTTPException(status_code=400, detail="El run completado no tiene brechas registradas")

    brechas_payload = [
        {
            "tipo_brecha": r.tipo_brecha,
            "brecha": r.brecha,
            "oportunidad": r.oportunidad,
            "articulo_titulo": None,
        }
        for r in brechas_rows
    ]

    contexto = {
        "tema_principal": pr.tema_principal,
        "metodologia_txt": pr.metodologia_txt,
        "sector_txt": pr.sector_txt,
        "objetivo": pr.objetivo,
    }

    # 4) Síntesis
    texto = synthesize_estado_arte(brechas_payload, contexto)

    # 5) version = max(version)+1 por proyecto
    max_ver = db.query(func.max(EstadoDelArte.version)).filter(EstadoDelArte.proyecto_id == proyecto_id).scalar()
    next_ver = (max_ver or 0) + 1

    # 6) Insert con run_id OBLIGATORIO
    rec = EstadoDelArte(
        id=str(uuid.uuid4()),
        proyecto_id=proyecto_id,
        run_id=run.id,
        version=next_ver,
        texto=texto,
        estado="generado",
        tokens_in=0,
        tokens_out=0,
    )
    db.add(rec)
    db.commit()

    return {"estado_arte_id": rec.id, "version": rec.version, "run_id": run.id}

@router.get("/{proyecto_id}/estado_arte/latest")
def obtener_estado_arte(proyecto_id: str, db: Session = Depends(get_db)):
    rec = (
        db.query(EstadoDelArte)
        .filter(EstadoDelArte.proyecto_id == proyecto_id)
        .order_by(EstadoDelArte.version.desc())
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Sin estado del arte para este proyecto")
    return {
        "id": rec.id,
        "version": rec.version,
        "run_id": rec.run_id,
        "estado": rec.estado,
        "texto": rec.texto,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
    }
