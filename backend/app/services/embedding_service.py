# app/services/embedding_service.py
import os, uuid, json
from typing import List, Tuple, Dict, Any
from dotenv import load_dotenv
from google import genai
from sqlalchemy.orm import Session

from app.models.embedding_doc import EmbeddingDoc
from app.models.archivo import Archivo
from app.models.articulo import Articulo
from app.utils.text_extractor import extract_full_text
from app.utils.chunker import split_into_chunks

load_dotenv()

MODE = os.getenv("GEMINI_MODE", "mock").lower()
API_KEY = os.getenv("GEMINI_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-004").replace("models/", "")

MOCK_DIM = 768
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
        resp = client.models.embed_content(
            model=EMBED_MODEL,
            contents=[t for _i, t in trozo],
        )
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
def index_articulo(db: Session, articulo_id: str, max_chars=1200, overlap=200) -> int:
    art: Articulo | None = db.query(Articulo).filter(Articulo.id == articulo_id).first()
    if not art:
        return 0

    arc: Archivo | None = (
        db.query(Archivo)
        .filter(Archivo.articulo_id == articulo_id)
        .order_by(Archivo.creado_en.desc())
        .first()
    )
    if not arc:
        return 0

    texto = extract_full_text(arc.ruta)
    chunks = split_into_chunks(texto, max_chars=max_chars, overlap=overlap)
    if not chunks:
        return 0

    vectors = _embed_texts(chunks)
    count = 0
    for i, (txt, vec) in enumerate(zip(chunks, vectors)):
        if not vec:  # salta fragmentos vacíos si los hubiera
            continue
        db.add(EmbeddingDoc(
            id=str(uuid.uuid4()),
            articulo_id=articulo_id,
            chunk_orden=i,          # <- requiere columna en modelo/BD
            texto=txt,
            embedding=vec,          # <- JSON nativo (no json.dumps)
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
    """Primeros k fragmentos en orden de aparición."""
    rows = (
        db.query(EmbeddingDoc)
        .filter(EmbeddingDoc.articulo_id == articulo_id)
        .order_by(EmbeddingDoc.chunk_orden.asc())
        .limit(k)
        .all()
    )
    return [r.texto for r in rows]

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
