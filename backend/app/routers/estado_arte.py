import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.dependencias import proyecto_propio
from app.models.proyecto import Proyecto
from app.models.run import Run, EstadoRun
from app.models.run_item import RunItem
from app.models.resultado_brecha import ResultadoBrecha
from app.models.estado_arte import EstadoDelArte
from app.models.articulo import Articulo
from app.services.gemini_service import synthesize_estado_arte
from app.services.metricas import sintesis as S
from app.services.registro_metricas import registrar_metrica

router = APIRouter(prefix="/proyectos", tags=["estado_arte"])

@router.post("/{proyecto_id}/estado_arte")
def generar_estado_arte(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    proyecto_id = proyecto.id
    # 1) Proyecto
    pr = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    # 2) Último RUN COMPLETADO del proyecto
    run = (
        db.query(Run)
        .filter(Run.proyecto_id == proyecto_id, Run.estado == EstadoRun.completado)
        .order_by(Run.finalizado_en.desc())
        .first()
    )
    if not run:
        raise HTTPException(status_code=400, detail="No hay runs completados para sintetizar estado del arte")

    # 3) Brechas SOLO de ese run
    # `.select()` explícito sobre la subconsulta: pasarle el objeto crudo a
    # `in_()` está en desuso desde SQLAlchemy 1.4 y dejará de funcionar. Hoy
    # solo emite un aviso, así que el fallo llegaría el día de una
    # actualización rutinaria de dependencias, lejos de esta línea.
    sub_items = db.query(RunItem.id).filter(RunItem.run_id == run.id).subquery()
    brechas_rows = (
        db.query(ResultadoBrecha)
        .filter(ResultadoBrecha.run_item_id.in_(sub_items.select()))
        .order_by(ResultadoBrecha.created_at.asc())
        .all()
    )
    if not brechas_rows:
        raise HTTPException(status_code=400, detail="El run completado no tiene brechas registradas")

    brechas_payload = [
        {
            "tipo_brecha": r.tipo_brecha,
            "brecha": r.brecha,
            "oportunidad": r.oportunidad,
            "articulo_titulo": None,
        }
        for r in brechas_rows
    ]

    contexto = {
        "tema_principal": pr.tema_principal,
        "metodologia_txt": pr.metodologia_txt,
        "sector_txt": pr.sector_txt,
        "objetivo": pr.objetivo,
    }

    # 4) Síntesis
    texto = synthesize_estado_arte(brechas_payload, contexto)

    # 5) version = max(version)+1 por proyecto
    max_ver = db.query(func.max(EstadoDelArte.version)).filter(EstadoDelArte.proyecto_id == proyecto_id).scalar()
    next_ver = (max_ver or 0) + 1

    # 6) Insert con run_id OBLIGATORIO
    rec = EstadoDelArte(
        id=str(uuid.uuid4()),
        proyecto_id=proyecto_id,
        run_id=run.id,
        version=next_ver,
        texto=texto,
        estado="generado",
        tokens_in=0,
        tokens_out=0,
    )
    db.add(rec)
    db.flush()

    # 7) Métricas de la síntesis (N5). Se calculan aquí porque necesitan el
    #    texto ya generado y todas las brechas del lote a la vez.
    medidas = _medir_sintesis(db, proyecto_id, rec, brechas_rows)
    db.commit()

    return {"estado_arte_id": rec.id, "version": rec.version, "run_id": run.id,
            "metricas": medidas}


def _medir_sintesis(db: Session, proyecto_id: str, rec: EstadoDelArte,
                    brechas_rows) -> dict:
    """Comprueba que la síntesis represente el lote y no invente referencias.

    Ambas cosas se calculan sin llamar al modelo: la cobertura con los
    embeddings, y las citas con los artículos del propio proyecto.
    """
    textos = [r.brecha or "" for r in brechas_rows]
    articulos = [
        {"titulo": a.titulo, "doi": a.doi}
        for a in db.query(Articulo).filter(Articulo.proyecto_id == proyecto_id).all()
    ]

    salida: dict = {}
    for codigo, calcular in (
        ("N5.3", lambda: S.n5_3_cobertura_sintesis(rec.texto, textos)),
        ("N5.5", lambda: S.n5_5_citas_fabricadas(rec.texto, articulos)),
    ):
        try:
            valor, detalle = calcular()
        except Exception as exc:  # noqa: BLE001
            # Que falle una métrica no debe impedir guardar el estado del arte:
            # mide sobre el resultado, no forma parte de él.
            valor, detalle = None, {"error": str(exc)[:200]}
        registrar_metrica(
            db, proyecto_id, "proyecto", rec.id, codigo, valor, detalle
        )
        salida[codigo] = {"valor": valor, "detalle": detalle}
    return salida

@router.get("/{proyecto_id}/estado_arte/latest")
def obtener_estado_arte(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    proyecto_id = proyecto.id
    rec = (
        db.query(EstadoDelArte)
        .filter(EstadoDelArte.proyecto_id == proyecto_id)
        .order_by(EstadoDelArte.version.desc())
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Sin estado del arte para este proyecto")
    return {
        "id": rec.id,
        "version": rec.version,
        "run_id": rec.run_id,
        "estado": rec.estado,
        "texto": rec.texto,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
    }
