# app/routers/metrics.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run_item import RunItem
from app.models.articulo import Articulo
from app.services.metrics import project_indicators

router = APIRouter(prefix="/proyectos", tags=["metrics"])

def _q_base(db: Session, proyecto_id: str):
    q = (
        db.query(ResultadoBrecha, RunItem, Articulo)
        .join(RunItem, ResultadoBrecha.run_item_id == RunItem.id)
        .join(Articulo, RunItem.articulo_id == Articulo.id)
        .filter(Articulo.proyecto_id == proyecto_id)
    )
    return q

@router.get("/{proyecto_id}/metrics/resumen")
def resumen_metricas(proyecto_id: str, db: Session = Depends(get_db)):
    total = (
        _q_base(db, proyecto_id)
        .with_entities(func.count(ResultadoBrecha.id))
        .scalar()
    )
    if total == 0:
        return {
            "total_brechas": 0,
            "tasa_aceptacion": 0.0,
            "avg_entropia": 0.0,
            "avg_sim_promedio": 0.0,
            "avg_val_score": 0.0,
            "por_estado": {},
            "por_tipo": {}
        }

    avg_ent = (
        _q_base(db, proyecto_id)
        .with_entities(func.avg(ResultadoBrecha.entropia))
        .scalar() or 0.0
    )
    avg_sim = (
        _q_base(db, proyecto_id)
        .with_entities(func.avg(ResultadoBrecha.sim_promedio))
        .scalar() or 0.0
    )
    avg_val = (
        _q_base(db, proyecto_id)
        .with_entities(func.avg(ResultadoBrecha.val_score))
        .scalar() or 0.0
    )

    # Conteos por estado_validacion
    rows_estado = (
        _q_base(db, proyecto_id)
        .with_entities(ResultadoBrecha.estado_validacion, func.count())
        .group_by(ResultadoBrecha.estado_validacion)
        .all()
    )
    por_estado = {k or "": int(v) for k, v in rows_estado}

    # Conteos por tipo_brecha
    rows_tipo = (
        _q_base(db, proyecto_id)
        .with_entities(ResultadoBrecha.tipo_brecha, func.count())
        .group_by(ResultadoBrecha.tipo_brecha)
        .all()
    )
    por_tipo = {k or "": int(v) for k, v in rows_tipo}

    # Tasa de aceptación (aceptadas / total)
    aceptadas = por_estado.get("aceptada", 0)
    tasa_aceptacion = round(aceptadas / total, 3) if total > 0 else 0.0

    return {
        "total_brechas": int(total),
        "tasa_aceptacion": float(tasa_aceptacion),
        "avg_entropia": float(round(avg_ent, 3)),
        "avg_sim_promedio": float(round(avg_sim, 3)),
        "avg_val_score": float(round(avg_val, 3)),
        "por_estado": por_estado,
        "por_tipo": por_tipo,
    }

@router.get("/{proyecto_id}/metrics/series")
def series_temporales(proyecto_id: str, db: Session = Depends(get_db)):
    rows = (
        _q_base(db, proyecto_id)
        .with_entities(func.date(ResultadoBrecha.created_at), func.count())
        .group_by(func.date(ResultadoBrecha.created_at))
        .order_by(func.date(ResultadoBrecha.created_at))
        .all()
    )
    serie = [{"fecha": str(d), "brechas": int(n)} for d, n in rows]
    return {"serie_brechas_por_dia": serie}

@router.get("/{proyecto_id}/metrics/resumen_ext")
def metrics_resumen_ext(proyecto_id: str, db: Session = Depends(get_db)):
    return project_indicators(db, proyecto_id)