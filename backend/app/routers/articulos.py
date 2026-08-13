from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencias import proyecto_propio
from app.models.articulo import Articulo
from app.models.proyecto import Proyecto
from app.schemas.articulo import ArticuloOut

router = APIRouter(prefix="/proyectos", tags=["articulos"])

@router.get("/{proyecto_id}/articulos", response_model=list[ArticuloOut])
def listar_articulos(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    # La dependencia ya resolvió el proyecto y comprobó el dueño; si no fuera
    # suyo, la petición no habría llegado hasta aquí.
    return (db.query(Articulo)
              .filter(Articulo.proyecto_id == proyecto.id)
              .order_by(Articulo.creado_en.asc())
              .all())
