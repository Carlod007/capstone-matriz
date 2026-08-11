# app/services/registro_api.py
"""
Anotacion de las llamadas al modelo.

Usa su propia sesion de base de datos, corta y aislada: el registro se hace
desde los servicios, que no reciben la sesion del endpoint, y debe poder
anotar una llamada fallida sin verse arrastrado por la transaccion que se
esta deshaciendo a causa de ese mismo fallo.

Registrar nunca debe romper el analisis. Si la anotacion falla se descarta en
silencio: perder una linea del contador es preferible a perder el trabajo.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

from app.models.llamada_api import (  # noqa: F401
    OP_ANALISIS, OP_EMBEDDING, OP_OTRA, OP_SINTESIS, LlamadaAPI,
)

# Solo las generaciones consumen la cuota diaria; los embeddings tienen la
# suya propia, limitada por minuto.
OPERACIONES_DE_GENERACION = (OP_ANALISIS, OP_SINTESIS)

REGISTRO_ACTIVO = os.getenv("REGISTRAR_LLAMADAS", "1") not in ("0", "false", "False")


def anotar(operacion: str, *, modelo: str | None = None, exito: bool = True,
           unidades: int = 1, motivo: str | None = None,
           tokens_in: int = 0, tokens_out: int = 0,
           proyecto_id: str | None = None) -> None:
    """Registra un intento de llamada. Nunca lanza excepcion."""
    if not REGISTRO_ACTIVO:
        return
    try:
        from app.database import SessionLocal

        s = SessionLocal()
        try:
            s.add(LlamadaAPI(
                id=str(uuid.uuid4()),
                proyecto_id=proyecto_id,
                operacion=operacion,
                modelo=modelo,
                unidades=max(1, int(unidades)),
                exito=bool(exito),
                motivo=(motivo or "")[:2000] or None,
                tokens_in=int(tokens_in or 0),
                tokens_out=int(tokens_out or 0),
            ))
            s.commit()
        finally:
            s.close()
    except Exception:
        # Deliberado: el contador es informativo, el analisis no.
        pass


def consumo(horas: int = 24) -> dict:
    """Consumo real registrado en la ventana indicada."""
    from app.database import SessionLocal
    from sqlalchemy import func as F

    desde = datetime.utcnow() - timedelta(hours=horas)
    s = SessionLocal()
    try:
        filas = (s.query(LlamadaAPI.operacion, LlamadaAPI.exito,
                         F.count(LlamadaAPI.id), F.sum(LlamadaAPI.unidades))
                 .filter(LlamadaAPI.creado_en >= desde)
                 .group_by(LlamadaAPI.operacion, LlamadaAPI.exito).all())
    except Exception:
        return {"disponible": False, "generaciones": 0, "fallidas": 0,
                "embeddings": 0}
    finally:
        s.close()

    generaciones = fallidas = embeddings = 0
    for operacion, exito, n, unidades in filas:
        n = int(n or 0)
        unidades = int(unidades or 0)
        if operacion in OPERACIONES_DE_GENERACION:
            generaciones += n
            if not exito:
                fallidas += n
        elif operacion == OP_EMBEDDING:
            embeddings += unidades
    return {
        "disponible": True,
        "generaciones": generaciones,
        "fallidas": fallidas,
        "embeddings": embeddings,
    }
