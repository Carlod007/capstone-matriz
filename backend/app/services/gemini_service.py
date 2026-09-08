# app/services/gemini_service.py
import os, json
from google import genai
from google.genai import types
from dotenv import load_dotenv

from app.services.limitador import con_reintentos, limitador_generacion
from app.services.registro_api import OP_ANALISIS, OP_SINTESIS, anotar
from app.tipos_brecha import (
    TIPOS_BRECHA,
    criterios_para_prompt,
    tipos_para_prompt,
)

load_dotenv()

MODE = os.getenv("GEMINI_MODE", "mock").lower()
API_KEY = os.getenv("GEMINI_API_KEY", "")
CHAT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Se incrementan solo cuando cambia el contenido o la semantica del prompt.
# La marca se fotografia al crear cada run; no se deduce leyendo datos viejos.
PROMPT_ANALISIS_VERSION = 2
PROMPT_SINTESIS_VERSION = 1

# Prompt del sistema: salida estrictamente en JSON y regla clara de tipificación
SYS_PROMPT = (
    "Eres un asistente para análisis bibliográfico. "
    "Devuelve SOLO JSON válido con campos EXACTOS: brecha, oportunidad, tipo_brecha, resumen. "
    f"Tipos válidos: {tipos_para_prompt()}. "
    "Selecciona el tipo por el foco predominante del problema, NO por mención superficial de 'método'. "
    "Criterio rápido:\n"
    f"{criterios_para_prompt()}\n"
    "El campo 'resumen' debe ser un párrafo de 5 a 8 líneas que sintetice el contenido central del artículo "
    "en lenguaje claro.\n"
    "No incluyas explicaciones fuera del JSON. No devuelvas listas ni arrays, solo un objeto JSON único."
)


# Pocas demostraciones para anclar la clasificación
FEW_SHOTS = [
    {
        "brecha": "La literatura sobre IA en educación técnica ignora programas de formación dual en Latinoamérica.",
        "oportunidad": "Realizar estudios empíricos en programas duales LATAM con comparación regional.",
        "tipo_brecha": "temática"
    },
    {
        "brecha": "Los estudios reportan métricas inconsistentes y sin protocolo de validación cruzada reproducible.",
        "oportunidad": "Proponer protocolo estandarizado con k-fold y reporte unificado de métricas.",
        "tipo_brecha": "metodológica"
    },
    {
        "brecha": "No existe un modelo conceptual integrado que conecte motivación, carga cognitiva y desempeño.",
        "oportunidad": "Plantear y contrastar un marco teórico con hipótesis medibles.",
        "tipo_brecha": "teórica"
    },
    {
        "brecha": "Falta una plataforma escalable para orquestar RAG con monitoreo y perfiles de rendimiento.",
        "oportunidad": "Desarrollar e evaluar un sistema modular con telemetría y pruebas de carga.",
        "tipo_brecha": "tecnológica"
    },
    {
        "brecha": "La evidencia se limita a una muestra pequeña y no existen replicaciones en cohortes independientes.",
        "oportunidad": "Ampliar la muestra y replicar los resultados con datos externos.",
        "tipo_brecha": "empírica"
    },
    {
        "brecha": "No se ha evaluado la adopción del modelo en condiciones reales ni su viabilidad económica.",
        "oportunidad": "Realizar un piloto de campo que mida usabilidad, costes y barreras operativas.",
        "tipo_brecha": "aplicada"
    }
]

RAG_MAX_TOTAL_CHARS = 12000
RAG_PER_DOC_LIMIT = 1500


def _mk_rag_block(
    context_docs: list[str] | None,
    max_total_chars: int = RAG_MAX_TOTAL_CHARS,
    per_doc_limit: int = RAG_PER_DOC_LIMIT,
) -> str:
    if not context_docs:
        return "Contexto recuperado (RAG): [sin fragmentos disponibles]"
    acc, total = [], 0
    for doc in context_docs:
        frag = (doc or "").strip()
        if not frag:
            continue
        if per_doc_limit and len(frag) > per_doc_limit:
            frag = frag[:per_doc_limit]
        if total + len(frag) > max_total_chars:
            break
        acc.append(frag)
        total += len(frag)
    if not acc:
        return "Contexto recuperado (RAG): [sin fragmentos disponibles]"
    return "Contexto recuperado (RAG):\n" + "\n---\n".join(acc)

USER_TMPL = """Contexto del proyecto:
- Tema: {tema_principal}
- Metodología: {metodologia_txt}
- Sector: {sector_txt}
- Objetivo: {objetivo}

{bloque_rag}

Analiza el ARTÍCULO y entrega:
- brecha: máxima 10 líneas, concreta y sustentable.
- oportunidad: propuesta aplicable.
- tipo_brecha: una de [{tipos_brecha}].
- resumen: párrafo de 5 a 8 líneas que sintetice el contenido principal del artículo.

EJEMPLOS DE SALIDA CORRECTA:
{few_shots}

ARTÍCULO:
{texto}
"""


