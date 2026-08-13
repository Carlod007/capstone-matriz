# tests/test_sintesis.py
"""Nivel N5: tipificacion y sintesis."""

import pytest

from app.services.metricas import sintesis as S


class TestReclasificador:
    """N5.2: cuantas veces la heuristica sobrescribe al modelo."""

    def test_marca_el_cambio(self):
        assert S.n5_2_efecto_reclasificador("temática", "metodológica") == 1.0

    def test_no_marca_si_coincide(self):
        assert S.n5_2_efecto_reclasificador("metodológica", "metodológica") == 0.0

    def test_tolera_valores_ausentes(self):
        assert S.n5_2_efecto_reclasificador(None, "metodológica") == 0.0
        assert S.n5_2_efecto_reclasificador("metodológica", None) == 0.0

    def test_la_heuristica_del_pipeline_sobrescribe_de_verdad(self):
        """Comprobacion de que N5.2 mide algo que ocurre.

        Si el reclasificador nunca cambiara nada, la metrica seria constante y
        no valdria la pena. Con un texto cargado de vocabulario metodologico
        deberia imponerse sobre la etiqueta del modelo.
        """
        from app.services.gemini_service import _rebalance_tipo

        texto = ("El estudio no reporta el protocolo de validación ni el muestreo "
                 "empleado, y su diseño experimental impide la reproducibilidad.")
        assert _rebalance_tipo(texto, "temática") == "metodológica"


class TestCobertura:
    """N5.3: que la sintesis represente todas las brechas."""

    BRECHAS = [
        "Falta validacion externa del modelo en cohortes independientes.",
        "No se documenta el consumo energetico del entrenamiento distribuido.",
    ]

    def test_sin_datos_devuelve_cero(self):
        valor, detalle = S.n5_3_cobertura_sintesis("", self.BRECHAS)
        assert valor == 0.0 and "motivo" in detalle

    def test_sin_brechas_devuelve_cero(self):
        valor, _ = S.n5_3_cobertura_sintesis("un estado del arte cualquiera", [])
        assert valor == 0.0

    def test_reporta_las_menos_representadas(self):
        """El detalle debe senalar cual quedo fuera, no solo cuantas."""
        texto = ("La literatura revisada coincide en la falta de validacion externa "
                 "del modelo en cohortes independientes, un problema recurrente.\n\n"
                 "Los trabajos analizados abordan el problema desde enfoques diversos "
                 "y con resultados dispares segun el dominio de aplicacion elegido.")
        valor, detalle = S.n5_3_cobertura_sintesis(texto, self.BRECHAS)
        assert 0.0 <= valor <= 1.0
        assert detalle["n_brechas"] == 2
        assert detalle["menos_representadas"]
        # Ordenadas de peor a mejor: la primera es la que mas riesgo tiene de
        # haberse quedado fuera.
        sims = [d["mejor_similitud"] for d in detalle["menos_representadas"]]
        assert sims == sorted(sims)


class TestCitas:
    """N5.5: el prompt prohibe inventar referencias; hay que comprobarlo."""

    ARTICULOS = [
        {"titulo": "Metabolic state driven monitoring of pigment formation",
         "doi": "10.1016/j.synbio.2026.06.002"},
        {"titulo": "A synergistic optimization framework for heat exchanger networks",
         "doi": "10.1016/j.ces.2026.124686"},
    ]

    def test_sin_citas_es_cero(self):
        texto = ("La literatura revisada coincide en la falta de validacion externa. "
                 "Los enfoques difieren segun el dominio analizado.")
        valor, detalle = S.n5_5_citas_fabricadas(texto, self.ARTICULOS)
        assert valor == 0.0
        assert detalle["n_citas"] == 0

    def test_detecta_un_doi_del_proyecto(self):
        texto = "Segun el trabajo 10.1016/j.ces.2026.124686 la optimizacion mejora."
        valor, detalle = S.n5_5_citas_fabricadas(texto, self.ARTICULOS)
        assert detalle["n_citas"] == 1
        assert detalle["reconocidas"] == 1
        assert valor == 0.0

    def test_detecta_un_doi_inventado(self):
        texto = "Como demuestra 10.9999/inventado.2024.0001, el metodo es superior."
        valor, detalle = S.n5_5_citas_fabricadas(texto, self.ARTICULOS)
        assert detalle["sin_correspondencia"] == 1
        assert valor == 1.0

    def test_detecta_cita_de_autor_y_anio(self):
        texto = "Trabajos previos (Fernandez, 2019) sostienen lo contrario."
        _, detalle = S.n5_5_citas_fabricadas(texto, self.ARTICULOS)
        assert detalle["n_citas"] >= 1
        assert any(c["clase"] == "autor_anio" for c in detalle["muestra"])

    def test_detecta_cita_numerica(self):
        texto = "Diversos autores [12] han abordado el problema."
        _, detalle = S.n5_5_citas_fabricadas(texto, self.ARTICULOS)
        assert any(c["clase"] == "numerica" for c in detalle["muestra"])

    def test_una_cita_junto_al_titulo_del_articulo_se_reconoce(self):
        texto = ("El trabajo sobre synergistic optimization framework for heat "
                 "exchanger networks (Autor, 2026) describe el enfoque.")
        _, detalle = S.n5_5_citas_fabricadas(texto, self.ARTICULOS)
        assert detalle["reconocidas"] >= 1


class TestCatalogo:
    def test_las_metricas_n5_estan_catalogadas(self):
        from app.services.metricas.catalogo import CATALOGO, ficha

        for c in ("N5.2", "N5.3", "N5.5"):
            assert c in CATALOGO, "falta la ficha de %s" % c

        # Dos de las tres se leen al reves: conviene que la interfaz lo sepa.
        assert ficha("N5.2").mejor == "bajo"
        assert ficha("N5.5").mejor == "bajo"
        assert ficha("N5.3").mejor == "alto"
