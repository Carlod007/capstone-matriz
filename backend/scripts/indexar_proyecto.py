# scripts/indexar_proyecto.py
"""
Indexa los articulos de un proyecto desde la terminal, con progreso.

La indexacion es la parte lenta del analisis: cada fragmento es una peticion
de embedding y el nivel gratuito limita a 100 por minuto, asi que un proyecto
de cinco articulos tarda un par de minutos. Hacerlo dentro de la peticion HTTP
del navegador es fragil, porque cualquier corte de la conexion aborta el lote
(A-01, pendiente de resolverse con procesamiento en segundo plano).

Ejecutandolo aqui, la indexacion queda hecha y persistida. Despues, el boton
"Analizar todo" de la interfaz encuentra los articulos ya indexados, se los
salta y solo realiza el analisis, que es rapido.

Uso:
    python scripts/indexar_proyecto.py                     # lista proyectos
    python scripts/indexar_proyecto.py <proyecto_id>
    python scripts/indexar_proyecto.py <proyecto_id> --reindexar
"""

from __future__ import annotations

import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import warnings  # noqa: E402
warnings.filterwarnings("ignore")

from app.database import SessionLocal  # noqa: E402
from app.models.articulo import Articulo  # noqa: E402
from app.models.embedding_doc import EmbeddingDoc  # noqa: E402
from app.models.proyecto import Proyecto  # noqa: E402
from app.services.embedding_service import (  # noqa: E402
    CHUNK_CHARS, CHUNK_OVERLAP, MODE, index_articulo,
)
from app.services.limitador import LIMITE_EMBEDDINGS_MIN  # noqa: E402
from app.utils.text_extractor import extraer_con_diagnostico  # noqa: E402


def listar(db) -> int:
    proyectos = db.query(Proyecto).order_by(Proyecto.creado_en.desc()).limit(10).all()
    if not proyectos:
        print("No hay proyectos.")
        return 0
    print("%-38s %-42s %s" % ("id", "tema", "articulos"))
    for p in proyectos:
        n = db.query(Articulo).filter(Articulo.proyecto_id == p.id).count()
        print("%-38s %-42s %d" % (p.id, (p.tema_principal or "")[:42], n))
    print()
    print("Uso: python scripts/indexar_proyecto.py <proyecto_id>")
    return 0


def indexar(db, proyecto_id: str, reindexar: bool) -> int:
    arts = (db.query(Articulo)
            .filter(Articulo.proyecto_id == proyecto_id)
            .order_by(Articulo.creado_en).all())
    if not arts:
        print("El proyecto no tiene articulos o no existe.")
        return 2

    print("Modo del modelo   :", MODE)
    print("Fragmentacion     : %d caracteres, %d de solape" % (CHUNK_CHARS, CHUNK_OVERLAP))
    print("Ritmo             : %d peticiones por minuto" % LIMITE_EMBEDDINGS_MIN)
    print("Articulos         :", len(arts))
    print()

    inicio = time.monotonic()
    total = 0
    fallos = 0

    for i, a in enumerate(arts, 1):
        etiqueta = (a.titulo or a.id)[:52]
        ya = db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id == a.id).count()
        if ya and not reindexar:
            print("[%d/%d] %-52s  ya indexado (%d fragmentos)" % (i, len(arts), etiqueta, ya))
            total += ya
            continue

        t0 = time.monotonic()
        try:
            n = index_articulo(db, a.id, reindexar=reindexar)
        except Exception as exc:  # noqa: BLE001
            fallos += 1
            print("[%d/%d] %-52s  FALLO: %s" % (i, len(arts), etiqueta, str(exc)[:90]))
            continue

        if n == 0:
            fallos += 1
            # Diagnostico N0: explica por que no se pudo, en lugar de callar.
            from app.models.archivo import Archivo
            arc = (db.query(Archivo).filter(Archivo.articulo_id == a.id)
                   .order_by(Archivo.creado_en.desc()).first())
            motivo = "sin archivo asociado"
            if arc:
                d = extraer_con_diagnostico(arc.ruta)
                motivo = "; ".join(d.avisos) or "texto insuficiente"
            print("[%d/%d] %-52s  SIN INDEXAR: %s" % (i, len(arts), etiqueta, motivo[:80]))
            continue

        total += n
        print("[%d/%d] %-52s  %3d fragmentos  (%.0f s)"
              % (i, len(arts), etiqueta, n, time.monotonic() - t0))

    transcurrido = time.monotonic() - inicio
    print()
    print("Total: %d fragmentos en %.0f s (%.1f min). Articulos con problemas: %d"
          % (total, transcurrido, transcurrido / 60.0, fallos))
    if fallos == 0:
        print()
        print("Listo. En la interfaz, pulsa 'Analizar todo': encontrara los")
        print("articulos ya indexados y solo ejecutara el analisis.")
    return 1 if fallos else 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    reindexar = "--reindexar" in sys.argv
    db = SessionLocal()
    try:
        if not args:
            return listar(db)
        return indexar(db, args[0], reindexar)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