_client = None


def _get_client() -> "genai.Client":
    """Devuelve el cliente del SDK, creándolo una sola vez.

    El SDK anterior (google.generativeai) está descontinuado y sin
    mantenimiento; se migró a google-genai (C-11).
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


def _usage(resp) -> dict:
    """Extrae el consumo de tokens de la respuesta.

    El SDK nuevo lo expone de forma directa; esto habilita poblar
    run.tokens_in / tokens_out y costo_estimado, que hoy quedan en cero (S-04).
    """
    um = getattr(resp, "usage_metadata", None)
    if um is None:
        return {"tokens_in": 0, "tokens_out": 0, "tokens_total": 0}
    return {
        "tokens_in": int(getattr(um, "prompt_token_count", 0) or 0),
        "tokens_out": int(getattr(um, "candidates_token_count", 0) or 0),
        "tokens_total": int(getattr(um, "total_token_count", 0) or 0),
    }


def _resp_text(resp) -> str:
    """Lectura robusta del texto de la respuesta."""
    txt = getattr(resp, "text", None)
    if txt:
        return txt
    for cand in (getattr(resp, "candidates", None) or []):
        content = getattr(cand, "content", None)
        for part in (getattr(content, "parts", None) or []):
            if getattr(part, "text", None):
                return part.text
    return ""

# Heurística mínima para corregir sesgo evidente en 'tipo_brecha'. Las frases
# genéricas "experimento" y "validación" no bastan para declarar una brecha
# metodológica: también pueden describir falta de evidencia empírica.
def _rebalance_tipo(brecha_text: str, tipo_modelo: str) -> str:
    t = (brecha_text or "").lower()
    palabras = {
        "metodológica": (
            "método", "metodo", "metodología", "muestreo", "protocolo",
            "validez", "reproducibilidad", "precision", "recall", "f1",
            "diseño experimental", "validación cruzada",
        ),
        "temática": (
            "tema", "temática", "dominio", "contexto", "caso", "población",
            "industria", "sector", "latinoamérica", "latinoamerica",
            "educación", "salud", "agro", "smart city", "dataset específico",
        ),
        "teórica": (
            "teoría", "teorico", "marco conceptual", "modelo conceptual",
            "constructo", "hipótesis", "hipotesis",
        ),
        "tecnológica": (
            "herramienta", "plataforma", "sistema", "arquitectura",
            "implementación", "rendimiento", "escalabilidad", "latencia",
        ),
        "empírica": (
            "evidencia empírica", "evidencia experimental", "datos insuficientes",
            "escasez de datos", "muestra pequeña", "muestra limitada",
            "pocos casos", "replicación externa", "replicaciones externas",
            "validación externa", "cohorte independiente",
            "cohortes independientes", "datos externos",
        ),
        "aplicada": (
            "transferencia", "adopción", "usabilidad", "viabilidad económica",
            "viabilidad práctica", "condiciones reales", "entorno real",
            "obra real", "aplicación práctica", "implementación práctica",
            "piloto de campo", "barreras operativas", "barreras regulatorias",
        ),
    }

    score = {
        tipo: sum(1 for palabra in candidatas if palabra in t)
        for tipo, candidatas in palabras.items()
    }

    best_tipo = max(score, key=score.get)
    if score[best_tipo] > score.get(tipo_modelo, 0):
        return best_tipo
    return tipo_modelo if tipo_modelo in TIPOS_BRECHA else "otra"

def analyze(texto: str, contexto: dict, context_docs: list[str] | None = None) -> dict:
    # --- MODO SIMULADO ---
    if MODE != "real":
        demo = FEW_SHOTS[0]
        # resumen simulado: primeras 120 palabras del texto
        resumen_mock = " ".join((texto or "").split()[:120]) or demo["brecha"]
        return {
            "brecha": demo["brecha"],
            "oportunidad": demo["oportunidad"],
            "tipo_brecha": demo["tipo_brecha"],
            "tipo_modelo": demo["tipo_brecha"],
            "resumen": resumen_mock,
            "_usage": {"tokens_in": 0, "tokens_out": 0, "tokens_total": 0},
        }

    # --- MODO REAL ---
    client = _get_client()

    bloque_rag = _mk_rag_block(context_docs)
    few_shots_json = json.dumps(FEW_SHOTS, ensure_ascii=False, indent=2)

    prompt = USER_TMPL.format(
        tema_principal=contexto.get("tema_principal", ""),
        metodologia_txt=contexto.get("metodologia_txt", ""),
        sector_txt=contexto.get("sector_txt", ""),
        objetivo=contexto.get("objetivo", ""),
        bloque_rag=bloque_rag,
        tipos_brecha=tipos_para_prompt(),
        few_shots=few_shots_json,
        texto=texto[:120_000]
    )

    limitador_generacion.adquirir(1)

    def _llamar():
        # Se anota cada intento, no solo el resultado final: una llamada que
        # falla con 429 tambien ha consumido cuota, y no contarla hacia que
        # el indicador se quedara corto justo cuando mas importa.
        try:
            r = client.models.generate_content(
                model=CHAT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYS_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
        except Exception as exc:
            anotar(OP_ANALISIS, modelo=CHAT_MODEL, exito=False, motivo=str(exc))
            raise
        u = _usage(r)
        anotar(OP_ANALISIS, modelo=CHAT_MODEL, exito=True,
               tokens_in=u["tokens_in"], tokens_out=u["tokens_out"])
        return r

    resp = con_reintentos(_llamar, descripcion="analyze")

    raw_text = _resp_text(resp)
    if not raw_text.strip():
        raise RuntimeError("Gemini devolvió respuesta vacía.")

    # --- Parseo robusto: permite lista o dict ---
    try:
        data = json.loads(raw_text)
        if isinstance(data, list):
            # si devuelve lista, toma el primer dict válido
            data = next((x for x in data if isinstance(x, dict)), {})

        if not isinstance(data, dict):
            raise ValueError("No es un objeto JSON válido")

        br = (data.get("brecha") or "").strip()
        op = (data.get("oportunidad") or "").strip()
        tipo = (data.get("tipo_brecha") or "otra").strip()
        resumen = (data.get("resumen") or "").strip()


        if len(br) < 20 or len(op) < 20 or len(resumen) < 40:
            raise ValueError("Salida incompleta")


        if tipo not in TIPOS_BRECHA:
            tipo = "otra"

        # Se conserva lo que dijo el modelo antes de que el reclasificador por
        # palabras clave intervenga. Sin ese dato no hay forma de saber cuantas
        # veces lo sobrescribe, y conservarlo sin medirlo es una suposicion
        # (N5.2).
        tipo_modelo = tipo
        tipo = _rebalance_tipo(br, tipo)
        return {
            "brecha": br,
            "oportunidad": op,
            "tipo_brecha": tipo,
            "tipo_modelo": tipo_modelo,
            "resumen": resumen,
            "_usage": _usage(resp),
        }


    except Exception as e:
        raise RuntimeError(f"Respuesta no válida de Gemini: {e}")

# Síntesis del estado del arte
def synthesize_estado_arte(brechas: list[dict], contexto: dict) -> str:
    if MODE != "real":
        bullets = "\n".join([f"- ({b.get('tipo_brecha','otra')}) {b.get('brecha','')}" for b in brechas][:10])
        return (
            f"Estado del arte preliminar sobre {contexto.get('tema_principal','')}\n\n"
            f"Metodología: {contexto.get('metodologia_txt','')}, Sector: {contexto.get('sector_txt','')}\n\n"
            f"Síntesis de brechas:\n{bullets}\n\n"
            "Líneas futuras: estandarizar métricas, replicación y estudios longitudinales."
        )

    client = _get_client()
    items = []
    for b in brechas[:50]:
        items.append(
            f"- Título: {b.get('articulo_titulo','(s/t)')}\n"
            f"  Tipo: {b.get('tipo_brecha','otra')}\n"
            f"  Brecha: {b.get('brecha','')}\n"
            f"  Oportunidad: {b.get('oportunidad','')}"
        )
    brechas_txt = "\n".join(items)

    prompt = f"""
