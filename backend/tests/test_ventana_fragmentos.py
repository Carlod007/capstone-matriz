# tests/test_ventana_fragmentos.py
"""
El verificador tambien lee los parrafos contiguos.

El troceado corta a mitad de frase. Sobre datos reales se llevo justo la parte
que decidia el sentido de una afirmacion: el fragmento entregado empezaba por
«, particularly for MLPs, as it neglects material hardening…» y el trozo
anterior -que no se entrego- terminaba con «the DNV formula underestimates the
load-bearing capacity».

Sin esas cinco palabras no habia forma de saber si el estandar falla por exceso
o por defecto. Con la ventana estrecha el verificador no se equivocaba: no
podia acertar.

Al ampliarla aparecio ademas un fragmento que ninguna version anterior habia
visto, donde el articulo advierte que el estandar «produces some dangerous
results under small bending moments», y con el la primera contradiccion real
detectada por el sistema.

Estas pruebas fijan que el vecino llegue, que no se dupliquen fragmentos y que
el orden sea el del documento: un vecino separado de su fragmento no
reconstruye ninguna frase.
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

pytestmark = pytest.mark.bd

# El caso real, partido por donde lo partio el troceado.
TROZOS = {
    9: "However, the DNV formula underestimates the load-bearing capacity, "
       "particularly for MLPs, as it neglects material hardening.",
    10: ", particularly for MLPs, as it neglects material hardening and contact "
        "stresses induced during manufacturing. As a result, this discrepancy "
        "highlights the need for a revised formula.",
    11: "The P and kappa curves are close to each other at low normalized "
        "moment levels but gradually separate.",
}


@pytest.fixture(scope="module", autouse=True)
def modelos_cargados():
    import main  # noqa: F401


@pytest.fixture
def brecha_con_fragmentos(db, usuario_prueba):
    """Una brecha cuyo unico fragmento recuperado es el trozo 10."""
    from app.models.articulo import Articulo
    from app.models.embedding_doc import EmbeddingDoc
    from app.models.proyecto import Proyecto
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.run import EstadoRun, Run
    from app.models.run_item import EstadoRunItem, RunItem

    pid, aid, rid, iid, bid = (str(uuid.uuid4()) for _ in range(5))
    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Ventana de evidencia",
                    objetivo="Comprobar que llegan los parrafos contiguos",
                    n_articulos_objetivo=1, estado_arte_generado=False))
    db.flush()
    db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="Tuberias"))
    db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
               n_items_total=1, n_items_ok=1))
    db.flush()
    db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                   estado=EstadoRunItem.analizado))
    db.flush()

    ids = {}
    for orden, texto in TROZOS.items():
        eid = str(uuid.uuid4())
        ids[orden] = eid
        db.add(EmbeddingDoc(id=eid, articulo_id=aid, chunk_orden=orden,
                            seccion="cuerpo", texto=texto, embedding=[0.1]))
    db.flush()
    # Solo se recupero el trozo 10: es el caso real.
    db.add(ResultadoBrecha(
        id=bid, run_item_id=iid, tipo_brecha="otra",
        brecha="El estandar puede producir disenos inseguros.",
        oportunidad="o",
        rag_hits=[{"embedding_id": ids[10], "seccion": "cuerpo"}]))
    db.commit()

    try:
        yield {"brecha": bid, "articulo": aid, "proyecto": pid, "ids": ids}
    finally:
        db.rollback()
        db.query(ResultadoBrecha).filter(ResultadoBrecha.id == bid).delete()
        db.query(EmbeddingDoc).filter(
            EmbeddingDoc.articulo_id == aid).delete(synchronize_session=False)
        db.query(RunItem).filter(RunItem.id == iid).delete()
        db.query(Run).filter(Run.id == rid).delete()
        db.query(Articulo).filter(Articulo.id == aid).delete()
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.commit()


def _fragmentos(db, bid):
    from app.models.resultado_brecha import ResultadoBrecha
    from app.routers.verificacion_rt import _fragmentos_de

    rb = db.query(ResultadoBrecha).filter(ResultadoBrecha.id == bid).first()
    return _fragmentos_de(db, rb)


class TestLaVentana:
    def test_llega_la_palabra_que_decide_el_sentido(self, db,
                                                    brecha_con_fragmentos):
        """La prueba del caso real: sin «underestimates» no hay forma de saber
        si el estandar falla por exceso o por defecto."""
        frags = _fragmentos(db, brecha_con_fragmentos["brecha"])
        todo = " ".join(f["texto"] for f in frags)

        assert "underestimates the load-bearing capacity" in todo, (
            "el trozo anterior no llego; el verificador seguiria sin poder "
            "juzgar la direccion del error")

    def test_estan_los_tres_trozos(self, db, brecha_con_fragmentos):
        frags = _fragmentos(db, brecha_con_fragmentos["brecha"])
        assert len(frags) == 3

    def test_van_en_orden_de_documento(self, db, brecha_con_fragmentos):
        """Un vecino separado de su fragmento no reconstruye ninguna frase."""
        frags = _fragmentos(db, brecha_con_fragmentos["brecha"])
        textos = [f["texto"] for f in frags]

        assert textos == [TROZOS[9], TROZOS[10], TROZOS[11]]

    def test_no_se_duplican_cuando_los_vecinos_se_solapan(
            self, db, brecha_con_fragmentos):
        """Con dos fragmentos contiguos recuperados, sus ventanas se pisan."""
        from app.models.resultado_brecha import ResultadoBrecha

        ids = brecha_con_fragmentos["ids"]
        rb = (db.query(ResultadoBrecha)
                .filter(ResultadoBrecha.id == brecha_con_fragmentos["brecha"])
                .first())
        rb.rag_hits = [{"embedding_id": ids[9], "seccion": "cuerpo"},
                       {"embedding_id": ids[10], "seccion": "cuerpo"}]
        db.commit()

        frags = _fragmentos(db, brecha_con_fragmentos["brecha"])
        textos = [f["texto"] for f in frags]

        assert len(textos) == len(set(textos)), "hay fragmentos repetidos"
        assert len(textos) == 3

    def test_sin_hits_no_hay_fragmentos(self, db, brecha_con_fragmentos):
        """El limite: ampliar la ventana no puede inventar contexto donde no
        se recupero nada."""
        from app.models.resultado_brecha import ResultadoBrecha

        rb = (db.query(ResultadoBrecha)
                .filter(ResultadoBrecha.id == brecha_con_fragmentos["brecha"])
                .first())
        rb.rag_hits = []
        db.commit()

        assert _fragmentos(db, brecha_con_fragmentos["brecha"]) == []
