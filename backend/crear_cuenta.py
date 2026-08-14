"""
Crea una cuenta desde la terminal.

Existe porque el alta por HTTP esta cerrada (REGISTRO_ABIERTO=false) y hace
falta alguna forma de crear la primera. Abrir el registro un momento para
darse de alta y volver a cerrarlo funciona, pero deja una ventana en la que
cualquiera que alcance el servidor puede registrarse.

Ademas adopta los proyectos sin dueno: los creados antes de que existieran
las cuentas quedaron con usuario_id nulo y, por diseno, no los ve nadie.

    python crear_cuenta.py

La contrasena se pide sin mostrarla en pantalla y no se pasa por argumento:
los argumentos quedan en el historial de la terminal.
"""

import getpass
import sys
import uuid


def _preguntar(texto: str) -> str:
    try:
        return input(texto).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado.")
        sys.exit(1)


def adoptar_huerfanos(s, usuario_id: str, primera: bool) -> int:
    """Asigna a `usuario_id` los proyectos sin dueno. Devuelve cuantos.

    Solo si es la primera cuenta: con varias, adjudicarle los huerfanos a
    quien pase por aqui seria entregarle datos que quiza no son suyos.

    El usuario tiene que existir ya en la base al llamar a esto. La
    actualizacion se ejecuta como SQL directo y no arrastra los objetos
    pendientes de la sesion: sin un flush previo, el UPDATE llega antes que
    el INSERT y la clave foranea falla.
    """
    from app.models.proyecto import Proyecto
    from app.models.usuario import Usuario  # noqa: F401  (registra la tabla)

    if not primera:
        return 0
    return (s.query(Proyecto)
             .filter(Proyecto.usuario_id.is_(None))
             .update({"usuario_id": usuario_id}, synchronize_session=False))


def main() -> int:
    from app.config import revisar
    from app.database import SessionLocal
    from app.models.proyecto import Proyecto
    from app.models.usuario import Usuario
    from app.services import seguridad

    revisar()

    correo = _preguntar("Correo: ").lower()
    if "@" not in correo:
        print("Eso no parece un correo.")
        return 1

    nombre = _preguntar("Nombre: ")
    if len(nombre) < 2:
        print("El nombre es demasiado corto.")
        return 1

    try:
        clave = getpass.getpass("Contrasena (no se vera al escribir): ")
        repetida = getpass.getpass("Reptela: ")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado.")
        return 1

    if clave != repetida:
        print("Las contrasenas no coinciden.")
        return 1

    try:
        seguridad.revisar_contrasena(clave)
    except seguridad.ContrasenaInvalida as exc:
        print(exc)
        return 1

    s = SessionLocal()
    try:
        if s.query(Usuario).filter(Usuario.correo == correo).first():
            print("Ya existe una cuenta con ese correo.")
            return 1

        # Se cuentan antes de anadir nada: con la cuenta nueva ya en la sesion,
        # el autoflush la incluiria en el recuento y "primera" jamas seria
        # cierto.
        huerfanos = s.query(Proyecto).filter(Proyecto.usuario_id.is_(None)).count()
        primera = s.query(Usuario).count() == 0

        usuario = Usuario(id=str(uuid.uuid4()), correo=correo,
                          contrasena_hash=seguridad.cifrar(clave),
                          nombre=nombre, activo=True)
        s.add(usuario)
        # El flush es obligatorio, no una optimizacion: la actualizacion de
        # mas abajo se ejecuta como SQL directo y no arrastra consigo los
        # objetos pendientes. Sin el, el UPDATE llega a la base antes que el
        # INSERT y la clave foranea apunta a un usuario que todavia no
        # existe: "Cannot add or update a child row".
        s.flush()

        adoptados = adoptar_huerfanos(s, usuario.id, primera)

        s.commit()
    finally:
        s.close()

    print("\nCuenta creada: %s" % correo)
    if adoptados:
        print("Proyectos adoptados: %d" % adoptados)
    elif huerfanos:
        print("Hay %d proyecto(s) sin dueno, pero ya existian otras cuentas, "
              "asi que no se han asignado solos." % huerfanos)
    print("Ya puedes iniciar sesion desde la aplicacion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
