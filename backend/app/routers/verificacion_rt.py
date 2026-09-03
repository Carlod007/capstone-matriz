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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencias import (
    comprobar_cuota_usuario,
    proyecto_propio,
    usuario_actual,
)
from app.models.usuario import Usuario
from app.models.articulo import Articulo
from app.models.metrica import Metrica, AMBITO_BRECHA
from app.models.proyecto import Proyecto
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run import Run
from app.models.run_item import RunItem
from app.services.ventana_evidencia import fragmentos_de_brecha
from app.services.verificacion import verificar
from app.services.registro_metricas import registrar_metrica

router = APIRouter(prefix="/proyectos", tags=["verificacion"])


CODIGOS_N2_COMPLETOS = {"N2.1", "N2.2", "N2.4", "N2.5", "N2.6", "N2.verificada"}


def _brechas_verificadas_completas(db: Session, proyecto_id: str) -> set[str]:
    """Brechas cuya verificacion disponible conserva todos sus resultados."""
    filas = (db.query(Metrica.referencia_id, Metrica.codigo, Metrica.valor)
             .filter(Metrica.proyecto_id == proyecto_id,
                     Metrica.codigo.in_(CODIGOS_N2_COMPLETOS))
             .all())
    por_brecha: dict[str, set[str]] = {}
    disponibles: set[str] = set()
    for referencia_id, codigo, valor in filas:
        por_brecha.setdefault(referencia_id, set()).add(codigo)
        if codigo == "N2.verificada" and valor == 1.0:
            disponibles.add(referencia_id)
    return {referencia_id for referencia_id in disponibles
            if CODIGOS_N2_COMPLETOS <= por_brecha.get(referencia_id, set())}


@router.post("/{proyecto_id}/verificar")
def verificar_proyecto(rehacer: bool = False,
                       proyecto: Proyecto = Depends(proyecto_propio),
                       usuario: Usuario = Depends(usuario_actual),
                       db: Session = Depends(get_db)):
    """Verifica la fidelidad de las brechas del último análisis.

    Con `rehacer=false` (lo habitual) solo se verifican las que aun no lo
    estan, de modo que reintentar tras un fallo a mitad no vuelve a pagar por
    las ya hechas.
    """
    comprobar_cuota_usuario(usuario)

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

    ya_hechas = _brechas_verificadas_completas(db, proyecto_id)

    resultados = []
    verificadas = 0
    for rb, art in filas:
        if rb.id in ya_hechas and not rehacer:
            resultados.append({"articulo": art.titulo, "estado": "ya verificada"})
            continue

        fragmentos = fragmentos_de_brecha(db, rb)
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
                 Metrica.codigo.in_(["N2.1", "N2.2", "N2.4", "N2.5", "N2.6",
                                     "N2.verificada"]))
         .delete(synchronize_session=False))

        def _add(codigo, valor, detalle=None):
            registrar_metrica(
                db, proyecto_id, AMBITO_BRECHA, rb.id,
                codigo, valor, detalle,
            )

        if v.disponible:
            _add("N2.1", v.fidelidad,
                 {"sin_respaldo": [a.texto for a in v.evidenciales_autonomas
                                   if not a.respaldada][:10]})
            _add("N2.2", v.trazabilidad, v.detalle_trazabilidad())
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
            # La cita se guarda con el valor: decir que una brecha ya está
            # resuelta la invalida entera, y eso hay que poder revisarlo.
            _add("N2.6", 1.0 if v.ya_resuelta else 0.0,
                 {"fragmento": v.fragmento_resuelta, "cita": v.cita_resuelta})
            verificadas += 1
        _add("N2.verificada", 1.0 if v.disponible else 0.0, v.resumen())
        db.commit()

        resultados.append({
            "articulo": art.titulo,
            "estado": "verificada" if v.disponible else "no verificada",
            "motivo": None if v.disponible else v.motivo,
            "fidelidad": v.fidelidad if v.disponible else None,
            "sin_respaldo": (sum(1 for a in v.evidenciales_autonomas
                                  if not a.respaldada)
                             if v.disponible else None),
            "contradicciones": (len(v.contradictorias) if v.disponible else None),
        })

    return {
        "run_id": run.id,
        "brechas": len(filas),
        "verificadas": verificadas,
        "detalle": resultados,
    }
