# app/routers/verificacion_rt.py
"""
Verificación de fidelidad sobre brechas ya analizadas.

Un proyecto analizado antes de que existiera el nivel N2 tiene sus brechas
guardadas pero sin verificar, y volver a analizarlo entero para obtenerla
costaría el doble de generaciones y ademas sustituiría unos resultados que
estaban bien.

Los fragmentos que sustentaron cada brecha quedaron registrados en su momento,
asi que la verificación puede hacerse sobre lo ya existente: una llamada por
brecha en lugar de dos.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.articulo import Articulo
from app.models.embedding_doc import EmbeddingDoc
from app.models.metrica import Metrica, AMBITO_BRECHA
from app.models.proyecto import Proyecto
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run import Run
from app.models.run_item import RunItem
from app.services.verificacion import verificar

router = APIRouter(prefix="/proyectos", tags=["verificacion"])


def _fragmentos_de(db: Session, rb: ResultadoBrecha) -> list[dict]:
    """Reconstruye los fragmentos que se usaron al generar la brecha.

    rag_hits guarda los identificadores y la seccion, no el texto, para no
    duplicar contenido; el texto se recupera de embedding_doc.
    """
    hits = rb.rag_hits if isinstance(rb.rag_hits, list) else []
    ids = [h.get("embedding_id") for h in hits
           if isinstance(h, dict) and h.get("embedding_id")]
    if not ids:
        return []
    filas = db.query(EmbeddingDoc).filter(EmbeddingDoc.id.in_(ids)).all()
    por_id = {f.id: f for f in filas}
    # Se respeta el orden original: es el que vio el modelo al redactar.
    salida = []
    for h in hits:
        f = por_id.get(h.get("embedding_id"))
        if f:
            salida.append({"texto": f.texto, "seccion": f.seccion or "otro"})
    return salida


@router.post("/{proyecto_id}/verificar")
def verificar_proyecto(proyecto_id: str, rehacer: bool = False,
                       db: Session = Depends(get_db)):
    """Verifica la fidelidad de las brechas del último análisis.

    Con `rehacer=false` (lo habitual) solo se verifican las que aun no lo
    estan, de modo que reintentar tras un fallo a mitad no vuelve a pagar por
    las ya hechas.
    """
    pr = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    run = (db.query(Run).filter(Run.proyecto_id == proyecto_id)
           .order_by(Run.iniciado_en.desc(), Run.id).first())
    if not run:
        raise HTTPException(status_code=400, detail="El proyecto no se ha analizado.")

    filas = (db.query(ResultadoBrecha, Articulo)
             .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
             .join(Articulo, Articulo.id == RunItem.articulo_id)
             .filter(RunItem.run_id == run.id).all())
    if not filas:
        raise HTTPException(status_code=400, detail="El análisis no dejó brechas.")

    ya_hechas = {m.referencia_id for m in
                 db.query(Metrica)
                 .filter(Metrica.proyecto_id == proyecto_id,
                         Metrica.codigo == "N2.verificada",
                         Metrica.valor == 1.0).all()}

    resultados = []
    verificadas = 0
    for rb, art in filas:
        if rb.id in ya_hechas and not rehacer:
            resultados.append({"articulo": art.titulo, "estado": "ya verificada"})
            continue

        fragmentos = _fragmentos_de(db, rb)
        if not fragmentos:
            resultados.append({
                "articulo": art.titulo,
                "estado": "sin fragmentos registrados",
            })
            continue

        v = verificar(rb.brecha or "", fragmentos)

        # Se descartan siempre las mediciones previas de esta brecha, no solo
        # al rehacer. Acumularlas dejaba varias filas del mismo codigo y quien
        # las leyera tenia que adivinar cual vale.
        (db.query(Metrica)
         .filter(Metrica.referencia_id == rb.id,
                 Metrica.codigo.in_(["N2.1", "N2.2", "N2.4", "N2.verificada"]))
         .delete(synchronize_session=False))

        def _add(codigo, valor, detalle=None):
            db.add(Metrica(id=str(uuid.uuid4()), proyecto_id=proyecto_id,
                           ambito=AMBITO_BRECHA, referencia_id=rb.id,
                           codigo=codigo, valor=valor, detalle=detalle))

        if v.disponible:
            _add("N2.1", v.fidelidad,
                 {"sin_respaldo": [a.texto for a in v.evidenciales
                                   if not a.respaldada][:10]})
            _add("N2.2", v.trazabilidad)
            _add("N2.4", v.equilibrio_evidencial)
            verificadas += 1
        _add("N2.verificada", 1.0 if v.disponible else 0.0, v.resumen())
        db.commit()

        resultados.append({
            "articulo": art.titulo,
            "estado": "verificada" if v.disponible else "no verificada",
            "motivo": None if v.disponible else v.motivo,
            "fidelidad": v.fidelidad if v.disponible else None,
            "sin_respaldo": (sum(1 for a in v.evidenciales if not a.respaldada)
                             if v.disponible else None),
        })

    return {
        "run_id": run.id,
        "brechas": len(filas),
        "verificadas": verificadas,
        "detalle": resultados,
    }
