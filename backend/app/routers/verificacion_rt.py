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
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencias import proyecto_propio
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
    """Los fragmentos que sustentaron la brecha, con sus trozos vecinos.

    rag_hits guarda los identificadores y la seccion, no el texto, para no
    duplicar contenido; el texto se recupera de embedding_doc.

    Se añaden los trozos contiguos (`chunk_orden ± 1`) por un motivo medido.
    El troceado corta a mitad de frase, y sobre datos reales se llevó justo la
    parte que decidía el sentido de una afirmación: el fragmento entregado
    empezaba por «, particularly for MLPs, as it neglects material hardening…»
    y el trozo anterior —no entregado— terminaba con «the DNV formula
    underestimates the load-bearing capacity». Sin esas cinco palabras, la
    brecha podía hablar de «diseños inseguros» sin que nada la desmintiera,
    cuando el artículo dice lo contrario: subestimar la capacidad es ser
    conservador, es decir, más seguro.

    Con la ventana estrecha el verificador no se equivocaba, no podía acertar.
    Ampliarla no cuesta ninguna llamada: los embeddings ya están guardados y
    solo se recuperan más filas de la misma tabla.
    """
    hits = rb.rag_hits if isinstance(rb.rag_hits, list) else []
    ids = [h.get("embedding_id") for h in hits
           if isinstance(h, dict) and h.get("embedding_id")]
    if not ids:
        return []
    filas = db.query(EmbeddingDoc).filter(EmbeddingDoc.id.in_(ids)).all()
    if not filas:
        return []

    # Los trozos buscados, por artículo: cada recuperado y sus dos contiguos.
    por_articulo: dict[str, set[int]] = {}
    for f in filas:
        if f.chunk_orden is None:
            continue
        ordenes = por_articulo.setdefault(f.articulo_id, set())
        ordenes.update((f.chunk_orden - 1, f.chunk_orden, f.chunk_orden + 1))

    if not por_articulo:
        return [{"texto": f.texto, "seccion": f.seccion or "otro"} for f in filas]

    condiciones = [
        and_(EmbeddingDoc.articulo_id == aid,
             EmbeddingDoc.chunk_orden.in_(sorted(ordenes)))
        for aid, ordenes in por_articulo.items()
    ]
    # En orden de documento y no en el de recuperación: los vecinos solo sirven
    # para reconstruir la frase partida si van pegados a su fragmento. Numerarlos
    # por relevancia los separaría otra vez.
    ampliados = (db.query(EmbeddingDoc)
                 .filter(or_(*condiciones))
                 .order_by(EmbeddingDoc.articulo_id, EmbeddingDoc.chunk_orden)
                 .all())
    return [{"texto": f.texto, "seccion": f.seccion or "otro"}
            for f in ampliados]


@router.post("/{proyecto_id}/verificar")
def verificar_proyecto(rehacer: bool = False,
                       proyecto: Proyecto = Depends(proyecto_propio),
                       db: Session = Depends(get_db)):
    """Verifica la fidelidad de las brechas del último análisis.

    Con `rehacer=false` (lo habitual) solo se verifican las que aun no lo
    estan, de modo que reintentar tras un fallo a mitad no vuelve a pagar por
    las ya hechas.
    """
    proyecto_id = proyecto.id

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
                 Metrica.codigo.in_(["N2.1", "N2.2", "N2.4", "N2.5",
                                     "N2.verificada"]))
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
            # El detalle guarda la frase y la cita que la desmiente, no solo el
            # número: una contradicción sin la prueba al lado no se puede
            # revisar, y es justo la medición que más falta hace poder revisar.
            _add("N2.5", v.tasa_contradiccion,
                 {"contradicciones": [
                     {"afirmacion": a.texto,
                      "fragmento": a.fragmento_contrario,
                      "cita": a.cita_contraria,
                      "tipo": a.tipo}
                     for a in v.contradictorias][:10]})
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
            "contradicciones": (len(v.contradictorias) if v.disponible else None),
        })

    return {
        "run_id": run.id,
        "brechas": len(filas),
        "verificadas": verificadas,
        "detalle": resultados,
    }
