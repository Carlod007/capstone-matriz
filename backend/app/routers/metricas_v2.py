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

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.articulo import Articulo
from app.models.estado_arte import EstadoDelArte
from app.models.metrica import Metrica
from app.models.proyecto import Proyecto
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run import Run, EstadoRun
from app.models.run_item import RunItem
from app.services import registro_api
from app.services.metricas import distribucion as D
from app.services.metricas.catalogo import CATALOGO, ficha

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
def metricas_proyecto(proyecto_id: str, db: Session = Depends(get_db)):
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
    referencias = set(ids_brecha) | set(ids_articulo) | {run.id}

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

    valores: dict[str, list] = {}
    for m in ultima.values():
        valores.setdefault(m.codigo, []).append(m.valor)

    salida = []
    for codigo in sorted(valores):
        d = D.describir(codigo, valores[codigo])
        f = ficha(codigo)
        salida.append({
            **d.dict(),
            "nombre": f.nombre if f else codigo,
            "nivel": f.nivel if f else "",
            "ambito": f.ambito if f else "",
            "mejor": f.mejor if f else "neutro",
            "rango": f.rango if f else "",
            "descripcion": f.descripcion if f else "",
            "interpretacion": f.interpretacion if f else "",
        })

    estados = {}
    for (e,) in (db.query(ResultadoBrecha.estado_validacion)
                 .filter(ResultadoBrecha.id.in_(ids_brecha or ["-"])).all()):
        estados[e or ""] = estados.get(e or "", 0) + 1

    ea = (db.query(EstadoDelArte)
          .filter(EstadoDelArte.proyecto_id == proyecto_id)
          .order_by(EstadoDelArte.version.desc()).first())

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
def metricas_por_articulo(proyecto_id: str, db: Session = Depends(get_db)):
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
    for m in (db.query(Metrica)
              .filter(Metrica.proyecto_id == proyecto_id)
              .order_by(Metrica.creado_en.asc()).all()):
        por_referencia.setdefault(m.referencia_id, {})[m.codigo] = m.valor

    articulos = []
    for rb, ri, art in filas:
        metricas = dict(por_referencia.get(rb.id, {}))
        metricas.update(por_referencia.get(art.id, {}))
        articulos.append({
            "articulo_id": art.id,
            "titulo": art.titulo,
            "doi": art.doi,
            "brecha_id": rb.id,
            "tipo_brecha": rb.tipo_brecha,
            "estado_validacion": rb.estado_validacion,
            "metricas": {c: v for c, v in sorted(metricas.items())},
        })

    return {
        "run": {"id": run.id},
        "catalogo": {c: f.dict() for c, f in CATALOGO.items()},
        "articulos": articulos,
    }


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

    LIMITE_DIARIO = 20
    restantes = max(0, LIMITE_DIARIO - generaciones)

    salida = {
        "ambito": "clave de API",
        "ventana": "ultimas 24 horas",
        "generaciones_estimadas": generaciones,
        "limite_diario_nivel_gratuito": LIMITE_DIARIO,
        "restantes_estimadas": restantes,
    }

    # Lo unico que depende del proyecto es cuanto costaria analizarlo, porque
    # varia con su numero de articulos. El consumo y la cuota son de la clave
    # y se comparten entre todos los proyectos.
    if proyecto_id:
        n_articulos = (db.query(Articulo)
                       .filter(Articulo.proyecto_id == proyecto_id).count())
        coste_ejecucion = n_articulos + 1
        runs = db.query(Run).filter(Run.proyecto_id == proyecto_id).all()
        salida.update({
            "proyecto_id": proyecto_id,
            "coste_de_una_ejecucion": coste_ejecucion,
            "alcanza_para_otra_ejecucion": restantes >= coste_ejecucion,
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
            "detalle": ("Tiene su propia cuota, limitada por minuto y no por dia. "
                        "Ademas la indexacion es idempotente: un articulo ya "
                        "indexado no se vuelve a procesar ni se vuelve a pagar."),
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
        "fuente_oficial": "ai.dev/rate-limit",
    }
    return salida


@router.get("/{proyecto_id}/consumo")
def consumo_de_proyecto(proyecto_id: str, db: Session = Depends(get_db)):
    """Consumo global mas el coste de analizar este proyecto."""
    return _consumo(db, proyecto_id)


@router_global.get("/consumo")
def consumo_global(db: Session = Depends(get_db)):
    """Consumo de la clave de API, sin atarlo a ningun proyecto."""
    return _consumo(db, None)
