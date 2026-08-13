# tests/test_aislamiento.py
"""
Separacion entre cuentas.

Estas son las pruebas mas importantes del proyecto. Un fallo aqui no produce
un numero equivocado: entrega los articulos de una persona a otra.

Dos comprobaciones distintas:

- `TestNingunaRutaAbierta` recorre las rutas registradas en la aplicacion y
  exige que todas pidan sesion. Es la que impide que una ruta nueva nazca sin
  proteccion: no hay que acordarse de anadirle una prueba, ya esta contada.
- `TestAjeno` crea dos cuentas y comprueba, endpoint por endpoint, que ninguna
  alcanza los datos de la otra.
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)

pytestmark = pytest.mark.bd


# Rutas que no llevan sesion, con el motivo. Cualquier otra que aparezca sin
# proteccion hace fallar la prueba; anadir aqui una excepcion obliga a
# escribir por que.
SIN_SESION = {
    ("/health", "GET"): "sonda de vida; no toca datos",
    ("/auth/login", "POST"): "es la puerta de entrada",
    ("/auth/registro", "POST"): "alta de cuenta; se protege con REGISTRO_ABIERTO",
    ("/openapi.json", "GET"): "documentacion generada por FastAPI",
    ("/docs", "GET"): "documentacion interactiva",
    ("/docs/oauth2-redirect", "GET"): "documentacion interactiva",
    ("/redoc", "GET"): "documentacion interactiva",
}


def _rutas():
    import main

    fuera = []
    for r in main.app.routes:
        if not hasattr(r, "methods"):
            continue
        for metodo in sorted(r.methods - {"HEAD", "OPTIONS"}):
            fuera.append((r.path, metodo, r))
    return fuera


class TestNingunaRutaAbierta:
    def test_todas_piden_sesion(self):
        """Recorre la aplicacion y exige `usuario_actual` en cada ruta."""
        from app.dependencias import (
            articulo_propio, proyecto_propio, run_propio, usuario_actual,
        )

        # Las dependencias de propiedad ya dependen de `usuario_actual`, asi
        # que declarar cualquiera de ellas cierra la ruta.
        VALEN = {usuario_actual, proyecto_propio, articulo_propio, run_propio}

        abiertas = []
        for ruta, metodo, r in _rutas():
            if (ruta, metodo) in SIN_SESION:
                continue
            llamadas = {d.call for d in r.dependant.dependencies}
            if not (llamadas & VALEN):
                abiertas.append("%s %s" % (metodo, ruta))

        assert not abiertas, (
            "rutas sin sesion: %s\nSi alguna debe ser publica, anadela a "
            "SIN_SESION con su motivo." % sorted(abiertas))

    def test_la_lista_de_excepciones_no_tiene_sobras(self):
        """Una excepcion para una ruta que ya no existe es una excepcion que
        nadie revisa y que podria volver a aplicarse a otra cosa."""
        existentes = {(ruta, metodo) for ruta, metodo, _ in _rutas()}
        sobran = set(SIN_SESION) - existentes
        assert not sobran, "excepciones de rutas inexistentes: %s" % sorted(sobran)


# ------------------------------------------------------------------ ajenos
@pytest.fixture(scope="module")
def dos_cuentas(db):
    """Dos usuarios; el primero con un proyecto, un articulo y una ejecucion."""
    from app.models.articulo import Articulo
    from app.models.proyecto import Proyecto
    from app.models.run import Run
    from app.models.usuario import Usuario
    from app.services import seguridad

    creados = {"usuarios": [], "proyecto": None}
    clave = "contrasena-de-prueba"

    def alta(etiqueta):
        u = Usuario(id=str(uuid.uuid4()),
                    correo="%s-%s@ejemplo.com" % (etiqueta, uuid.uuid4().hex[:8]),
                    contrasena_hash=seguridad.cifrar(clave),
                    nombre=etiqueta, activo=True)
        db.add(u)
        creados["usuarios"].append(u)
        return u

    duena = alta("duena")
    ajena = alta("ajena")
    db.flush()

    pid, aid, rid = (str(uuid.uuid4()) for _ in range(3))
    db.add(Proyecto(id=pid, usuario_id=duena.id, tema_principal="Tema de la duena",
                    objetivo="Objetivo de prueba para el aislamiento",
                    n_articulos_objetivo=1, estado_arte_generado=False))
    db.flush()
    db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="Articulo de la duena"))
    db.add(Run(id=rid, proyecto_id=pid, n_items_total=1, n_items_ok=0))
    db.commit()

    try:
        yield {"duena": duena.id, "ajena": ajena.id, "clave": clave,
               "correo_duena": duena.correo, "correo_ajena": ajena.correo,
               "proyecto": pid, "articulo": aid, "run": rid}
    finally:
        db.rollback()
        db.query(Run).filter(Run.id == rid).delete()
        db.query(Articulo).filter(Articulo.id == aid).delete()
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        for u in creados["usuarios"]:
            db.query(Usuario).filter(Usuario.id == u.id).delete()
        db.commit()


@pytest.fixture(scope="module")
def cli():
    from fastapi.testclient import TestClient
    import main

    return TestClient(main.app)


def _cabecera(cli, correo, clave):
    t = cli.post("/auth/login", json={"correo": correo, "contrasena": clave})
    assert t.status_code == 200, t.text
    return {"Authorization": "Bearer %s" % t.json()["token"]}


@pytest.fixture(scope="module")
def como_ajena(cli, dos_cuentas):
    return _cabecera(cli, dos_cuentas["correo_ajena"], dos_cuentas["clave"])


@pytest.fixture(scope="module")
def como_duena(cli, dos_cuentas):
    return _cabecera(cli, dos_cuentas["correo_duena"], dos_cuentas["clave"])


def _rutas_de_prueba(datos):
    """Cada ruta con identificador, con el metodo que le corresponde."""
    p, a, r = datos["proyecto"], datos["articulo"], datos["run"]
    return [
        ("GET", "/proyectos/%s" % p),
        ("GET", "/proyectos/%s/articulos" % p),
        ("GET", "/proyectos/%s/runs" % p),
        ("GET", "/proyectos/%s/estado_arte/latest" % p),
        ("GET", "/proyectos/%s/metricas" % p),
        ("GET", "/proyectos/%s/metricas/por_articulo" % p),
        ("GET", "/proyectos/%s/metrics/resumen" % p),
        ("GET", "/proyectos/%s/metrics/series" % p),
        ("GET", "/proyectos/%s/metrics/resumen_ext" % p),
        ("GET", "/proyectos/%s/metrics/plots" % p),
        ("GET", "/proyectos/%s/dashboard" % p),
        ("GET", "/proyectos/%s/consumo" % p),
        ("GET", "/export/proyectos/%s/brechas.csv" % p),
        ("GET", "/export/proyectos/%s/estado_arte.md" % p),
        ("GET", "/export/proyectos/%s/matriz.json" % p),
        ("GET", "/export/proyectos/%s/matriz.pdf" % p),
        ("GET", "/export/proyectos/%s/dashboard.pdf" % p),
        ("GET", "/articulos/%s/brechas" % a),
        ("GET", "/proyectos/runs/%s/items" % r),
        ("GET", "/proyectos/runs/%s/items_debug" % r),
        ("POST", "/proyectos/%s/runs" % p),
        ("POST", "/proyectos/%s/estado_arte" % p),
        ("POST", "/proyectos/%s/verificar" % p),
        ("POST", "/proyectos/%s/analizar_todo" % p),
        ("POST", "/proyectos/runs/%s/process_next" % r),
        ("POST", "/embeddings/index/%s" % a),
    ]


class TestAjeno:
    def test_no_alcanza_nada_de_la_otra_cuenta(self, cli, dos_cuentas, como_ajena):
        """404 y no 403: un 403 confirmaria que ese identificador existe, y con
        eso se puede averiguar que hay en la base probando identificadores."""
        fallos = []
        for metodo, ruta in _rutas_de_prueba(dos_cuentas):
            r = cli.request(metodo, ruta, headers=como_ajena)
            if r.status_code != 404:
                fallos.append("%s %s -> %d" % (metodo, ruta, r.status_code))
        assert not fallos, "alcanzables por una cuenta ajena: %s" % fallos

    def test_la_duena_si_alcanza_lo_suyo(self, cli, dos_cuentas, como_duena):
        """El contraste. Sin esta, un 404 en todo tambien pasaria la anterior."""
        for ruta in ("/proyectos/%s" % dos_cuentas["proyecto"],
                     "/proyectos/%s/articulos" % dos_cuentas["proyecto"],
                     "/proyectos/%s/runs" % dos_cuentas["proyecto"],
                     "/proyectos/runs/%s/items" % dos_cuentas["run"],
                     "/articulos/%s/brechas" % dos_cuentas["articulo"]):
            r = cli.get(ruta, headers=como_duena)
            assert r.status_code == 200, "%s -> %d" % (ruta, r.status_code)

    def test_el_listado_no_muestra_proyectos_ajenos(self, cli, dos_cuentas, como_ajena):
        r = cli.get("/proyectos", headers=como_ajena)
        assert r.status_code == 200
        assert dos_cuentas["proyecto"] not in [p["id"] for p in r.json()]

    def test_sin_sesion_no_se_alcanza_nada(self, cli, dos_cuentas):
        fallos = []
        for metodo, ruta in _rutas_de_prueba(dos_cuentas):
            r = cli.request(metodo, ruta)
            if r.status_code != 401:
                fallos.append("%s %s -> %d" % (metodo, ruta, r.status_code))
        assert not fallos, "alcanzables sin sesion: %s" % fallos

    def test_la_busqueda_no_devuelve_fragmentos_ajenos(self, cli, dos_cuentas, como_ajena):
        """Sin lista de articulos, la busqueda recorria los de toda la base."""
        r = cli.get("/embeddings/search", params={"q": "cualquier cosa"},
                    headers=como_ajena)
        assert r.status_code == 200
        assert r.json() == []

    def test_pedir_un_articulo_ajeno_en_la_busqueda_no_lo_devuelve(
            self, cli, dos_cuentas, como_ajena):
        r = cli.get("/embeddings/search",
                    params={"q": "cualquier cosa",
                            "articulo_id": dos_cuentas["articulo"]},
                    headers=como_ajena)
        assert r.status_code == 200
        assert r.json() == []

    def test_un_proyecto_nuevo_nace_con_dueno(self, cli, como_duena, dos_cuentas, db):
        from app.models.proyecto import Proyecto

        r = cli.post("/proyectos", headers=como_duena, json={
            "tema_principal": "Proyecto recien creado",
            "objetivo": "Comprobar que el dueno se asigna solo",
            "n_articulos_objetivo": 1})
        assert r.status_code == 200
        pid = r.json()["id"]
        try:
            # El endpoint escribio en su propia sesion. Esta lleva una
            # transaccion abierta y, con REPEATABLE READ, seguiria viendo la
            # instantanea anterior: sin cerrarla, la fila recien creada no
            # existe para esta consulta.
            db.rollback()
            fila = db.query(Proyecto).filter(Proyecto.id == pid).first()
            assert fila.usuario_id == dos_cuentas["duena"]
        finally:
            db.query(Proyecto).filter(Proyecto.id == pid).delete()
            db.commit()

    def test_un_proyecto_sin_dueno_no_lo_ve_nadie(self, cli, como_duena, db):
        """Los proyectos anteriores a las cuentas quedan sin dueno. No deben
        verse por defecto: el fallo tiene que ser cerrado."""
        from app.models.proyecto import Proyecto

        pid = str(uuid.uuid4())
        db.add(Proyecto(id=pid, usuario_id=None, tema_principal="Huerfano",
                        objetivo="Proyecto sin dueno, de antes de las cuentas",
                        n_articulos_objetivo=1, estado_arte_generado=False))
        db.commit()
        try:
            assert cli.get("/proyectos/%s" % pid, headers=como_duena).status_code == 404
            listado = cli.get("/proyectos", headers=como_duena).json()
            assert pid not in [p["id"] for p in listado]
        finally:
            db.query(Proyecto).filter(Proyecto.id == pid).delete()
            db.commit()
