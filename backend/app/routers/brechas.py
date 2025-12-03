from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run_item import RunItem

router = APIRouter(prefix="/articulos", tags=["brechas"])

@router.get("/{articulo_id}/brechas")
def listar_brechas(articulo_id: str, db: Session = Depends(get_db)):
    run_items = db.query(RunItem.id).filter(RunItem.articulo_id == articulo_id).subquery()
    rows = (
        db.query(ResultadoBrecha)
        .filter(ResultadoBrecha.run_item_id.in_(run_items.select()))
        .order_by(ResultadoBrecha.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "tipo_brecha": r.tipo_brecha,
            "brecha": r.brecha,
            "oportunidad": r.oportunidad,
            "estado_validacion": r.estado_validacion,
            "rag_hits": getattr(r, "rag_hits", None),
            "sim_promedio": getattr(r, "sim_promedio", None),
            "entropia": getattr(r, "entropia", None),
            "val_score": getattr(r, "val_score", None),
            "val_reason": getattr(r, "val_reason", None),
            "es_duplicada": getattr(r, "es_duplicada", None),
            "dup_de": getattr(r, "dup_de", None),
            "creado_en": r.created_at,
        }
        for r in rows
    ]
