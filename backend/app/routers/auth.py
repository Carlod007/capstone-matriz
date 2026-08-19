# app/routers/auth.py
"""Alta de cuenta, inicio de sesion y quien soy."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import JWT_HORAS, JWT_MAXIMO_HORAS, REGISTRO_ABIERTO
from app.database import get_db
from app.dependencias import usuario_actual
from app.models.usuario import Usuario
from app.schemas.usuario import LoginIn, RegistroIn, SesionOut, UsuarioOut
from app.services import seguridad

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash de descarte con el que comparar cuando el correo no existe. Sin esto,
# un correo desconocido responde de inmediato y uno registrado tarda lo que
# tarda bcrypt: la diferencia de tiempo revela que cuentas existen.
_HASH_SENUELO = seguridad.cifrar("contrasena de relleno para igualar tiempos")

_CREDENCIALES_MALAS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Correo o contrasena incorrectos.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _sesion(usuario: Usuario) -> SesionOut:
    return SesionOut(
        token=seguridad.emitir_token(usuario.id),
        expira_en_horas=JWT_HORAS,
        usuario=UsuarioOut.model_validate(usuario),
    )


@router.post("/registro", response_model=SesionOut, status_code=201)
def registrar(datos: RegistroIn, db: Session = Depends(get_db)):
    """Crea una cuenta. Cerrado salvo que REGISTRO_ABIERTO diga lo contrario.

    La instancia es de una sola persona por ahora, y la cuota de la API de
    Gemini es de la clave, no del usuario: una cuenta de mas es cuota de menos
    para todas las demas.
    """
    if not REGISTRO_ABIERTO:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El registro esta cerrado en esta instancia.",
        )

    if db.query(Usuario).filter(Usuario.correo == datos.correo).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese correo.",
        )

    try:
        hash_ = seguridad.cifrar(datos.contrasena)
    except seguridad.ContrasenaInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    usuario = Usuario(
        id=str(uuid.uuid4()),
        correo=datos.correo,
        contrasena_hash=hash_,
        nombre=datos.nombre,
        activo=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return _sesion(usuario)


@router.post("/login", response_model=SesionOut)
def iniciar_sesion(datos: LoginIn, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.correo == datos.correo).first()

    # Se comprueba siempre, exista o no la cuenta, para que las dos ramas
    # cuesten lo mismo.
    valida = seguridad.comprobar(
        datos.contrasena,
        usuario.contrasena_hash if usuario else _HASH_SENUELO,
    )

    if usuario is None or not valida or not usuario.activo:
        raise _CREDENCIALES_MALAS

    return _sesion(usuario)


@router.get("/yo", response_model=UsuarioOut)
def quien_soy(usuario: Usuario = Depends(usuario_actual)):
    """Para que el frontend sepa si el token guardado sigue sirviendo."""
    return usuario


@router.post("/renovar", response_model=SesionOut)
def renovar(usuario: Usuario = Depends(usuario_actual),
            autorizacion: str | None = Header(None, alias="Authorization")):
    """Alarga la sesion de quien la esta usando, sin volver a pedir la clave.

    A las ocho horas la sesion caducaba en seco. Si eso pasaba a mitad de un
    formulario, se perdia lo escrito: la aplicacion no puede distinguir «se fue
    hace ocho horas» de «lleva ocho horas trabajando».

    Dos limites, y los dos importan:

    - Se exige un token todavia valido. Renovar uno caducado seria no caducar
      nunca. De eso se encarga `usuario_actual`, la misma dependencia que
      protege el resto de la aplicacion: autenticar a mano aqui habria dejado
      esta ruta fuera de la comprobacion que exige que todas la declaren.
    - No se pasa del techo absoluto contado desde que se escribio la
      contrasena. Sin el, la renovacion continua volveria permanente cualquier
      token filtrado, y aqui no hay forma de revocar uno.

    La cabecera se vuelve a leer solo para recuperar `ini`, que la dependencia
    no expone porque al resto de la aplicacion no le hace falta.
    """
    try:
        datos = seguridad.datos_token(
            (autorizacion or "").split(" ", 1)[1].strip())
        inicio = seguridad.inicio_de_sesion(datos)
    except (IndexError, seguridad.TokenInvalido):
        raise _CREDENCIALES_MALAS from None

    if datetime.now(timezone.utc) - inicio >= timedelta(hours=JWT_MAXIMO_HORAS):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesion alcanzo su duracion maxima. Vuelve a entrar.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # El inicio original viaja al token nuevo: es lo que impide que renovar
    # una y otra vez alargue la sesion indefinidamente.
    return SesionOut(
        token=seguridad.emitir_token(usuario.id, inicio_sesion=inicio),
        expira_en_horas=JWT_HORAS,
        usuario=UsuarioOut.model_validate(usuario),
    )
