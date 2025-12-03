from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.articulo import Articulo
from app.schemas.articulo import ArticuloOut

router = APIRouter(prefix="/proyectos", tags=["articulos"])

@router.get("/{proyecto_id}/articulos", response_model=list[ArticuloOut])
def listar_articulos(proyecto_id: str, db: Session = Depends(get_db)):
    rows = db.query(Articulo).filter(Articulo.proyecto_id == proyecto_id).order_by(Articulo.creado_en.asc()).all()
    if rows is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado o sin artículos")
    return rows
