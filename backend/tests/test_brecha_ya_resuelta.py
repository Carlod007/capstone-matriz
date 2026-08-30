# tests/test_brecha_ya_resuelta.py
"""
N2.6: la brecha pide lo que el articulo ya hizo.

Salio de anotar a mano las cinco brechas de un proyecto real. Dos quedaron como
«parcial», y las dos por lo mismo: presentaban la aportacion del propio
articulo como un vacio abierto. Una pedia desarrollar una formula que el
articulo ya habia desarrollado y validado; la otra planteaba como pendiente la
integracion que el articulo demuestra en su titulo.

Ninguna metrica podia verlo, y menos que ninguna la fidelidad: los articulos
motivan su aportacion explicando que faltaba antes, asi que esas frases estan
en el texto y salen respaldadas una a una. Una de las dos brechas tenia
N2.1 = 1.000 con fidelidad perfecta.

El fallo no vive en ninguna afirmacion suelta sino en el tiempo verbal del
conjunto, y por eso N2.6 es una propiedad de la brecha entera y no de cada
frase.
"""

import os

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")


def _interpretar(payload, n_fragmentos=4):
    import json

    from app.services.verificacion import _interpretar

    return _interpretar(json.dumps(payload), {}, n_fragmentos)


AFIRMACION = {"texto": "El estandar omite el endurecimiento del material.",
              "tipo": "evidencial", "respaldada": True, "fragmento": 1,
              "cita": "does not account for strain hardening",
              "motivo": "el fragmento 1 lo dice"}


class TestSeInterpreta:
    def test_marcada_con_su_cita(self):
        v = _interpretar({
            "afirmaciones": [AFIRMACION],
            "ya_resuelta": True,
            "fragmento_resuelta": 2,
            "cita_resuelta": "a modified expression was proposed",
        })

        assert v.ya_resuelta is True
        assert v.fragmento_resuelta == 2
        assert v.cita_resuelta == "a modified expression was proposed"

    def test_no_marcada_es_lo_normal(self):
        v = _interpretar({"afirmaciones": [AFIRMACION], "ya_resuelta": False})

        assert v.ya_resuelta is False
        assert v.fragmento_resuelta is None
        assert v.cita_resuelta is None

    def test_ausente_no_es_lo_mismo_que_verdadera(self):
        """Un verificador antiguo, o uno que ignore el paso, no debe invalidar
        todas las brechas por omision."""
        v = _interpretar({"afirmaciones": [AFIRMACION]})

        assert v.ya_resuelta is False


class TestNoSeAceptaSinPrueba:
    """Decir que una brecha ya esta resuelta la invalida entera.

    Es la afirmacion mas destructiva que puede hacer el verificador, asi que
    exige senalar donde. Sin fragmento seria una acusacion sin prueba, y el
    falso positivo aqui cuesta descartar trabajo que estaba bien.
    """

    def test_sin_fragmento_no_se_acepta(self):
        v = _interpretar({"afirmaciones": [AFIRMACION], "ya_resuelta": True,
                          "fragmento_resuelta": None,
                          "cita_resuelta": "algo"})

        assert v.ya_resuelta is False

    def test_fragmento_inventado_no_se_acepta(self):
        v = _interpretar({"afirmaciones": [AFIRMACION], "ya_resuelta": True,
                          "fragmento_resuelta": 99}, n_fragmentos=4)

        assert v.ya_resuelta is False
        assert v.fragmento_resuelta is None


class TestEsIndependienteDeLaFidelidad:
    def test_una_brecha_perfecta_puede_estar_ya_resuelta(self):
        """El caso real, y el motivo de que la metrica exista aparte.

        Con todas las afirmaciones respaldadas la fidelidad da 1.0, y aun asi
        la brecha no senala nada pendiente.
        """
        v = _interpretar({
            "afirmaciones": [AFIRMACION,
                             {**AFIRMACION, "texto": "El estandar subestima la "
                                                     "capacidad de carga."}],
            "ya_resuelta": True,
            "fragmento_resuelta": 3,
            "cita_resuelta": "the formula in this study ensures safe results",
        })

        assert v.fidelidad == 1.0, "todas las evidenciales estan respaldadas"
        assert v.ya_resuelta is True, "y aun asi la brecha no aporta nada nuevo"

    def test_aparece_en_el_resumen(self):
        v = _interpretar({"afirmaciones": [AFIRMACION], "ya_resuelta": True,
                          "fragmento_resuelta": 1, "cita_resuelta": "x"})
        r = v.resumen()

        assert r["ya_resuelta"] is True
        assert r["cita_resuelta"] == "x"


class TestElCatalogo:
    def test_esta_declarada_y_va_al_reves(self):
        from app.services.metricas.catalogo import ficha

        f = ficha("N2.6")
        assert f is not None, "sin ficha, el panel la mostraria sin nombre"
        assert f.mejor == "bajo", (
            "una brecha ya resuelta es peor, no mejor; con la direccion al "
            "reves el panel leeria un 1.0 como un buen resultado")
        assert f.rango == "0 o 1", "es de si o no: se cuenta, no se promedia"
