# app/routers/runs.py
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencias import (
    comprobar_cuota_usuario,
    proyecto_propio,
    run_propio,
    usuario_actual,
)
from app.models.usuario import Usuario
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

from app.services import almacenamiento, cola
from app.services.gemini_service import analyze
from app.services.embedding_service import recuperar_contexto, construir_consulta
from app.services.document_structure import extraer_abstract
from app.services.metricas import niveles as N
from app.services.metricas import sintesis as S
from app.services.verificacion import verificar
from app.services.ventana_evidencia import fragmentos_de_brecha
from app.services.procedencia import capturar_procedencia
from app.services.registro_metricas import registrar_metrica

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
    registrar_metrica(
        db, proyecto_id, ambito, referencia_id, codigo, valor, detalle
    )


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
    secciones_articulo = N.secciones_sustantivas_indexadas(db, art.id)
    valor_n12, detalle_n12 = N.n1_2_cobertura_seccional(
        recuperados, secciones_articulo
    )
    _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N1.2",
             valor_n12, detalle_n12)

    vectores = N.vectores_de(db, [r["embedding_id"] for r in recuperados])
    _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N1.3",
             N.n1_3_diversidad_contexto(vectores),
             {"n_fragmentos": len(vectores)})

    # --- N2: fidelidad a la fuente ---
    # Es el unico nivel que necesita una llamada adicional al modelo. Si falla
    # o esta desactivado se registra el motivo en lugar de un valor: una
    # medicion que no se hizo no es una medicion con resultado cero.
    # La verificacion normal y la posterior usan la misma ventana. Los vecinos
    # reconstruyen frases que el troceado pudo partir; si por compatibilidad no
    # se puede reconstruir desde rag_hits, se conservan los recuperados.
    ventana = fragmentos_de_brecha(db, rb) or recuperados
    ver = verificar(brecha_txt, ventana)
    if ver.disponible:
        _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N2.1", ver.fidelidad,
                 {"sin_respaldo": [a.texto for a in ver.evidenciales
                                   if not a.respaldada][:10]})
        _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N2.2", ver.trazabilidad)
        _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N2.4",
                 ver.equilibrio_evidencial)
        _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N2.5",
                 ver.tasa_contradiccion,
                 {"contradicciones": [
                     {"afirmacion": a.texto,
                      "fragmento": a.fragmento_contrario,
                      "cita": a.cita_contraria,
                      "tipo": a.tipo}
                     for a in ver.contradictorias][:10]})
        _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N2.6",
                 1.0 if ver.ya_resuelta else 0.0,
                 {"fragmento": ver.fragmento_resuelta,
                  "cita": ver.cita_resuelta})
    _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N2.verificada",
             1.0 if ver.disponible else 0.0, ver.resumen())

    # --- N5.2: cuantas veces el reclasificador sobrescribe al modelo ---
    tipo_modelo = res.get("tipo_modelo")
    _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, "N5.2",
             S.n5_2_efecto_reclasificador(tipo_modelo, res.get("tipo_brecha")),
             {"tipo_modelo": tipo_modelo, "tipo_final": res.get("tipo_brecha")})

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

    # Las cinco variantes de ROUGE se guardan sin valor cuando no son
    # aplicables, no en cero.
    #
    # Antes se almacenaba el 0.0 que traían por defecto, y la pantalla mostraba
    # "0.000": exactamente el problema que esta capa vino a resolver. Un cero
    # se lee como "el resumen no se parece en nada al abstract" cuando lo que
    # ocurre es que ROUGE cuenta palabras compartidas y el resumen está en
    # español mientras el abstract está en inglés. Sin valor y con el motivo al
    # lado, la interfaz puede decir "no aplicable" y explicar por qué.
    detalle_rouge = None if m4.rouge_aplicable else {
        "aplicable": False,
        "motivo": m4.motivo,
        "idioma_resumen": m4.idioma_generado,
        "idioma_abstract": m4.idioma_referencia,
    }
    for codigo, valor in (("N4.1a", m4.rouge1_prec), ("N4.1b", m4.rouge1_rec),
                          ("N4.1c", m4.rouge1_f1), ("N4.1d", m4.rouge2_f1),
                          ("N4.1e", m4.rougeL_f1)):
        det = dict(detalle_rouge) if detalle_rouge else None
        if codigo == "N4.1a":
            det = det or {}
            det["referencia_valida"] = m4.referencia_valida
        _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, codigo,
                 valor if m4.rouge_aplicable else None, det)

    # Estas dos sí valen entre idiomas distintos: la similitud semántica compara
    # significado y la densidad léxica no depende de la referencia.
    for codigo, valor in (("N4.2", m4.similitud_semantica),
                          ("N4.4", m4.densidad_lexica)):
        _metrica(db, art.proyecto_id, AMBITO_BRECHA, rb.id, codigo, valor)

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
            # La condición es `rouge_aplicable`, no `referencia_valida`. Son
            # distintas: un abstract puede ser perfectamente válido y aun así
            # estar en otro idioma que el resumen, y entonces ROUGE vale 0.0
            # por construcción. Con la condición anterior ese 0.0 se guardaba
            # como si fuera una medición. La tabla `metrica` ya lo trataba
            # bien; esta se quedó atrás.
            rouge1_prec=str(m4.rouge1_prec) if m4.rouge_aplicable else None,
            rouge1_rec=str(m4.rouge1_rec) if m4.rouge_aplicable else None,
            rouge1_f1=str(m4.rouge1_f1) if m4.rouge_aplicable else None,
        ))


