# tests/test_autenticacion.py
"""
Contrasenas, tokens y alta de cuenta.

Las de criptografia no tocan la base y corren en cualquier maquina. Las de
endpoint van marcadas con `bd`.
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-solo-para-pruebas-" + "x" * 32)


class TestContrasenas:
    def test_el_hash_no_es_la_contrasena(self):
        from app.services import seguridad

        h = seguridad.cifrar("una contrasena larga")
        assert "una contrasena larga" not in h
        assert h.startswith("$2")

    def test_dos_hashes_de_la_misma_contrasena_difieren(self):
        """Cada hash lleva su propia sal. Si dos coincidieran, la base
        revelaria que dos personas usan la misma contrasena."""
        from app.services import seguridad

        assert seguridad.cifrar("misma contrasena") != seguridad.cifrar("misma contrasena")

    def test_comprueba_la_correcta_y_rechaza_la_falsa(self):
        from app.services import seguridad

        h = seguridad.cifrar("la buena de verdad")
        assert seguridad.comprobar("la buena de verdad", h)
        assert not seguridad.comprobar("la buena de verdaD", h)
        assert not seguridad.comprobar("", h)

    def test_un_hash_corrupto_no_revienta(self):
        """Debe verse igual que una contrasena equivocada, no como un error
        del servidor que delataria el estado de la base."""
        from app.services import seguridad

        assert not seguridad.comprobar("cualquiera", "esto no es un hash")

    def test_rechaza_las_demasiado_cortas(self):
        from app.services import seguridad

        with pytest.raises(seguridad.ContrasenaInvalida):
            seguridad.cifrar("corta7c")

    def test_rechaza_las_que_bcrypt_truncaria(self):
        """bcrypt ignora en silencio lo que pase de 72 bytes: dos contrasenas
        distintas con el mismo prefijo abririan la misma cuenta."""
        from app.services import seguridad

        with pytest.raises(seguridad.ContrasenaInvalida):
            seguridad.cifrar("a" * 73)

    def test_cuenta_bytes_y_no_caracteres(self):
        """Con acentos, 72 caracteres pasan de 72 bytes en UTF-8."""
        from app.services import seguridad

        with pytest.raises(seguridad.ContrasenaInvalida):
            seguridad.cifrar("ñ" * 40)  # 80 bytes


class TestTokens:
    def test_ida_y_vuelta(self):
        from app.services import seguridad

        uid = str(uuid.uuid4())
        assert seguridad.leer_token(seguridad.emitir_token(uid)) == uid

    def test_rechaza_un_token_alterado(self):
        from app.services import seguridad

        t = seguridad.emitir_token(str(uuid.uuid4()))
        cabeza, cuerpo, firma = t.split(".")
        with pytest.raises(seguridad.TokenInvalido):
            seguridad.leer_token("%s.%s.%s" % (cabeza, cuerpo, firma[::-1]))

    def test_rechaza_basura(self):
        from app.services import seguridad

        with pytest.raises(seguridad.TokenInvalido):
            seguridad.leer_token("no-es-un-token")

    def test_rechaza_uno_caducado(self):
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.config import JWT_ALGORITMO, JWT_SECRETO
        from app.services import seguridad

        ayer = datetime.now(timezone.utc) - timedelta(hours=1)
        vencido = jwt.encode(
            {"sub": "alguien", "iat": ayer, "exp": ayer + timedelta(seconds=1)},
            JWT_SECRETO, algorithm=JWT_ALGORITMO)
        with pytest.raises(seguridad.TokenInvalido):
            seguridad.leer_token(vencido)

    def test_rechaza_el_algoritmo_none(self):
        """El fallo clasico de JWT: aceptar el algoritmo que declara el propio
        token permite entrar sin conocer el secreto."""
        import jwt

        from app.services import seguridad

        sin_firma = jwt.encode({"sub": "intruso"}, key="", algorithm="none")
        with pytest.raises(seguridad.TokenInvalido):
            seguridad.leer_token(sin_firma)

    def test_rechaza_uno_firmado_con_otro_secreto(self):
        from datetime import datetime, timedelta, timezone

        import jwt

        from app.services import seguridad

        ahora = datetime.now(timezone.utc)
        ajeno = jwt.encode(
            {"sub": "intruso", "iat": ahora, "exp": ahora + timedelta(hours=1)},
            "otro-secreto-distinto-y-suficientemente-largo-para-HS256",
            algorithm="HS256")
        with pytest.raises(seguridad.TokenInvalido):
            seguridad.leer_token(ajeno)


class TestConfiguracion:
    def test_avisa_si_falta_el_secreto(self, monkeypatch):
        import importlib

        from app import config

        monkeypatch.setenv("JWT_SECRETO", "")
        recargado = importlib.reload(config)
        try:
            faltan = recargado.revisar(estricto=False)
            assert any("JWT_SECRETO" in f for f in faltan)
            with pytest.raises(RuntimeError):
                recargado.revisar()
        finally:
            monkeypatch.undo()
            importlib.reload(config)

    def test_rechaza_un_secreto_corto(self, monkeypatch):
        import importlib

        from app import config

        monkeypatch.setenv("JWT_SECRETO", "corto")
        recargado = importlib.reload(config)
        try:
            assert any("JWT_SECRETO" in f for f in recargado.revisar(estricto=False))
        finally:
            monkeypatch.undo()
            importlib.reload(config)

    def test_el_registro_nace_cerrado(self, monkeypatch):
        import importlib

        from app import config

        monkeypatch.delenv("REGISTRO_ABIERTO", raising=False)
        recargado = importlib.reload(config)
        try:
            assert recargado.REGISTRO_ABIERTO is False
        finally:
            monkeypatch.undo()
            importlib.reload(config)


# --------------------------------------------------------------- endpoints
pytestmark_bd = pytest.mark.bd


@pytest.fixture
def cliente():
    from fastapi.testclient import TestClient
    import main

    return TestClient(main.app)


@pytest.fixture
def cuenta(db):
    """Una cuenta de prueba, borrada al terminar."""
    import uuid as _uuid

    from app.models.usuario import Usuario
    from app.services import seguridad

    correo = "prueba-%s@ejemplo.com" % _uuid.uuid4().hex[:8]
    clave = "contrasena-de-prueba"
    u = Usuario(id=str(_uuid.uuid4()), correo=correo,
                contrasena_hash=seguridad.cifrar(clave),
                nombre="Cuenta de prueba", activo=True)
    db.add(u)
    db.commit()
    try:
        yield {"correo": correo, "contrasena": clave, "id": u.id}
    finally:
        db.rollback()
        db.query(Usuario).filter(Usuario.correo == correo).delete()
        db.commit()


@pytest.mark.bd
class TestEndpoints:
    def test_inicio_de_sesion_correcto(self, cliente, cuenta):
        r = cliente.post("/auth/login", json={
            "correo": cuenta["correo"], "contrasena": cuenta["contrasena"]})
        assert r.status_code == 200
        d = r.json()
        assert d["token"]
        assert d["usuario"]["correo"] == cuenta["correo"]

    def test_la_respuesta_nunca_lleva_el_hash(self, cliente, cuenta):
        """Lo mas facil de filtrar y lo mas caro de filtrar."""
        r = cliente.post("/auth/login", json={
            "correo": cuenta["correo"], "contrasena": cuenta["contrasena"]})
        assert "contrasena_hash" not in r.text
        assert "contrasena" not in r.json()["usuario"]

    def test_contrasena_incorrecta_da_401(self, cliente, cuenta):
        r = cliente.post("/auth/login", json={
            "correo": cuenta["correo"], "contrasena": "equivocada del todo"})
        assert r.status_code == 401

    def test_no_distingue_correo_inexistente_de_clave_mala(self, cliente, cuenta):
        """Si los mensajes difirieran, se podria averiguar que correos tienen
        cuenta probandolos uno a uno."""
        sin_cuenta = cliente.post("/auth/login", json={
            "correo": "nadie-%s@ejemplo.com" % uuid.uuid4().hex[:8],
            "contrasena": "loquesea12345"})
        con_cuenta = cliente.post("/auth/login", json={
            "correo": cuenta["correo"], "contrasena": "equivocada del todo"})
        assert sin_cuenta.status_code == con_cuenta.status_code == 401
        assert sin_cuenta.json()["detail"] == con_cuenta.json()["detail"]

    def test_cuenta_desactivada_no_entra(self, cliente, cuenta, db):
        from app.models.usuario import Usuario

        db.query(Usuario).filter(Usuario.id == cuenta["id"]).update({"activo": False})
        db.commit()
        r = cliente.post("/auth/login", json={
            "correo": cuenta["correo"], "contrasena": cuenta["contrasena"]})
        assert r.status_code == 401

    def test_yo_devuelve_la_cuenta_del_token(self, cliente, cuenta):
        t = cliente.post("/auth/login", json={
            "correo": cuenta["correo"], "contrasena": cuenta["contrasena"]}).json()["token"]
        r = cliente.get("/auth/yo", headers={"Authorization": "Bearer %s" % t})
        assert r.status_code == 200
        assert r.json()["id"] == cuenta["id"]

    def test_yo_sin_cabecera_da_401(self, cliente):
        assert cliente.get("/auth/yo").status_code == 401

    def test_yo_con_token_invalido_da_401(self, cliente):
        r = cliente.get("/auth/yo", headers={"Authorization": "Bearer inventado"})
        assert r.status_code == 401
        assert "WWW-Authenticate" in r.headers

    def test_token_de_una_cuenta_borrada_da_401(self, cliente, cuenta, db):
        from app.models.usuario import Usuario

        t = cliente.post("/auth/login", json={
            "correo": cuenta["correo"], "contrasena": cuenta["contrasena"]}).json()["token"]
        db.query(Usuario).filter(Usuario.id == cuenta["id"]).delete()
        db.commit()
        assert cliente.get(
            "/auth/yo", headers={"Authorization": "Bearer %s" % t}).status_code == 401

    def test_el_registro_esta_cerrado(self, cliente):
        r = cliente.post("/auth/registro", json={
            "correo": "nuevo@ejemplo.com", "nombre": "Nuevo",
            "contrasena": "contrasena-larga"})
        assert r.status_code == 403

    def test_el_correo_debe_ser_valido(self, cliente):
        r = cliente.post("/auth/login", json={
            "correo": "esto no es un correo", "contrasena": "loquesea12345"})
        assert r.status_code == 422
