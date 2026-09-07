from pydantic import BaseModel
from typing import Optional, List, Any

class RunCreate(BaseModel):
    # futuro: flags (usar_ocr, usar_crossref, etc.)
    pass

class RunOut(BaseModel):
    id: str
    proyecto_id: str
    estado: str
    n_items_total: int
    n_items_ok: int
    # Etapa visible, derivada de la ejecución y de su síntesis. Una ejecución
    # puede tener todos los artículos completos y seguir redactando el estado
    # del arte, por lo que `estado` por sí solo no basta para la interfaz.
    fase: str | None = None
    error_msg: str | None = None
    procedencia: dict[str, Any] | None = None
    class Config:
        from_attributes = True

class RunItemOut(BaseModel):
    id: str
    articulo_id: str
    estado: str
    class Config:
        from_attributes = True
