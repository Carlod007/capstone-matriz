"""Procedencia reproducible de una ejecucion del pipeline.

La fotografia se toma al crear el run. No consulta Git ni archivos externos:
en una imagen Docker esos elementos pueden no existir. La revision de codigo
la inyecta el despliegue mediante ``APP_REVISION``; si falta se conserva como
desconocida en vez de adivinarla.
"""

from __future__ import annotations

import os


ESQUEMA_PROCEDENCIA = 1
VERSION_PIPELINE = 1


def capturar_procedencia() -> dict:
    """Devuelve una fotografia JSON de los componentes que afectan el resultado."""
    # Imports locales: evitan que cargar modelos abra o configure clientes de
    # Gemini antes de que la aplicacion realmente los necesite.
    from app.services.embedding_service import (
        CHUNK_CHARS,
        CHUNK_OVERLAP,
        EMBED_DIM,
        EMBED_MODEL,
        RECUPERACION_LAMBDA_DIVERSIDAD,
        RECUPERACION_MIN_SUSTANTIVOS,
        RECUPERACION_TOP_K,
    )
    from app.services.gemini_service import (
        CHAT_MODEL,
        PROMPT_ANALISIS_VERSION,
        PROMPT_SINTESIS_VERSION,
        RAG_MAX_TOTAL_CHARS,
        RAG_PER_DOC_LIMIT,
    )
    from app.services.verificacion import PROMPT_VERIFICACION_VERSION

    revision = (os.getenv("APP_REVISION") or "").strip() or None
    return {
        "esquema": ESQUEMA_PROCEDENCIA,
        "pipeline": VERSION_PIPELINE,
        "revision_codigo": revision,
        "modelos": {
            "generacion": CHAT_MODEL,
            "embedding": EMBED_MODEL,
            "embedding_dimensiones": EMBED_DIM,
        },
        "prompts": {
            "analisis": PROMPT_ANALISIS_VERSION,
            "sintesis": PROMPT_SINTESIS_VERSION,
            "verificacion": PROMPT_VERIFICACION_VERSION,
        },
        "fragmentacion": {
            "caracteres": CHUNK_CHARS,
            "solapamiento": CHUNK_OVERLAP,
        },
        "recuperacion": {
            "top_k": RECUPERACION_TOP_K,
            "lambda_diversidad": RECUPERACION_LAMBDA_DIVERSIDAD,
            "min_fragmentos_sustantivos": RECUPERACION_MIN_SUSTANTIVOS,
            "max_caracteres_prompt": RAG_MAX_TOTAL_CHARS,
            "max_caracteres_fragmento": RAG_PER_DOC_LIMIT,
        },
    }


def resumen_procedencia(procedencia: dict | None) -> str:
    """Resumen estable para informes legibles por personas."""
    if not procedencia:
        return "procedencia no registrada (resultado anterior al versionado)"
    modelos = procedencia.get("modelos") or {}
    prompts = procedencia.get("prompts") or {}
    return (
        "pipeline v%s; revisión %s; generación %s; embedding %s; "
        "prompts análisis/síntesis/verificación v%s/v%s/v%s"
        % (
            procedencia.get("pipeline", "?"),
            procedencia.get("revision_codigo") or "desconocida",
            modelos.get("generacion", "?"),
            modelos.get("embedding", "?"),
            prompts.get("analisis", "?"),
            prompts.get("sintesis", "?"),
            prompts.get("verificacion", "?"),
        )
    )
