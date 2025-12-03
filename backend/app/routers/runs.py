# app/routers/runs.py
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.run import Run, EstadoRun
from app.models.run_item import RunItem, EstadoRunItem
from app.models.articulo import Articulo
from app.models.archivo import Archivo
from app.models.resultado_brecha import ResultadoBrecha
from app.models.proyecto import Proyecto
from app.models.resultado_resumen import ResultadoResumen  # modelo de resúmenes
from app.schemas.run import RunCreate, RunOut, RunItemOut

from app.services.gemini_service import analyze
from app.services.embedding_service import get_top_chunks
from app.services.metrics import (
    validate_breach_with_rag,
    shannon_entropy_bits_and_norm,
    find_duplicate_breach,
    auto_validate,
    lexical_density,  # usamos esto para la densidad léxica del resumen
)

from app.utils.text_extractor import extract_full_text

router = APIRouter(prefix="/proyectos", tags=["runs"])


# ----------------------------
# CREAR RUN
# ----------------------------
@router.post("/{proyecto_id}/runs", response_model=RunOut)
def crear_run(
    proyecto_id: str, _body: RunCreate | None = None, db: Session = Depends(get_db)
):
    arts = db.query(Articulo).filter(Articulo.proyecto_id == proyecto_id).all()
    if not arts:
        raise HTTPException(status_code=400, detail="El proyecto no tiene artículos.")

    run_id = str(uuid.uuid4())
    r = Run(
        id=run_id,
        proyecto_id=proyecto_id,
        estado=EstadoRun.creado,
        n_items_total=len(arts),
        n_items_ok=0,
    )
    db.add(r)
    db.flush()

    for a in arts:
        db.add(
            RunItem(
                id=str(uuid.uuid4()),
                run_id=run_id,
                articulo_id=a.id,
                estado=EstadoRunItem.pendiente,
            )
        )
    db.commit()

    return RunOut.model_construct(
        id=run_id,
        proyecto_id=proyecto_id,
        estado=r.estado.value,
        n_items_total=r.n_items_total,
        n_items_ok=r.n_items_ok,
    )


# ----------------------------
# LISTAR RUNS
# ----------------------------
@router.get("/{proyecto_id}/runs", response_model=list[RunOut])
def listar_runs(proyecto_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(Run)
        .filter(Run.proyecto_id == proyecto_id)
        .order_by((Run.iniciado_en == None).asc(), Run.iniciado_en.desc())
        .all()
    )
    return [
        RunOut.model_construct(
            id=x.id,
            proyecto_id=x.proyecto_id,
            estado=x.estado.value,
            n_items_total=x.n_items_total,
            n_items_ok=x.n_items_ok,
        )
        for x in rows
    ]


# ----------------------------
# LISTAR ITEMS
# ----------------------------
@router.get("/runs/{run_id}/items", response_model=list[RunItemOut])
def listar_items(run_id: str, db: Session = Depends(get_db)):
    items = db.query(RunItem).filter(RunItem.run_id == run_id).all()
    return [
        RunItemOut.model_construct(
            id=i.id, articulo_id=i.articulo_id, estado=i.estado.value
        )
        for i in items
    ]


# ----------------------------
# DEBUG ITEMS (ver errores)
# ----------------------------
@router.get("/runs/{run_id}/items_debug")
def listar_items_debug(run_id: str, db: Session = Depends(get_db)):
    items = db.query(RunItem).filter(RunItem.run_id == run_id).all()
    return [
        {
            "id": i.id,
            "articulo_id": i.articulo_id,
            "estado": i.estado.value,
            "error_msg": i.error_msg,
        }
        for i in items
    ]


