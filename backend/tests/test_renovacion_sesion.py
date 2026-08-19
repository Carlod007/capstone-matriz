# tests/test_renovacion_sesion.py
"""
La sesion se alarga mientras se usa, pero no para siempre.

A las ocho horas caducaba en seco. Si eso ocurria a mitad de un formulario se
perdia lo escrito, y el servidor no puede distinguir «se fue hace ocho horas»
de «lleva ocho horas trabajando».

Renovar sin limite tendria el problema contrario: sin revocacion, la caducidad
es la unica defensa que hay contra un token filtrado, y una renovacion continua
lo volveria permanente. De ahi el techo absoluto contado desde que se escribio
la contrasena, que viaja en el token como `ini` y no se toca al renovar.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

pytestmark = pytest.mark.bd


@pytest.fixture(scope="module", autouse=True)
def modelos_cargados():
    import main  # noqa: F401


def _cabecera(token):
    return {"Authorization": "Bearer %s" % token}


class TestElTokenLlevaSuOrigen:
    def test_ini_e_iat_empiezan_iguales(self):
        from app.services import seguridad

        datos = seguridad.datos_token(seguridad.emitir_token("u1"))
        assert abs(datos["ini"] - int(datos["iat"])) <= 1

    def test_al_renovar_iat_avanza_y_ini_se_queda(self):
        """Es lo unico que impide que renovar alargue la sesion sin fin."""
        from app.services import seguridad

        inicio = datetime.now(timezone.utc) - timedelta(hours=5)
        datos = seguridad.datos_token(
            seguridad.emitir_token("u1", inicio_sesion=inicio))

        assert datos["ini"] == int(inicio.timestamp())
        assert int(datos["iat"]) > datos["ini"], "iat debe ser el momento actual"

    def test_un_token_antiguo_sin_ini_usa_su_iat(self):
        """Los emitidos antes de que existiera `ini` no lo traen.

        Se toma su `iat`: es lo mas antiguo que puede afirmarse de ellos, de
        modo que una sesion vieja no obtiene un techo mas generoso que una
        nueva.
        """
        import jwt

        from app.config import JWT_ALGORITMO, JWT_SECRETO
        from app.services import seguridad

        hace_dos_horas = datetime.now(timezone.utc) - timedelta(hours=2)
        viejo = jwt.encode(
            {"sub": "u1", "iat": hace_dos_horas,
             "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            JWT_SECRETO, algorithm=JWT_ALGORITMO)

        inicio = seguridad.inicio_de_sesion(seguridad.datos_token(viejo))
        assert abs((inicio - hace_dos_horas).total_seconds()) <= 1


class TestElEndpoint:
    def test_devuelve_un_token_nuevo(self, cliente, usuario_prueba):
        anterior = cliente.headers["Authorization"].split(" ", 1)[1]

        r = cliente.post("/auth/renovar")
        assert r.status_code == 200, r.text
        nuevo = r.json()["token"]

        assert nuevo, "no llego token"
        assert r.json()["usuario"]["correo"] == usuario_prueba["correo"]
        # Sirve para pedir datos, que es lo unico que importa de un token.
        assert cliente.get("/auth/yo", headers=_cabecera(nuevo)).status_code == 200
        assert cliente.get("/auth/yo",
                           headers=_cabecera(anterior)).status_code == 200

    def test_conserva_el_inicio_de_la_sesion(self, cliente):
        """Renovar no puede reiniciar el reloj del techo."""
        from app.services import seguridad

        antes = seguridad.datos_token(
            cliente.headers["Authorization"].split(" ", 1)[1])
        despues = seguridad.datos_token(
            cliente.post("/auth/renovar").json()["token"])

        assert despues["ini"] == antes["ini"]

    def test_sin_token_no_renueva(self, cliente):
        from fastapi.testclient import TestClient

        import main

        anonimo = TestClient(main.app)
        assert anonimo.post("/auth/renovar").status_code == 401

    def test_un_token_caducado_no_renueva(self, cliente, usuario_prueba):
        """Renovar uno caducado seria no caducar nunca."""
        import jwt

        from app.config import JWT_ALGORITMO, JWT_SECRETO

        ayer = datetime.now(timezone.utc) - timedelta(days=1)
        caducado = jwt.encode(
            {"sub": usuario_prueba["id"], "iat": ayer,
             "ini": int(ayer.timestamp()),
             "exp": ayer + timedelta(hours=1)},
            JWT_SECRETO, algorithm=JWT_ALGORITMO)

        r = cliente.post("/auth/renovar", headers=_cabecera(caducado))
        assert r.status_code == 401

    def test_pasado_el_techo_hay_que_volver_a_entrar(self, cliente,
                                                     usuario_prueba):
        """El limite del arreglo, y el motivo de que exista `ini`.

        Con un token todavia valido pero de una sesion que empezo hace mas del
        maximo, la renovacion se niega: sin esto, encadenar renovaciones haria
        eterno cualquier token filtrado.
        """
        from app.config import JWT_MAXIMO_HORAS
        from app.services import seguridad

        muy_antiguo = (datetime.now(timezone.utc)
                       - timedelta(hours=JWT_MAXIMO_HORAS + 1))
        token = seguridad.emitir_token(usuario_prueba["id"],
                                       inicio_sesion=muy_antiguo)
        # El token en si no ha caducado: solo la sesion.
        assert cliente.get("/auth/yo",
                           headers=_cabecera(token)).status_code == 200

        r = cliente.post("/auth/renovar", headers=_cabecera(token))
        assert r.status_code == 401
        assert "maxima" in r.json()["detail"].lower()

    def test_justo_antes_del_techo_todavia_renueva(self, cliente,
                                                   usuario_prueba):
        """El otro lado del limite: una sesion larga pero dentro de plazo no
        debe cortarse."""
        from app.config import JWT_MAXIMO_HORAS
        from app.services import seguridad

        casi = (datetime.now(timezone.utc)
                - timedelta(hours=JWT_MAXIMO_HORAS - 1))
        token = seguridad.emitir_token(usuario_prueba["id"], inicio_sesion=casi)

        assert cliente.post("/auth/renovar",
                            headers=_cabecera(token)).status_code == 200