Contexto del proyecto
- Tema: {contexto.get('tema_principal','')}
- Metodología: {contexto.get('metodologia_txt','')}
- Sector: {contexto.get('sector_txt','')}
- Objetivo: {contexto.get('objetivo','')}

Usa las brechas detectadas para redactar un ESTADO DEL ARTE claro y cohesionado (2–5 párrafos),
con panorama general, tendencias, vacíos y líneas futuras. No inventes citas ni bibliografía.

BRECHAS:
{brechas_txt}
"""

    limitador_generacion.adquirir(1)

    def _llamar():
        try:
            r = client.models.generate_content(
                model=CHAT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="Redacta un estado del arte a partir de las brechas detectadas.",
                    temperature=0.2,
                ),
            )
        except Exception as exc:
            anotar(OP_SINTESIS, modelo=CHAT_MODEL, exito=False, motivo=str(exc))
            raise
        u = _usage(r)
        anotar(OP_SINTESIS, modelo=CHAT_MODEL, exito=True,
               tokens_in=u["tokens_in"], tokens_out=u["tokens_out"])
        return r

    resp = con_reintentos(_llamar, descripcion="synthesize_estado_arte")

    text = _resp_text(resp)
    if not text.strip():
        raise RuntimeError("Gemini devolvió respuesta vacía al sintetizar estado del arte.")
    return text.strip()
