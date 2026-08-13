# app/routers/embeddings.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencias import articulo_propio, usuario_actual
from app.models.articulo import Articulo
from app.models.proyecto import Proyecto
from app.models.usuario import Usuario
from app.services.embedding_service import index_articulo, embed_query

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.post("/index/{articulo_id}")
def indexar_articulo(
    articulo: Articulo = Depends(articulo_propio),
    db: Session = Depends(get_db),
):
    n = index_articulo(db, articulo.id)
    if n == 0:
        raise HTTPException(status_code=400, detail="No se pudo indexar (sin archivo o sin texto).")
    return {"articulo_id": articulo.id, "chunks_indexados": n}


@router.get("/search")
def buscar(
    q: str = Query(..., description="Consulta"),
    articulo_id: list[str] | None = Query(None, description="Filtrar por uno o más artículos"),
    top_k: int = 5,
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    """Busca por significado entre los fragmentos de los artículos propios.

    Sin lista de artículos, esta búsqueda recorría los fragmentos de todos los
    de la base. Con una sola persona daba igual; con varias cuentas devolvía
    texto de artículos ajenos, que es precisamente lo que el paso 2 viene a
    impedir.

    Los identificadores que llegan por parámetro se cruzan con los del usuario
    en lugar de comprobarse uno a uno: pedir uno ajeno no da error —eso
    confirmaría que existe—, simplemente no aporta resultados.
    """
    propios = {
        a[0] for a in db.query(Articulo.id)
        .join(Proyecto, Proyecto.id == Articulo.proyecto_id)
        .filter(Proyecto.usuario_id == usuario.id)
        .all()
    }

    ids = [i for i in articulo_id if i in propios] if articulo_id else sorted(propios)
    if not ids:
        return []

    hits = embed_query(db, ids, q, top_k=top_k)
    return [{"embedding_id": eid, "score": float(s), "texto": txt} for eid, s, txt in hits]
