# tests/test_metrics_v1_rouge.py
"""
El camino antiguo de metricas tambien respeta el idioma.

La capa v2 declaraba ROUGE "no aplicable" entre idiomas distintos, pero
`app/services/metrics.py` —el que alimenta /metrics/resumen y el PDF del
panel— seguia promediando esos ceros con los valores buenos. Corregirlo en un
sitio y no en el otro es peor que no corregirlo: deja dos cifras distintas
para lo mismo sin decir cual vale.

La regla tiene que ser la misma que en v2: se compara solo si el idioma se
reconoce y coincide.
"""

import os

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

# Lo bastante largos para que el detector se pronuncie: con una frase suelta
# responde "indeterminado", y esa es justamente la situacion que la regla debe
# tratar como no comparable.
ABSTRACT_EN = (
    "This paper proposes a graph neural network to predict the performance of "
    "heat exchanger networks. The model is trained on a fixed superstructure "
    "and evaluated against mathematical programming baselines on sixty "
    "industrial cases. Results show that the surrogate reduces computation "
    "time while keeping the optimality gap below five percent in most of the "
    "evaluated configurations of the network."
)
RESUMEN_ES = (
    "El trabajo propone una red neuronal de grafos para predecir el "
    "rendimiento de las redes de intercambiadores de calor. El modelo se "
    "entrena sobre una superestructura fija y se evalua frente a la "
    "programacion matematica en sesenta casos industriales. Los resultados "
    "muestran que el sustituto reduce el tiempo de computo manteniendo la "
    "brecha de optimalidad por debajo del cinco por ciento."
)
RESUMEN_EN = (
    "The work proposes a graph neural network to predict the performance of "
    "heat exchanger networks. The model is trained on a fixed superstructure "
    "and evaluated against mathematical programming on sixty industrial "
    "cases. Results show the surrogate reduces computation time while the "
    "optimality gap stays below five percent in most configurations."
)


class TestDeteccionDeIdioma:
    def test_reconoce_los_dos_idiomas(self):
        """Si esto fallara, la regla no podria distinguir nada."""
        from app.services.metricas import texto as T

        assert T.idioma(ABSTRACT_EN) == "en"
        assert T.idioma(RESUMEN_ES) == "es"

    def test_con_texto_corto_no_se_pronuncia(self):
        """Y por eso la regla exige idioma reconocido, no solo que coincida:
        con dos textos cortos ambos salen iguales y compararlos seria volver a
        promediar ceros sin saberlo."""
        from app.services.metricas import texto as T

        assert T.idioma("El modelo.") not in ("es", "en")


class TestMismaReglaQueV2:
    """La condicion de v1 debe dar el mismo veredicto que `rouge_aplicable`."""

    def _aplicable_v1(self, ref, hyp):
        from app.services.metricas import texto as T

        a, b = T.idioma(ref), T.idioma(hyp)
        return a == b and a in ("es", "en")

    def _aplicable_v2(self, ref, hyp):
        from app.services.metricas import niveles as N

        return N.n4_calidad_resumen(hyp, ref).rouge_aplicable

    @pytest.mark.parametrize("ref,hyp", [
        (ABSTRACT_EN, RESUMEN_ES),   # idiomas distintos
        (ABSTRACT_EN, RESUMEN_EN),   # mismo idioma
        (ABSTRACT_EN, "Muy corto."),  # indeterminado
    ])
    def test_los_dos_caminos_coinciden(self, ref, hyp):
        assert self._aplicable_v1(ref, hyp) == self._aplicable_v2(ref, hyp)


