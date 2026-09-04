from pydantic import BaseModel, Field


class EtiquetaN26In(BaseModel):
    ya_resuelta: bool
    justificacion: str = Field(min_length=1, max_length=4000)
