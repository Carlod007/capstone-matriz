import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.proyecto import Proyecto
from app.schemas.proyecto import ProyectoCreate, ProyectoOut

router = APIRouter(prefix="/proyectos", tags=["proyectos"])

@router.post("", response_model=ProyectoOut)
def crear_proyecto(payload: ProyectoCreate, db: Session = Depends(get_db)):
    nuevo = Proyecto(
        id=str(uuid.uuid4()),
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
def listar_proyectos(db: Session = Depends(get_db)):
    return db.query(Proyecto).order_by(Proyecto.creado_en.desc()).all()
