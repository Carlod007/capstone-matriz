from pydantic import BaseModel
from typing import Optional, List

class RunCreate(BaseModel):
    # futuro: flags (usar_ocr, usar_crossref, etc.)
    pass

class RunOut(BaseModel):
    id: str
    proyecto_id: str
    estado: str
    n_items_total: int
    n_items_ok: int
    class Config:
        from_attributes = True

class RunItemOut(BaseModel):
    id: str
    articulo_id: str
    estado: str
    class Config:
        from_attributes = True
