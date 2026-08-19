"""Recuperacion de la ventana de evidencia usada para verificar una brecha.

La verificacion normal y la verificacion posterior deben juzgar exactamente el
mismo contexto. Mantener esta regla en un servicio compartido evita que una
ruta use solo los fragmentos recuperados mientras la otra añade sus vecinos.
"""

from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.embedding_doc import EmbeddingDoc
from app.models.resultado_brecha import ResultadoBrecha


def fragmentos_de_brecha(db: Session, rb: ResultadoBrecha) -> list[dict]:
    """Devuelve los fragmentos registrados y sus trozos contiguos.

    ``rag_hits`` guarda identificadores, no el texto. Se recuperan los trozos
    ``chunk_orden +/- 1`` porque el troceado puede cortar justo la frase que
    determina el sentido de una afirmacion. No hay una llamada adicional al
    modelo: todos los embeddings ya estan almacenados.
    """
    hits = rb.rag_hits if isinstance(rb.rag_hits, list) else []
    ids = [h.get("embedding_id") for h in hits
           if isinstance(h, dict) and h.get("embedding_id")]
    if not ids:
        return []

    filas = db.query(EmbeddingDoc).filter(EmbeddingDoc.id.in_(ids)).all()
    if not filas:
        return []

    por_articulo: dict[str, set[int]] = {}
    for fila in filas:
        if fila.chunk_orden is None:
            continue
        ordenes = por_articulo.setdefault(fila.articulo_id, set())
        ordenes.update((fila.chunk_orden - 1, fila.chunk_orden,
                        fila.chunk_orden + 1))

    if not por_articulo:
        return [{"texto": f.texto, "seccion": f.seccion or "otro"}
                for f in filas]

    condiciones = [
        and_(EmbeddingDoc.articulo_id == articulo_id,
             EmbeddingDoc.chunk_orden.in_(sorted(ordenes)))
        for articulo_id, ordenes in por_articulo.items()
    ]
    ampliados = (db.query(EmbeddingDoc)
                 .filter(or_(*condiciones))
                 .order_by(EmbeddingDoc.articulo_id,
                           EmbeddingDoc.chunk_orden)
                 .all())
    return [{"texto": f.texto, "seccion": f.seccion or "otro"}
            for f in ampliados]
