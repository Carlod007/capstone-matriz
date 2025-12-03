from pydantic import BaseModel

class ArticuloOut(BaseModel):
    id: str
    titulo: str | None
    doi: str | None
    class Config:
        from_attributes = True
