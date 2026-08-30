# tests/test_redundancia_n34.py
"""
N3.4 contaba las brechas sobrantes, no las redundantes.

Al encontrar una pareja casi identica marcaba solo el segundo elemento, con lo
que el primero de cada pareja quedaba sin contar. Tres brechas identicas daban
0.667 en vez de 1.0: dos de tres marcadas, cuando las tres son intercambiables
y ninguna aporta nada que no aporten las otras.

Ademas el resultado dependia del orden de recorrido, porque «el primero» de
cada pareja lo decidia el orden en que llegaban las claves del diccionario. Una
misma medicion sobre los mismos datos podia dar numeros distintos.

Cambia el significado numerico de la metrica, asi que el detalle guarda una
version de formula: sin ella, los valores de antes y de despues quedarian
mezclados en la serie historica sin forma de distinguirlos.
"""

import os

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")


IDENTICA = ("Falta validacion externa del modelo en cohortes independientes "
            "con datos de otras instituciones.")
DISTINTA = ("El estudio no cuantifica el coste computacional del entrenamiento "
            "en arquitecturas de memoria limitada.")


def _n34(brechas, umbral=0.85):
    from app.services.metricas.niveles import n3_4_redundancia

    return n3_4_redundancia(brechas, umbral=umbral)


class TestElRecuento:
    def test_tres_identicas_son_todas_redundantes(self):
        """El caso que delataba el fallo: ninguna de las tres aporta nada que
        no aporten las otras dos."""
        valor, _ = _n34({"a": IDENTICA, "b": IDENTICA, "c": IDENTICA})

        assert valor == 1.0, (
            "marcar solo el segundo de cada pareja dejaba una sin contar y "
            "daba 0.667")

    def test_dos_identicas_de_cuatro(self):
        valor, detalle = _n34({
            "a": IDENTICA, "b": IDENTICA,
            "c": DISTINTA, "d": "Otra brecha completamente diferente sobre "
                                "el consumo energetico de los sensores.",
        })

        assert valor == 0.5, "dos de cuatro"
        assert len(detalle["pares_duplicados"]) == 1

    def test_sin_duplicados_es_cero(self):
        """El limite: marcar de mas seria peor que marcar de menos."""
        valor, _ = _n34({"a": IDENTICA, "b": DISTINTA})

        assert valor == 0.0

    def test_hace_falta_mas_de_una_brecha(self):
        valor, detalle = _n34({"a": IDENTICA})

        assert valor == 0.0
        assert "al menos dos" in detalle["motivo"]


class TestEsDeterminista:
    def test_el_orden_de_entrada_no_cambia_el_resultado(self):
        """Con el fallo anterior si lo cambiaba: «el primero» de cada pareja se
        salvaba, y cual era el primero dependia del orden de las claves."""
        brechas = {"z": IDENTICA, "a": IDENTICA, "m": DISTINTA}
        al_reves = {"m": DISTINTA, "a": IDENTICA, "z": IDENTICA}

        assert _n34(brechas)[0] == _n34(al_reves)[0]

    def test_las_parejas_guardadas_tambien_son_estables(self):
        """Se guardan para poder auditar el resultado; si cambian de una
        ejecucion a otra, no sirven para eso."""
        brechas = {"z": IDENTICA, "a": IDENTICA}
        primero = _n34(brechas)[1]["pares_duplicados"]
        segundo = _n34({"a": IDENTICA, "z": IDENTICA})[1]["pares_duplicados"]

        assert primero == segundo


class TestLaVersionDeFormula:
    def test_el_detalle_dice_con_que_formula_se_calculo(self):
        """Sin esto, los valores de antes y de despues del arreglo quedan
        mezclados en la serie historica sin forma de distinguirlos."""
        from app.services.metricas.niveles import FORMULA_N3_4

        _, detalle = _n34({"a": IDENTICA, "b": DISTINTA})

        assert detalle["formula"] == FORMULA_N3_4
        assert FORMULA_N3_4 >= 2, (
            "la version debe subir cuando cambia el significado del numero")


class TestDireccionesNoDemostradas:
    """Dos metricas declaraban una direccion que nadie habia comprobado.

    Decir «mayor es mejor» es una afirmacion sobre la calidad, y el panel la
    usa para pintar la lectura. Mientras no haya anotacion humana con la que
    contrastarla, lo honesto es describir el valor y no premiarlo.
    """

    def test_composicion_evidencial_es_descriptiva(self):
        """Una brecha solo de conclusiones es especulacion; una que solo
        describe lo que el articulo dice no senala ningun vacio. Ninguno de los
        dos extremos es la meta."""
        from app.services.metricas.catalogo import ficha

        f = ficha("N2.4")
        assert f.mejor == "neutro"
        assert f.nombre == "Composición evidencial"

    def test_reetiquetado_es_descriptivo(self):
        """Decir «menos es mejor» daba por supuesto que la heuristica estorba,
        y nunca se comprobo si acierta mas o menos que el modelo."""
        from app.services.metricas.catalogo import ficha

        assert ficha("N5.2").mejor == "neutro"
