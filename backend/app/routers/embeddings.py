# app/routers/embeddings.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.embedding_service import index_articulo, embed_query

router = APIRouter(prefix="/embeddings", tags=["embeddings"])

@router.post("/index/{articulo_id}")
def indexar_articulo(articulo_id: str, db: Session = Depends(get_db)):
    n = index_articulo(db, articulo_id)
    if n == 0:
        raise HTTPException(status_code=400, detail="No se pudo indexar (sin archivo o sin texto).")
    return {"articulo_id": articulo_id, "chunks_indexados": n}

@router.get("/search")
def buscar(
    q: str = Query(..., description="Consulta"),
    articulo_id: list[str] | None = Query(None, description="Filtrar por uno o más artículos"),
    top_k: int = 5,
    db: Session = Depends(get_db),
):
    ids = articulo_id or []
    hits = embed_query(db, ids, q, top_k=top_k)
    return [{"embedding_id": eid, "score": float(s), "texto": txt} for eid, s, txt in hits]
