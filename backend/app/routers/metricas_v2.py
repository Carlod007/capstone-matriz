# app/routers/metricas_v2.py
"""
Endpoints de la capa de medición v2.

Sustituyen a /metrics/resumen, que leía las columnas retiradas y por eso
devuelve ceros: la interfaz mostraba entropía, similitud y val_score en 0,
dando la impresión de estar rota cuando en realidad esas métricas ya no se
calculan.

Se sirven distribuciones completas, no solo promedios. Una media de 0.86 con
un rango intercuartílico de 0.02 y otra con 0.40 dicen cosas muy distintas, y
presentarlas igual fue lo que oculto el problema original.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencias import proyecto_propio, usuario_actual
from app.models.usuario import Usuario
from app.models.articulo import Articulo
from app.models.estado_arte import EstadoDelArte
from app.models.metrica import Metrica
from app.models.proyecto import Proyecto
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run import Run, EstadoRun
from app.models.run_item import RunItem
from app.services import limitador, registro_api, verificacion
from app.services.metricas import distribucion as D
from app.services.metricas.catalogo import CATALOGO, ficha_para_version

router = APIRouter(prefix="/proyectos", tags=["metricas-v2"])

# La cuota pertenece a la clave de API, no al proyecto. Servirla solo bajo
# /proyectos/{id}/consumo daba a entender lo contrario y obligaba a entrar en
# un proyecto para saber cuanto margen quedaba.
router_global = APIRouter(tags=["metricas-v2"])


def _ultimo_run(db: Session, proyecto_id: str) -> Run | None:
    # MySQL no admite NULLS LAST y tampoco hace falta: en orden descendente
    # coloca los nulos al final, que es justo lo que se busca.
    return (db.query(Run)
            .filter(Run.proyecto_id == proyecto_id)
            .order_by(Run.iniciado_en.desc(), Run.id)
            .first())


@router.get("/{proyecto_id}/metricas")
def metricas_proyecto(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    proyecto_id = proyecto.id
    """Distribuciones de cada métrica del último análisis del proyecto."""
    pr = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    run = _ultimo_run(db, proyecto_id)
    if not run:
        return {"proyecto_id": proyecto_id, "run": None, "metricas": [],
                "aviso": "El proyecto todavía no se ha analizado."}

    # Identificadores del último run: las métricas de ejecuciones anteriores
    # se conservan, pero mezclarlas falsearía las distribuciones.
    ids_brecha = [r[0] for r in
                  db.query(ResultadoBrecha.id)
                  .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
                  .filter(RunItem.run_id == run.id).all()]
    ids_articulo = [r[0] for r in
                    db.query(RunItem.articulo_id).filter(RunItem.run_id == run.id).all()]

    # La sintesis y sus metricas N5 pertenecen a una ejecucion concreta. Una
    # sintesis de un run anterior no debe aparecer como resultado del actual.
    ea = (db.query(EstadoDelArte)
          .filter(EstadoDelArte.proyecto_id == proyecto_id,
                  EstadoDelArte.run_id == run.id)
          .order_by(EstadoDelArte.version.desc(),
                    EstadoDelArte.created_at.desc())
          .first())
    referencias = set(ids_brecha) | set(ids_articulo) | {run.id}
    if ea:
        referencias.add(ea.id)

    # Una métrica de ámbito artículo conserva el mismo `referencia_id` entre
    # ejecuciones, así que filtrar solo por referencia mezclaría el análisis
    # actual con los anteriores. Se conserva la medición más reciente de cada
    # par (entidad, código), que es el valor vigente.
    ultima: dict[tuple[str, str], Metrica] = {}
    for m in (db.query(Metrica)
              .filter(Metrica.proyecto_id == proyecto_id)
              .order_by(Metrica.creado_en.asc()).all()):
        if m.referencia_id in referencias:
            ultima[(m.referencia_id, m.codigo)] = m

    # La version forma parte de la identidad de la serie. Agrupar solo por
    # codigo mezclaría en silencio valores producidos por formulas distintas.
    valores: dict[tuple[str, int | None, str], list] = {}
    motivos: dict[tuple[str, int | None, str], list[str]] = {}
    procedencias: dict[tuple[str, int | None, str], dict | None] = {}
    for m in ultima.values():
        firma = json.dumps(m.procedencia, sort_keys=True, separators=(",", ":"))
        clave = (m.codigo, m.version_formula, firma)
        valores.setdefault(clave, []).append(m.valor)
        procedencias[clave] = m.procedencia
        # Cuando la medición se descartó, el porqué quedó guardado junto a ella.
        # La pantalla decía «no produjo valores», que es cierto y no explica
        # nada: el motivo estaba en la base desde el principio.
        if isinstance(m.detalle, dict) and m.detalle.get("motivo"):
            motivos.setdefault(clave, []).append(str(m.detalle["motivo"]))

    salida = []
    for codigo, version_formula, firma in sorted(
        valores, key=lambda x: (x[0], -1 if x[1] is None else x[1], x[2])
    ):
        clave = (codigo, version_formula, firma)
        d = D.describir(codigo, valores[clave])
        f = ficha_para_version(codigo, version_formula)

        # Solo se informa del motivo si no quedó ningún valor y todas las
        # mediciones descartadas coinciden en la razón. Con motivos distintos,
        # resumirlos en uno sería elegir por el lector cuál vale.
        razones = set(motivos.get(clave, []))
        motivo = razones.pop() if d.n == 0 and len(razones) == 1 else None

        salida.append({
            **d.dict(),
            "nombre": f.nombre if f else codigo,
            "nivel": f.nivel if f else "",
            "ambito": f.ambito if f else "",
            "mejor": f.mejor if f else "neutro",
            "rango": f.rango if f else "",
            "descripcion": f.descripcion if f else "",
            "interpretacion": f.interpretacion if f else "",
            "motivo_sin_datos": motivo,
            "version_formula": version_formula,
            "procedencia": procedencias[clave],
            "procedencia_formula": (
                "registrada" if version_formula is not None else "legado/desconocido"
            ),
            # Cuántas mediciones se intentaron, hubieran dado valor o no. Sin
            # esto, «n=0» no distingue entre «no se midió nada» y «se midieron
            # cinco y ninguna aplicaba».
            "n_intentos": len(valores[clave]),
        })

    estados = {}
    for (e,) in (db.query(ResultadoBrecha.estado_validacion)
                 .filter(ResultadoBrecha.id.in_(ids_brecha or ["-"])).all()):
        estados[e or ""] = estados.get(e or "", 0) + 1

    return {
        "proyecto_id": proyecto_id,
        "run": {
            "id": run.id,
            "estado": run.estado.value if hasattr(run.estado, "value") else str(run.estado),
            "finalizado_en": str(run.finalizado_en) if run.finalizado_en else None,
            "n_items_total": run.n_items_total,
            "n_items_ok": run.n_items_ok,
            "tokens_in": run.tokens_in or 0,
            "tokens_out": run.tokens_out or 0,
            "procedencia": run.procedencia,
        },
        "conteos": {
            "articulos": len(set(ids_articulo)),
            "brechas": len(ids_brecha),
            "por_estado_validacion": estados,
        },
        "estado_arte": ({"version": ea.version, "fecha": str(ea.created_at),
                         "caracteres": len((ea.texto or "").strip())} if ea else None),
        "metricas": salida,
        # La validación automática está desactivada a propósito hasta
        # calibrarla; conviene que la interfaz lo diga en vez de mostrar
        # "pendiente" sin explicación.
        "validacion_calibrada": False,
    }


@router.get("/{proyecto_id}/metricas/por_articulo")
def metricas_por_articulo(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    proyecto_id = proyecto.id
    """Valor de cada métrica para cada artículo del último análisis."""
    run = _ultimo_run(db, proyecto_id)
    if not run:
        return {"run": None, "articulos": []}

    filas = (db.query(ResultadoBrecha, RunItem, Articulo)
             .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
             .join(Articulo, Articulo.id == RunItem.articulo_id)
             .filter(RunItem.run_id == run.id).all())

    # Igual que arriba: se toma la medición más reciente de cada par.
    por_referencia: dict[str, dict] = {}
    versiones_por_referencia: dict[str, dict] = {}
    procedencias_por_referencia: dict[str, dict] = {}
    for m in (db.query(Metrica)
              .filter(Metrica.proyecto_id == proyecto_id)
              .order_by(Metrica.creado_en.asc()).all()):
        por_referencia.setdefault(m.referencia_id, {})[m.codigo] = m.valor
        versiones_por_referencia.setdefault(m.referencia_id, {})[
            m.codigo
        ] = m.version_formula
        procedencias_por_referencia.setdefault(m.referencia_id, {})[
            m.codigo
        ] = m.procedencia

    articulos = []
    for rb, ri, art in filas:
        metricas = dict(por_referencia.get(rb.id, {}))
        metricas.update(por_referencia.get(art.id, {}))
        versiones = dict(versiones_por_referencia.get(rb.id, {}))
        versiones.update(versiones_por_referencia.get(art.id, {}))
        procedencias_metricas = dict(procedencias_por_referencia.get(rb.id, {}))
        procedencias_metricas.update(procedencias_por_referencia.get(art.id, {}))
        articulos.append({
            "articulo_id": art.id,
            "titulo": art.titulo,
            "doi": art.doi,
            "brecha_id": rb.id,
            "tipo_brecha": rb.tipo_brecha,
            "estado_validacion": rb.estado_validacion,
            "metricas": {c: v for c, v in sorted(metricas.items())},
            "versiones_formula": {c: v for c, v in sorted(versiones.items())},
            "procedencias_metricas": {
                c: v for c, v in sorted(procedencias_metricas.items())
            },
        })

    return {
        "run": {"id": run.id, "procedencia": run.procedencia},
        "catalogo": {c: f.dict() for c, f in CATALOGO.items()},
        "articulos": articulos,
    }


def _renovaciones_por_resultados(db: Session, horas: int = 24) -> dict:
    """Renovaciones deducidas de los resultados guardados.

    Respaldo para cuando el registro de llamadas aun no tiene datos. Es menos
    fiel —no ve los intentos fallidos— pero permite dar una cuenta atras en
    lugar de no dar ninguna.
    """
    from sqlalchemy import func as F, select

    try:
        ahora = db.execute(select(F.now())).scalar()
    except Exception:
        return {"disponible": False, "ahora": None, "eventos": []}
    if ahora is None:
        return {"disponible": False, "ahora": None, "eventos": []}

    desde = registro_api.corte(horas)
    marcas = [r[0] for r in
              db.query(ResultadoBrecha.created_at)
              .filter(ResultadoBrecha.created_at >= desde).all() if r[0]]
    marcas += [r[0] for r in
               db.query(EstadoDelArte.created_at)
               .filter(EstadoDelArte.created_at >= desde).all() if r[0]]
    marcas.sort()

    eventos = []
    for i, m in enumerate(marcas[:40], start=1):
        vence = m + timedelta(hours=horas)
        eventos.append({
            "momento": vence.isoformat(),
            "segundos": max(0, int((vence - ahora).total_seconds())),
            "recupera": 1,
            "acumulado": i,
        })
    return {"disponible": True, "ahora": ahora.isoformat(), "eventos": eventos}


def _consumo(db: Session, proyecto_id: str | None):
    """Consumo de API, para no chocar con la cuota sin avisar.

    La cuota es de la clave, no del proyecto: se comparte entre todos. Por eso
    el recuento es global y solo el coste de una ejecución depende del
    proyecto, que es lo que varía con su número de artículos.

    El nivel gratuito permite 20 generaciones al día. Cada análisis gasta una
    por artículo más una para la síntesis, de modo que un proyecto de cinco
    artículos consume seis. Sin este recuento, el límite se descubre a mitad
    de una ejecución y el trabajo se pierde.
    """
    # El corte se calcula con el reloj de la base, no con el de Python: las
    # marcas se escriben en hora local del servidor y compararlas contra UTC
    # expulsaba registros de la ventana antes de tiempo.
    desde = registro_api.corte(24)

    # Fuente preferente: el registro de llamadas, que anota tambien las
    # fallidas. Contar solo los resultados guardados dejaba fuera los
    # intentos con error, que consumen cuota igualmente, y el indicador se
    # quedaba corto justo tras una racha de 429.
    registrado = registro_api.consumo(horas=24)
    if registrado.get("disponible") and registrado.get("generaciones"):
        generaciones = registrado["generaciones"]
        fallidas = registrado["fallidas"]
        embeddings = registrado["embeddings"]
        fuente = "registro de llamadas"
    else:
        brechas_hoy = (db.query(ResultadoBrecha)
                       .filter(ResultadoBrecha.created_at >= desde).count())
        sintesis_hoy = (db.query(EstadoDelArte)
                        .filter(EstadoDelArte.created_at >= desde).count())
        generaciones = brechas_hoy + sintesis_hoy
        fallidas = 0
        embeddings = 0
        fuente = "resultados guardados"

    LIMITE_DIARIO = limitador.LIMITE_GENERACION_DIA
    restantes = max(0, LIMITE_DIARIO - generaciones)

    # Reinicio del proveedor: sus cuotas diarias vuelven a cero de golpe a
    # medianoche del huso que rotula su panel, no llamada a llamada. Es una
    # referencia distinta de nuestra ventana movil y conviene dar las dos.
    ahora_utc = datetime.now(timezone.utc)
    reinicio = limitador.proximo_reinicio_diario(ahora_utc)

    # Momento exacto en que cada llamada sale de la ventana y devuelve margen.
    reno = registro_api.renovaciones(horas=24)
    if not reno.get("disponible") or not reno.get("eventos"):
        reno = _renovaciones_por_resultados(db)

    salida = {
        "ambito": "clave de API",
        "ventana": "ultimas 24 horas",
        "generaciones_estimadas": generaciones,
        "limite_diario_nivel_gratuito": LIMITE_DIARIO,
        "restantes_estimadas": restantes,
        # El reloj del servidor viaja con la respuesta para que la cuenta
        # atras se descuente contra el, y no contra el del navegador.
        "ahora_servidor": reno.get("ahora"),
        "renovaciones": reno.get("eventos", []),
        # Referencia del proveedor, que es la que manda.
        "reinicio_proveedor": {
            "momento_utc": reinicio.isoformat(),
            "segundos": limitador.segundos_hasta_reinicio(ahora_utc),
            "huso": "UTC%+d" % limitador.HUSO_REINICIO,
            "detalle": ("El panel de AI Studio rotula sus graficas en UTC%+d, de "
                        "modo que la cuota diaria vuelve a cero a la medianoche "
                        "de ese huso, toda de golpe."
                        % limitador.HUSO_REINICIO),
        },
    }

    # Lo unico que depende del proyecto es cuanto costaria analizarlo, porque
    # varia con su numero de articulos. El consumo y la cuota son de la clave
    # y se comparten entre todos los proyectos.
    if proyecto_id:
        n_articulos = (db.query(Articulo)
                       .filter(Articulo.proyecto_id == proyecto_id).count())
        # Una llamada por articulo para analizarlo, otra para verificar su
        # fidelidad si esta activada, y una final para la sintesis.
        verifica = verificacion.VERIFICAR
        coste_ejecucion = n_articulos * (2 if verifica else 1) + 1
        runs = db.query(Run).filter(Run.proyecto_id == proyecto_id).all()

        # Cuando habra margen para una ejecucion entera: hace falta que
        # caduquen tantas llamadas como falten para cubrir su coste.
        faltan = max(0, coste_ejecucion - restantes)
        espera = None
        if faltan:
            for ev in salida.get("renovaciones", []):
                if ev["acumulado"] >= faltan:
                    espera = {"momento": ev["momento"], "segundos": ev["segundos"]}
                    break

        salida.update({
            "proyecto_id": proyecto_id,
            "coste_de_una_ejecucion": coste_ejecucion,
            "alcanza_para_otra_ejecucion": restantes >= coste_ejecucion,
            "generaciones_que_faltan": faltan,
            "disponible_para_ejecucion_en": espera,
            "tokens_acumulados": {
                "entrada": sum(r.tokens_in or 0 for r in runs),
                "salida": sum(r.tokens_out or 0 for r in runs),
            },
            # Desglose explicito: sin el, "cuesta 6" no dice de donde sale ese 6.
            "desglose": [
                {
                    "concepto": "Analisis de cada articulo",
                    "cantidad": n_articulos,
                    "detalle": ("Una llamada por articulo. Es la que lee los "
                                "fragmentos recuperados y produce la brecha, la "
                                "oportunidad, el tipo y el resumen."),
                },
                *([{
                    "concepto": "Verificacion de fidelidad",
                    "cantidad": n_articulos,
                    "detalle": ("Una llamada por articulo. Descompone la brecha en "
                                "afirmaciones y comprueba cuales se sostienen en "
                                "los fragmentos. Puede desactivarse con "
                                "VERIFICAR_FIDELIDAD=0."),
                }] if verifica else []),
                {
                    "concepto": "Sintesis del estado del arte",
                    "cantidad": 1,
                    "detalle": ("Una sola llamada al final, que redacta el estado "
                                "del arte a partir de todas las brechas del lote."),
                },
            ],
        })

    salida["no_cuentan"] = [
        {
            "concepto": "Indexacion de los PDF (embeddings)",
            "detalle": ("Usa otro modelo y por tanto otra cuota: %d peticiones por "
                        "minuto y %d al dia, contadas aparte de las generaciones. "
                        "Ademas la indexacion es idempotente, asi que un articulo "
                        "ya indexado no se vuelve a procesar ni se vuelve a pagar."
                        % (limitador.LIMITE_EMBEDDINGS_MIN,
                           limitador.LIMITE_EMBEDDINGS_DIA)),
        },
        {
            "concepto": "Metricas locales",
            "detalle": ("Los niveles N1, N3 y N4 se calculan con los embeddings ya "
                        "generados, sin ninguna llamada adicional."),
        },
    ]
    salida["fuente"] = fuente
    salida["generaciones_fallidas"] = fallidas
    salida["embeddings_ventana"] = embeddings
    # Se declara explicitamente el alcance del recuento. Un contador que se
    # presenta como exacto sin serlo lleva a decisiones equivocadas, que es
    # justo el problema que este proyecto vino a corregir.
    salida["exactitud"] = {
        "cuenta": (
            "Todas las llamadas hechas por esta aplicacion, incluidas las "
            "que fallaron: un intento con error consume cuota igual."
            if fuente == "registro de llamadas" else
            "Solo los resultados guardados. Las llamadas fallidas no se "
            "contabilizan, asi que el consumo real puede ser mayor."
        ),
        "no_cuenta": [
            "Llamadas de otras aplicaciones que usen la misma clave.",
            "Llamadas anteriores a la puesta en marcha de este registro.",
        ],
        "ventana": (
            "Se miden las ultimas 24 horas moviles. El proveedor reinicia "
            "su cuota a una hora fija, de modo que el momento de "
            "renovacion puede no coincidir."
        ),
        "ambito": (
            "La cuota pertenece a la clave de API y se comparte entre todos "
            "los proyectos: lo que consume uno resta a los demas."
        ),
        "cuenta_atras": (
            "La cuenta atras es exacta respecto a la ventana movil de 24 horas "
            "que lleva esta aplicacion, calculada con el reloj de la base de "
            "datos. El proveedor aplica su propio criterio de reinicio y no lo "
            "indica en la respuesta de error, asi que puede renovar antes."
        ),
        "fuente_oficial": "ai.dev/rate-limit",
    }
    return salida


@router.get("/{proyecto_id}/consumo")
def consumo_de_proyecto(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    """Consumo global mas el coste de analizar este proyecto."""
    return _consumo(db, proyecto.id)


@router_global.get("/consumo")
def consumo_global(
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    """Consumo de la clave de API, sin atarlo a ningun proyecto.

    El numero es deliberadamente global y no por usuario: la cuota es de la
    clave de Gemini y se reparte entre todos los de la instancia, asi que lo
    util es saber cuanto queda en total. Pide sesion igual —no tiene por que
    verlo cualquiera que llegue al backend—, pero no revela nada de otras
    cuentas: solo un total de llamadas.
    """
    return _consumo(db, None)
