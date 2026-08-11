# scripts/reetiquetar_secciones.py
"""
Reasigna la seccion de los fragmentos ya indexados, sin gastar cuota.

La etiqueta de seccion se deduce de la posicion del fragmento en el texto, no
del embedding. Cuando mejora la deteccion de encabezados no hace falta volver
a generar los vectores: basta recalcular las etiquetas.

Es lo que separa una correccion barata de una cara. Reindexar cinco articulos
cuesta cerca de doscientas peticiones de embedding; reetiquetar cuesta cero.

Uso:
    python scripts/reetiquetar_secciones.py <proyecto_id>
"""

from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import warnings  # noqa: E402
warnings.filterwarnings("ignore")

from app.database import SessionLocal  # noqa: E402
from app.models.archivo import Archivo  # noqa: E402
from app.models.articulo import Articulo  # noqa: E402
from app.models.embedding_doc import EmbeddingDoc  # noqa: E402
from app.models.proyecto import Proyecto  # noqa: E402
from app.services.document_structure import (  # noqa: E402
    SECCIONES_SUSTANTIVAS, detectar_secciones, seccion_en,
)
from app.utils.text_extractor import extraer_con_diagnostico  # noqa: E402


def reetiquetar(db, proyecto_id: str) -> int:
    arts = (db.query(Articulo).filter(Articulo.proyecto_id == proyecto_id)
            .order_by(Articulo.creado_en).all())
    if not arts:
        print("El proyecto no tiene articulos o no existe.")
        return 2

    cambiados_total = 0
    for i, a in enumerate(arts, 1):
        frags = (db.query(EmbeddingDoc)
                 .filter(EmbeddingDoc.articulo_id == a.id)
                 .order_by(EmbeddingDoc.chunk_orden).all())
        if not frags:
            print("[%d/%d] %-46s  sin fragmentos" % (i, len(arts), (a.titulo or a.id)[:46]))
            continue

        arc = (db.query(Archivo).filter(Archivo.articulo_id == a.id)
               .order_by(Archivo.creado_en.desc()).first())
        if not arc or not os.path.isfile(arc.ruta):
            print("[%d/%d] %-46s  archivo no disponible" % (i, len(arts), (a.titulo or a.id)[:46]))
            continue

        texto = extraer_con_diagnostico(arc.ruta).texto
        secciones = detectar_secciones(texto)

        antes = {}
        cambiados = 0
        for f in frags:
            antes[f.seccion or "otro"] = antes.get(f.seccion or "otro", 0) + 1
            nueva = seccion_en(secciones, f.char_inicio or 0)
            if nueva != f.seccion:
                f.seccion = nueva
                cambiados += 1
        db.flush()

        despues = {}
        for f in frags:
            despues[f.seccion or "otro"] = despues.get(f.seccion or "otro", 0) + 1

        sus_antes = sum(v for k, v in antes.items() if k in SECCIONES_SUSTANTIVAS)
        sus_desp = sum(v for k, v in despues.items() if k in SECCIONES_SUSTANTIVAS)
        cambiados_total += cambiados

        print("[%d/%d] %-46s  %d fragmentos, %d reasignados" %
              (i, len(arts), (a.titulo or a.id)[:46], len(frags), cambiados))
        print("        antes  : %s" % ", ".join("%s=%d" % kv for kv in sorted(antes.items())))
        print("        despues: %s" % ", ".join("%s=%d" % kv for kv in sorted(despues.items())))
        print("        fragmentos en secciones sustantivas: %d -> %d" % (sus_antes, sus_desp))

    db.commit()
    print()
    print("Total reasignados: %d" % cambiados_total)
    print("No se ha consumido cuota de API: los vectores no se han tocado.")
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    db = SessionLocal()
    try:
        if not args:
            for p in db.query(Proyecto).order_by(Proyecto.creado_en.desc()).limit(10):
                print("%s  %s" % (p.id, (p.tema_principal or "")[:50]))
            print()
            print("Uso: python scripts/reetiquetar_secciones.py <proyecto_id>")
            return 0
        return reetiquetar(db, args[0])
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
