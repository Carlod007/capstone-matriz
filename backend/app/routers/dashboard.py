# app/routers/dashboard.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.proyecto import Proyecto
from app.models.articulo import Articulo
from app.models.archivo import Archivo
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run_item import RunItem
from app.models.estado_arte import EstadoDelArte

router = APIRouter(prefix="/proyectos", tags=["dashboard"])

def _q_base(db: Session, proyecto_id: str):
    return (
        db.query(ResultadoBrecha, RunItem, Articulo)
        .join(RunItem, ResultadoBrecha.run_item_id == RunItem.id)
        .join(Articulo, RunItem.articulo_id == Articulo.id)
        .filter(Articulo.proyecto_id == proyecto_id)
    )

@router.get("/{proyecto_id}/dashboard")
def dashboard(proyecto_id: str, db: Session = Depends(get_db)):
    pr = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    q = _q_base(db, proyecto_id)

    total_brechas = q.with_entities(func.count(ResultadoBrecha.id)).scalar() or 0
    avg_ent = q.with_entities(func.avg(ResultadoBrecha.entropia)).scalar() or 0
    avg_sim = q.with_entities(func.avg(ResultadoBrecha.sim_promedio)).scalar() or 0
    avg_val = q.with_entities(func.avg(ResultadoBrecha.val_score)).scalar() or 0

    por_estado_rows = (
        q.with_entities(ResultadoBrecha.estado_validacion, func.count())
         .group_by(ResultadoBrecha.estado_validacion).all()
    )
    por_estado = {k or "": int(v) for k, v in por_estado_rows}

    por_tipo_rows = (
        q.with_entities(ResultadoBrecha.tipo_brecha, func.count())
         .group_by(ResultadoBrecha.tipo_brecha).all()
    )
    por_tipo = {k or "": int(v) for k, v in por_tipo_rows}

    serie_rows = (
        q.with_entities(func.date(ResultadoBrecha.created_at), func.count())
         .group_by(func.date(ResultadoBrecha.created_at))
         .order_by(func.date(ResultadoBrecha.created_at))
         .all()
    )
    serie = [{"fecha": str(d), "brechas": int(n)} for d, n in serie_rows]

    n_articulos = db.query(Articulo).filter(Articulo.proyecto_id == proyecto_id).count()
    n_archivos = (
        db.query(Archivo).join(Articulo, Archivo.articulo_id == Articulo.id)
        .filter(Articulo.proyecto_id == proyecto_id).count()
    )

    ea = (
        db.query(EstadoDelArte)
        .filter(EstadoDelArte.proyecto_id == proyecto_id)
        .order_by(EstadoDelArte.created_at.desc())
        .first()
    )
    estado_arte = None
    if ea:
        estado_arte = {
            "version": ea.version,
            "estado": ea.estado,
            "fecha": str(ea.created_at),
            "chars": len((ea.texto or "").strip()),
        }

    return {
        "proyecto": {
            "id": pr.id,
            "tema_principal": pr.tema_principal,
            "objetivo": pr.objetivo,
        },
        "conteos": {
            "articulos": n_articulos,
            "archivos": n_archivos,
            "brechas": total_brechas,
        },
        "metricas": {
            "avg_entropia": float(round(avg_ent, 3)),
            "avg_sim_promedio": float(round(avg_sim, 3)),
            "avg_val_score": float(round(avg_val, 3)),
            "por_estado": por_estado,
            "por_tipo": por_tipo,
            "serie_brechas_por_dia": serie,
        },
        "estado_arte": estado_arte,
    }
