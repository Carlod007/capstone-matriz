# app/services/embedding_service.py
import os, uuid, json
from typing import List, Tuple, Dict, Any
from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from app.models.embedding_doc import EmbeddingDoc
from app.models.archivo import Archivo
from app.models.articulo import Articulo
from app.utils.text_extractor import extract_full_text, extraer_con_diagnostico
from app.utils.chunker import split_into_chunks, fragmentar
from app.services.document_structure import (
    detectar_secciones,
    seccion_en,
    SECCIONES_SUSTANTIVAS,
)
from app.services.limitador import con_reintentos, limitador_embeddings
from app.services.registro_api import OP_EMBEDDING, anotar

# Tamaño de fragmento. Se hace configurable porque incide directamente en la
# cuota: cada fragmento es un texto embebido y el nivel gratuito los cuenta de
# uno en uno. Con 1200 caracteres un artículo largo generaba más de sesenta
# fragmentos y dos artículos bastaban para agotar el minuto.
CHUNK_CHARS = int(os.getenv("CHUNK_CHARS", "1800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "250"))

load_dotenv()

MODE = os.getenv("GEMINI_MODE", "mock").lower()
API_KEY = os.getenv("GEMINI_API_KEY", "")
# text-embedding-004 fue retirado por Google y devuelve 404: el sistema no
# podía indexar nada en modo real. El sustituto es gemini-embedding-001 (C-13).
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001").replace("models/", "")

# El modelo entrega 3072 dimensiones por defecto. Se reducen a 768 porque los
# vectores se guardan como JSON en MySQL y la búsqueda recorre todos los
# fragmentos en memoria: cuadruplicar el tamaño penaliza sin necesidad. El
# modelo admite truncado por diseño, así que la pérdida de calidad es menor.
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))

# Parametros productivos de recuperacion. Se nombran para que el algoritmo y
# la fotografia de procedencia lean la misma fuente y no puedan divergir.
RECUPERACION_TOP_K = 8
RECUPERACION_LAMBDA_DIVERSIDAD = 0.7
RECUPERACION_MIN_SUSTANTIVOS = 3

MOCK_DIM = EMBED_DIM
_client = None


def _get_client() -> "genai.Client":
    """Devuelve el cliente del SDK, creándolo una sola vez.

    Antes la configuración ocurría en tiempo de importación y lanzaba
    RuntimeError si faltaba la clave, lo que impedía arrancar el backend para
    pruebas sin consumir cuota (C-09). Migrado a google-genai (C-11).
    """
    global _client
    if MODE != "real":
        raise RuntimeError("_get_client() solo debe usarse en GEMINI_MODE=real")
    if not API_KEY:
        raise RuntimeError(
            "Falta GEMINI_API_KEY en .env. Usa GEMINI_MODE=mock para ejecutar "
            "el sistema sin consumir cuota de API."
        )
    if _client is None:
        _client = genai.Client(api_key=API_KEY)
    return _client


