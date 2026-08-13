import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencias import proyecto_propio, usuario_actual
from app.models.proyecto import Proyecto
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

@router.get("", response_model=list[ProyectoOut])
def listar_proyectos(
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    # El filtro por dueño va en la consulta. Un proyecto sin dueño —de antes
    # de que existieran las cuentas— tampoco aparece aquí: no es de nadie.
    return (db.query(Proyecto)
              .filter(Proyecto.usuario_id == usuario.id)
              .order_by(Proyecto.creado_en.desc())
              .all())


@router.get("/{proyecto_id}", response_model=ProyectoOut)
def obtener_proyecto(proyecto: Proyecto = Depends(proyecto_propio)):
    """Un proyecto suelto, para que el frontend pueda entrar por su URL.

    Hasta ahora la única forma de conocer un proyecto era listarlos todos;
    con rutas propias en el frontend hace falta poder pedir uno por su
    identificador.
    """
    return proyecto
