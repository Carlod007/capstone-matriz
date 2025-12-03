from pydantic import BaseModel, Field
from typing import Optional

class ProyectoCreate(BaseModel):
    tema_principal: str = Field(min_length=3, max_length=200)
    objetivo: str = Field(min_length=10, max_length=4000)
    metodologia_txt: Optional[str] = None
    sector_txt: Optional[str] = None
    n_articulos_objetivo: int

class ProyectoOut(BaseModel):
    id: str
    tema_principal: str
    n_articulos_objetivo: int
    estado_arte_generado: bool
    class Config:
        from_attributes = True
