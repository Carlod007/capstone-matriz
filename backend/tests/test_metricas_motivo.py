# tests/test_metricas_motivo.py
"""
Cuando una metrica no tiene valor, el panel dice por que.

El motivo se guardaba junto a cada medicion descartada y la pantalla no lo
usaba: mostraba «no produjo valores», que es cierto y no explica nada. En las
ROUGE de un proyecto real el motivo estaba en la base desde el primer analisis
-el resumen y el abstract en idiomas distintos- y el lector no podia verlo.

Tambien se informa de cuantas mediciones se intentaron: sin ese dato, «n=0» no
distingue entre «no se midio nada» y «se midieron cinco y ninguna aplicaba».
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

pytestmark = pytest.mark.bd

MOTIVO = ("ROUGE no era aplicable: mide palabras compartidas y el resumen y el "
          "abstract estaban en idiomas distintos.")


@pytest.fixture(scope="module", autouse=True)
def modelos_cargados():
    import main  # noqa: F401


@pytest.fixture
def proyecto_con_metricas(db, usuario_prueba):
    """Un analisis con dos brechas: ROUGE descartada y una metrica con valor."""
    from app.models.articulo import Articulo
    from app.models.metrica import Metrica
    from app.models.proyecto import Proyecto
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.run import EstadoRun, Run
    from app.models.run_item import EstadoRunItem, RunItem

    pid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Motivos",
                    objetivo="Comprobar que se explica la ausencia de datos",
                    n_articulos_objetivo=2, estado_arte_generado=False))
    db.flush()
    db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
               n_items_total=2, n_items_ok=2))
    db.flush()

    brechas = []
    for i in range(2):
        aid, iid, bid = (str(uuid.uuid4()) for _ in range(3))
        db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="A%d" % i))
        db.flush()
        db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                       estado=EstadoRunItem.analizado))
        db.flush()
        db.add(ResultadoBrecha(id=bid, run_item_id=iid, tipo_brecha="otra",
                               brecha="b", oportunidad="o", rag_hits=[]))
        brechas.append(bid)
    db.flush()

    for bid in brechas:
        # Sin valor y con motivo: es el caso de las ROUGE entre idiomas.
        db.add(Metrica(id=str(uuid.uuid4()), proyecto_id=pid, ambito="brecha",
                       referencia_id=bid, codigo="N4.1a", valor=None,
                       detalle={"aplicable": False, "motivo": MOTIVO}))
        # Con valor: sirve de contraste, no debe llevar motivo.
        db.add(Metrica(id=str(uuid.uuid4()), proyecto_id=pid, ambito="brecha",
                       referencia_id=bid, codigo="N4.2", valor=0.9,
                       detalle={"motivo": "esto no debe salir"}))
    db.commit()

    try:
        yield {"proyecto": pid, "run": rid, "brechas": brechas}
    finally:
        db.rollback()
        db.query(Metrica).filter(Metrica.proyecto_id == pid).delete(
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


def _metrica(cliente, pid, codigo):
    r = cliente.get(f"/proyectos/{pid}/metricas")
    assert r.status_code == 200, r.text
    return next(m for m in r.json()["metricas"] if m["codigo"] == codigo)


class TestMotivoDeLaAusencia:
    def test_sin_valor_se_explica_el_porque(self, cliente,
                                            proyecto_con_metricas):
        m = _metrica(cliente, proyecto_con_metricas["proyecto"], "N4.1a")

        assert m["n"] == 0
        assert m["motivo_sin_datos"] == MOTIVO
        assert m["n_intentos"] == 2, (
            "n=0 no distingue entre no medir nada y medir dos veces sin que "
            "ninguna aplicara")

    def test_con_valor_no_se_muestra_motivo(self, cliente,
                                            proyecto_con_metricas):
        """El limite: un motivo guardado junto a una medicion valida no es una
        explicacion de ausencia, y sacarlo confundiria."""
        m = _metrica(cliente, proyecto_con_metricas["proyecto"], "N4.2")

        assert m["n"] == 2
        assert m["motivo_sin_datos"] is None

    def test_con_motivos_distintos_no_se_inventa_uno(self, db, cliente,
                                                     proyecto_con_metricas):
        """Resumir dos razones en una seria elegir por el lector cual vale."""
        from app.models.metrica import Metrica

        pid = proyecto_con_metricas["proyecto"]
        (db.query(Metrica)
           .filter(Metrica.proyecto_id == pid, Metrica.codigo == "N4.1a")
           .limit(1).all())
        primera = (db.query(Metrica)
                     .filter(Metrica.proyecto_id == pid,
                             Metrica.codigo == "N4.1a")
                     .first())
        primera.detalle = {"aplicable": False, "motivo": "otra razon distinta"}
        db.commit()

        m = _metrica(cliente, pid, "N4.1a")
        assert m["n"] == 0
        assert m["motivo_sin_datos"] is None
        assert m["n_intentos"] == 2
