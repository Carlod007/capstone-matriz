# tests/test_crear_cuenta.py
"""
Adopcion de los proyectos sin dueno al crear la primera cuenta.

El script no tenia pruebas y fallaba en su unico camino importante: la
actualizacion se ejecuta como SQL directo y no arrastra los objetos
pendientes de la sesion, asi que el UPDATE llegaba a la base antes que el
INSERT del usuario y la clave foranea reventaba.

Se prueba `adoptar_huerfanos`, que recibe si es la primera cuenta en lugar de
deducirlo contando usuarios. Cuando lo deducia dentro, la prueba dependia de
que la base no tuviera ninguna otra cuenta, y bastaba otra prueba de la suite
para desbaratarla.
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)

pytestmark = pytest.mark.bd


@pytest.fixture
def escenario(db):
    """Una cuenta y un proyecto sin dueno, ambos de usar y tirar.

    La adopcion alcanza a *todos* los proyectos sin dueno de la base, no solo
    al de esta prueba: en una base de desarrollo eso incluye los reales. La
    fixture anota cuales estaban sin dueno antes y los devuelve a ese estado
    al terminar. Sin esto, ejecutar la prueba dejaba los proyectos del usuario
    a nombre de una cuenta de mentira, que ademas no se podia borrar porque la
    clave foranea es RESTRICT.
    """
    from app.models.proyecto import Proyecto
    from app.models.usuario import Usuario
    from app.services import seguridad

    previos = [p[0] for p in db.query(Proyecto.id)
               .filter(Proyecto.usuario_id.is_(None)).all()]

    u = Usuario(id=str(uuid.uuid4()),
                correo="alta-%s@ejemplo.com" % uuid.uuid4().hex[:8],
                contrasena_hash=seguridad.cifrar("contrasena-de-prueba"),
                nombre="Prueba", activo=True)
    db.add(u)
    db.flush()

    pid = str(uuid.uuid4())
    db.add(Proyecto(id=pid, usuario_id=None, tema_principal="Sin dueno",
                    objetivo="Proyecto anterior a que existieran las cuentas",
                    n_articulos_objetivo=1, estado_arte_generado=False))
    db.commit()

    try:
        yield {"usuario_id": u.id, "proyecto_id": pid, "previos": previos}
    finally:
        db.rollback()
        if previos:
            (db.query(Proyecto).filter(Proyecto.id.in_(previos))
               .update({"usuario_id": None}, synchronize_session=False))
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.query(Usuario).filter(Usuario.id == u.id).delete()
        db.commit()


class TestAdopcion:
    def test_la_primera_cuenta_los_adopta(self, db, escenario):
        from crear_cuenta import adoptar_huerfanos
        from app.models.proyecto import Proyecto

        n = adoptar_huerfanos(db, escenario["usuario_id"], primera=True)
        db.commit()

        assert n >= 1
        fila = db.query(Proyecto).filter(Proyecto.id == escenario["proyecto_id"]).first()
        assert fila.usuario_id == escenario["usuario_id"]

    def test_una_cuenta_posterior_no_adopta_nada(self, db, escenario):
        """Adjudicar proyectos ajenos a quien pase por aqui seria entregarle
        datos que no son suyos."""
        from crear_cuenta import adoptar_huerfanos
        from app.models.proyecto import Proyecto

        n = adoptar_huerfanos(db, escenario["usuario_id"], primera=False)
        db.commit()

        assert n == 0
        fila = db.query(Proyecto).filter(Proyecto.id == escenario["proyecto_id"]).first()
        assert fila.usuario_id is None

    def test_el_usuario_debe_existir_antes(self, db, escenario):
        """Es el fallo que tuvo el script: sin el usuario en la base, la clave
        foranea rechaza la actualizacion."""
        from sqlalchemy.exc import IntegrityError

        from crear_cuenta import adoptar_huerfanos

        inexistente = str(uuid.uuid4())
        with pytest.raises(IntegrityError):
            adoptar_huerfanos(db, inexistente, primera=True)
            db.commit()
        db.rollback()