def _mock_embed(text: str, dim: int = MOCK_DIM) -> list[float]:
    """Embedding determinista por 'hashing trick', sin llamadas de red.

    No es semántico, pero sí es estable entre ejecuciones y conserva la
    propiedad que importa para probar el pipeline: dos textos con vocabulario
    parecido obtienen vectores parecidos, así que el coseno se comporta de
    forma sensata en las pruebas.
    """
    import hashlib, math, re

    vec = [0.0] * dim
    for tok in re.findall(r"\w+", (text or "").lower()):
        h = hashlib.md5(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        signo = 1.0 if h[4] % 2 == 0 else -1.0
        vec[idx] += signo
    norma = math.sqrt(sum(x * x for x in vec))
    if norma == 0.0:
        return [0.0] * dim
    return [x / norma for x in vec]


# ---------------------------
# Helpers de embeddings
# ---------------------------
def _embed_texts(texts: list[str], batch: int = 32) -> list[list[float]]:
    """Devuelve una lista de vectores (lista de floats) para cada texto.

    El SDK nuevo acepta varios textos por llamada, así que se envían por lotes
    en lugar de uno a uno como hacía la versión anterior.
    """
    vectors: list[list[float]] = [[] for _ in texts]

    # Índices con contenido real; los vacíos conservan su posición.
    pend = [(i, (t or "").strip()) for i, t in enumerate(texts) if (t or "").strip()]
    if not pend:
        raise RuntimeError("No se generaron embeddings")

    if MODE != "real":
        for i, t in pend:
            vectors[i] = _mock_embed(t)
        return vectors

    client = _get_client()
    for ini in range(0, len(pend), batch):
        trozo = pend[ini:ini + batch]

        # El SDK agrupa los textos en una sola llamada HTTP, pero el servicio
        # contabiliza cada texto por separado contra la cuota por minuto. Se
        # piden tantas fichas como textos, no una por llamada (A-02).
        limitador_embeddings.adquirir(len(trozo))

        def _llamar(trozo=trozo):
            try:
                r = client.models.embed_content(
                    model=EMBED_MODEL,
                    contents=[t for _i, t in trozo],
                    config=types.EmbedContentConfig(output_dimensionality=EMBED_DIM),
                )
            except Exception as exc:
                anotar(OP_EMBEDDING, modelo=EMBED_MODEL, exito=False,
                       unidades=len(trozo), motivo=str(exc))
                raise
            anotar(OP_EMBEDDING, modelo=EMBED_MODEL, exito=True,
                   unidades=len(trozo))
            return r

        resp = con_reintentos(
            _llamar, descripcion="embed_content(%d textos)" % len(trozo))
        emb = getattr(resp, "embeddings", None) or []
        if len(emb) != len(trozo):
            raise RuntimeError(
                "El servicio devolvió %d embeddings para %d textos"
                % (len(emb), len(trozo))
            )
        for (i, _t), e in zip(trozo, emb):
            vals = getattr(e, "values", None)
            if not vals:
                raise RuntimeError("Formato de embedding desconocido")
            vectors[i] = list(vals)

    if not any(v for v in vectors):
        raise RuntimeError("No se generaron embeddings")
    return vectors

def _cos(a: list[float], b: list[float]) -> float:
    import math
    if not a or not b:
        return 0.0
    da = math.sqrt(sum(x*x for x in a)) or 1.0
    db_ = math.sqrt(sum(x*x for x in b)) or 1.0
    return sum(x*y for x, y in zip(a, b)) / (da * db_)

# ---------------------------
# Indexación (RAG - fase build)
# ---------------------------
def index_articulo(db: Session, articulo_id: str, max_chars: int | None = None,
                   overlap: int | None = None, reindexar: bool = False) -> int:
    """Indexa un artículo. Es idempotente.

    Si ya tiene fragmentos se devuelve el número existente sin volver a
    llamar a la API. Antes no se comprobaba, de modo que reintentar tras un
    fallo a mitad de lote duplicaba los fragmentos del artículo ya procesado
    y volvía a gastar cuota por ellos.

    Con `reindexar=True` se descartan los fragmentos previos y se recalculan,
    que es lo que hace falta al cambiar el tamaño de fragmento o el modelo.
    """
    max_chars = CHUNK_CHARS if max_chars is None else max_chars
    overlap = CHUNK_OVERLAP if overlap is None else overlap

    art: Articulo | None = db.query(Articulo).filter(Articulo.id == articulo_id).first()
    if not art:
        return 0

    existentes = (db.query(EmbeddingDoc)
                  .filter(EmbeddingDoc.articulo_id == articulo_id).count())
    if existentes and not reindexar:
        return existentes
    if existentes and reindexar:
        db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id == articulo_id).delete()
        db.flush()

    arc: Archivo | None = (
        db.query(Archivo)
        .filter(Archivo.articulo_id == articulo_id)
        .order_by(Archivo.creado_en.desc())
        .first()
    )
    if not arc:
        return 0

    # `arc.ruta` guarda una clave de almacenamiento, no un camino del disco.
    from app.services import almacenamiento

    try:
        ruta_pdf = almacenamiento.ruta_local(arc.ruta)
    except almacenamiento.ClaveInvalida:
        return 0

    diag = extraer_con_diagnostico(ruta_pdf)
    texto = diag.texto
    fragmentos = fragmentar(texto, max_chars=max_chars, overlap=overlap)
    if not fragmentos:
        return 0

    # Cada fragmento se etiqueta con la sección del artículo en la que cae,
    # para poder exigir cobertura al recuperar contexto (M-10).
    secciones = detectar_secciones(texto)

    vectors = _embed_texts([f.texto for f in fragmentos])
    count = 0
    for i, (frag, vec) in enumerate(zip(fragmentos, vectors)):
        if not vec:  # salta fragmentos vacíos si los hubiera
            continue
        db.add(EmbeddingDoc(
            id=str(uuid.uuid4()),
            articulo_id=articulo_id,
            chunk_orden=i,          # <- requiere columna en modelo/BD
            texto=frag.texto,
            embedding=vec,          # <- JSON nativo (no json.dumps)
            seccion=seccion_en(secciones, frag.inicio),
            char_inicio=frag.inicio,
            char_fin=frag.fin,
        ))
        count += 1
    db.commit()
    return count