# ----------------------------
# PROCESAR SIGUIENTE ITEM (Gemini + RAG + Validación Automática)
# ----------------------------
@router.post("/runs/{run_id}/process_next", response_model=RunOut)
def process_next_item(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run no encontrado")

    pendiente = (
        db.query(RunItem)
        .filter(RunItem.run_id == run_id, RunItem.estado == EstadoRunItem.pendiente)
        .first()
    )
    if not pendiente or run.n_items_ok >= run.n_items_total:
        run.estado = EstadoRun.completado
        run.finalizado_en = datetime.utcnow()
        db.commit()
        return RunOut.model_construct(
            id=run.id,
            proyecto_id=run.proyecto_id,
            estado=run.estado.value,
            n_items_total=run.n_items_total,
            n_items_ok=run.n_items_ok,
        )

    item = pendiente
    art = db.query(Articulo).filter(Articulo.id == item.articulo_id).first()
    arc = (
        db.query(Archivo)
        .filter(Archivo.articulo_id == art.id)
        .order_by(Archivo.creado_en.desc())
        .first()
    )
    if not arc:
        item.estado = EstadoRunItem.fallido
        item.error_msg = "Artículo sin archivo asociado."
        db.commit()
        return RunOut.model_construct(
            id=run.id,
            proyecto_id=run.proyecto_id,
            estado=run.estado.value,
            n_items_total=run.n_items_total,
            n_items_ok=run.n_items_ok,
        )

    texto = extract_full_text(arc.ruta)
    if len(texto.strip()) < 300:
        item.estado = EstadoRunItem.fallido
        item.error_msg = "Texto insuficiente (PDF vacío o escaneado)."
        db.commit()
        return RunOut.model_construct(
            id=run.id,
            proyecto_id=run.proyecto_id,
            estado=run.estado.value,
            n_items_total=run.n_items_total,
            n_items_ok=run.n_items_ok,
        )

    pr = db.query(Proyecto).filter(Proyecto.id == run.proyecto_id).first()
    contexto = {
        "tema_principal": pr.tema_principal,
        "metodologia_txt": pr.metodologia_txt,
        "sector_txt": pr.sector_txt,
        "objetivo": pr.objetivo,
    }

    if run.estado == EstadoRun.creado:
        run.estado = EstadoRun.en_progreso
        run.iniciado_en = datetime.utcnow()

    try:
        # --- Paso 1: recuperar fragmentos RAG (si existen) ---
        support = get_top_chunks(db, art.id, k=8)  # list[str] o []

        # --- Paso 2: análisis de brecha con Gemini usando RAG ---
        res = analyze(texto, contexto, context_docs=(support if support else None))

        # --- Paso 3: métricas y validación automática ---
        sim_avg, hits, val_score = validate_breach_with_rag(
            db, art.id, res.get("brecha", "")
        )
        ent_bits, ent_norm = shannon_entropy_bits_and_norm(res.get("brecha", ""))
        dup_row, es_dup = find_duplicate_breach(
            db, art.id, res.get("brecha", ""), thr=0.80
        )
        estado_val, razon_val = auto_validate(
            sim_avg, ent_norm, val_score, es_dup
        )

        # --- Paso 4: guardar resultado de brecha ---
        rb = ResultadoBrecha(
            id=str(uuid.uuid4()),
            run_item_id=item.id,
            tipo_brecha=res.get("tipo_brecha", "otra"),
            brecha=res.get("brecha", ""),
            oportunidad=res.get("oportunidad", ""),
            evidencia=None,
            rag_hits=hits,
            sim_promedio=round(sim_avg, 4),
            entropia=round(ent_bits, 3),
            val_score=round(val_score, 4),
            val_reason=razon_val,
            es_duplicada=es_dup,
            dup_de=(dup_row.id if es_dup else None),
            estado_validacion=estado_val,
        )
        db.add(rb)

        # --- Guardar resúmenes para ROUGE-1 y densidad léxica ---
        try:
            resumen_generado = (res.get("resumen") or "").strip()
        except Exception:
            resumen_generado = ""

        # referencia: primeras 180 palabras del texto completo
        resumen_referencia = " ".join((texto or "").split()[:180])

        if len(resumen_generado) > 50 and len(resumen_referencia) > 50:
            # calcular densidad léxica del resumen generado
            ld = lexical_density(resumen_generado)

            rr = ResultadoResumen(
                id=str(uuid.uuid4()),
                articulo_id=art.id,
                resumen_generado=resumen_generado,
                resumen_referencia=resumen_referencia,
                lexical_density=round(ld, 4),
                # los ROUGE-1 se recalculan en metrics.project_indicators;
                # estos campos pueden quedar en None o usarse luego si quieres persistirlos.
                rouge1_prec=None,
                rouge1_rec=None,
                rouge1_f1=None,
            )
            db.add(rr)

        item.estado = EstadoRunItem.analizado
        run.n_items_ok += 1

        # --- Paso 5: cierre automático si no hay pendientes ---
        pendiente_restante = (
            db.query(RunItem)
            .filter(
                RunItem.run_id == run_id,
                RunItem.estado == EstadoRunItem.pendiente,
            )
            .first()
        )
        if not pendiente_restante:
            run.estado = EstadoRun.completado
            run.finalizado_en = datetime.utcnow()

    except Exception as e:
        item.estado = EstadoRunItem.fallido
        item.error_msg = str(e)

    db.commit()
    return RunOut.model_construct(
        id=run.id,
        proyecto_id=run.proyecto_id,
        estado=run.estado.value,
        n_items_total=run.n_items_total,
        n_items_ok=run.n_items_ok,
    )
