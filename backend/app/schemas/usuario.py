from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegistroIn(BaseModel):
    correo: EmailStr
    nombre: str = Field(min_length=2, max_length=120)
    # El minimo real lo impone seguridad.revisar_contrasena; aqui se repite
    # para que el error llegue como 422 con el campo senalado, en vez de como
    # una excepcion generica del servicio.
    contrasena: str = Field(min_length=8, max_length=72)

    @field_validator("correo")
    @classmethod
    def normalizar(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("nombre")
    @classmethod
    def limpiar(cls, v: str) -> str:
        return v.strip()


class LoginIn(BaseModel):
    correo: EmailStr
    contrasena: str

    @field_validator("correo")
    @classmethod
    def normalizar(cls, v: str) -> str:
        return v.strip().lower()


class UsuarioOut(BaseModel):
    """Lo unico que sale de un usuario.

    Se declaran los campos uno a uno en lugar de volcar el modelo: asi
    contrasena_hash no puede colarse en una respuesta por haber anadido un
    campo al modelo y haberse olvidado de este archivo.
    """

    id: str
    correo: str
    nombre: str
    creado_en: datetime | None = None

    class Config:
        from_attributes = True


class SesionOut(BaseModel):
    token: str
    tipo: str = "bearer"
    expira_en_horas: int
    usuario: UsuarioOut
