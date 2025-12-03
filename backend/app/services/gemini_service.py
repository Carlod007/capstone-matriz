# app/services/gemini_service.py
import os, json
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()

MODE = os.getenv("GEMINI_MODE", "mock").lower()
API_KEY = os.getenv("GEMINI_API_KEY", "")

# Prompt del sistema: salida estrictamente en JSON y regla clara de tipificación
SYS_PROMPT = (
    "Eres un asistente para análisis bibliográfico. "
    "Devuelve SOLO JSON válido con campos EXACTOS: brecha, oportunidad, tipo_brecha, resumen. "
    "Tipos válidos: metodológica, temática, teórica, tecnológica, otra. "
    "Selecciona el tipo por el foco predominante del problema, NO por mención superficial de 'método'. "
    "Criterio rápido:\n"
    "- metodológica: fallas de diseño/medición/protocolo/muestreo/reproducibilidad/validación.\n"
    "- temática: el tema/caso/población/ámbito está poco cubierto o mal delimitado.\n"
    "- teórica: faltan marcos conceptuales/modelos/constructos/hipótesis.\n"
    "- tecnológica: carencia de herramientas/sistemas/arquitecturas/implementación o performance.\n"
    "- otra: si ninguna aplica.\n"
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
    }
]

def _mk_rag_block(context_docs: list[str] | None, max_total_chars: int = 12000, per_doc_limit: int = 1500) -> str:
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
- tipo_brecha: una de [metodológica, temática, teórica, tecnológica, otra].
- resumen: párrafo de 5 a 8 líneas que sintetice el contenido principal del artículo.

EJEMPLOS DE SALIDA CORRECTA:
{few_shots}

ARTÍCULO:
{texto}
"""


def _ensure_api():
    if MODE == "real" and not API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en .env")
    if MODE == "real":
        genai.configure(api_key=API_KEY)

# Heurística mínima para corregir sesgo evidente en 'tipo_brecha'
def _rebalance_tipo(brecha_text: str, tipo_modelo: str) -> str:
    t = (brecha_text or "").lower()
    kw_met = ("método","metodo","metodología","muestreo","protocolo","validez","reproducibilidad",
              "precision","recall","f1","experimento","diseño experimental","validación")
    kw_tem = ("tema","temática","dominio","contexto","caso","población","industria","sector",
              "latinoamérica","latinoamerica","educación","salud","agro","smart city","dataset específico")
    kw_teo = ("teoría","teorico","marco conceptual","modelo conceptual","constructo","hipótesis","hipotesis")
    kw_tec = ("herramienta","plataforma","sistema","arquitectura","implementación","rendimiento","escalabilidad","latencia")

    score = {"metodológica":0, "temática":0, "teórica":0, "tecnológica":0}
    for w in kw_met:
        if w in t: score["metodológica"] += 1
    for w in kw_tem:
        if w in t: score["temática"] += 1
    for w in kw_teo:
        if w in t: score["teórica"] += 1
    for w in kw_tec:
        if w in t: score["tecnológica"] += 1

    best_tipo = max(score, key=score.get)
    if score[best_tipo] > score.get(tipo_modelo, 0):
        return best_tipo
    return tipo_modelo if tipo_modelo in score or tipo_modelo=="otra" else "otra"

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
            "resumen": resumen_mock,
        }

    # --- MODO REAL ---
    _ensure_api()
    model = genai.GenerativeModel("models/gemini-2.5-flash")

    bloque_rag = _mk_rag_block(context_docs)
    few_shots_json = json.dumps(FEW_SHOTS, ensure_ascii=False, indent=2)

    prompt = USER_TMPL.format(
        tema_principal=contexto.get("tema_principal", ""),
        metodologia_txt=contexto.get("metodologia_txt", ""),
        sector_txt=contexto.get("sector_txt", ""),
        objetivo=contexto.get("objetivo", ""),
        bloque_rag=bloque_rag,
        few_shots=few_shots_json,
        texto=texto[:120_000]
    )

    resp = model.generate_content(
        [
            {"role": "user", "parts": [SYS_PROMPT]},
            {"role": "user", "parts": [prompt]},
        ],
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    )

    # --- Lectura robusta de respuesta ---
    if hasattr(resp, "text") and resp.text:
        raw_text = resp.text
    else:
        raw_text = ""
        if hasattr(resp, "candidates") and resp.candidates:
            parts = resp.candidates[0].content.parts
            if parts and hasattr(parts[0], "text"):
                raw_text = parts[0].text

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


        if tipo not in {"metodológica", "temática", "teórica", "tecnológica", "otra"}:
            tipo = "otra"

        tipo = _rebalance_tipo(br, tipo)
        return {
            "brecha": br,
            "oportunidad": op,
            "tipo_brecha": tipo,
            "resumen": resumen,
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

    _ensure_api()
    model = genai.GenerativeModel("models/gemini-2.5-flash")
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

    resp = model.generate_content(
        [{"role": "user", "parts": ["Redacta estado del arte a partir de brechas."]},
         {"role": "user", "parts": [prompt]}],
        generation_config={"temperature": 0.2}
    )

    if hasattr(resp, "text") and resp.text:
        text = resp.text
    else:
        text = ""
        if getattr(resp, "candidates", None):
            parts = resp.candidates[0].content.parts
            if parts and hasattr(parts[0], "text"):
                text = parts[0].text

    if not text.strip():
        raise RuntimeError("Gemini devolvió respuesta vacía al sintetizar estado del arte.")
    return text.strip()
