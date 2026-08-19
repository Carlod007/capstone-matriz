# app/services/metrics.py
from __future__ import annotations
from typing import List, Tuple, Optional, Dict
from sqlalchemy.orm import Session
import math, json, collections

from app.models.embedding_doc import EmbeddingDoc
from app.models.run_item import RunItem
from app.models.resultado_brecha import ResultadoBrecha
from app.models.articulo import Articulo
from app.models.run import Run  # ← para unir por proyecto
from app.services.embedding_service import _embed_texts  # helper existente
from app.services.metricas import texto as T  # detección de idioma
from app.services.text_cleaning import normalize_basic

# Importar ResultadoResumen (resumen_generado, resumen_referencia, lexical_density, rouge1_*)
try:
    from app.models.resultado_resumen import ResultadoResumen
except Exception:  # pragma: no cover
    ResultadoResumen = None  # type: ignore


# ---------- utilidades ----------
def embed_text(text: str) -> List[float]:
    return _embed_texts([text or ""])[0]


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def jaccard(a: str, b: str) -> float:
    A = set((a or "").lower().split())
    B = set((b or "").lower().split())
    if not A and not B:
        return 0.0
    return len(A & B) / float(len(A | B))


def _tok_unigrams(text: str) -> list[str]:
    # limpieza básica para ROUGE-1 (minúsculas, sin signos raros)
    t = normalize_basic(text or "").lower()
    for ch in ",.;:!?()[]{}\"'«»/\\\n\r\t":
        t = t.replace(ch, " ")
    return [w for w in t.split() if w]


def rouge1_prf(ref: str, hyp: str) -> tuple[float, float, float]:
    """ROUGE-1 precisión, recall, F1 sobre unigrams."""
    R = _tok_unigrams(ref)
    H = _tok_unigrams(hyp)
    if not R or not H:
        return 0.0, 0.0, 0.0
    ref_counts = collections.Counter(R)
    hyp_counts = collections.Counter(H)
    overlap = sum(min(hyp_counts[w], ref_counts[w]) for w in hyp_counts)
    prec = overlap / max(1, sum(hyp_counts.values()))
    rec = overlap / max(1, sum(ref_counts.values()))
    f1 = 0.0 if (prec + rec) == 0 else 2 * prec * rec / (prec + rec)
    return prec, rec, f1


def _coherencia_desde_entropia_norm(entropia_norm: float) -> float:
    """Coherencia ~ 1 - entropía_norm, recortado a [0,1]."""
    x = 1.0 - max(0.0, min(1.0, entropia_norm))
    return max(0.0, min(1.0, x))


def _safe_avg(values):
    nums = []
    for v in values:
        try:
            if v is None:
                continue
            f = float(v)
            nums.append(f)
        except Exception:
            continue
    return sum(nums) / len(nums) if nums else 0.0


def _to_pct_0_100(x, lo=0.0, hi=1.0, invert: bool = False):
    # normaliza x de [lo,hi] a [0,100]; si invert=True invierte la escala
    if hi == lo:
        return 0.0
    try:
        t = (float(x) - lo) / (hi - lo)
    except Exception:
        return 0.0
    t = 1.0 - t if invert else t
    return max(0.0, min(100.0, t * 100.0))


# ---------- validación con RAG ----------
def validate_breach_with_rag(
    db: Session, articulo_id: str, brecha_text: str, top_k: int = 8
) -> tuple[float, int, float]:
    """
    Calcula la similitud media entre la brecha y los embeddings del artículo.
    Devuelve (sim_promedio, rag_hits, val_score).
    """
    q_vec = embed_text(brecha_text)
    docs = db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id == articulo_id).all()
    if not docs:
        return 0.0, 0, 0.0

    scored: List[float] = []
    for d in docs:
        vec = d.embedding
        if isinstance(vec, str):
            try:
                vec = json.loads(vec)
            except Exception:
                vec = []
        scored.append(cosine(q_vec, vec))

    scored = [s for s in scored if s > 0]
    if not scored:
        return 0.0, 0, 0.0

    scored.sort(reverse=True)
    top = scored[: max(1, top_k)]
    sim_avg = sum(top) / float(len(top))
    hits = sum(1 for s in top if s >= 0.5)
    val_score = (sim_avg + (hits / len(top))) / 2.0
    return sim_avg, hits, val_score


