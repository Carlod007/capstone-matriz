# tests/test_cuota_por_usuario.py
"""
La cuota se reparte entre cuentas antes de gastarla.

Las veinte generaciones diarias del nivel gratuito son de la CLAVE de Gemini,
no del usuario. Con el registro abierto y sin reparto, unas pocas cuentas
desconocidas dejarian al dueno sin su dia antes del mediodia; por eso el alta
esta cerrada.

Repartir no crea capacidad, pero permite abrir el alta sin regalar el dia. El
limite por cuenta nace desactivado: con una sola persona el techo real es el de
la clave, y un segundo tope solo serviria para bloquear antes de tiempo.

La comprobacion va ANTES de encolar. Un lote rechazado a mitad deja articulos
en estados intermedios y ya habra gastado las llamadas que salieron.
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

pytestmark = pytest.mark.bd


@pytest.fixture(scope="module", autouse=True)
def modelos_cargados():
    import main  # noqa: F401


@pytest.fixture
def proyecto_con_gasto(db, usuario_prueba):
    """Un proyecto de la cuenta de pruebas con tres generaciones anotadas."""
    from app.models.articulo import Articulo
    from app.models.llamada_api import LlamadaAPI
    from app.models.proyecto import Proyecto

    pid, aid = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Reparto de cuota",
                    objetivo="Comprobar el limite por cuenta",
                    n_articulos_objetivo=1, estado_arte_generado=False))
    db.flush()
    db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="A"))
    for _ in range(3):
        db.add(LlamadaAPI(id=str(uuid.uuid4()), proyecto_id=pid,
                          operacion="analisis", exito=True, unidades=1))
    db.commit()
    try:
        yield {"proyecto": pid, "articulo": aid}
    finally:
        db.rollback()
        db.query(LlamadaAPI).filter(LlamadaAPI.proyecto_id == pid).delete(
            synchronize_session=False)
        db.query(Articulo).filter(Articulo.proyecto_id == pid).delete(
            synchronize_session=False)
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.commit()


class TestElRecuentoPorCuenta:
    def test_cuenta_solo_lo_de_esa_cuenta(self, db, proyecto_con_gasto,
                                          usuario_prueba):
        """Lo gastado por otra cuenta no puede contar contra esta."""
        from app.models.llamada_api import LlamadaAPI
        from app.models.proyecto import Proyecto
        from app.models.usuario import Usuario
        from app.services import registro_api, seguridad

        otro, pid_ajeno = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(Usuario(id=otro, correo="ajeno-%s@x.com" % otro[:8],
                       contrasena_hash=seguridad.cifrar("clave-de-la-otra"),
                       nombre="Otra", activo=True))
        db.flush()
        db.add(Proyecto(id=pid_ajeno, usuario_id=otro, tema_principal="Ajeno",
                        objetivo="Gasta de su parte", n_articulos_objetivo=1,
                        estado_arte_generado=False))
        db.flush()
        for _ in range(7):
            db.add(LlamadaAPI(id=str(uuid.uuid4()), proyecto_id=pid_ajeno,
                              operacion="analisis", exito=True, unidades=1))
        db.commit()

        try:
            mio = registro_api.consumo(usuario_id=usuario_prueba["id"])
            suyo = registro_api.consumo(usuario_id=otro)
            total = registro_api.consumo()

            assert mio["generaciones"] == 3
            assert suyo["generaciones"] == 7
            assert total["generaciones"] >= 10, (
                "el total sigue siendo el que manda frente al proveedor")
        finally:
            db.rollback()
            db.query(LlamadaAPI).filter(
                LlamadaAPI.proyecto_id == pid_ajeno).delete(
                synchronize_session=False)
            db.query(Proyecto).filter(Proyecto.id == pid_ajeno).delete()
            db.query(Usuario).filter(Usuario.id == otro).delete()
            db.commit()


class TestLaPuerta:
    def _usuario(self, db, usuario_prueba):
        from app.models.usuario import Usuario

        return db.query(Usuario).filter(
            Usuario.id == usuario_prueba["id"]).first()

    def test_sin_limite_configurado_no_bloquea(self, db, monkeypatch,
                                               proyecto_con_gasto,
                                               usuario_prueba):
        """Es el estado por defecto y el de esta instancia."""
        from app.dependencias import comprobar_cuota_usuario
        from app.services import limitador

        monkeypatch.setattr(limitador, "LIMITE_GENERACION_DIA_USUARIO", 0)
        comprobar_cuota_usuario(self._usuario(db, usuario_prueba))

    def test_por_debajo_del_reparto_deja_pasar(self, db, monkeypatch,
                                               proyecto_con_gasto,
                                               usuario_prueba):
        from app.dependencias import comprobar_cuota_usuario
        from app.services import limitador

        monkeypatch.setattr(limitador, "LIMITE_GENERACION_DIA_USUARIO", 10)
        comprobar_cuota_usuario(self._usuario(db, usuario_prueba))

    def test_alcanzado_el_reparto_niega_con_429(self, db, monkeypatch,
                                                proyecto_con_gasto,
                                                usuario_prueba):
        from fastapi import HTTPException

        from app.dependencias import comprobar_cuota_usuario
        from app.services import limitador

        monkeypatch.setattr(limitador, "LIMITE_GENERACION_DIA_USUARIO", 3)
        with pytest.raises(HTTPException) as exc:
            comprobar_cuota_usuario(self._usuario(db, usuario_prueba))

        assert exc.value.status_code == 429
        assert "reparto diario" in exc.value.detail

    def test_si_el_contador_falla_no_bloquea(self, db, monkeypatch,
                                             usuario_prueba):
        """Negar por las dudas dejaria la aplicacion inservible ante un fallo
        del registro, que es un problema mucho menor que no poder trabajar."""
        from app.dependencias import comprobar_cuota_usuario
        from app.services import limitador, registro_api

        monkeypatch.setattr(limitador, "LIMITE_GENERACION_DIA_USUARIO", 1)
        monkeypatch.setattr(registro_api, "consumo",
                            lambda *a, **k: {"disponible": False})
        comprobar_cuota_usuario(self._usuario(db, usuario_prueba))


class TestSeAplicaDondeSeGasta:
    def test_analizar_se_niega_con_el_reparto_agotado(self, cliente, monkeypatch,
                                                      proyecto_con_gasto):
        """La puerta va antes de encolar, no cuando responde el proveedor."""
        from app.services import limitador

        monkeypatch.setattr(limitador, "LIMITE_GENERACION_DIA_USUARIO", 3)
        r = cliente.post("/proyectos/%s/runs" % proyecto_con_gasto["proyecto"])
        assert r.status_code == 429, r.text

    def test_verificar_se_niega_igual(self, cliente, monkeypatch,
                                      proyecto_con_gasto):
        from app.services import limitador

        monkeypatch.setattr(limitador, "LIMITE_GENERACION_DIA_USUARIO", 3)
        r = cliente.post("/proyectos/%s/verificar"
                         % proyecto_con_gasto["proyecto"])
        assert r.status_code == 429, r.text

    def test_con_el_reparto_libre_analizar_sigue_funcionando(
            self, cliente, monkeypatch, proyecto_con_gasto):
        """El limite del arreglo: no puede estorbar en el caso normal."""
        from app.services import limitador

        monkeypatch.setattr(limitador, "LIMITE_GENERACION_DIA_USUARIO", 0)
        r = cliente.post("/proyectos/%s/runs" % proyecto_con_gasto["proyecto"])
        assert r.status_code == 200, r.text
