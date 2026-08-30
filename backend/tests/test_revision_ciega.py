# tests/test_revision_ciega.py
"""
El resultado no se sirve hasta terminar de anotar.

La revision estaba debajo del panel de metricas, asi que quien bajaba a anotar
ya habia visto que el sistema se daba un 1.000 de fidelidad. Juzgar despues de
eso no es juzgar, es confirmar, y entonces comparar las dos columnas deja de
medir el acierto del sistema para medir su eco.

La ceguera se impone en el servidor y no en la pantalla. Ocultar el dato en el
frontend no bastaria: habria viajado igual y cualquiera podria leerlo, asi que
dejaria de ser una propiedad del procedimiento para ser una decision de
maquetacion.

Tambien se reserva el desglose por veredicto: saber que se llevan cuatro
«correcta» condiciona la quinta tanto como el porcentaje.
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
def proyecto_con_tres(db, usuario_prueba):
    from app.models.articulo import Articulo
    from app.models.proyecto import Proyecto
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.run import EstadoRun, Run
    from app.models.run_item import EstadoRunItem, RunItem

    pid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Revision ciega",
                    objetivo="Comprobar que el resultado se reserva",
                    n_articulos_objetivo=3, estado_arte_generado=False))
    db.flush()
    db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
               n_items_total=3, n_items_ok=3))
    db.flush()

    brechas = []
    for i in range(3):
        aid, iid, bid = (str(uuid.uuid4()) for _ in range(3))
        db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="A%d" % i))
        db.flush()
        db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                       estado=EstadoRunItem.analizado))
        db.flush()
        db.add(ResultadoBrecha(id=bid, run_item_id=iid, tipo_brecha="otra",
                               brecha="Brecha %d" % i, oportunidad="o",
                               rag_hits=[]))
        brechas.append(bid)
    db.commit()

    try:
        yield {"proyecto": pid, "brechas": brechas}
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


def _anotar(cliente, pid, bid, veredicto="correcta"):
    return cliente.put("/proyectos/%s/validacion/%s" % (pid, bid),
                       json={"veredicto": veredicto})


def _resumen(cliente, pid):
    return cliente.get("/proyectos/%s/validacion" % pid).json()["resumen"]


class TestElResultadoSeReserva:
    def test_a_medias_no_hay_acierto(self, cliente, proyecto_con_tres):
        pid = proyecto_con_tres["proyecto"]
        _anotar(cliente, pid, proyecto_con_tres["brechas"][0])

        r = _resumen(cliente, pid)
        assert r["acierto"] is None, "el marcador condiciona lo que falta"
        assert r["revision_completa"] is False
        assert r["anotadas"] == 1, "el progreso si se puede ver"
        assert r["pendientes"] == 2

    def test_el_desglose_tambien_se_reserva(self, cliente, proyecto_con_tres):
        """Saber que se llevan dos «correcta» condiciona la tercera."""
        pid = proyecto_con_tres["proyecto"]
        _anotar(cliente, pid, proyecto_con_tres["brechas"][0])

        assert _resumen(cliente, pid)["por_veredicto"] is None

    def test_al_terminar_aparece(self, cliente, proyecto_con_tres):
        pid = proyecto_con_tres["proyecto"]
        b = proyecto_con_tres["brechas"]
        _anotar(cliente, pid, b[0], "correcta")
        _anotar(cliente, pid, b[1], "correcta")
        r = _resumen(cliente, pid)
        assert r["acierto"] is None, "con una pendiente todavia no"

        _anotar(cliente, pid, b[2], "correcta")
        r = _resumen(cliente, pid)
        assert r["revision_completa"] is True
        assert r["acierto"] == 1.0
        assert r["por_veredicto"]["correcta"] == 3

    def test_retirar_un_veredicto_vuelve_a_ocultarlo(self, cliente,
                                                     proyecto_con_tres):
        """El limite: si deja de estar completa, el resultado se retira otra
        vez. De lo contrario bastaria anotar todo y borrar una para verlo."""
        pid = proyecto_con_tres["proyecto"]
        for bid in proyecto_con_tres["brechas"]:
            _anotar(cliente, pid, bid)
        assert _resumen(cliente, pid)["acierto"] is not None

        cliente.delete("/proyectos/%s/validacion/%s"
                       % (pid, proyecto_con_tres["brechas"][0]))
        assert _resumen(cliente, pid)["acierto"] is None


class TestLaComparacion:
    def test_no_se_da_a_medias(self, cliente, proyecto_con_tres):
        pid = proyecto_con_tres["proyecto"]
        _anotar(cliente, pid, proyecto_con_tres["brechas"][0])

        r = cliente.get("/proyectos/%s/validacion/comparacion" % pid)
        assert r.status_code == 409, r.text
        assert "Faltan 2" in r.json()["detail"]

    def test_al_terminar_trae_las_dos_columnas(self, db, cliente,
                                               proyecto_con_tres):
        from app.models.metrica import AMBITO_BRECHA, Metrica

        pid = proyecto_con_tres["proyecto"]
        b = proyecto_con_tres["brechas"]
        db.add(Metrica(id=str(uuid.uuid4()), proyecto_id=pid,
                       ambito=AMBITO_BRECHA, referencia_id=b[0],
                       codigo="N2.1", valor=0.75))
        db.commit()
        for bid in b:
            _anotar(cliente, pid, bid, "correcta")

        r = cliente.get("/proyectos/%s/validacion/comparacion" % pid)
        assert r.status_code == 200, r.text
        datos = r.json()
        assert len(datos["brechas"]) == 3
        fila = next(x for x in datos["brechas"] if x["id"] == b[0])
        assert fila["veredicto"] == "correcta"
        assert fila["metricas"]["N2.1"] == 0.75

    def test_sin_sesion_no_se_sirve(self, proyecto_con_tres):
        from fastapi.testclient import TestClient

        import main

        anonimo = TestClient(main.app)
        r = anonimo.get("/proyectos/%s/validacion/comparacion"
                        % proyecto_con_tres["proyecto"])
        assert r.status_code in (401, 403)