# ---------- detección de duplicados ----------
def find_duplicate_breach(
    db: Session, articulo_id: str, nueva_brecha: str, thr: float = 0.80
) -> tuple[Optional[ResultadoBrecha], bool]:
    """
    Busca una brecha previa similar (Jaccard) del mismo artículo.
    Retorna (brecha_duplicada, es_duplicada)
    """
    # `.select()` explícito: pasar la subconsulta cruda a `in_()` está en
    # desuso desde SQLAlchemy 1.4 y romperá en una versión futura.
    subq = db.query(RunItem.id).filter(RunItem.articulo_id == articulo_id).subquery()
    prev = (
        db.query(ResultadoBrecha)
        .filter(ResultadoBrecha.run_item_id.in_(subq.select()))
        .all()
    )

    best_row: Optional[ResultadoBrecha] = None
    best = 0.0
    for r in prev:
        s = jaccard(nueva_brecha, r.brecha or "")
        if s > best:
            best, best_row = s, r
    if best >= thr:
        return best_row, True
    return None, False


# --- Validación automática basada en métricas ---
def auto_validate(
    sim_promedio: float, entropia_norm: float, val_score: float, es_duplicada: bool
) -> tuple[str, str]:
    """
    Usa entropía NORMALIZADA (0–1). Regla:
      - Rechazada si duplicada.
      - Rechazada si sim_promedio < 0.25 o entropia_norm > 0.70.
      - Aceptada si val_score >= 0.60.
      - Pendiente en los demás casos.
    """
    if es_duplicada:
        return "rechazada", "Duplicada con otra brecha del mismo artículo."
    if sim_promedio < 0.25:
        return "rechazada", f"Similaridad insuficiente (sim_promedio={sim_promedio:.2f} < 0.25)."
    if entropia_norm > 0.70:
        return "rechazada", f"Alta entropía del texto (entropía_norm={entropia_norm:.2f} > 0.70)."
    if val_score >= 0.60:
        return "aceptada", f"Pasa umbral de calidad (val_score={val_score:.2f} ≥ 0.60)."
    return "pendiente", "Métricas inconclusas; requiere revisión posterior."