router = APIRouter(prefix="/proyectos", tags=["runs"])


# ----------------------------
# CREAR RUN
# ----------------------------
@router.post("/{proyecto_id}/runs", response_model=RunOut)
def crear_run(
    _body: RunCreate | None = None,
    proyecto: Proyecto = Depends(proyecto_propio),
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    # Antes de encolar nada: un lote rechazado a mitad deja artículos en
    # estados intermedios y ya habrá gastado las llamadas que salieron.
    comprobar_cuota_usuario(usuario)

    proyecto_id = proyecto.id
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
        procedencia=capturar_procedencia(),
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
        procedencia=r.procedencia,
    )


# ----------------------------
# LISTAR RUNS
# ----------------------------
@router.get("/{proyecto_id}/runs", response_model=list[RunOut])
def listar_runs(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    proyecto_id = proyecto.id
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
            procedencia=x.procedencia,
        )
        for x in rows
    ]


@router.get("/{proyecto_id}/run_activo")
def run_activo(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    """El análisis en curso del proyecto, o `null` si no hay ninguno.

    Lo consulta el frontend al abrir un proyecto. Sin esto, quien lanzaba un
    análisis y salía de la pantalla no volvía a ver su avance: el progreso
    vivía solo en la memoria de la pestaña, de modo que el trabajo seguía en
    el servidor pero la interfaz lo daba por perdido.
    """
    run = (db.query(Run)
             .filter(Run.proyecto_id == proyecto.id,
                     Run.estado.in_((EstadoRun.creado, EstadoRun.en_progreso)))
             .order_by(Run.iniciado_en.desc())
             .first())
    if run is None:
        return None

    return {
        "id": run.id,
        "proyecto_id": run.proyecto_id,
        "estado": run.estado.value,
        "n_items_total": run.n_items_total,
        "n_items_ok": cola.contar_ok(db, run.id),
        # Un trabajo encolado sin trabajador en marcha se queda quieto para
        # siempre y nada lo delata. Decirlo aquí evita que parezca lentitud.
        "en_marcha": db.query(RunItem.id).filter(
            RunItem.run_id == run.id,
            RunItem.estado == EstadoRunItem.en_proceso).first() is not None,
        "error_msg": run.error_msg,
    }


# ----------------------------
# LISTAR ITEMS
# ----------------------------
@router.get("/runs/{run_id}/items", response_model=list[RunItemOut])
def listar_items(
    run: Run = Depends(run_propio),
    db: Session = Depends(get_db),
):
    items = db.query(RunItem).filter(RunItem.run_id == run.id).all()
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
def listar_items_debug(
    run: Run = Depends(run_propio),
    db: Session = Depends(get_db),
):
    items = db.query(RunItem).filter(RunItem.run_id == run.id).all()
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
# PROCESAR UN ITEM (Gemini + RAG + métricas)
# ----------------------------
class FalloDefinitivo(Exception):
    """No tiene sentido reintentar: el artículo no da para más.

    Un PDF sin texto seguirá sin texto en el siguiente intento. Distinguirlo
    de un corte de red es lo que evita gastar tres intentos y tres veces la
    cuota en algo que no puede salir bien.
    """


def procesar_item(db: Session, run: Run, item: RunItem) -> None:
    """Analiza un artículo y deja el ítem en `analizado`.

    No decide qué hacer con los fallos: los deja salir. Quien lo llama —el
    trabajador o el endpoint— sabe si conviene reintentar, y esa decisión no
    debería estar enterrada aquí.
    """
    run_id = run.id
    art = db.query(Articulo).filter(Articulo.id == item.articulo_id).first()
    if not art:
        raise FalloDefinitivo("El artículo ya no existe.")

    arc = (
        db.query(Archivo)
        .filter(Archivo.articulo_id == art.id)
        .order_by(Archivo.creado_en.desc())
        .first()
    )
    if not arc:
        raise FalloDefinitivo("Artículo sin archivo asociado.")

    # `arc.ruta` es una clave, no un camino: se traduce aquí. Los archivos
    # subidos antes de que existieran las claves siguen guardando la ruta
    # absoluta, y `ruta_local` las acepta tal cual.
    try:
        ruta_pdf = almacenamiento.ruta_local(arc.ruta)
    except almacenamiento.ClaveInvalida as e:
        raise FalloDefinitivo("Referencia de archivo no válida: %s" % e) from None

    diag = extraer_con_diagnostico(ruta_pdf)
    texto = diag.texto
    if not diag.utilizable:
        from app.services.ocr_fallback import ocr_disponible
        ok_ocr, motivo_ocr = ocr_disponible()
        motivos = list(diag.avisos) or ["Texto insuficiente."]
        if not ok_ocr and diag.metodo != "ocr":
            motivos.append("OCR no disponible. " + motivo_ocr)
        # El diagnóstico N0 sustituye al escueto "Texto insuficiente": ahora el
        # usuario sabe por qué falló y si es recuperable.
        raise FalloDefinitivo(" | ".join(motivos))

    pr = db.query(Proyecto).filter(Proyecto.id == run.proyecto_id).first()
    contexto = {
        "tema_principal": pr.tema_principal,
        "metodologia_txt": pr.metodologia_txt,
        "sector_txt": pr.sector_txt,
        "objetivo": pr.objetivo,
    }

    # --- Paso 0: indexar si hace falta ---
    # La indexación estaba en `analizar_todo`, dentro de la petición HTTP, y
    # es la otra parte lenta. Aquí es idempotente: lo ya indexado no se vuelve
    # a pagar, así que un reintento no repite el gasto.
    ya_indexado = (db.query(EmbeddingDoc.id)
                     .filter(EmbeddingDoc.articulo_id == art.id).first())
    if not ya_indexado:
        from app.services.embedding_service import index_articulo

        if index_articulo(db, art.id) == 0:
            raise FalloDefinitivo(
                "No se pudo indexar el artículo: sin archivo o sin texto.")

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
    _registrar_metricas(db, art, rb, res, texto, recuperados, ruta_pdf)

    item.estado = EstadoRunItem.analizado
    item.error_msg = None  # si venía de un intento fallido, ya no aplica
    # La sesión se crea con autoflush=False, así que sin este volcado la
    # consulta siguiente leería el estado antiguo del ítem en la base.
    db.flush()

    # Se recuenta en la base en lugar de hacer `n_items_ok += 1`. Con un solo
    # proceso daba igual; con varios trabajadores, dos incrementos a la vez
    # leen el mismo valor y uno de los dos se pierde.
    run.n_items_ok = cola.contar_ok(db, run_id)
    db.commit()


def cerrar_run(db: Session, run: Run) -> None:
    """Da la ejecución por terminada y calcula las métricas del lote.

    Es idempotente: cerrar dos veces la misma ejecución no duplica nada, lo
    que importa porque quien la cierra es un barrido periódico y no el
    trabajador que acabó el último artículo. Si ese trabajador muriera justo
    después de guardarlo, nadie cerraría la ejecución.
    """
    if run.estado == EstadoRun.completado:
        return

    run.n_items_ok = cola.contar_ok(db, run.id)
    run.estado = EstadoRun.completado
    run.finalizado_en = datetime.now()
    # N3.1 y N3.4 comparan las brechas entre sí, de modo que solo tienen
    # sentido cuando el lote está completo.
    _metricas_de_lote(db, run)
    db.commit()


@router.get("/runs/{run_id}", response_model=RunOut)
def estado_run(run: Run = Depends(run_propio), db: Session = Depends(get_db)):
    """Cómo va una ejecución. Es lo que consulta el frontend mientras espera.

    Se recuenta en la base en vez de devolver el contador guardado: si un
    trabajador cayó a mitad, el contador podría haberse quedado corto.
    """
    run.n_items_ok = cola.contar_ok(db, run.id)
    return _estado(run)


@router.post("/runs/{run_id}/process_next", response_model=RunOut)
def process_next_item(
    run: Run = Depends(run_propio),
    db: Session = Depends(get_db),
):
    """Procesa un artículo de la ejecución y devuelve cómo va.

    Se conserva para el análisis conducido desde el navegador, que sigue
    sirviendo cuando quien mira quiere ver el avance paso a paso. El trabajo
    de fondo lo hace `trabajador.py`, sobre la misma cola y las mismas
    funciones: los dos caminos no pueden divergir porque comparten el código.
    """
    item = cola.tomar_pendiente(db, run_id=run.id)

    if item is None:
        if not cola.quedan_pendientes(db, run.id):
            cerrar_run(db, run)
        return _estado(run)

    cola.marcar_en_progreso(db, run)
    try:
        procesar_item(db, run, item)
    except FalloDefinitivo as e:
        item.estado = EstadoRunItem.fallido
        item.error_msg = str(e)[:2000]
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        cola.devolver(db, item, str(e))

    if not cola.quedan_pendientes(db, run.id):
        cerrar_run(db, run)

    db.refresh(run)
    return _estado(run)


def _estado(run: Run) -> RunOut:
    return RunOut.model_construct(
        id=run.id,
        proyecto_id=run.proyecto_id,
        estado=run.estado.value if hasattr(run.estado, "value") else run.estado,
        n_items_total=run.n_items_total,
        n_items_ok=run.n_items_ok,
        procedencia=run.procedencia,
    )
