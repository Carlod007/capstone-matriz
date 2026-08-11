# app/services/metricas/niveles.py
"""
Métricas locales de los niveles N1, N3 y N4.

"Locales" significa que se calculan sin llamadas adicionales al modelo: usan
los embeddings ya generados durante la indexación y operaciones sobre texto.
Se pueden ejecutar sobre cada artículo sin coste adicional de API.

Los niveles que sí requieren un juez (N1.1 precisión del contexto, N2 fidelidad
evidencial, N4.3 fidelidad del resumen) quedan para el paso siguiente.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from sqlalchemy.orm import Session

from app.models.embedding_doc import EmbeddingDoc
from app.services.document_structure import SECCIONES_SUSTANTIVAS
from app.services.embedding_service import _cos, _embed_texts
from app.services.metricas import texto as T


# ================================================================= N1
def n1_2_cobertura_seccional(recuperados: Sequence[dict]) -> float:
    """Proporción de secciones sustantivas presentes en el contexto (N1.2).

    Con la implementación anterior de la recuperación este valor sería casi
    siempre 0: el contexto se tomaba del principio del documento y método,
    resultados y discusión nunca entraban.
    """
    if not recuperados:
        return 0.0
    presentes = {r.get("seccion") for r in recuperados} & set(SECCIONES_SUSTANTIVAS)
    return round(len(presentes) / len(SECCIONES_SUSTANTIVAS), 4)


def n1_3_diversidad_contexto(vectores: Sequence[Sequence[float]]) -> float:
    """Uno menos la similitud media por pares entre los fragmentos (N1.3).

    Un valor bajo indica que el contexto repite la misma idea y desaprovecha
    la ventana del modelo.
    """
    vs = [v for v in vectores if v]
    if len(vs) < 2:
        return 0.0
    pares = [
        _cos(vs[i], vs[j])
        for i in range(len(vs))
        for j in range(i + 1, len(vs))
    ]
    return round(1.0 - (sum(pares) / len(pares)), 4)


# ================================================================= N3
def n3_1_discriminabilidad(brechas_por_articulo: Dict[str, str]) -> tuple[float, dict]:
    """Cuánto se diferencian las brechas de artículos distintos (N3.1).

    Es la métrica más diagnóstica de todas. Si el modelo emite la misma
    brecha genérica para los diez artículos del lote, este valor se desploma
    y lo delata. Sustituye al Jaccard intra-artículo, que solo comparaba una
    brecha con otras del mismo artículo, donde el problema no ocurre.

    Devuelve (valor, detalle) con el par más parecido, para poder inspeccionar
    el caso concreto.
    """
    ids = [k for k, v in brechas_por_articulo.items() if (v or "").strip()]
    if len(ids) < 2:
        return 0.0, {"motivo": "se necesitan al menos dos artículos con brecha"}

    vectores = _embed_texts([brechas_por_articulo[i] for i in ids])
    pares: List[tuple[float, str, str]] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if vectores[i] and vectores[j]:
                pares.append((_cos(vectores[i], vectores[j]), ids[i], ids[j]))
    if not pares:
        return 0.0, {"motivo": "sin vectores utilizables"}

    media = sum(p[0] for p in pares) / len(pares)
    peor = max(pares, key=lambda p: p[0])
    return round(1.0 - media, 4), {
        "similitud_media": round(media, 4),
        "par_mas_parecido": {"a": peor[1], "b": peor[2], "similitud": round(peor[0], 4)},
        "n_pares": len(pares),
    }


def n3_2_densidad_anclajes(brecha: str) -> float:
    """Anclajes concretos por cada 100 palabras (N3.2)."""
    return T.densidad_anclajes(brecha)


def n3_3_contenido_informativo(brecha: str, corpus: Sequence[str]) -> float:
    """Contenido informativo medio, calibrado sobre el corpus del proyecto (N3.3)."""
    tabla = T.idf([T.tokens_contenido(c) for c in corpus if (c or "").strip()])
    return round(T.contenido_informativo(brecha, tabla), 4)


def n3_4_redundancia(brechas_por_articulo: Dict[str, str], umbral: float = 0.85
                     ) -> tuple[float, dict]:
    """Proporción de brechas casi idénticas a otra del proyecto (N3.4).

    Reemplaza la detección por Jaccard con umbral 0.80 sobre bolsa de
    palabras, que prácticamente nunca se alcanzaba entre dos paráfrasis, y
    amplía el alcance del artículo al proyecto completo.
    """
    ids = [k for k, v in brechas_por_articulo.items() if (v or "").strip()]
    if len(ids) < 2:
        return 0.0, {"motivo": "se necesitan al menos dos artículos con brecha"}

    vectores = _embed_texts([brechas_por_articulo[i] for i in ids])
    duplicados: List[dict] = []
    marcados: set[str] = set()
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if not (vectores[i] and vectores[j]):
                continue
            s = _cos(vectores[i], vectores[j])
            if s >= umbral:
                duplicados.append({"a": ids[i], "b": ids[j], "similitud": round(s, 4)})
                marcados.add(ids[j])
    return round(len(marcados) / len(ids), 4), {
        "umbral": umbral,
        "pares_duplicados": duplicados[:20],
        "n_articulos": len(ids),
    }


# ================================================================= N4
@dataclass
class MetricasResumen:
    rouge1_prec: float = 0.0
    rouge1_rec: float = 0.0
    rouge1_f1: float = 0.0
    rouge2_f1: float = 0.0
    rougeL_f1: float = 0.0
    similitud_semantica: float = 0.0
    densidad_lexica: float = 0.0
    compresion: float = 0.0
    referencia_valida: bool = False
    rouge_aplicable: bool = False
    idioma_referencia: str = ""
    idioma_generado: str = ""
    motivo: str = ""

    def dict(self) -> dict:
        d = self.__dict__.copy()
        return d


def n4_calidad_resumen(resumen_generado: str, abstract: str | None) -> MetricasResumen:
    """Calidad del resumen frente al abstract real del artículo (N4).

    Si no se pudo extraer el abstract, se devuelve `referencia_valida=False` y
    los valores quedan en cero **sin calcularse**. Antes se usaban las primeras
    180 palabras del PDF —portada, autores y encabezado de revista— y el
    resultado, aunque numéricamente válido, no significaba nada (M-02).
    """
    m = MetricasResumen()
    gen = (resumen_generado or "").strip()
    ref = (abstract or "").strip()

    if not gen:
        m.motivo = "No hay resumen generado."
        return m
    if len(ref) < 100:
        m.motivo = ("No se pudo extraer el abstract del artículo; ROUGE no se "
                    "calcula para no producir una cifra sin significado.")
        m.densidad_lexica = round(T.densidad_lexica(gen), 4)
        return m

    m.referencia_valida = True
    m.idioma_referencia = T.idioma(ref)
    m.idioma_generado = T.idioma(gen)

    # ROUGE mide solape de palabras: entre idiomas distintos da casi cero por
    # construcción, por fiel que sea el resumen. En el primer lote real los
    # artículos estaban en inglés y el resumen se generaba en español, con lo
    # que ROUGE-1 salía en 0.05 mientras la similitud semántica era 0.90. Dar
    # esa cifra como medida de calidad seria engañoso.
    m.rouge_aplicable = (
        m.idioma_referencia == m.idioma_generado
        and m.idioma_referencia in ("es", "en")
    )

    if m.rouge_aplicable:
        p1, r1, f1 = T.rouge_n(ref, gen, 1)
        m.rouge1_prec, m.rouge1_rec, m.rouge1_f1 = round(p1, 4), round(r1, 4), round(f1, 4)
        m.rouge2_f1 = round(T.rouge_n(ref, gen, 2)[2], 4)
        m.rougeL_f1 = round(T.rouge_l(ref, gen)[2], 4)
    else:
        m.motivo = (
            "ROUGE no es aplicable: el resumen está en '%s' y el abstract en "
            "'%s'. Al medir solape léxico, entre idiomas distintos daría un "
            "valor cercano a cero con independencia de la calidad. Se usa la "
            "similitud semántica, que sí funciona entre idiomas."
            % (m.idioma_generado, m.idioma_referencia)
        )

    # N4.2: capta la paráfrasis correcta que ROUGE penaliza por no compartir
    # vocabulario literal, y es la única de las dos que sigue siendo válida
    # cuando resumen y abstract están en idiomas distintos.
    vs = _embed_texts([ref, gen])
    m.similitud_semantica = round(_cos(vs[0], vs[1]), 4) if vs[0] and vs[1] else 0.0

    m.densidad_lexica = round(T.densidad_lexica(gen), 4)
    m.compresion = round(len(T.tokenizar(gen)) / max(1, len(T.tokenizar(ref))), 4)
    return m


# ================================================================= agregado
def vectores_de(db: Session, ids: Sequence[str]) -> List[List[float]]:
    """Recupera los vectores ya almacenados de unos fragmentos."""
    if not ids:
        return []
    filas = db.query(EmbeddingDoc).filter(EmbeddingDoc.id.in_(list(ids))).all()
    por_id = {f.id: f for f in filas}
    salida: List[List[float]] = []
    for i in ids:
        f = por_id.get(i)
        if not f:
            continue
        v = f.embedding
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                v = []
        if v:
            salida.append(v)
    return salida