# ========== Indicadores agregados del proyecto (para dashboard PDF) ==========
def project_indicators(db: Session, proyecto_id: str) -> Dict[str, Dict]:
    """
    Devuelve:
      {
        "promedios": {
            "avg_sim_promedio": float,
            "avg_entropia": float,           # bits
            "avg_entropia_norm": float,      # 0..1
            "avg_val_score": float,
            "aceptadas": int,
            "rechazadas": int,
            "pendientes": int,
            "total": int,
            "pct_brechas_aceptadas": float,   # 0..1
            # None cuando no hubo ningún par comparable: sin resúmenes
            # todavía, o con el resumen y el abstract en idiomas distintos,
            # donde ROUGE daría casi cero por construcción. Quien lo consuma
            # debe mostrar "no aplicable", no 0.000.
            "avg_rouge1_prec": float | None,
            "avg_rouge1_rec": float | None,
            "avg_rouge1_f1": float | None,
            "rouge_pares_comparados": int,
            # El total, y su desglose por motivo. No son intercambiables:
            # "idiomas distintos" es un par que existe y no se puede
            # comparar; "indeterminado" es que el detector no se pronuncio
            # y no se sabe si el par era comparable.
            "rouge_descartados_idioma": int,
            "rouge_descartados_idioma_distinto": int,
            "rouge_descartados_idioma_indeterminado": int,
            # También None si no se midió ninguna: mide palabras con contenido
            # dentro de un texto, así que —a diferencia de ROUGE— no le afecta
            # el idioma de la referencia y se calcula siempre que haya resumen.
            "avg_lexical_density": float | None,
            "densidad_resumenes_medidos": int
        },
        "dimensiones": {
            "Identificación de brechas": float (%),
            "Síntesis y claridad": float (%),
            "Validación automática": float (%),
            "Calidad global": float (%)
        },
        # Además se devuelven claves planas para el PDF/front:
        "similitud_promedio": float,        # 0..1
        "avg_val_score": float,             # 0..1
        "avg_entropia_norm": float,         # 0..1
        "pct_brechas_aceptadas": float,     # 0..1
        "rouge1_f1": float | None,          # None si no hubo nada comparable
        "claridad_visualizacion": float,    # 0..1 (proxy)
        "utilidad_sistema": float           # 0..1 (proxy)
      }

    Importante: NO usa ResultadoBrecha.articulo_id (no existe).
    Une ResultadoBrecha -> RunItem -> Run (filtrando por proyecto_id).
    """
    # 1) run_items del proyecto
    run_items = (
        db.query(RunItem.id, RunItem.articulo_id)
        .join(Run, Run.id == RunItem.run_id)
        .filter(Run.proyecto_id == proyecto_id)
        .all()
    )
    if not run_items:
        vacio = {
            "promedios": {
                "avg_sim_promedio": 0.0,
                "avg_entropia": 0.0,
                "avg_entropia_norm": 0.0,
                "avg_val_score": 0.0,
                "aceptadas": 0,
                "rechazadas": 0,
                "pendientes": 0,
                "total": 0,
                "pct_brechas_aceptadas": 0.0,
                # Sin valor y no cero: aquí no se ha medido nada todavía, y un
                # 0.000 en el panel se lee como "los resúmenes salieron
                # pésimos" cuando lo que pasa es que no hay ninguno.
                "avg_rouge1_prec": None,
                "avg_rouge1_rec": None,
                "avg_rouge1_f1": None,
                "rouge_pares_comparados": 0,
                "rouge_descartados_idioma": 0,
                "rouge_descartados_idioma_distinto": 0,
                "rouge_descartados_idioma_indeterminado": 0,
                "avg_lexical_density": None,
                "densidad_resumenes_medidos": 0,
            },
            "dimensiones": {},
        }
        # espejos planos
        vacio.update(
            {
                "similitud_promedio": 0.0,
                "avg_val_score": 0.0,
                "avg_entropia_norm": 0.0,
                "pct_brechas_aceptadas": 0.0,
                "rouge1_f1": None,
                "claridad_visualizacion": 0.0,
                "utilidad_sistema": 0.0,
            }
        )
        return vacio

    run_item_ids = [ri.id for ri in run_items]
    articulo_ids = [ri.articulo_id for ri in run_items if ri.articulo_id]

    # 2) brechas de esos run_items
    brechas = (
        db.query(ResultadoBrecha)
        .filter(ResultadoBrecha.run_item_id.in_(run_item_ids))
        .all()
    )

    if not brechas:
        vacio = {
            "promedios": {
                "avg_sim_promedio": 0.0,
                "avg_entropia": 0.0,
                "avg_entropia_norm": 0.0,
                "avg_val_score": 0.0,
                "aceptadas": 0,
                "rechazadas": 0,
                "pendientes": 0,
                "total": 0,
                "pct_brechas_aceptadas": 0.0,
                # Sin valor y no cero: aquí no se ha medido nada todavía, y un
                # 0.000 en el panel se lee como "los resúmenes salieron
                # pésimos" cuando lo que pasa es que no hay ninguno.
                "avg_rouge1_prec": None,
                "avg_rouge1_rec": None,
                "avg_rouge1_f1": None,
                "rouge_pares_comparados": 0,
                "rouge_descartados_idioma": 0,
                "rouge_descartados_idioma_distinto": 0,
                "rouge_descartados_idioma_indeterminado": 0,
                "avg_lexical_density": None,
                "densidad_resumenes_medidos": 0,
            },
            "dimensiones": {},
        }
        vacio.update(
            {
                "similitud_promedio": 0.0,
                "avg_val_score": 0.0,
                "avg_entropia_norm": 0.0,
                "pct_brechas_aceptadas": 0.0,
                "rouge1_f1": None,
                "claridad_visualizacion": 0.0,
                "utilidad_sistema": 0.0,
            }
        )
        return vacio

    # 3) Métricas numéricas de brechas
    sims = [getattr(b, "sim_promedio", None) for b in brechas]
    ents = [getattr(b, "entropia", None) for b in brechas]  # bits
    vscore = [getattr(b, "val_score", None) for b in brechas]

    # entropía NORMALIZADA por brecha: preferir campo 'entropia_norm', si no existe usar bits/8
    ents_norm = []
    for b in brechas:
        v = getattr(b, "entropia_norm", None)
        if v is None:
            bits = getattr(b, "entropia", None)
            if bits is not None:
                try:
                    v = min(max(float(bits) / 8.0, 0.0), 1.0)
                except Exception:
                    v = None
        if v is not None:
            ents_norm.append(float(v))

    avg_sim = _safe_avg(sims)
    avg_ent = _safe_avg(ents)         # bits
    avg_ent_norm = _safe_avg(ents_norm)  # 0..1
    avg_vsc = _safe_avg(vscore)

    # 3.bis) ROUGE-1 promedio (resúmenes automáticos vs referencia)
    avg_rouge_prec = 0.0
    avg_rouge_rec = 0.0
    avg_rouge_f1 = 0.0
    avg_lex_density = 0.0

    # Se declaran aquí y no dentro del `if`: más abajo se consultan para decidir
    # si hubo algún par comparable, y sin proyecto o sin resúmenes ese bloque no
    # llega a ejecutarse.
    precs: list[float] = []
    recs: list[float] = []
    f1s: list[float] = []
    lexs: list[float] = []
    descartados_distinto = 0
    descartados_indeterminado = 0

    if ResultadoResumen is not None and articulo_ids:
        try:
            res_rows = (
                db.query(ResultadoResumen)
                .filter(ResultadoResumen.articulo_id.in_(articulo_ids))
                .all()
            )
        except Exception:
            res_rows = []

        if res_rows:
            for rr in res_rows:
                ref = getattr(rr, "resumen_referencia", "") or ""
                hyp = getattr(rr, "resumen_generado", "") or ""

                # Cada métrica pide solo lo que de verdad necesita.
                #
                # La densidad léxica mide la proporción de palabras con
                # contenido dentro de un solo texto. No compara nada con la
                # referencia, así que le basta el resumen: ni el idioma del
                # abstract ni su ausencia la afectan. Estuvo dos veces detrás
                # de una condición que no era suya —primero la del idioma,
                # luego la de la referencia—, y las dos veces el efecto fue el
                # mismo: descontar del promedio resúmenes perfectamente
                # medidos, y de paso hundir la dimensión de síntesis que se
                # calcula con ella.
                if hyp:
                    ld = getattr(rr, "lexical_density", None)
                    if ld is not None:
                        try:
                            lexs.append(float(ld))
                        except Exception:
                            pass

                # ROUGE sí necesita los dos textos: compara uno contra otro.
                if not ref or not hyp:
                    continue

                # Y además cuenta palabras compartidas, así que entre un
                # resumen en español y un abstract en inglés da un valor
                # cercano a cero por construcción, por fiel que sea el resumen.
                #
                # La capa v2 ya lo tenía en cuenta, pero este camino —el que
                # alimenta /metrics/resumen y el PDF del panel— seguía
                # promediando esos ceros con los valores buenos y sacando una
                # media engañosa. Corregirlo en un sitio y no en el otro es
                # peor que no corregirlo: deja dos cifras distintas para lo
                # mismo sin decir cuál vale.
                #
                # La condición es idéntica a la de v2, y por eso exige que el
                # idioma sea reconocido y no solo que coincida: con textos
                # cortos el detector responde "indeterminado" para los dos, y
                # comparar entonces sería volver a promediar ceros sin saberlo.
                # Los dos motivos se cuentan por separado porque no son la
                # misma noticia. "Están en idiomas distintos" señala un par que
                # existe y no es comparable; "no se reconoce el idioma" señala
                # que el detector no se pronunció —textos demasiado cortos, o
                # un idioma fuera de es/en— y ahí ni siquiera se sabe si el par
                # era comparable. Sumarlos obliga a describirlos con una frase
                # que solo es cierta para la mitad.
                idioma_ref, idioma_hyp = T.idioma(ref), T.idioma(hyp)
                if idioma_ref not in ("es", "en") or idioma_hyp not in ("es", "en"):
                    descartados_indeterminado += 1
                    continue
                if idioma_ref != idioma_hyp:
                    descartados_distinto += 1
                    continue

                p, r, f1 = rouge1_prf(ref, hyp)
                precs.append(p)
                recs.append(r)
                f1s.append(f1)

            avg_rouge_prec = _safe_avg(precs)
            avg_rouge_rec = _safe_avg(recs)
            avg_rouge_f1 = _safe_avg(f1s)
            avg_lex_density = _safe_avg(lexs)

    # 4) Conteos por estado_validacion
    estados = [
        (getattr(b, "estado_validacion", "") or "").lower().strip()
        for b in brechas
    ]
    aceptadas = sum(1 for s in estados if s == "aceptada")
    rechazadas = sum(1 for s in estados if s == "rechazada")
    pendientes = sum(1 for s in estados if s == "pendiente")
    total = len(brechas)
    pct_aceptadas = (aceptadas / total) if total else 0.0

    promedios = {
        "avg_sim_promedio": float(avg_sim),
        "avg_entropia": float(avg_ent),              # bits (informativo)
        "avg_entropia_norm": float(avg_ent_norm),    # 0..1
        "avg_val_score": float(avg_vsc),
        "aceptadas": aceptadas,
        "rechazadas": rechazadas,
        "pendientes": pendientes,
        "total": total,
        "pct_brechas_aceptadas": float(pct_aceptadas),
        # None y no 0.0 cuando no hubo ningún par comparable: un cero se lee
        # como "los resúmenes no se parecen en nada" y lo que ocurre es que la
        # métrica no aplica. Quien consuma esto debe mostrar "no aplicable".
        "avg_rouge1_prec": None if not precs else float(avg_rouge_prec),
        "avg_rouge1_rec": None if not recs else float(avg_rouge_rec),
        "avg_rouge1_f1": None if not f1s else float(avg_rouge_f1),
        "rouge_pares_comparados": len(f1s),
        # El total se conserva por compatibilidad, pero quien redacte un texto
        # a partir de él debe usar el desglose: decir "descartados por estar en
        # idiomas distintos" sobre la suma es falso en cuanto hay uno solo
        # indeterminado.
        "rouge_descartados_idioma": descartados_distinto + descartados_indeterminado,
        "rouge_descartados_idioma_distinto": descartados_distinto,
        "rouge_descartados_idioma_indeterminado": descartados_indeterminado,
        # Mismo criterio que arriba, por el mismo motivo: sin ningún resumen
        # medido, un 0.0 se lee como "los resúmenes no tienen ni una palabra
        # con contenido", que es un juicio, no una ausencia de datos.
        "avg_lexical_density": None if not lexs else float(avg_lex_density),
        "densidad_resumenes_medidos": len(lexs),
    }

    # 5) Dimensiones (normalizadas a %)
    # 5.1 Identificación de brechas → similitud promedio
    dim_identificacion = _to_pct_0_100(avg_sim, 0.0, 1.0, invert=False)

    # 5.2 Síntesis y claridad → combina ROUGE-1 F1, entropía invertida y densidad léxica
    componentes_sintesis = []
    if avg_rouge_f1 > 0:
        componentes_sintesis.append(_to_pct_0_100(avg_rouge_f1, 0.0, 1.0, invert=False))
    if avg_ent_norm > 0:
        componentes_sintesis.append(_to_pct_0_100(avg_ent_norm, 0.0, 1.0, invert=True))
    if avg_lex_density > 0:
        componentes_sintesis.append(_to_pct_0_100(avg_lex_density, 0.0, 1.0, invert=False))

    dim_sintesis = (
        sum(componentes_sintesis) / len(componentes_sintesis)
        if componentes_sintesis
        else 0.0
    )

    # 5.3 Validación automática → mezcla de val_score y % aceptadas
    comp_validacion = []
    if avg_vsc > 0:
        comp_validacion.append(_to_pct_0_100(avg_vsc, 0.0, 1.0, invert=False))
    if pct_aceptadas > 0:
        comp_validacion.append(_to_pct_0_100(pct_aceptadas, 0.0, 1.0, invert=False))

    dim_validacion = (
        sum(comp_validacion) / len(comp_validacion)
        if comp_validacion
        else 0.0
    )

    dim_vals = [dim_identificacion, dim_sintesis, dim_validacion]
    dim_quality = (
        sum(dim_vals)
        / len([v for v in dim_vals if isinstance(v, (int, float))])
        if any(dim_vals)
        else 0.0
    )

    dimensiones = {
        "Identificación de brechas": round(dim_identificacion, 1),
        "Síntesis y claridad": round(dim_sintesis, 1),
        "Validación automática": round(dim_validacion, 1),
        "Calidad global": round(dim_quality, 1),
    }

    # ---- Proxies para el PDF/front (claridad visualización & utilidad) ----
    try:
        have_plots = bool(db.query(EmbeddingDoc).first())
    except Exception:
        have_plots = False
    claridad_viz = 1.0 if have_plots else 0.0

    indicadores_para_utilidad = [
        avg_sim,
        avg_vsc,
        (1.0 - avg_ent_norm),
        pct_aceptadas,
        claridad_viz,
    ]
    utilidad = (
        sum(
            1
            for x in indicadores_para_utilidad
            if (isinstance(x, (int, float)) and x > 0)
        )
        / len(indicadores_para_utilidad)
    )

    # ---- respuesta compuesta: estructura + claves planas espejo ----
    out = {
        "promedios": promedios,
        "dimensiones": dimensiones,
        # espejos planos (para PDF/Front)
        "similitud_promedio": float(avg_sim),
        "avg_val_score": float(avg_vsc),
        "avg_entropia_norm": float(avg_ent_norm),
        "pct_brechas_aceptadas": float(pct_aceptadas),
        "rouge1_f1": None if not f1s else float(avg_rouge_f1),
        "avg_lexical_density": None if not lexs else float(avg_lex_density),
        "claridad_visualizacion": float(claridad_viz),
        "utilidad_sistema": float(utilidad),
    }
    return out