@pytest.fixture
def proyecto_con_resumen(db, usuario_prueba):
    """Proyecto completo: ejecucion, articulo, brecha y resumen.

    Hace falta el conjunto entero. `project_indicators` sale por un atajo si
    el proyecto no tiene ejecuciones o no tiene brechas, y ese atajo no llega
    al calculo de ROUGE: una prueba montada a medias comprobaria el atajo
    creyendo que comprueba el calculo.
    """
    import uuid

    from app.models.articulo import Articulo
    from app.models.proyecto import Proyecto
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.resultado_resumen import ResultadoResumen
    from app.models.run import EstadoRun, Run
    from app.models.run_item import EstadoRunItem, RunItem

    pid, aid, rid, iid = (str(uuid.uuid4()) for _ in range(4))
    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Idiomas distintos",
                    objetivo="Comprobar el promedio de ROUGE en el camino v1",
                    n_articulos_objetivo=1, estado_arte_generado=False))
    db.flush()
    db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="Articulo"))
    db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
               n_items_total=1, n_items_ok=1))
    db.flush()
    db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                   estado=EstadoRunItem.analizado))
    db.flush()
    db.add(ResultadoBrecha(id=str(uuid.uuid4()), run_item_id=iid,
                           tipo_brecha="otra", brecha="una brecha",
                           oportunidad="una oportunidad", rag_hits=[]))
    db.commit()

    def poner_resumen(generado, referencia):
        db.add(ResultadoResumen(id=str(uuid.uuid4()), articulo_id=aid,
                                resumen_generado=generado,
                                resumen_referencia=referencia))
        db.commit()

    try:
        yield {"proyecto": pid, "articulo": aid, "run": rid,
               "poner_resumen": poner_resumen}
    finally:
        db.rollback()
        db.query(ResultadoResumen).filter(
            ResultadoResumen.articulo_id == aid).delete(synchronize_session=False)
        db.query(ResultadoBrecha).filter(
            ResultadoBrecha.run_item_id == iid).delete(synchronize_session=False)
        db.query(RunItem).filter(RunItem.run_id == rid).delete(
            synchronize_session=False)
        db.query(Run).filter(Run.id == rid).delete()
        db.query(Articulo).filter(Articulo.id == aid).delete()
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.commit()


@pytest.mark.bd
class TestPromedios:
    def test_entre_idiomas_distintos_no_da_numero(self, db, proyecto_con_resumen):
        """Un cero se lee como "los resumenes no se parecen en nada", y lo que
        ocurre es que no habia nada comparable."""
        from app.services import metrics

        proyecto_con_resumen["poner_resumen"](RESUMEN_ES, ABSTRACT_EN)

        p = (metrics.project_indicators(db, proyecto_con_resumen["proyecto"])
             or {}).get("promedios", {})

        assert p.get("avg_rouge1_f1") is None, (
            "con idiomas distintos no debe salir un numero, salio %r"
            % p.get("avg_rouge1_f1"))
        assert p.get("rouge_descartados_idioma") == 1
        assert p.get("rouge_pares_comparados") == 0

    def test_en_el_mismo_idioma_si_da_numero(self, db, proyecto_con_resumen):
        """El contraste: sin esta, devolver siempre None pasaria la anterior."""
        from app.services import metrics

        proyecto_con_resumen["poner_resumen"](RESUMEN_EN, ABSTRACT_EN)

        p = (metrics.project_indicators(db, proyecto_con_resumen["proyecto"])
             or {}).get("promedios", {})

        assert p.get("avg_rouge1_f1") is not None
        assert p.get("avg_rouge1_f1") > 0
        assert p.get("rouge_pares_comparados") == 1
        assert p.get("rouge_descartados_idioma") == 0

    def test_un_proyecto_sin_analizar_tampoco_da_cero(self, db, usuario_prueba):
        """El atajo de "sin ejecuciones" devolvia 0.0 en las tres ROUGE, que es
        el mismo cero enganoso por otra puerta."""
        import uuid

        from app.models.proyecto import Proyecto
        from app.services import metrics

        pid = str(uuid.uuid4())
        db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                        tema_principal="Sin analizar",
                        objetivo="Comprobar el atajo de proyecto vacio",
                        n_articulos_objetivo=1, estado_arte_generado=False))
        db.commit()
        try:
            r = metrics.project_indicators(db, pid) or {}
            p = r.get("promedios", {})
            assert p.get("avg_rouge1_f1") is None
            assert p.get("avg_rouge1_prec") is None
            assert r.get("rouge1_f1") is None
        finally:
            db.rollback()
            db.query(Proyecto).filter(Proyecto.id == pid).delete()
            db.commit()
