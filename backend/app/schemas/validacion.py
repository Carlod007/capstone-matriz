from pydantic import BaseModel, Field


class ValidacionIn(BaseModel):
    veredicto: str = Field(description="correcta | parcial | incorrecta")
    # Obligatoria para «parcial» e «incorrecta», y la comprueba el endpoint y
    # no el esquema: el motivo del rechazo forma parte de la regla de negocio
    # -un veredicto negativo sin explicacion no sirve para nada- y ahi se puede
    # decir por que en el mensaje de error.
    justificacion: str | None = None


class ValidacionOut(BaseModel):
    brecha_id: str
    veredicto: str
    justificacion: str | None
    resumen: dict