def shannon_entropy_bits_and_norm(text: str) -> Tuple[float, float]:
    """
    Retorna (entropía_en_bits, entropía_normalizada_0_1) sobre texto LIMPIO.
    Normaliza por 8 bits (1 byte) para tener escala 0–1 estable.
    """
    text = normalize_basic(text or "")
    if not text:
        return 0.0, 0.0

    cnt = collections.Counter(text)
    n = float(len(text))
    probs = [c / n for c in cnt.values()]
    bits = -sum(p * math.log2(p) for p in probs)

    max_bits = 8.0  # tope byte → 0..1 estable
    norm = min(bits / max_bits, 1.0)
    return bits, norm


def lexical_density(text: str) -> float:
    """
    Densidad léxica ≈ proporción de palabras con contenido
    (no stopwords) respecto al total de palabras.
    Devuelve valor entre 0 y 1.
    """
    text = normalize_basic(text or "")
    tokens = (text or "").lower().split()
    if not tokens:
        return 0.0

    # Stopwords simples (ES + EN, aproximado)
    stopwords = {
        "el","la","los","las","un","una","unos","unas",
        "de","del","al","a","en","y","o","u","que","con","por","para",
        "se","es","son","fue","ser","como","su","sus","lo","ya","no","sí",
        "the","a","an","and","or","of","in","on","for","to","is","are","was","were",
        "this","that","these","those","it","its","at","from","by","as","be","been",
    }

    content = [t for t in tokens if t not in stopwords]
    return len(content) / len(tokens) if tokens else 0.0
