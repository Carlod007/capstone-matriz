# tests/test_validacion_humana.py
"""
N6: el juicio de una persona sobre cada brecha.

Todas las demas metricas comparan al sistema consigo mismo. Dicen si es
consistente, no si acierta. Esta es la unica que puede decir lo segundo, y por
eso su valor no esta en el porcentaje sino en la justificacion: un «esta mal»
sin motivo no permite corregir el sistema ni sostener la evaluacion.

Estas pruebas fijan las decisiones que hacen util el dato: que el veredicto
negativo exija explicacion, que cada persona solo pueda tocar el suyo, que el
acierto se calcule sobre lo anotado y no sobre el total, y que nadie pueda
anotar brechas de otra cuenta.
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
def proyecto_con_brechas(db, usuario_prueba):
    """Un analisis con cuatro brechas, sin anotar."""
    from app.models.articulo import Articulo
    from app.models.proyecto import Proyecto
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.run import EstadoRun, Run
    from app.models.run_item import EstadoRunItem, RunItem

    pid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Validacion humana",
                    objetivo="Comprobar la anotacion de brechas",
                    n_articulos_objetivo=4, estado_arte_generado=False))
    db.flush()
    db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
               n_items_total=4, n_items_ok=4))
    db.flush()

    brechas = []
    for i in range(4):
        aid, iid, bid = (str(uuid.uuid4()) for _ in range(3))
        db.add(Articulo(id=aid, proyecto_id=pid, doi=None,
                        titulo="Articulo %d" % i))
        db.flush()
        db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                       estado=EstadoRunItem.analizado))
        db.flush()
        db.add(ResultadoBrecha(id=bid, run_item_id=iid, tipo_brecha="otra",
                               brecha="Brecha %d" % i,
                               oportunidad="Oportunidad %d" % i, rag_hits=[]))
        brechas.append(bid)
    db.commit()

    try:
        yield {"proyecto": pid, "run": rid, "brechas": brechas}
    finally:
        from app.models.validacion_humana import ValidacionHumana

        db.rollback()
        db.query(ValidacionHumana).filter(
            ValidacionHumana.brecha_id.in_(brechas)).delete(
            synchronize_session=False)
        db.query(ResultadoBrecha).filter(
            ResultadoBrecha.id.in_(brechas)).delete(synchronize_session=False)
        db.query(RunItem).filter(RunItem.run_id == rid).delete(
            synchronize_session=False)
        db.query(Run).filter(Run.id == rid).delete()
        db.query(Articulo).filter(Articulo.proyecto_id == pid).delete(
            synchronize_session=False)
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.commit()


def _anotar(cliente, pid, bid, veredicto, justificacion=None):
    return cliente.put("/proyectos/%s/validacion/%s" % (pid, bid),
                       json={"veredicto": veredicto,
                             "justificacion": justificacion})


class TestAnotar:
    def test_marcar_correcta_no_exige_motivo(self, cliente,
                                             proyecto_con_brechas):
        """No hay nada que objetar, asi que no hay nada que explicar."""
        pid = proyecto_con_brechas["proyecto"]
        r = _anotar(cliente, pid, proyecto_con_brechas["brechas"][0], "correcta")

        assert r.status_code == 200, r.text
        assert r.json()["veredicto"] == "correcta"

    def test_un_rechazo_sin_motivo_se_niega(self, cliente,
                                            proyecto_con_brechas):
        """Es la regla que hace util la anotacion.

        Sin el motivo escrito, el dato dice que algo fallo pero no que, y no
        sirve ni para corregir el sistema ni para el capitulo de resultados.
        """
        pid = proyecto_con_brechas["proyecto"]
        for veredicto in ("incorrecta", "parcial"):
            r = _anotar(cliente, pid, proyecto_con_brechas["brechas"][1],
                        veredicto)
            assert r.status_code == 422, r.text
            assert "falla" in r.json()["detail"].lower()

    def test_los_espacios_no_cuentan_como_motivo(self, cliente,
                                                 proyecto_con_brechas):
        r = _anotar(cliente, proyecto_con_brechas["proyecto"],
                    proyecto_con_brechas["brechas"][1], "incorrecta", "   ")
        assert r.status_code == 422

    def test_cambiar_de_opinion_sustituye_y_no_acumula(self, db, cliente,
                                                       proyecto_con_brechas):
        from app.models.validacion_humana import ValidacionHumana

        pid = proyecto_con_brechas["proyecto"]
        bid = proyecto_con_brechas["brechas"][0]
        _anotar(cliente, pid, bid, "correcta")
        _anotar(cliente, pid, bid, "incorrecta", "confunde el metodo")

        db.expire_all()
        filas = db.query(ValidacionHumana).filter(
            ValidacionHumana.brecha_id == bid).all()
        assert len(filas) == 1
        assert filas[0].veredicto == "incorrecta"
        assert filas[0].justificacion == "confunde el metodo"

    def test_un_veredicto_inventado_se_rechaza(self, cliente,
                                               proyecto_con_brechas):
        r = _anotar(cliente, proyecto_con_brechas["proyecto"],
                    proyecto_con_brechas["brechas"][0], "regular", "x")
        assert r.status_code == 422

    def test_retirar_deja_la_brecha_sin_veredicto(self, cliente,
                                                  proyecto_con_brechas):
        pid = proyecto_con_brechas["proyecto"]
        bid = proyecto_con_brechas["brechas"][0]
        _anotar(cliente, pid, bid, "correcta")

        r = cliente.delete("/proyectos/%s/validacion/%s" % (pid, bid))
        assert r.status_code == 200
        assert r.json()["resumen"]["anotadas"] == 0


class TestElResumen:
    def test_el_acierto_se_calcula_sobre_lo_anotado(self, cliente,
                                                    proyecto_con_brechas):
        """Dividir entre el total daria un numero que sube solo al seguir
        anotando, y que no significa nada mientras falten brechas."""
        pid = proyecto_con_brechas["proyecto"]
        b = proyecto_con_brechas["brechas"]
        _anotar(cliente, pid, b[0], "correcta")
        r = _anotar(cliente, pid, b[1], "incorrecta", "no se sostiene")

        resumen = r.json()["resumen"]
        assert resumen["anotadas"] == 2
        assert resumen["total"] == 4
        assert resumen["pendientes"] == 2
        assert resumen["acierto"] == 0.5, "una de dos, no una de cuatro"

    def test_parcial_vale_medio_punto(self, cliente, proyecto_con_brechas):
        """Contarla como acierto o como fallo completo falsea el resultado en
        direcciones opuestas."""
        pid = proyecto_con_brechas["proyecto"]
        b = proyecto_con_brechas["brechas"]
        _anotar(cliente, pid, b[0], "correcta")
        r = _anotar(cliente, pid, b[1], "parcial", "acierta el problema, "
                                                   "falla el matiz")

        assert r.json()["resumen"]["acierto"] == 0.75

    def test_sin_anotar_el_acierto_no_es_cero(self, cliente,
                                              proyecto_con_brechas):
        """Un cero aqui se leeria como «el sistema no acerto ninguna»."""
        r = cliente.get("/proyectos/%s/validacion"
                        % proyecto_con_brechas["proyecto"])
        assert r.status_code == 200, r.text
        assert r.json()["resumen"]["acierto"] is None
        assert r.json()["resumen"]["anotadas"] == 0

    def test_declara_cuantos_anotadores_hay(self, cliente,
                                            proyecto_con_brechas):
        """No presupone una persona que todavia no dejo ningun veredicto."""
        r = cliente.get("/proyectos/%s/validacion"
                        % proyecto_con_brechas["proyecto"])
        assert r.json()["resumen"]["anotadores"] == 0

        _anotar(cliente, proyecto_con_brechas["proyecto"],
                proyecto_con_brechas["brechas"][0], "correcta")
        r = cliente.get("/proyectos/%s/validacion"
                        % proyecto_con_brechas["proyecto"])
        assert r.json()["resumen"]["anotadores"] == 1

    def test_el_resumen_solo_describe_la_ultima_ejecucion(
            self, db, cliente, proyecto_con_brechas):
        """Una anotacion historica no infla el total ni el acierto vigente."""
        from datetime import datetime

        from app.models.articulo import Articulo
        from app.models.resultado_brecha import ResultadoBrecha
        from app.models.run import EstadoRun, Run
        from app.models.run_item import EstadoRunItem, RunItem

        pid = proyecto_con_brechas["proyecto"]
        _anotar(cliente, pid, proyecto_con_brechas["brechas"][0], "correcta")

        rid, aid, iid, bid = (str(uuid.uuid4()) for _ in range(4))
        db.add(Articulo(id=aid, proyecto_id=pid, doi=None,
                        titulo="Articulo del segundo analisis"))
        db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
                   iniciado_en=datetime(2099, 1, 1), n_items_total=1,
                   n_items_ok=1))
        db.flush()
        db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                       estado=EstadoRunItem.analizado))
        db.flush()
        db.add(ResultadoBrecha(id=bid, run_item_id=iid, tipo_brecha="otra",
                               brecha="Brecha vigente", oportunidad="o",
                               rag_hits=[]))
        db.commit()

        try:
            datos = cliente.get("/proyectos/%s/validacion" % pid).json()
            assert datos["run"] == rid
            assert datos["resumen"]["total"] == 1
            assert datos["resumen"]["anotadas"] == 0
            assert datos["resumen"]["acierto"] is None
            assert datos["resumen"]["anotadores"] == 0
        finally:
            db.rollback()
            db.query(ResultadoBrecha).filter(
                ResultadoBrecha.id == bid).delete()
            db.query(RunItem).filter(RunItem.id == iid).delete()
            db.query(Run).filter(Run.id == rid).delete()
            db.query(Articulo).filter(Articulo.id == aid).delete()
            db.commit()


class TestElListado:
    def test_trae_las_brechas_con_el_veredicto_propio(self, cliente,
                                                      proyecto_con_brechas):
        pid = proyecto_con_brechas["proyecto"]
        _anotar(cliente, pid, proyecto_con_brechas["brechas"][0], "correcta")

        datos = cliente.get("/proyectos/%s/validacion" % pid).json()
        assert len(datos["brechas"]) == 4
        anotada = next(b for b in datos["brechas"]
                       if b["id"] == proyecto_con_brechas["brechas"][0])
        assert anotada["veredicto"] == "correcta"
        assert all(b["veredicto"] is None for b in datos["brechas"]
                   if b["id"] != anotada["id"])


class TestElAislamiento:
    def test_no_se_anotan_brechas_de_otra_cuenta(self, db, cliente,
                                                 proyecto_con_brechas):
        """El guardian comprueba el proyecto, no la brecha: sin el filtro,
        conocer un identificador ajeno bastaria para anotarlo desde uno
        propio."""
        from app.models.articulo import Articulo
        from app.models.proyecto import Proyecto
        from app.models.resultado_brecha import ResultadoBrecha
        from app.models.run import EstadoRun, Run
        from app.models.run_item import EstadoRunItem, RunItem
        from app.models.usuario import Usuario
        from app.services import seguridad

        otro, pid2, rid2, aid2, iid2, bid2 = (str(uuid.uuid4()) for _ in range(6))
        db.add(Usuario(id=otro, correo="ajeno-%s@x.com" % otro[:8],
                       contrasena_hash=seguridad.cifrar("clave-de-la-otra"),
                       nombre="Otra", activo=True))
        db.flush()
        db.add(Proyecto(id=pid2, usuario_id=otro, tema_principal="Ajeno",
                        objetivo="No tocar", n_articulos_objetivo=1,
                        estado_arte_generado=False))
        db.flush()
        db.add(Articulo(id=aid2, proyecto_id=pid2, doi=None, titulo="Ajeno"))
        db.add(Run(id=rid2, proyecto_id=pid2, estado=EstadoRun.completado,
                   n_items_total=1, n_items_ok=1))
        db.flush()
        db.add(RunItem(id=iid2, run_id=rid2, articulo_id=aid2,
                       estado=EstadoRunItem.analizado))
        db.flush()
        db.add(ResultadoBrecha(id=bid2, run_item_id=iid2, tipo_brecha="otra",
                               brecha="ajena", oportunidad="o", rag_hits=[]))
        db.commit()

        try:
            # Desde el proyecto propio, con el identificador de la brecha ajena.
            r = _anotar(cliente, proyecto_con_brechas["proyecto"], bid2,
                        "correcta")
            assert r.status_code == 404, r.text
        finally:
            from app.models.validacion_humana import ValidacionHumana

            db.rollback()
            db.query(ValidacionHumana).filter(
                ValidacionHumana.brecha_id == bid2).delete(
                synchronize_session=False)
            db.query(ResultadoBrecha).filter(ResultadoBrecha.id == bid2).delete()
            db.query(RunItem).filter(RunItem.id == iid2).delete()
            db.query(Run).filter(Run.id == rid2).delete()
            db.query(Articulo).filter(Articulo.id == aid2).delete()
            db.query(Proyecto).filter(Proyecto.id == pid2).delete()
            db.query(Usuario).filter(Usuario.id == otro).delete()
            db.commit()

    def test_el_veredicto_ajeno_se_cuenta_pero_no_se_ve(self, db, cliente,
                                                        proyecto_con_brechas):
        """Saber que dijo otro antes de opinar arruina la independencia, que es
        lo unico que hace util el acuerdo entre jueces."""
        from app.models.usuario import Usuario
        from app.models.validacion_humana import ValidacionHumana
        from app.services import seguridad

        otro = str(uuid.uuid4())
        bid = proyecto_con_brechas["brechas"][0]
        db.add(Usuario(id=otro, correo="juez-%s@x.com" % otro[:8],
                       contrasena_hash=seguridad.cifrar("clave-del-juez"),
                       nombre="Segundo juez", activo=True))
        db.flush()
        db.add(ValidacionHumana(id=str(uuid.uuid4()), brecha_id=bid,
                                usuario_id=otro, veredicto="incorrecta",
                                justificacion="opinion ajena"))
        db.commit()

        try:
            datos = cliente.get("/proyectos/%s/validacion"
                                % proyecto_con_brechas["proyecto"]).json()
            fila = next(b for b in datos["brechas"] if b["id"] == bid)

            assert fila["veredicto"] is None, "no debe verse el ajeno"
            assert fila["otros_anotadores"] == 1, "pero si que existe"
            assert "opinion ajena" not in str(datos)
            assert datos["resumen"]["anotadores"] == 1
        finally:
            db.rollback()
            db.query(ValidacionHumana).filter(
                ValidacionHumana.usuario_id == otro).delete(
                synchronize_session=False)
            db.query(Usuario).filter(Usuario.id == otro).delete()
            db.commit()