# ---------------------------
# Búsqueda y recuperación
# ---------------------------
def embed_query(db: Session, articulo_ids: List[str], query: str, top_k: int = 5) -> List[Tuple[str, float, str]]:
    """Devuelve [(embedding_doc_id, score, texto)]"""
    q_vec = _embed_texts([query])[0]

    q = db.query(EmbeddingDoc)
    if articulo_ids:
        q = q.filter(EmbeddingDoc.articulo_id.in_(articulo_ids))
    docs = q.all()

    scored: List[Tuple[str, float, str]] = []
    for d in docs:
        vec = d.embedding
        # si por algún motivo quedó string, intenta parsear
        if isinstance(vec, str):
            try:
                vec = json.loads(vec)
            except Exception:
                vec = []
        scored.append((d.id, _cos(q_vec, vec), d.texto))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]

def get_top_chunks(db: Session, articulo_id: str, k: int = 8) -> list[str]:
    """Primeros k fragmentos en orden de aparición.

    OBSOLETA. Pese al nombre, el criterio es posicional y no de relevancia:
    devuelve siempre el principio del artículo. Usada como contexto del
    modelo, hacía que el análisis viera solo resumen e introducción y nunca
    método, resultados ni discusión (M-10). Se conserva para usos de
    depuración; para obtener contexto usar `recuperar_contexto`.
    """
    rows = (
        db.query(EmbeddingDoc)
        .filter(EmbeddingDoc.articulo_id == articulo_id)
        .order_by(EmbeddingDoc.chunk_orden.asc())
        .limit(k)
        .all()
    )
    return [r.texto for r in rows]


def construir_consulta(contexto: Dict[str, Any]) -> str:
    """Consulta de recuperación a partir del contexto del proyecto.

    Sin esto la recuperación no tiene contra qué medir relevancia. Incluye el
    tema, el objetivo y el sector declarados por el investigador, más términos
    que orientan la búsqueda hacia lo que revela una brecha.
    """
    partes = [
        (contexto.get("tema_principal") or "").strip(),
        (contexto.get("objetivo") or "").strip(),
        (contexto.get("sector_txt") or "").strip(),
        (contexto.get("metodologia_txt") or "").strip(),
        "limitaciones del estudio, vacíos de investigación, trabajo futuro, "
        "diseño metodológico, muestra, validación, resultados y hallazgos",
    ]
    return " ".join(p for p in partes if p)


