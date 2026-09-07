import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencias import proyecto_propio, usuario_actual
from app.models.archivo import Archivo
from app.models.articulo import Articulo
from app.models.estado_arte import EstadoDelArte
from app.models.proyecto import Proyecto
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run import EstadoRun, Run
from app.models.run_item import RunItem
from app.models.usuario import Usuario
from app.schemas.proyecto import ProyectoCreate, ProyectoOut
from app.services import almacenamiento
from app.services.estado_proceso import GENERANDO_ESTADO_ARTE, fase_run

router = APIRouter(prefix="/proyectos", tags=["proyectos"])

@router.post("", response_model=ProyectoOut)
def crear_proyecto(
    payload: ProyectoCreate,
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    nuevo = Proyecto(
        id=str(uuid.uuid4()),
        usuario_id=usuario.id,
        tema_principal=payload.tema_principal,
        objetivo=payload.objetivo,
        metodologia_txt=payload.metodologia_txt,
        sector_txt=payload.sector_txt,
        n_articulos_objetivo=payload.n_articulos_objetivo,
        estado_arte_generado=False,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

def _resumen(db: Session, proyectos: list[Proyecto]) -> list[ProyectoOut]:
    """Añade a cada proyecto sus recuentos, con consultas agrupadas.

    Está fuera de los endpoints para que la lista y el proyecto suelto den la
    misma respuesta. Cuando esto vivía dentro del listado, `GET /proyectos/{id}`
    devolvía los valores por defecto —cero artículos, cero brechas y sin estado
    del arte— para proyectos que sí los tenían: el mismo esquema mentía o no
    según por qué puerta se pidiera.
    """
    if not proyectos:
        return []

    ids = [p.id for p in proyectos]

    # Agrupadas y no una por proyecto: la pantalla del listado pedía antes los
    # artículos y el estado del arte de cada uno por separado, tantas
    # peticiones como tarjetas cada vez que se abría.
    articulos = dict(
        db.query(Articulo.proyecto_id, func.count(Articulo.id))
          .filter(Articulo.proyecto_id.in_(ids))
          .group_by(Articulo.proyecto_id)
          .all()
    )

    # Artículos con brecha, no brechas en bruto: cada análisis añade una nueva
    # y conserva las anteriores, así que la suma directa crecería al reanalizar
    # aunque el proyecto siguiera teniendo los mismos artículos.
    #
    # Ojo al leer esta cifra: NO es el número de filas de la matriz exportada.
    # Esa devuelve hoy una fila por cada brecha histórica, así que un proyecto
    # reanalizado tiene más filas que artículos con brecha. Son dos preguntas
    # distintas —cuántos artículos han dado brecha, y cuántos análisis se han
    # acumulado— y conviene no confundirlas.
    brechas = dict(
        db.query(Run.proyecto_id,
                 func.count(distinct(RunItem.articulo_id)))
          .join(RunItem, RunItem.run_id == Run.id)
          .join(ResultadoBrecha, ResultadoBrecha.run_item_id == RunItem.id)
          .filter(Run.proyecto_id.in_(ids))
          .group_by(Run.proyecto_id)
          .all()
    )

    # De la tabla, no de `proyecto.estado_arte_generado`: esa columna se
    # escribe `False` al crear el proyecto y nadie la actualiza cuando la
    # síntesis se genera, así que es siempre falsa. La pantalla lo resolvía
    # pidiendo /estado_arte/latest de cada proyecto y mirando si respondía.
    estados_arte = db.query(
        EstadoDelArte.proyecto_id, EstadoDelArte.run_id
    ).filter(EstadoDelArte.proyecto_id.in_(ids)).all()
    con_estado_arte = {proyecto_id for proyecto_id, _ in estados_arte}
    runs_con_estado_arte = {run_id for _, run_id in estados_arte}

    # Puede haber una ejecución de análisis activa por proyecto. Mientras la
    # haya, esa es la etapa actual aunque exista una síntesis histórica.
    activos = {}
    for run in (db.query(Run)
                  .filter(Run.proyecto_id.in_(ids),
                          Run.estado.in_((EstadoRun.creado,
                                          EstadoRun.en_progreso)))
                  .order_by(Run.iniciado_en.desc(), Run.id.desc())
                  .all()):
        activos.setdefault(run.proyecto_id, run)

    # Solo hace falta el último completado por proyecto. ROW_NUMBER evita
    # traer todo el historial a Python cuando un proyecto se ha reanalizado.
    orden = func.row_number().over(
        partition_by=Run.proyecto_id,
        order_by=(Run.finalizado_en.desc(), Run.id.desc()),
    ).label("orden")
    completados_ordenados = (
        db.query(Run.id.label("run_id"), orden)
          .filter(Run.proyecto_id.in_(ids),
                  Run.estado == EstadoRun.completado)
          .subquery()
    )
    ultimos_completados = {
        run.proyecto_id: run
        for run in (db.query(Run)
                      .join(completados_ordenados,
                            completados_ordenados.c.run_id == Run.id)
                      .filter(completados_ordenados.c.orden == 1)
                      .all())
    }

    def estado_actual(proyecto_id: str) -> tuple[str, bool]:
        run = activos.get(proyecto_id) or ultimos_completados.get(proyecto_id)
        if run is None:
            return "sin_analizar", False
        tiene_actual = run.id in runs_con_estado_arte
        return fase_run(run, tiene_actual), tiene_actual

    salida = []
    for p in proyectos:
        estado_proceso, tiene_actual = estado_actual(p.id)
        salida.append(ProyectoOut(
            id=p.id,
            tema_principal=p.tema_principal,
            n_articulos_objetivo=p.n_articulos_objetivo,
            estado_arte_generado=bool(p.estado_arte_generado),
            tiene_estado_arte=p.id in con_estado_arte,
            tiene_estado_arte_actual=tiene_actual,
            estado_proceso=estado_proceso,
            n_articulos=articulos.get(p.id, 0),
            n_brechas=brechas.get(p.id, 0),
        ))
    return salida


@router.get("", response_model=list[ProyectoOut])
def listar_proyectos(
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    # El filtro por dueño va en la consulta. Un proyecto sin dueño —de antes
    # de que existieran las cuentas— tampoco aparece aquí: no es de nadie.
    return _resumen(db, (db.query(Proyecto)
                           .filter(Proyecto.usuario_id == usuario.id)
                           .order_by(Proyecto.creado_en.desc())
                           .all()))


@router.get("/{proyecto_id}", response_model=ProyectoOut)
def obtener_proyecto(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    """Un proyecto suelto, para que el frontend pueda entrar por su URL.

    Hasta ahora la única forma de conocer un proyecto era listarlos todos;
    con rutas propias en el frontend hace falta poder pedir uno por su
    identificador.
    """
    return _resumen(db, [proyecto])[0]


@router.delete("/{proyecto_id}")
def borrar_proyecto(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    """Elimina un proyecto propio, sus datos derivados y sus PDF.

    La base resuelve casi todo por cascada. Los archivos físicos se eliminan
    después de confirmar la transacción: si la base rechazara el borrado, los
    PDF seguirían disponibles en vez de dejar filas que apuntan a nada.
    """
    proyecto_id = proyecto.id
    activo = (db.query(Run.id)
                .filter(Run.proyecto_id == proyecto.id,
                        Run.estado.in_((EstadoRun.creado,
                                        EstadoRun.en_progreso)))
                .first())
    if activo:
        raise HTTPException(
            status_code=409,
            detail="El proyecto tiene un análisis en curso. Espera a que "
                   "termine antes de eliminarlo.",
        )

    # La síntesis ocurre después de cerrar el run. También se protege ese
    # intervalo: borrar el proyecto mientras el trabajador está escribiendo el
    # estado del arte haría que intentara guardar sobre un proyecto inexistente.
    ultimo = (db.query(Run)
                .filter(Run.proyecto_id == proyecto.id,
                        Run.estado == EstadoRun.completado)
                .order_by(Run.finalizado_en.desc(), Run.id.desc())
                .first())
    if ultimo:
        tiene_sintesis = db.query(EstadoDelArte.id).filter(
            EstadoDelArte.run_id == ultimo.id).first() is not None
        if fase_run(ultimo, tiene_sintesis) == GENERANDO_ESTADO_ARTE:
            raise HTTPException(
                status_code=409,
                detail="El proyecto está generando el estado del arte. "
                       "Espera a que termine antes de eliminarlo.",
            )

    rutas_pdf = [ruta for (ruta,) in db.query(Archivo.ruta)
                                         .filter(Archivo.proyecto_id == proyecto.id)
                                         .all()]

    # estado_arte apunta a run con RESTRICT. Se retira primero de forma
    # explícita; el resto cuelga del proyecto mediante CASCADE.
    (db.query(EstadoDelArte)
       .filter(EstadoDelArte.proyecto_id == proyecto.id)
       .delete(synchronize_session=False))
    db.delete(proyecto)
    db.commit()

    no_borrados = 0
    for ruta in rutas_pdf:
        try:
            almacenamiento.borrar(ruta)
        except Exception:  # noqa: BLE001
            # La base ya no menciona el PDF. Se informa el residuo para que no
            # parezca que todo salió perfecto si el disco rechazó el borrado.
            no_borrados += 1

    return {
        "proyecto_id": proyecto_id,
        "borrado": True,
        "pdf_no_borrados": no_borrados,
    }
