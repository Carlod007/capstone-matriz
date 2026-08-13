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
    OP_ANALISIS, OP_EMBEDDING, OP_OTRA, OP_SINTESIS, OP_VERIFICACION, LlamadaAPI,
)

# Estas operaciones consumen la cuota diaria de generacion. Los embeddings
# usan otro modelo y tienen cuota propia, contada aparte.
OPERACIONES_DE_GENERACION = (OP_ANALISIS, OP_SINTESIS, OP_VERIFICACION)

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


def corte(horas: int = 24):
    """Inicio de la ventana, calculado con el reloj de la base de datos.

    Las marcas de tiempo se escriben con CURRENT_TIMESTAMP, es decir en la
    hora local del servidor. Compararlas contra `datetime.utcnow()` introduce
    el desfase del huso: con cinco horas de diferencia, los registros salian
    de la ventana cinco horas antes de tiempo y el contador de consumo caia a
    cero teniendo cuota gastada. Usar el mismo reloj en ambos lados elimina el
    problema sin depender de como este configurado el servidor.
    """
    from sqlalchemy import func as F, text

    return F.date_sub(F.now(), text("INTERVAL %d HOUR" % int(horas)))


def _ahora_bd(s) -> datetime | None:
    """Hora del servidor de base de datos.

    Se devuelve al cliente para que descuente el tiempo contra este reloj y
    no contra el del navegador, que puede ir desfasado.
    """
    from sqlalchemy import func as F, select

    try:
        return s.execute(select(F.now())).scalar()
    except Exception:
        return None


def renovaciones(horas: int = 24, limite: int = 40) -> dict:
    """Cuándo vuelve a haber margen, según la ventana móvil.

    Cada llamada deja de contar exactamente `horas` después de haberse hecho,
    así que el momento en que se recupera margen es calculable con precisión a
    partir de las marcas guardadas.

    Es un dato exacto sobre *nuestra* ventana. No equivale necesariamente al
    reinicio del proveedor, que aplica su propio criterio y no lo publica en
    la respuesta de error: eso se advierte aparte en lugar de presentarlo como
    si fuera lo mismo.
    """
    from app.database import SessionLocal

    s = SessionLocal()
    try:
        ahora = _ahora_bd(s)
        filas = (s.query(LlamadaAPI.creado_en)
                 .filter(LlamadaAPI.creado_en >= corte(horas),
                         LlamadaAPI.operacion.in_(OPERACIONES_DE_GENERACION))
                 .order_by(LlamadaAPI.creado_en.asc())
                 .limit(limite).all())
        marcas = [f[0] for f in filas if f[0] is not None]
    except Exception:
        return {"disponible": False, "ahora": None, "eventos": []}
    finally:
        s.close()

    if ahora is None:
        return {"disponible": False, "ahora": None, "eventos": []}

    eventos = []
    acumulado = 0
    for m in marcas:
        vence = m + timedelta(hours=horas)
        acumulado += 1
        eventos.append({
            "momento": vence.isoformat(),
            "segundos": max(0, int((vence - ahora).total_seconds())),
            "recupera": 1,
            "acumulado": acumulado,
        })
    return {"disponible": True, "ahora": ahora.isoformat(), "eventos": eventos}


def consumo(horas: int = 24) -> dict:
    """Consumo real registrado en la ventana indicada."""
    from app.database import SessionLocal
    from sqlalchemy import func as F

    s = SessionLocal()
    try:
        filas = (s.query(LlamadaAPI.operacion, LlamadaAPI.exito,
                         F.count(LlamadaAPI.id), F.sum(LlamadaAPI.unidades))
                 .filter(LlamadaAPI.creado_en >= corte(horas))
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
