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

from app.models.rag_log import RagLog

from app.models.metrica import Metrica, AMBITO_BRECHA, AMBITO_ARTICULO
from app.models.embedding_doc import EmbeddingDoc

from app.services.gemini_service import analyze
from app.services.embedding_service import recuperar_contexto, construir_consulta
from app.services.document_structure import extraer_abstract
from app.services.metricas import niveles as N
from app.services.verificacion import verificar

from app.utils.text_extractor import extraer_con_diagnostico

# Retiradas de este pipeline: validate_breach_with_rag, auto_validate,
# shannon_entropy_bits_and_norm, find_duplicate_breach y lexical_density.
# La entropía de caracteres era cuasi-constante, val_score combinaba dos
# señales en un número no interpretable, y los umbrales de rechazo estaban
# por debajo del piso de ruido de los embeddings. Sus sustitutas están en
# app/services/metricas/.


def _metrica(db, proyecto_id: str, ambito: str, referencia_id: str, codigo: str,
             valor: float | None, detalle: dict | None = None) -> None:
    """Registra una medición en el almacén genérico de métricas."""
    db.add(Metrica(
        id=str(uuid.uuid4()),
        proyecto_id=proyecto_id,
        ambito=ambito,
        referencia_id=referencia_id,
        codigo=codigo,
        valor=None if valor is None else float(valor),
        detalle=detalle,
    ))


def _metricas_de_lote(db, run) -> None:
    """Métricas que solo tienen sentido comparando artículos entre sí.

    N3.1 (discriminabilidad) es la más diagnóstica de toda la capa: si el
    modelo emitió la misma brecha genérica para todos los artículos del lote,
    aquí se ve. El Jaccard anterior no podía detectarlo porque solo comparaba
    brechas del mismo artículo, donde el problema no se manifiesta.
    """
    # Idempotente: el cierre del lote puede alcanzarse por dos caminos, y las
    # métricas no deben duplicarse si se pasa por ambos.
    ya = (db.query(Metrica)
          .filter(Metrica.ambito == "run", Metrica.referencia_id == run.id,
                  Metrica.codigo == "N3.1")
          .first())
    if ya:
        return

    filas = (
        db.query(ResultadoBrecha, RunItem)
        .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
        .filter(RunItem.run_id == run.id)
        .all()
    )
    brechas = {ri.articulo_id: (rb.brecha or "") for rb, ri in filas}
    if len(brechas) < 2:
        return

    valor, detalle = N.n3_1_discriminabilidad(brechas)
    _metrica(db, run.proyecto_id, "run", run.id, "N3.1", valor, detalle)

    valor, detalle = N.n3_4_redundancia(brechas)
    _metrica(db, run.proyecto_id, "run", run.id, "N3.4", valor, detalle)


