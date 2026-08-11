# scripts/reindexar.py
"""
Descarta los fragmentos indexados de un proyecto para volver a generarlos.

Hace falta cuando cambia el tamano de fragmento o el modelo de embeddings:
sin esto conviven fragmentos de distinta configuracion en el mismo proyecto y
las metricas dejan de ser comparables entre articulos.

Uso:
    python scripts/reindexar.py                    # muestra el estado
    python scripts/reindexar.py <proyecto_id>      # limpia ese proyecto
    python scripts/reindexar.py <proyecto_id> --si # sin confirmacion
"""

from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import warnings  # noqa: E402
warnings.filterwarnings("ignore")

from app.database import SessionLocal  # noqa: E402
from app.models.articulo import Articulo  # noqa: E402
from app.models.embedding_doc import EmbeddingDoc  # noqa: E402
from app.models.proyecto import Proyecto  # noqa: E402
from app.services.embedding_service import CHUNK_CHARS, CHUNK_OVERLAP  # noqa: E402


def estado(db) -> None:
    print("Configuracion actual de fragmentacion: %d caracteres, %d de solape"
          % (CHUNK_CHARS, CHUNK_OVERLAP))
    print()
    proyectos = db.query(Proyecto).order_by(Proyecto.creado_en.desc()).limit(10).all()
    if not proyectos:
        print("No hay proyectos.")
        return
    for p in proyectos:
        arts = db.query(Articulo).filter(Articulo.proyecto_id == p.id).all()
        total = 0
        detalle = []
        for a in arts:
            n = db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id == a.id).count()
            total += n
            detalle.append(n)
        print("%s  %-42s  articulos=%d  fragmentos=%d %s"
              % (p.id[:8], (p.tema_principal or "")[:42], len(arts), total, detalle))


def limpiar(db, proyecto_id: str, confirmado: bool) -> int:
    arts = db.query(Articulo).filter(Articulo.proyecto_id == proyecto_id).all()
    if not arts:
        print("El proyecto no tiene articulos o no existe.")
        return 2

    ids = [a.id for a in arts]
    n = db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id.in_(ids)).count()
    print("Proyecto %s: %d articulos, %d fragmentos indexados." % (proyecto_id[:8], len(ids), n))
    if n == 0:
        print("Nada que limpiar.")
        return 0

    if not confirmado:
        print()
        print("Se eliminaran esos %d fragmentos. Volver a generarlos consumira" % n)
        print("aproximadamente esa misma cantidad de peticiones de embedding.")
        resp = input("Continuar? (s/N): ").strip().lower()
        if resp != "s":
            print("Cancelado.")
            return 1

    db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id.in_(ids)).delete(
        synchronize_session=False)
    db.commit()
    print("Eliminados. Al volver a ejecutar el analisis se indexara de nuevo")
    print("con la configuracion actual (%d caracteres)." % CHUNK_CHARS)
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    confirmado = "--si" in sys.argv
    db = SessionLocal()
    try:
        if not args:
            estado(db)
            print()
            print("Para limpiar: python scripts/reindexar.py <proyecto_id>")
            return 0
        return limpiar(db, args[0], confirmado)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