def recuperar_contexto(
    db: Session,
    articulo_id: str,
    contexto: Dict[str, Any],
    k: int = RECUPERACION_TOP_K,
    lambda_diversidad: float = RECUPERACION_LAMBDA_DIVERSIDAD,
    min_sustantivos: int = RECUPERACION_MIN_SUSTANTIVOS,
) -> List[Dict[str, Any]]:
    """Selecciona los fragmentos que se entregarán al modelo.

    Combina tres criterios, en sustitución del corte posicional anterior:

    1. **Relevancia**: similitud coseno frente a la consulta construida a
       partir del contexto del proyecto.
    2. **Diversidad** (MMR): penaliza el fragmento que se parece a los ya
       elegidos, para no llenar la ventana con variantes del mismo párrafo.
    3. **Cuota seccional**: reserva plazas para método, resultados, discusión
       y limitaciones, de modo que el ranking no deje fuera las secciones
       donde de verdad se aprecia una brecha.

    Devuelve una lista de diccionarios con texto, sección y puntuación, apta
    para registrar trazabilidad además de para construir el prompt.
    """
    docs = (
        db.query(EmbeddingDoc)
        .filter(EmbeddingDoc.articulo_id == articulo_id)
        .order_by(EmbeddingDoc.chunk_orden.asc())
        .all()
    )
    if not docs:
        return []

    consulta = construir_consulta(contexto)
    q_vec = _embed_texts([consulta])[0]

    candidatos = []
    for d in docs:
        vec = d.embedding
        if isinstance(vec, str):
            try:
                vec = json.loads(vec)
            except Exception:
                vec = []
        if not vec:
            continue
        candidatos.append({
            "id": d.id,
            "texto": d.texto,
            "seccion": d.seccion or "otro",
            "orden": d.chunk_orden,
            "char_inicio": d.char_inicio,
            "char_fin": d.char_fin,
            "vector": vec,
            "score": _cos(q_vec, vec),
        })
    if not candidatos:
        return []

    candidatos.sort(key=lambda c: c["score"], reverse=True)

    seleccion: List[Dict[str, Any]] = []
    restantes = list(candidatos)

    def _elegir(pool: list) -> dict | None:
        """Mejor candidato del pool según relevancia penalizada por redundancia."""
        mejor, mejor_val = None, None
        for c in pool:
            if not seleccion:
                val = c["score"]
            else:
                redundancia = max(_cos(c["vector"], s["vector"]) for s in seleccion)
                val = lambda_diversidad * c["score"] - (1 - lambda_diversidad) * redundancia
            if mejor_val is None or val > mejor_val:
                mejor, mejor_val = c, val
        return mejor

    # 1) Cuota seccional: asegura presencia de las secciones sustantivas.
    disponibles_sustantivas = {
        c["seccion"] for c in restantes if c["seccion"] in SECCIONES_SUSTANTIVAS
    }
    for seccion in sorted(disponibles_sustantivas):
        if len(seleccion) >= min(min_sustantivos, k):
            break
        pool = [c for c in restantes if c["seccion"] == seccion]
        elegido = _elegir(pool)
        if elegido is not None:
            seleccion.append(elegido)
            restantes.remove(elegido)

    # 2) El resto por relevancia con diversificación.
    while len(seleccion) < k and restantes:
        elegido = _elegir(restantes)
        if elegido is None:
            break
        seleccion.append(elegido)
        restantes.remove(elegido)

    # Se devuelve en orden de aparición: el modelo razona mejor con el
    # documento en su secuencia natural que con un ranking de relevancia.
    seleccion.sort(key=lambda c: c["orden"])
    return [
        {
            "embedding_id": c["id"],
            "texto": c["texto"],
            "seccion": c["seccion"],
            "orden": c["orden"],
            "score": round(c["score"], 4),
            "char_inicio": c["char_inicio"],
            "char_fin": c["char_fin"],
        }
        for c in seleccion
    ]

def build_rag_context(db: Session, articulo_id: str, k: int = 8, max_chars: int = 3000) -> str:
    """
    Devuelve un contexto concatenado de hasta k fragmentos del artículo.
    Se recorta a max_chars para no desbordar el prompt del LLM.
    """
    parts = get_top_chunks(db, articulo_id, k=k)
    ctx = "\n\n".join(parts)
    return ctx[:max_chars]

# ---------------------------
# Scoring para validación automática
# ---------------------------
def score_against_rag(db: Session, articulo_id: str, texto: str, top_k: int = 5) -> Dict[str, Any]:
    """
    Calcula similitud entre 'texto' y los embeddings del artículo.
    Retorna:
      {
        "sim_promedio": float,
        "rag_hits": [{"score": float, "fragmento": str}, ...]
      }
    """
    hits = embed_query(db, [articulo_id], texto, top_k=top_k)
    if not hits:
        return {"sim_promedio": 0.0, "rag_hits": []}

    scores = [s for _id, s, _t in hits]
    sim_prom = sum(scores) / max(len(scores), 1)
    rag_hits = [{"score": round(s, 4), "fragmento": t[:300]} for _id, s, t in hits]
    return {"sim_promedio": round(sim_prom, 4), "rag_hits": rag_hits}
