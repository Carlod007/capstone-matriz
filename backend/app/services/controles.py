# app/services/controles.py
"""
Controles negativos del sistema.

La idea es simple: si se degrada deliberadamente la entrada y las salidas no
cambian, entonces el sistema no estaba leyendo esa entrada. Son la forma más
barata de comprobar que el análisis responde de verdad al artículo y al
contexto del proyecto, y no está rellenando una plantilla.

Cada control se ejecuta en una de dos capas:

- **Recuperación**: qué fragmentos se seleccionan. No requiere API, se puede
  ejecutar en modo simulado tantas veces como haga falta.
- **Generación**: qué brecha produce el modelo. Requiere API real, porque en
  modo simulado la respuesta es fija por construcción y cualquier conclusión
  sería falsa.

Un control que no puede evaluarse devuelve el veredicto ``no_concluyente``.
Nunca devuelve ``pasa`` por defecto: un control que no se ejecutó no es un
control superado.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Sequence

from sqlalchemy.orm import Session

from app.models.embedding_doc import EmbeddingDoc
from app.services.embedding_service import recuperar_contexto, _embed_texts, _cos

PASA = "pasa"
FALLA = "falla"
NO_CONCLUYENTE = "no_concluyente"


@dataclass
class ResultadoControl:
    codigo: str
    nombre: str
    capa: str                 # recuperacion | generacion
    veredicto: str
    valor: float | None = None
    umbral: float | None = None
    detalle: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- utilidades
def _rangos(valores: Sequence[float]) -> List[float]:
    """Rangos con promedio en los empates, como exige Spearman."""
    indexados = sorted(range(len(valores)), key=lambda i: valores[i])
    rangos = [0.0] * len(valores)
    i = 0
    while i < len(indexados):
        j = i
        while j + 1 < len(indexados) and valores[indexados[j + 1]] == valores[indexados[i]]:
            j += 1
        promedio = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            rangos[indexados[k]] = promedio
        i = j + 1
    return rangos


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """Correlación de rangos. Devuelve 0.0 si no es calculable."""
    if len(a) != len(b) or len(a) < 3:
        return 0.0
    ra, rb = _rangos(a), _rangos(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((y - mb) ** 2 for y in rb))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def jaccard_conjuntos(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / float(len(sa | sb))


def _puntuar_todos(db: Session, articulo_id: str, contexto: dict) -> Dict[str, float]:
    """Puntuación de relevancia de cada fragmento bajo un contexto dado."""
    from app.services.embedding_service import construir_consulta
    import json

    docs = db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id == articulo_id).all()
    if not docs:
        return {}
    q = _embed_texts([construir_consulta(contexto)])[0]
    salida: Dict[str, float] = {}
    for d in docs:
        vec = d.embedding
        if isinstance(vec, str):
            try:
                vec = json.loads(vec)
            except Exception:
                vec = []
        if vec:
            salida[d.id] = _cos(q, vec)
    return salida


def barajar_oraciones(texto: str, semilla: int = 20260810) -> str:
    """Reordena las oraciones destruyendo el hilo argumental.

    El vocabulario se conserva intacto: solo cambia el orden. Sirve para
    distinguir un sistema que comprende la estructura del razonamiento de uno
    que reacciona a la mera presencia de palabras.
    """
    oraciones = re.split(r"(?<=[\.\?\!])\s+", texto)
    oraciones = [o for o in oraciones if o.strip()]
    rng = random.Random(semilla)
    rng.shuffle(oraciones)
    return " ".join(oraciones)


# ---------------------------------------------------------------- C1
def c1_permutacion_contexto(
    db: Session,
    articulo_id: str,
    contexto_propio: dict,
    contexto_ajeno: dict,
    k: int = 8,
    umbral_rho: float = 0.95,
) -> ResultadoControl:
    """¿Cambia la selección si cambia el contexto del proyecto?

    Se puntúa el mismo artículo bajo dos contextos de investigación distintos.
    Si el orden de relevancia es prácticamente idéntico, la recuperación no
    está usando el contexto y la supuesta personalización es una ilusión.
    """
    p1 = _puntuar_todos(db, articulo_id, contexto_propio)
    p2 = _puntuar_todos(db, articulo_id, contexto_ajeno)
    comunes = sorted(set(p1) & set(p2))
    if len(comunes) < 3:
        return ResultadoControl(
            "C1", "Permutación de contexto", "recuperacion", NO_CONCLUYENTE,
            detalle="Se necesitan al menos 3 fragmentos indexados; hay %d." % len(comunes))

    rho = spearman([p1[i] for i in comunes], [p2[i] for i in comunes])

    sel1 = [r["embedding_id"] for r in recuperar_contexto(db, articulo_id, contexto_propio, k=k)]
    sel2 = [r["embedding_id"] for r in recuperar_contexto(db, articulo_id, contexto_ajeno, k=k)]
    jac = jaccard_conjuntos(sel1, sel2)

    veredicto = FALLA if rho >= umbral_rho else PASA
    return ResultadoControl(
        "C1", "Permutación de contexto", "recuperacion", veredicto,
        valor=round(rho, 4), umbral=umbral_rho,
        detalle=(
            "Correlación de rangos entre ambos contextos: %.4f (menor es mejor; "
            "por encima de %.2f el contexto no influye). Solape de la selección "
            "final: %.2f." % (rho, umbral_rho, jac)
        ),
        extra={"jaccard_seleccion": round(jac, 4), "fragmentos": len(comunes)},
    )


# ---------------------------------------------------------------- C2
def c2_texto_barajado(
    texto: str,
    analizar: Callable[[str], str] | None = None,
    umbral_similitud: float = 0.97,
) -> ResultadoControl:
    """¿Depende la salida del orden del razonamiento, o solo del vocabulario?

    Requiere generación real: en modo simulado la respuesta es fija y el
    control no puede concluir nada.
    """
    if analizar is None:
        return ResultadoControl(
            "C2", "Texto barajado", "generacion", NO_CONCLUYENTE,
            detalle="Requiere generación real (GEMINI_MODE=real). En modo "
                    "simulado la salida es constante por construcción.")

    original = analizar(texto)
    barajado = analizar(barajar_oraciones(texto))
    v = _embed_texts([original, barajado])
    sim = _cos(v[0], v[1])
    veredicto = FALLA if sim >= umbral_similitud else PASA
    return ResultadoControl(
        "C2", "Texto barajado", "generacion", veredicto,
        valor=round(sim, 4), umbral=umbral_similitud,
        detalle=("Similitud entre la brecha del texto original y la del texto "
                 "barajado: %.4f. Un valor casi idéntico indica que el modelo "
                 "reacciona al vocabulario y no al razonamiento." % sim),
    )


# ---------------------------------------------------------------- C3
def c3_articulo_ajeno(
    db: Session,
    articulo_pertinente: str,
    articulo_ajeno: str,
    contexto: dict,
    k: int = 8,
    margen_minimo: float = 0.05,
) -> ResultadoControl:
    """¿Distingue el sistema un artículo de su tema de uno que no lo es?

    Es la base empírica del umbral de abstención: si la relevancia de un
    artículo ajeno no es claramente menor, el sistema no puede saber cuándo
    debe abstenerse.
    """
    rp = recuperar_contexto(db, articulo_pertinente, contexto, k=k)
    ra = recuperar_contexto(db, articulo_ajeno, contexto, k=k)
    if not rp or not ra:
        return ResultadoControl(
            "C3", "Artículo ajeno al tema", "recuperacion", NO_CONCLUYENTE,
            detalle="Falta indexación en alguno de los dos artículos.")

    mp = sum(r["score"] for r in rp) / len(rp)
    ma = sum(r["score"] for r in ra) / len(ra)
    margen = mp - ma
    veredicto = PASA if margen >= margen_minimo else FALLA
    return ResultadoControl(
        "C3", "Artículo ajeno al tema", "recuperacion", veredicto,
        valor=round(margen, 4), umbral=margen_minimo,
        detalle=("Relevancia media del artículo pertinente %.4f frente a %.4f "
                 "del ajeno; margen %.4f. Sin margen no hay base para decidir "
                 "una abstención." % (mp, ma, margen)),
        extra={"media_pertinente": round(mp, 4), "media_ajeno": round(ma, 4)},
    )


# ---------------------------------------------------------------- C4
def c4_duplicado_exacto(
    db: Session,
    articulo_a: str,
    articulo_b: str,
    contexto: dict,
    k: int = 8,
    umbral_solape: float = 0.90,
) -> ResultadoControl:
    """Dos copias del mismo PDF deben recuperar el mismo contexto.

    Una divergencia aquí no es riqueza analítica: es inestabilidad.
    """
    ra = recuperar_contexto(db, articulo_a, contexto, k=k)
    rb = recuperar_contexto(db, articulo_b, contexto, k=k)
    if not ra or not rb:
        return ResultadoControl(
            "C4", "Duplicado exacto", "recuperacion", NO_CONCLUYENTE,
            detalle="Falta indexación en alguno de los dos artículos.")

    # Los identificadores difieren por ser filas distintas: se comparan los
    # textos y el orden seccional, que es lo que llega al modelo.
    ta = [" ".join(r["texto"].split()) for r in ra]
    tb = [" ".join(r["texto"].split()) for r in rb]
    solape = jaccard_conjuntos(ta, tb)
    misma_seccion = [r["seccion"] for r in ra] == [r["seccion"] for r in rb]
    veredicto = PASA if solape >= umbral_solape else FALLA
    return ResultadoControl(
        "C4", "Duplicado exacto", "recuperacion", veredicto,
        valor=round(solape, 4), umbral=umbral_solape,
        detalle=("Solape del contexto recuperado entre las dos copias: %.4f. "
                 "Secuencia de secciones idéntica: %s."
                 % (solape, "sí" if misma_seccion else "no")),
        extra={"misma_secuencia_secciones": misma_seccion},
    )


# ---------------------------------------------------------------- C5
def c5_estabilidad(
    db: Session,
    articulo_id: str,
    contexto: dict,
    k: int = 8,
    repeticiones: int = 5,
) -> ResultadoControl:
    """La misma entrada debe producir la misma recuperación.

    Cualquier variación aquí sería ruido no atribuible al artículo, y
    contaminaría todas las métricas aguas abajo.
    """
    sels = []
    for _ in range(max(2, repeticiones)):
        sels.append([r["embedding_id"] for r in recuperar_contexto(db, articulo_id, contexto, k=k)])
    if not sels[0]:
        return ResultadoControl(
            "C5", "Estabilidad entre ejecuciones", "recuperacion", NO_CONCLUYENTE,
            detalle="El artículo no tiene fragmentos indexados.")

    solapes = [jaccard_conjuntos(sels[0], s) for s in sels[1:]]
    minimo = min(solapes)
    veredicto = PASA if minimo == 1.0 else FALLA
    return ResultadoControl(
        "C5", "Estabilidad entre ejecuciones", "recuperacion", veredicto,
        valor=round(minimo, 4), umbral=1.0,
        detalle=("%d ejecuciones sobre la misma entrada; solape mínimo %.4f. "
                 "La recuperación debe ser determinista." % (len(sels), minimo)),
    )


# ---------------------------------------------------------------- C6
def c6_articulo_exhaustivo(
    analizar: Callable[[str], str] | None = None,
    texto_exhaustivo: str = "",
    texto_limitado: str = "",
    umbral_similitud: float = 0.97,
) -> ResultadoControl:
    """Un artículo exhaustivo debería dar brechas más estrechas que uno limitado.

    Requiere generación real.
    """
    if analizar is None or not texto_exhaustivo or not texto_limitado:
        return ResultadoControl(
            "C6", "Artículo sin brechas evidentes", "generacion", NO_CONCLUYENTE,
            detalle="Requiere generación real (GEMINI_MODE=real) y ambos textos "
                    "de contraste.")

    a = analizar(texto_exhaustivo)
    b = analizar(texto_limitado)
    v = _embed_texts([a, b])
    sim = _cos(v[0], v[1])
    veredicto = FALLA if sim >= umbral_similitud else PASA
    return ResultadoControl(
        "C6", "Artículo sin brechas evidentes", "generacion", veredicto,
        valor=round(sim, 4), umbral=umbral_similitud,
        detalle=("Similitud entre la brecha de un estudio exhaustivo y la de uno "
                 "limitado: %.4f. Valores casi idénticos indican que el modelo "
                 "emite la misma plantilla sea cual sea el artículo." % sim),
    )


# ---------------------------------------------------------------- informe
def resumen(resultados: List[ResultadoControl]) -> Dict[str, Any]:
    conteo = {PASA: 0, FALLA: 0, NO_CONCLUYENTE: 0}
    for r in resultados:
        conteo[r.veredicto] = conteo.get(r.veredicto, 0) + 1
    return {
        "total": len(resultados),
        "pasa": conteo[PASA],
        "falla": conteo[FALLA],
        "no_concluyente": conteo[NO_CONCLUYENTE],
        "controles": [r.dict() for r in resultados],
    }
