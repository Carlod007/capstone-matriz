# tests/test_almacenamiento.py
"""
Acceso a los PDF detras de una interfaz.

Lo que se comprueba no es que se pueda escribir un fichero, sino las dos
cosas que hacen que esta capa exista: que una clave no pueda salirse de la
carpeta de almacenamiento, y que los archivos subidos antes de que existieran
las claves sigan abriendose.
"""

import os
import uuid

import pytest


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    """Almacenamiento apuntando a un directorio de usar y tirar."""
    from app.services import almacenamiento

    monkeypatch.setattr(almacenamiento, "STORAGE_DIR", str(tmp_path))
    return almacenamiento


class TestGuardarYRecuperar:
    def test_ida_y_vuelta(self, almacen):
        clave = almacen.nueva_clave(str(uuid.uuid4()))
        almacen.guardar(clave, b"%PDF-1.4 contenido")

        with open(almacen.ruta_local(clave), "rb") as f:
            assert f.read() == b"%PDF-1.4 contenido"

    def test_la_clave_empieza_por_el_usuario(self, almacen):
        """El aislamiento entre cuentas tambien en el disco: con todos los PDF
        en el mismo directorio, un error al construir un nombre podia servir
        el archivo de otra persona."""
        uid = str(uuid.uuid4())
        assert almacen.nueva_clave(uid).startswith(uid + "/")

    def test_dos_claves_nunca_coinciden(self, almacen):
        uid = str(uuid.uuid4())
        assert almacen.nueva_clave(uid) != almacen.nueva_clave(uid)

    def test_existe_y_borrar(self, almacen):
        clave = almacen.nueva_clave(str(uuid.uuid4()))
        assert almacen.existe(clave) is False
        almacen.guardar(clave, b"algo")
        assert almacen.existe(clave) is True
        assert almacen.borrar(clave) is True
        assert almacen.existe(clave) is False
        assert almacen.borrar(clave) is False


class TestClavesPeligrosas:
    """Las claves salen de la base, que se alimenta de lo que sube el usuario.

    Una con `..` permitiria leer cualquier fichero de la maquina, asi que se
    comprueban en lugar de confiar en ellas.
    """

    @pytest.mark.parametrize("mala", [
        "../../../../etc/passwd",
        "../fuera.pdf",
        "usuario/../../fuera.pdf",
        "sin-barra.pdf",
        "usuario/archivo.exe",
        "",
    ])
    def test_se_rechazan(self, almacen, mala):
        with pytest.raises(almacen.ClaveInvalida):
            almacen.ruta_local(mala)

    def test_no_se_pueden_guardar(self, almacen):
        with pytest.raises(almacen.ClaveInvalida):
            almacen.guardar("../fuera.pdf", b"contenido")

    def test_existe_no_revienta_con_una_mala(self, almacen):
        assert almacen.existe("../../../etc/passwd") is False


class TestCompatibilidad:
    def test_una_ruta_absoluta_antigua_sigue_valiendo(self, almacen, tmp_path):
        """Los archivos anteriores a las claves guardan la ruta del disco.
        Convertirlos exigiria mover ficheros y reescribir la base; aceptarlos
        cuesta tres lineas y evita que los proyectos ya cargados dejen de
        abrirse."""
        antiguo = tmp_path / "de-antes.pdf"
        antiguo.write_bytes(b"%PDF-1.4 antiguo")

        assert almacen.ruta_local(str(antiguo)) == str(antiguo)
        assert almacen.existe(str(antiguo)) is True


class TestConfiguracion:
    def test_cors_no_admite_comodin(self, monkeypatch):
        """Con sesiones activas, '*' hace que los navegadores rechacen las
        peticiones: el efecto real seria que la aplicacion deja de funcionar
        sin decir por que."""
        import importlib

        from app import config

        monkeypatch.setenv("CORS_ORIGENES", "*")
        recargado = importlib.reload(config)
        try:
            faltan = recargado.revisar(estricto=False)
            assert any("CORS_ORIGENES" in f for f in faltan)
        finally:
            monkeypatch.undo()
            importlib.reload(config)

    def test_los_origenes_se_leen_separados_por_comas(self, monkeypatch):
        import importlib

        from app import config

        monkeypatch.setenv("CORS_ORIGENES",
                           "https://midominio.com, http://localhost:5173")
        recargado = importlib.reload(config)
        try:
            assert recargado.CORS_ORIGENES == [
                "https://midominio.com", "http://localhost:5173"]
        finally:
            monkeypatch.undo()
            importlib.reload(config)

    def test_hay_un_valor_por_defecto_para_desarrollo(self, monkeypatch):
        import importlib

        from app import config

        monkeypatch.delenv("CORS_ORIGENES", raising=False)
        recargado = importlib.reload(config)
        try:
            assert "http://localhost:5173" in recargado.CORS_ORIGENES
        finally:
            monkeypatch.undo()
            importlib.reload(config)
