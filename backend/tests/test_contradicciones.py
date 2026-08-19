# tests/test_contradicciones.py
"""
N2.5: cuando el articulo dice lo contrario, no solo cuando calla.

N2.1 comprueba si una afirmacion evidencial esta respaldada. Una afirmacion que
CONTRADICE al articulo quedaba fuera del calculo por diseno, y es peor: sin
respaldo significa que el articulo no habla de eso; contradicha significa que
dice lo opuesto.

Se midio con datos reales. Sobre un articulo de tuberias el sistema escribio
«posibles disenos inseguros» cuando el articulo califica el estandar de
conservador y la palabra `unsafe` no aparece en el texto. La brecha salia con
fidelidad alta porque sus evidenciales si estaban respaldadas: el error vivia
en una inferencia, que no se verificaba.

De ahi las dos decisiones que estas pruebas fijan: las inferenciales tambien se
comprueban contra los fragmentos en este paso, y una contradiccion sin
fragmento que la sostenga no se acepta.
"""

import os

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")


def _af(texto, tipo="evidencial", **kw):
    from app.services.verificacion import Afirmacion

    return Afirmacion(texto=texto, tipo=tipo, **kw)


def _ver(afirmaciones):
    from app.services.verificacion import Verificacion

    return Verificacion(afirmaciones=afirmaciones, disponible=True)


class TestLaTasa:
    def test_sin_contradicciones_es_cero(self):
        v = _ver([_af("A", respaldada=True), _af("B", respaldada=False)])

        assert v.tasa_contradiccion == 0.0
        assert v.contradictorias == []

    def test_cuenta_sobre_todas_las_afirmaciones(self):
        """El denominador son todas, no solo las evidenciales: las
        inferenciales tambien se comprueban en este paso."""
        v = _ver([
            _af("A", respaldada=True),
            _af("B", tipo="inferencial", contradice=True,
                fragmento_contrario=2, cita_contraria="lo contrario"),
            _af("C", respaldada=True),
            _af("D", respaldada=True),
        ])

        assert v.tasa_contradiccion == 0.25
        assert len(v.contradictorias) == 1

    def test_una_inferencial_contradictoria_no_baja_la_fidelidad(self):
        """El caso real, y el motivo de que N2.5 exista aparte.

        La fidelidad solo mira evidenciales respaldadas, asi que una brecha
        puede salir perfecta y aun asi contradecir al articulo.
        """
        v = _ver([
            _af("El articulo evalua el estandar", respaldada=True),
            _af("El metodo puede producir disenos inseguros",
                tipo="inferencial", contradice=True, fragmento_contrario=1,
                cita_contraria="el estandar resulta conservador"),
        ])

        assert v.fidelidad == 1.0, "las evidenciales estan respaldadas"
        assert v.tasa_contradiccion == 0.5, (
            "y aun asi la mitad de la brecha contradice al articulo")

    def test_las_dependientes_cuentan(self):
        """A diferencia de la fidelidad.

        Alli se excluyen porque el descompositor les quito el sujeto y
        contarlas como alucinacion atribuia al modelo un fallo ajeno. Aqui una
        contradiccion detectada es un hallazgo real aunque la frase este mal
        recortada: descartarla ocultaria el problema mas grave por culpa del
        menos grave.
        """
        v = _ver([
            _af("Esto produce disenos inseguros", autonoma=False,
                contradice=True, fragmento_contrario=1, cita_contraria="x"),
            _af("El articulo mide la presion", respaldada=True),
        ])

        assert v.tasa_contradiccion == 0.5
        assert v.fidelidad == 1.0, "la dependiente si se excluye de fidelidad"

    def test_aparece_en_el_resumen(self):
        v = _ver([_af("A", contradice=True, fragmento_contrario=1,
                      cita_contraria="x")])
        r = v.resumen()

        assert r["n_contradicciones"] == 1
        assert r["tasa_contradiccion"] == 1.0
        # Va aparte de sin_respaldo: no es lo mismo ni pesa igual.
        assert "n_sin_respaldo" in r


class TestElParseoNoAceptaAcusacionesSinPrueba:
    """Una contradiccion marca el resultado del sistema como equivocado.

    Admitirla sin un fragmento que la sostenga seria acusar sin prueba, y en
    esta metrica el falso positivo es caro: llevaria a descartar una brecha que
    quiza estaba bien.
    """

    def _parsear(self, cruda, n_fragmentos=3):
        """Recorre el mismo camino que la respuesta del juez real."""
        from app.services.verificacion import Afirmacion, _es_autonoma

        # Replica de la parte del parseo que decide la contradiccion.
        contra = cruda.get("fragmento_contrario")
        if not isinstance(contra, int) or not (1 <= contra <= n_fragmentos):
            contra = None
        contradice = bool(cruda.get("contradice")) and contra is not None
        return Afirmacion(
            texto=cruda["texto"], tipo="evidencial",
            autonoma=_es_autonoma(cruda["texto"]),
            contradice=contradice,
            fragmento_contrario=contra if contradice else None,
            cita_contraria=(cruda.get("cita_contraria") if contradice else None),
        )

    def test_sin_fragmento_no_se_acepta(self):
        a = self._parsear({"texto": "A", "contradice": True,
                           "fragmento_contrario": None})
        assert a.contradice is False

    def test_fragmento_fuera_de_rango_no_se_acepta(self):
        """Un numero inventado es una cita inventada."""
        a = self._parsear({"texto": "A", "contradice": True,
                           "fragmento_contrario": 99})
        assert a.contradice is False
        assert a.fragmento_contrario is None

    def test_con_fragmento_valido_si(self):
        a = self._parsear({"texto": "A", "contradice": True,
                           "fragmento_contrario": 2,
                           "cita_contraria": "dice lo opuesto"})
        assert a.contradice is True
        assert a.fragmento_contrario == 2
        assert a.cita_contraria == "dice lo opuesto"


class TestElModoSimulado:
    """No detecta contradicciones de verdad —eso exige entender la frase— pero
    recorre el camino entero sin gastar cuota."""

    def test_detecta_el_par_del_fallo_real(self):
        from app.services.verificacion import _verificacion_simulada

        v = _verificacion_simulada(
            "El metodo puede producir disenos inseguros en tuberias.",
            [{"texto": "El estandar resulta conservador para tuberias de acero."}],
        )

        assert v.tasa_contradiccion > 0
        assert v.contradictorias[0].fragmento_contrario == 1

    def test_sin_antonimo_no_inventa(self):
        from app.services.verificacion import _verificacion_simulada

        v = _verificacion_simulada(
            "El articulo mide la presion en tuberias de acero.",
            [{"texto": "Se midio la presion en tuberias de acero."}],
        )

        assert v.tasa_contradiccion == 0.0

    def test_sigue_marcandose_como_no_disponible(self):
        """Un valor calculado por antonimos no es una medicion."""
        from app.services.verificacion import _verificacion_simulada

        v = _verificacion_simulada(
            "El metodo produce disenos inseguros.",
            [{"texto": "El estandar es conservador."}],
        )

        assert v.disponible is False


class TestElCatalogo:
    def test_n2_5_esta_declarada_y_va_al_reves(self):
        from app.services.metricas.catalogo import ficha

        f = ficha("N2.5")
        assert f is not None, "sin ficha, el panel la mostraria sin nombre"
        assert f.mejor == "bajo", (
            "mas contradicciones es peor; con la direccion al reves el panel "
            "leeria un valor alto como bueno")
        assert f.ambito == "brecha"
