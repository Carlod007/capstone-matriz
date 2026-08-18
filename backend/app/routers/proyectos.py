import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencias import proyecto_propio, usuario_actual
from app.models.articulo import Articulo
from app.models.estado_arte import EstadoDelArte
from app.models.proyecto import Proyecto
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run import Run
from app.models.run_item import RunItem
from app.models.usuario import Usuario
from app.schemas.proyecto import ProyectoCreate, ProyectoOut

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
    con_estado_arte = {
        r[0] for r in db.query(EstadoDelArte.proyecto_id)
                        .filter(EstadoDelArte.proyecto_id.in_(ids))
                        .distinct()
    }

    return [
        ProyectoOut(
            id=p.id,
            tema_principal=p.tema_principal,
            n_articulos_objetivo=p.n_articulos_objetivo,
            estado_arte_generado=bool(p.estado_arte_generado),
            tiene_estado_arte=p.id in con_estado_arte,
            n_articulos=articulos.get(p.id, 0),
            n_brechas=brechas.get(p.id, 0),
        )
        for p in proyectos
    ]


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
