# tests/test_rouge_no_aplicable.py
"""
ROUGE cuando resumen y abstract estan en idiomas distintos.

ROUGE cuenta palabras compartidas. Con el resumen en espanol y el abstract en
ingles da un valor cercano a cero por construccion, por fiel que sea el
resumen: en el primer lote real salia 0.05 mientras la similitud semantica era
0.90. La capa detectaba el caso, pero los campos se quedaban en su 0.0 por
defecto y se guardaban asi, de modo que la pantalla mostraba "0.000" — el
mismo fallo que este proyecto vino a corregir.

Estas pruebas no gastan cuota: comprueban la estructura del calculo.
"""

import os

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

ABSTRACT_EN = (
    "This paper proposes a graph neural network to predict heat exchanger "
    "network performance. The model is trained on a fixed superstructure and "
    "evaluated against mathematical programming baselines on sixty cases."
)
RESUMEN_ES = (
    "El trabajo propone una red neuronal de grafos para predecir el "
    "rendimiento de redes de intercambiadores de calor. El modelo se entrena "
    "sobre una superestructura fija y se evalua frente a programacion "
    "matematica en sesenta casos."
)
RESUMEN_EN = (
    "The work proposes a graph neural network to predict the performance of "
    "heat exchanger networks, trained on a fixed superstructure and evaluated "
    "against mathematical programming on sixty cases."
)


class TestAplicabilidad:
    def test_entre_idiomas_distintos_no_aplica(self):
        from app.services.metricas import niveles as N

        m = N.n4_calidad_resumen(RESUMEN_ES, ABSTRACT_EN)
        assert m.rouge_aplicable is False
        assert m.motivo, "tiene que explicar por que no aplica"
        assert "idioma" in m.motivo.lower()

    def test_en_el_mismo_idioma_si_aplica(self):
        from app.services.metricas import niveles as N

        m = N.n4_calidad_resumen(RESUMEN_EN, ABSTRACT_EN)
        assert m.rouge_aplicable is True
        assert m.rouge1_f1 > 0, "con vocabulario compartido debe medir algo"

    def test_la_similitud_semantica_se_calcula_igual(self):
        """Es la que sigue valiendo entre idiomas, y la razon de que no
        aplicar ROUGE no deje al articulo sin medicion de resumen."""
        from app.services.metricas import niveles as N

        m = N.n4_calidad_resumen(RESUMEN_ES, ABSTRACT_EN)
        assert m.similitud_semantica is not None


@pytest.mark.bd
class TestComoSeGuarda:
    """Lo que importa de verdad: que en la base quede sin valor, no en cero.

    Un 0.0 guardado se muestra como "0.000" y se lee como "el resumen no se
    parece en nada al abstract", que es exactamente lo contrario de lo que
    ocurre.
    """

    def test_las_rouge_se_guardan_sin_valor(self, db, usuario_prueba,
                                            monkeypatch):
        import uuid

        from app.models.articulo import Articulo
        from app.models.metrica import Metrica
        from app.models.proyecto import Proyecto
        from app.models.resultado_brecha import ResultadoBrecha
        from app.models.run import Run
        from app.models.run_item import EstadoRunItem, RunItem
        from app.services.verificacion import Afirmacion, Verificacion
        import app.routers.runs as runs_router
        from app.routers.runs import _registrar_metricas

        pid, aid, rid, iid = (str(uuid.uuid4()) for _ in range(4))
        db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                        tema_principal="Idiomas distintos",
                        objetivo="Comprobar que ROUGE no se guarda en cero",
                        n_articulos_objetivo=1, estado_arte_generado=False))
        db.flush()
        art = Articulo(id=aid, proyecto_id=pid, doi=None, titulo="Articulo")
        db.add(art)
        db.add(Run(id=rid, proyecto_id=pid, n_items_total=1, n_items_ok=0))
        db.flush()
        db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                       estado=EstadoRunItem.analizado))
        db.flush()
        rb = ResultadoBrecha(id=str(uuid.uuid4()), run_item_id=iid,
                             tipo_brecha="otra", brecha="una brecha",
                             oportunidad="una oportunidad", rag_hits=[])
        db.add(rb)
        db.flush()

        # El texto del articulo lleva el abstract en ingles; el resumen que se
        # le pasa va en espanol.
        texto = "Abstract\n" + ABSTRACT_EN + "\n\n1. Introduction\nTexto." * 20
        res = {"brecha": "una brecha", "resumen": RESUMEN_ES}

        # El juez se sustituye por una respuesta disponible y determinista:
        # fija que el pipeline normal guarde tambien N2.5 y su evidencia, sin
        # hacer una llamada real al modelo.
        afirmacion = Afirmacion(
            texto="El articulo sostiene lo contrario.",
            tipo="evidencial", respaldada=True, fragmento=1, cita="cita",
            contradice=True, fragmento_contrario=1,
            cita_contraria="fragmento contrario")
        monkeypatch.setattr(
            runs_router, "verificar",
            lambda _brecha, _fragmentos: Verificacion(
                afirmaciones=[afirmacion], disponible=True))

        try:
            _registrar_metricas(db, art, rb, res, texto, [], None)
            db.commit()

            guardadas = {
                m.codigo: m for m in db.query(Metrica)
                .filter(Metrica.referencia_id == rb.id).all()
            }
            for codigo in ("N4.1a", "N4.1b", "N4.1c", "N4.1d", "N4.1e"):
                if codigo not in guardadas:
                    continue
                m = guardadas[codigo]
                assert m.valor is None, (
                    "%s se guardo como %r; debe quedar sin valor" % (codigo, m.valor))
                assert (m.detalle or {}).get("aplicable") is False
                assert (m.detalle or {}).get("motivo")

            # La similitud semantica si tiene que traer numero.
            if "N4.2" in guardadas:
                assert guardadas["N4.2"].valor is not None

            assert guardadas["N2.5"].valor == 1.0
            contradiccion = guardadas["N2.5"].detalle["contradicciones"][0]
            assert contradiccion["afirmacion"] == afirmacion.texto
            assert contradiccion["fragmento"] == 1
            assert contradiccion["cita"] == "fragmento contrario"
        finally:
            db.rollback()
            db.query(Metrica).filter(Metrica.referencia_id == rb.id).delete(
                synchronize_session=False)
            db.query(Metrica).filter(Metrica.proyecto_id == pid).delete(
                synchronize_session=False)
            db.query(ResultadoBrecha).filter(ResultadoBrecha.id == rb.id).delete()
            db.query(RunItem).filter(RunItem.run_id == rid).delete(
                synchronize_session=False)
            db.query(Run).filter(Run.id == rid).delete()
            db.query(Articulo).filter(Articulo.id == aid).delete()
            db.query(Proyecto).filter(Proyecto.id == pid).delete()
            db.commit()
