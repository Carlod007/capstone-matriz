# app/dependencias.py
"""
Dependencias compartidas de FastAPI.

`usuario_actual` es la que sostiene el aislamiento entre cuentas: cualquier
endpoint que la declare queda cerrado a quien no traiga un token valido.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.services.seguridad import TokenInvalido, leer_token

# auto_error=False para responder 401 con nuestro mensaje y con la cabecera
# WWW-Authenticate: sin ella el navegador no sabe que debe reautenticar.
_portador = HTTPBearer(auto_error=False)

_NO_AUTORIZADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sesion no valida o caducada. Vuelve a iniciar sesion.",
    headers={"WWW-Authenticate": "Bearer"},
)


def usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_portador),
    db: Session = Depends(get_db),
) -> Usuario:
    """El usuario del token, o 401.

    El motivo del rechazo —sin cabecera, token alterado, caducado, cuenta
    desactivada— no se distingue por fuera. Contar cual de ellos fue le dice a
    quien prueba tokens si va por buen camino.
    """
    if credenciales is None or not credenciales.credentials:
        raise _NO_AUTORIZADO

    try:
        usuario_id = leer_token(credenciales.credentials)
    except TokenInvalido:
        raise _NO_AUTORIZADO from None

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if usuario is None or not usuario.activo:
        # El token es legitimo pero la cuenta ya no existe o esta desactivada.
        raise _NO_AUTORIZADO

    return usuario
