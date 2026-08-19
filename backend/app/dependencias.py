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


# ------------------------------------------------------------------ cuota
def comprobar_cuota_usuario(usuario: Usuario) -> None:
    """Niega la operación si la cuenta agotó su reparto del día.

    Se comprueba ANTES de encolar, no cuando el proveedor responde con un
    error. Un análisis rechazado a mitad deja artículos en estados intermedios
    y consume las llamadas que sí llegaron a salir; decir que no antes de
    empezar no cuesta nada y se entiende.

    Sin límite configurado no comprueba nada: con una sola cuenta el techo
    real es el de la clave, y añadir un segundo tope solo serviría para
    bloquear antes de tiempo.
    """
    from app.services import limitador, registro_api

    tope = limitador.LIMITE_GENERACION_DIA_USUARIO
    if tope <= 0:
        return

    datos = registro_api.consumo(usuario_id=usuario.id)
    if not datos.get("disponible"):
        # Sin registro no se puede afirmar que haya gastado nada, y negar por
        # las dudas dejaría la aplicación inservible ante un fallo del contador.
        return

    gastadas = int(datos.get("generaciones") or 0)
    if gastadas >= tope:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=("Has consumido tu reparto diario (%d de %d generaciones). "
                    "La cuota es compartida entre las cuentas de esta "
                    "instancia y se restablece al día siguiente."
                    % (gastadas, tope)),
        )


# --------------------------------------------------------------- propiedad
#
# Casi todo cuelga de un proyecto: los articulos son de un proyecto, las
# ejecuciones tambien, las brechas de una ejecucion y las metricas de un
# proyecto. Basta entonces con resolver el proyecto y comprobar su dueno.
#
# Dos reglas que se siguen en todas las funciones de aqui:
#
# 1. El filtro por dueno va DENTRO de la consulta, no en un `if` posterior.
#    Un `if` se puede olvidar en una rama; un JOIN no devuelve la fila.
# 2. Lo ajeno responde 404, no 403. Un 403 confirma que ese identificador
#    existe, y eso ya es informacion: permite averiguar cuantos proyectos hay
#    y cuales, probando identificadores.

_NO_ENCONTRADO = HTTPException(status_code=404, detail="No encontrado.")


def _proyecto_de(db: Session, usuario: Usuario, proyecto_id: str):
    from app.models.proyecto import Proyecto

    pr = (db.query(Proyecto)
            .filter(Proyecto.id == proyecto_id,
                    Proyecto.usuario_id == usuario.id)
            .first())
    if pr is None:
        raise _NO_ENCONTRADO
    return pr


def proyecto_propio(
    proyecto_id: str,
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    """El proyecto de la ruta, si es de quien lo pide. Si no, 404."""
    return _proyecto_de(db, usuario, proyecto_id)


def articulo_propio(
    articulo_id: str,
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    """El articulo de la ruta, comprobando el dueno de su proyecto."""
    from app.models.articulo import Articulo
    from app.models.proyecto import Proyecto

    art = (db.query(Articulo)
             .join(Proyecto, Proyecto.id == Articulo.proyecto_id)
             .filter(Articulo.id == articulo_id,
                     Proyecto.usuario_id == usuario.id)
             .first())
    if art is None:
        raise _NO_ENCONTRADO
    return art


def run_propio(
    run_id: str,
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    """La ejecucion de la ruta, comprobando el dueno de su proyecto."""
    from app.models.proyecto import Proyecto
    from app.models.run import Run

    run = (db.query(Run)
             .join(Proyecto, Proyecto.id == Run.proyecto_id)
             .filter(Run.id == run_id, Proyecto.usuario_id == usuario.id)
             .first())
    if run is None:
        raise _NO_ENCONTRADO
    return run
