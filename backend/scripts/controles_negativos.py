# scripts/controles_negativos.py
"""
Ejecuta los controles negativos sobre un proyecto real y emite un informe.

Uso:
    python scripts/controles_negativos.py                # usa datos sinteticos
    python scripts/controles_negativos.py <proyecto_id>  # usa un proyecto de la BD

Los controles de la capa de generacion solo concluyen con GEMINI_MODE=real,
porque en modo simulado la respuesta del modelo es fija por construccion.
"""

from __future__ import annotations

import os
import sys
import uuid

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import warnings  # noqa: E402
warnings.filterwarnings("ignore")

from app.database import SessionLocal  # noqa: E402
from app.services import controles as C  # noqa: E402

ANCHO = 78
COLOR = {C.PASA: "PASA", C.FALLA: "FALLA", C.NO_CONCLUYENTE: "N/C"}


def _linea(ch="-"):
    print(ch * ANCHO)


def imprimir(r: C.ResultadoControl) -> None:
    marca = COLOR.get(r.veredicto, "?")
    print("[%-5s] %-4s %-34s (%s)" % (marca, r.codigo, r.nombre, r.capa))
    if r.valor is not None:
        print("         valor %.4f   umbral %.4f" % (r.valor, r.umbral or 0.0))
    for trozo in _envolver(r.detalle, ANCHO - 9):
        print("         " + trozo)
    print()


def _envolver(texto: str, ancho: int) -> list[str]:
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        if len(actual) + len(p) + 1 > ancho:
            lineas.append(actual)
            actual = p
        else:
            actual = (actual + " " + p).strip()
    if actual:
        lineas.append(actual)
    return lineas


def _analizador_real():
    """Devuelve una funcion texto -> brecha, o None si no hay API real."""
    if os.getenv("GEMINI_MODE", "mock").lower() != "real":
        return None
    from app.services.gemini_service import analyze

    ctx = {"tema_principal": "Analisis de brechas", "objetivo": "Detectar vacios",
           "sector_txt": "", "metodologia_txt": ""}

    def f(texto: str) -> str:
        return analyze(texto, ctx).get("brecha", "")

    return f


def ejecutar(proyecto_id: str | None) -> int:
    db = SessionLocal()
    creado = None
    try:
        if proyecto_id:
            from app.models.articulo import Articulo
            arts = db.query(Articulo).filter(Articulo.proyecto_id == proyecto_id).all()
            if len(arts) < 2:
                print("El proyecto necesita al menos 2 articulos indexados.")
                return 2
            from app.models.proyecto import Proyecto
            pr = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
            contexto = {"tema_principal": pr.tema_principal, "objetivo": pr.objetivo,
                        "sector_txt": pr.sector_txt, "metodologia_txt": pr.metodologia_txt}
            ids = {"pertinente": arts[0].id, "duplicado": arts[0].id, "ajeno": arts[-1].id}
        else:
            print("Sin proyecto indicado: se generan datos sinteticos.")
            ids, contexto, creado = _sinteticos(db)

        ctx_ajeno = {"tema_principal": "Migracion de cetaceos y temperatura oceanica",
                     "objetivo": "Relacionar calentamiento del agua con rutas migratorias",
                     "sector_txt": "Biologia marina", "metodologia_txt": "Satelital"}

        analizar = _analizador_real()

        print()
        _linea("=")
        print("CONTROLES NEGATIVOS")
        _linea("=")
        print("modo del modelo : %s" % os.getenv("GEMINI_MODE", "mock"))
        print("proyecto        : %s" % (proyecto_id or creado))
        print()
        _linea()
        print()

        rs = [
            C.c1_permutacion_contexto(db, ids["pertinente"], contexto, ctx_ajeno),
            C.c2_texto_barajado(_texto_de(db, ids["pertinente"]), analizar=analizar),
            C.c3_articulo_ajeno(db, ids["pertinente"], ids["ajeno"], contexto),
            C.c4_duplicado_exacto(db, ids["pertinente"], ids["duplicado"], contexto),
            C.c5_estabilidad(db, ids["pertinente"], contexto),
            C.c6_articulo_exhaustivo(analizar=analizar),
        ]
        for r in rs:
            imprimir(r)

        res = C.resumen(rs)
        _linea("=")
        print("RESUMEN   pasan %d    fallan %d    no concluyentes %d    de %d"
              % (res["pasa"], res["falla"], res["no_concluyente"], res["total"]))
        _linea("=")
        if res["no_concluyente"]:
            print("Los controles no concluyentes requieren GEMINI_MODE=real.")
        return 1 if res["falla"] else 0
    finally:
        if creado:
            from app.models.proyecto import Proyecto
            db.rollback()
            db.query(Proyecto).filter(Proyecto.id == creado).delete()
            db.commit()
        db.close()


def _texto_de(db, articulo_id: str) -> str:
    from app.models.embedding_doc import EmbeddingDoc
    filas = (db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id == articulo_id)
             .order_by(EmbeddingDoc.chunk_orden).all())
    return " ".join(f.texto for f in filas)


def _sinteticos(db):
    """Crea un proyecto de prueba reutilizando los materiales de tests/."""
    sys.path.insert(0, os.path.join(RAIZ, "tests"))
    from conftest import (SECCIONES_ARTICULO, SECCIONES_AJENO, _construir_pdf,
                          CONTEXTO_PROPIO)
    from app.models.proyecto import Proyecto
    from app.models.articulo import Articulo
    from app.models.archivo import Archivo, EstadoArchivo
    from app.services.embedding_service import index_articulo
    import tempfile

    tmp = tempfile.mkdtemp(prefix="controles_")
    pdf_a = _construir_pdf(os.path.join(tmp, "a.pdf"), SECCIONES_ARTICULO)
    pdf_b = _construir_pdf(os.path.join(tmp, "b.pdf"), SECCIONES_AJENO)

    pid = str(uuid.uuid4())
    ids = {k: str(uuid.uuid4()) for k in ("pertinente", "duplicado", "ajeno")}
    db.add(Proyecto(id=pid, tema_principal=CONTEXTO_PROPIO["tema_principal"],
                    objetivo=CONTEXTO_PROPIO["objetivo"], metodologia_txt="DSRM",
                    sector_txt="Educacion superior", n_articulos_objetivo=3))
    db.flush()
    for clave, ruta in (("pertinente", pdf_a), ("duplicado", pdf_a), ("ajeno", pdf_b)):
        db.add(Articulo(id=ids[clave], proyecto_id=pid, titulo="ctrl-" + clave))
        db.flush()
        db.add(Archivo(id=str(uuid.uuid4()), proyecto_id=pid, articulo_id=ids[clave],
                       nombre=clave + ".pdf", ruta=ruta,
                       hash_sha256=uuid.uuid4().hex * 2, bytes=0,
                       estado=EstadoArchivo.extraido))
        db.flush()
    db.commit()
    for clave in ids:
        index_articulo(db, ids[clave])
    return ids, dict(CONTEXTO_PROPIO), pid


if __name__ == "__main__":
    sys.exit(ejecutar(sys.argv[1] if len(sys.argv) > 1 else None))