def _registrar_metricas(db, art, rb, res, texto, recuperados, ruta_pdf) -> None:
    """Calcula y persiste las métricas locales de un artículo analizado.

    Son "locales" porque no requieren llamadas adicionales al modelo: se
    apoyan en los embeddings ya generados durante la indexación. Las que
    necesitan un juez (fidelidad evidencial, precisión del contexto) quedan
    para el nivel N2.
    """
    brecha_txt = res.get("brecha", "") or ""
    resumen_txt = (res.get("resumen") or "").strip()

    # --- N1: calidad de la recuperación ---
    _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N1.2",
             N.n1_2_cobertura_seccional(recuperados),
             {"secciones": sorted({r["seccion"] for r in recuperados})})

    vectores = N.vectores_de(db, [r["embedding_id"] for r in recuperados])
    _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N1.3",
             N.n1_3_diversidad_contexto(vectores),
             {"n_fragmentos": len(vectores)})

    # --- N2: fidelidad a la fuente ---
    # Es el unico nivel que necesita una llamada adicional al modelo. Si falla
    # o esta desactivado se registra el motivo en lugar de un valor: una
    # medicion que no se hizo no es una medicion con resultado cero.
    ver = verificar(brecha_txt, recuperados)
    if ver.disponible:
        _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N2.1", ver.fidelidad,
                 {"sin_respaldo": [a.texto for a in ver.evidenciales
                                   if not a.respaldada][:10]})
        _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N2.2", ver.trazabilidad)
        _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N2.4",
                 ver.equilibrio_evidencial)
    _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N2.verificada",
             1.0 if ver.disponible else 0.0, ver.resumen())

    # --- N3: especificidad ---
    _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N3.2", N.n3_2_densidad_anclajes(brecha_txt))

    # El IDF necesita un corpus amplio para distinguir lo raro de lo frecuente.
    # Calculado sobre los ocho fragmentos recuperados, casi todos los términos
    # aparecían en todos los documentos y la métrica salía cuasi-constante
    # (IQR 0.018 en el primer lote real). Se usa el proyecto entero.
    corpus = [t for (t,) in db.query(EmbeddingDoc.texto)
              .join(Articulo, Articulo.id == EmbeddingDoc.articulo_id)
              .filter(Articulo.proyecto_id == art.proyecto_id).all()]
    _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N3.3",
             N.n3_3_contenido_informativo(brecha_txt, corpus),
             {"tamano_corpus": len(corpus)})

    # --- N4: calidad del resumen, contra el abstract REAL ---
    abstract = extraer_abstract(texto)
    m4 = N.n4_calidad_resumen(resumen_txt, abstract)
    for codigo, valor in (("N4.1a", m4.rouge1_prec), ("N4.1b", m4.rouge1_rec),
                          ("N4.1c", m4.rouge1_f1), ("N4.1d", m4.rouge2_f1),
                          ("N4.1e", m4.rougeL_f1), ("N4.2", m4.similitud_semantica),
                          ("N4.4", m4.densidad_lexica)):
        _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, codigo, valor,
                 {"referencia_valida": m4.referencia_valida} if codigo == "N4.1a" else None)

    _metrica(db, art.proyecto_id, AMBITO_ARTICULO, art.id, "N4.ref",
             1.0 if m4.referencia_valida else 0.0,
             {"motivo": m4.motivo, "chars_abstract": len(abstract or "")})

    if resumen_txt:
        db.add(ResultadoResumen(
            id=str(uuid.uuid4()),
            articulo_id=art.id,
            resumen_generado=resumen_txt,
            # Ahora la referencia es el abstract del artículo. Antes eran las
            # primeras 180 palabras del PDF: portada, autores y encabezado de
            # revista, con lo que ROUGE medía el solape con la carátula (M-02).
            resumen_referencia=(abstract or ""),
            lexical_density=m4.densidad_lexica,
            rouge1_prec=str(m4.rouge1_prec) if m4.referencia_valida else None,
            rouge1_rec=str(m4.rouge1_rec) if m4.referencia_valida else None,
            rouge1_f1=str(m4.rouge1_f1) if m4.referencia_valida else None,
        ))


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
        run.finalizado_en = datetime.now()
        _metricas_de_lote(db, run)
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

    diag = extraer_con_diagnostico(arc.ruta)
    texto = diag.texto
    if not diag.utilizable:
        from app.services.ocr_fallback import ocr_disponible
        ok_ocr, motivo_ocr = ocr_disponible()
        motivos = list(diag.avisos) or ["Texto insuficiente."]
        if not ok_ocr and diag.metodo != "ocr":
            motivos.append("OCR no disponible. " + motivo_ocr)
        item.estado = EstadoRunItem.fallido
        # El diagnóstico N0 sustituye al escueto "Texto insuficiente": ahora el
        # usuario sabe por qué falló y si es recuperable.
        item.error_msg = " | ".join(motivos)[:2000]
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
        run.iniciado_en = datetime.now()

    try:
        # --- Paso 1: recuperar fragmentos por relevancia ---
        # Antes se usaba get_top_chunks(), que devolvía los primeros ocho
        # fragmentos del documento: el modelo solo veía resumen e introducción
        # y nunca método, resultados ni discusión (M-10).
        recuperados = recuperar_contexto(db, art.id, contexto, k=8)
        support = [r["texto"] for r in recuperados]

        # Trazabilidad: qué fragmentos se usaron en este análisis.
        if recuperados:
            db.add(RagLog(
                id=str(uuid.uuid4()),
                proyecto_id=run.proyecto_id,
                run_id=run_id,
                articulo_id=art.id,
                consulta=construir_consulta(contexto)[:2000],
                top_k=len(recuperados),
                scores=[
                    {
                        "embedding_id": r["embedding_id"],
                        "seccion": r["seccion"],
                        "score": r["score"],
                    }
                    for r in recuperados
                ],
            ))

        # --- Paso 2: análisis de brecha con Gemini usando RAG ---
        res = analyze(texto, contexto, context_docs=(support if support else None))

        brecha_txt = res.get("brecha", "")

        # --- Paso 3: guardar el resultado de brecha ---
        # La validación automática queda en "pendiente" a propósito. Las
        # reglas anteriores se apoyaban en la entropía de caracteres y en un
        # val_score compuesto cuyos umbrales nunca llegaban a activarse, de
        # modo que casi todo terminaba en "aceptada" sin haber sido validado.
        # Un estado honesto es preferible a un sello de goma: la validación
        # volverá cuando los umbrales estén calibrados contra juicio experto.
        rb = ResultadoBrecha(
            id=str(uuid.uuid4()),
            run_item_id=item.id,
            tipo_brecha=res.get("tipo_brecha", "otra"),
            brecha=brecha_txt,
            oportunidad=res.get("oportunidad", ""),
            evidencia=None,
            rag_hits=[
                {"embedding_id": r["embedding_id"], "seccion": r["seccion"],
                 "score": r["score"]}
                for r in recuperados
            ],
            val_reason="Pendiente de calibración de la validación automática.",
            estado_validacion="pendiente",
        )
        db.add(rb)
        db.flush()

        # Contabilidad de consumo (S-04). El SDK nuevo expone usage_metadata,
        # así que los campos del esquema dejan de quedarse en cero y se puede
        # conocer el coste real de cada ejecución.
        uso = res.get("_usage") or {}
        run.tokens_in = (run.tokens_in or 0) + int(uso.get("tokens_in", 0))
        run.tokens_out = (run.tokens_out or 0) + int(uso.get("tokens_out", 0))

        # --- Paso 4: métricas locales N1, N3 y N4 ---
        _registrar_metricas(db, art, rb, res, texto, recuperados, arc.ruta)

        item.estado = EstadoRunItem.analizado
        run.n_items_ok += 1
        # La sesión se crea con autoflush=False, así que sin este volcado la
        # consulta siguiente leería el estado antiguo del ítem en la base y
        # el lote nunca se daría por terminado por esta vía.
        db.flush()

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
            run.finalizado_en = datetime.now()
            # N3.1 y N3.4 comparan las brechas entre sí, de modo que solo
            # tienen sentido cuando el lote está completo.
            _metricas_de_lote(db, run)

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
