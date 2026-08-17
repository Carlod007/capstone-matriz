# tests/test_descomposicion.py
"""
Afirmaciones que perdieron el sujeto al descomponerse.

Sobre datos reales, cuatro de las cinco brechas de una prueba bajaron de 1.0
de fidelidad por afirmaciones como "Esto limita su fiabilidad" o
"Esto lleva a inestabilidad en la optimizacion". Sin antecedente no hay
fragmento que pueda respaldarlas, asi que contarlas como alucinacion atribuye
al modelo un fallo que es del verificador.

Estas pruebas fijan ese comportamiento y no gastan cuota: trabajan sobre la
estructura, sin llamar a la API.
"""

import os

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)


class TestDeteccion:
    @pytest.mark.parametrize("texto", [
        "Esto permite que las predicciones violen restricciones bioquimicas.",
        "Esto lleva a inestabilidad en la optimizacion.",
        "Esto limita su fiabilidad.",
        "Ello impide su aplicacion directa.",
        "Eso reduce la precision.",
        "Lo anterior invalida el resultado.",
        "Dicho enfoque no se evaluo.",
        "Dichas limitaciones no se cuantificaron.",
        "se basan en... una superestructura predefinida.",
        "El modelo omite factores… como el endurecimiento.",
    ])
    def test_se_marcan_las_que_perdieron_el_sujeto(self, texto):
        from app.services.verificacion import _es_autonoma

        assert _es_autonoma(texto) is False

    @pytest.mark.parametrize("texto", [
        "La ausencia de restricciones enzimaticas permite predicciones irreales.",
        "El estandar DNV-ST-F101 omite los efectos de fabricacion.",
        "Este articulo evalua sesenta muestras.",
        "Este estudio no reporta el acuerdo entre anotadores.",
        "Estos autores emplearon espectroscopia Raman.",
        "Estas limitaciones afectan al diseno de la red.",
        "El marco propuesto se valido a escala piloto.",
    ])
    def test_no_se_marcan_las_autonomas(self, texto):
        """El filtro se queda corto a proposito.

        "Este articulo...", "Estos autores..." y "Estas limitaciones..."
        remiten al contexto, pero traen un sustantivo con el que buscar en los
        fragmentos. Descartarlas subiria la fidelidad excluyendo afirmaciones
        que si se podian comprobar, y una metrica que se infla sola no sirve.
        """
        from app.services.verificacion import _es_autonoma

        assert _es_autonoma(texto) is True


class TestFidelidad:
    def _v(self, *afirmaciones):
        from app.services.verificacion import Afirmacion, Verificacion

        return Verificacion(
            afirmaciones=[Afirmacion(**a) for a in afirmaciones],
            disponible=True,
        )

    def test_las_dependientes_no_hunden_la_fidelidad(self):
        """El caso real: una evidencial respaldada y tres sin sujeto. Antes
        salia 0.25; debe salir 1.0, porque de las comprobables ninguna falla."""
        from app.services.verificacion import EVIDENCIAL

        v = self._v(
            {"texto": "El estandar omite los efectos de fabricacion.",
             "tipo": EVIDENCIAL, "respaldada": True, "autonoma": True},
            {"texto": "Esto limita su fiabilidad.",
             "tipo": EVIDENCIAL, "respaldada": False, "autonoma": False},
            {"texto": "Esto lleva a inestabilidad.",
             "tipo": EVIDENCIAL, "respaldada": False, "autonoma": False},
            {"texto": "Esto reduce la generalizacion.",
             "tipo": EVIDENCIAL, "respaldada": False, "autonoma": False},
        )
        assert v.fidelidad == 1.0
        assert len(v.dependientes) == 3

    def test_una_alucinacion_de_verdad_si_baja_la_fidelidad(self):
        """El arreglo no debe tapar el fallo que la metrica existe para ver."""
        from app.services.verificacion import EVIDENCIAL

        v = self._v(
            {"texto": "El articulo mide la temperatura.",
             "tipo": EVIDENCIAL, "respaldada": True, "autonoma": True},
            {"texto": "El articulo evaluo sesenta plantas industriales.",
             "tipo": EVIDENCIAL, "respaldada": False, "autonoma": True},
        )
        assert v.fidelidad == 0.5

    def test_sin_evidenciales_autonomas_la_fidelidad_es_cero(self):
        """Si todas perdieron el sujeto no hay nada verificado, y decir 1.0
        seria peor que decir 0.0: afirmaria una fidelidad que nadie comprobo."""
        from app.services.verificacion import EVIDENCIAL

        v = self._v(
            {"texto": "Esto limita su fiabilidad.",
             "tipo": EVIDENCIAL, "respaldada": False, "autonoma": False},
        )
        assert v.fidelidad == 0.0

    def test_el_resumen_cuenta_las_descartadas(self):
        """Si esto sube, el problema esta en la descomposicion y no en el
        modelo que redacto la brecha. Tiene que verse."""
        from app.services.verificacion import EVIDENCIAL

        v = self._v(
            {"texto": "El articulo usa espectroscopia Raman.",
             "tipo": EVIDENCIAL, "respaldada": True, "autonoma": True},
            {"texto": "Esto permite el control en linea.",
             "tipo": EVIDENCIAL, "respaldada": False, "autonoma": False},
        )
        r = v.resumen()
        assert r["n_dependientes"] == 1
        assert r["n_sin_respaldo"] == 0


class TestInstruccion:
    def test_el_prompt_prohibe_los_pronombres(self):
        """La primera defensa es pedirlo bien; el filtro es la segunda."""
        from app.services.verificacion import SYS_PROMPT

        assert "Esto" in SYS_PROMPT
        assert "prohibido" in SYS_PROMPT.lower()
        assert "puntos suspensivos" in SYS_PROMPT.lower()
