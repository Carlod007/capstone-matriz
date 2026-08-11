# tests/test_estructura_real.py
"""
Deteccion de secciones en formatos reales de revista.

Estos casos provienen del primer lote de articulos reales, donde la deteccion
fallaba: el abstract no se reconocio en ninguno de los cinco y, sin el, ROUGE
no podia calcularse. Se conservan como regresion.
"""

from app.services.document_structure import (
    SECCIONES_SUSTANTIVAS,
    _clasificar_linea,
    _colapsar_espaciado,
    detectar_secciones,
    extraer_abstract,
    nombres_detectados,
)


class TestEncabezadosEspaciados:
    """Estilo tipografico de Elsevier: las letras llegan separadas."""

    def test_abstract_en_mayusculas_espaciado(self):
        assert _clasificar_linea("A B S T R A C T") == "resumen"

    def test_abstract_en_minusculas_espaciado(self):
        assert _clasificar_linea("a b s t r a c t") == "resumen"

    def test_colapsa_solo_si_todas_son_letras_sueltas(self):
        assert _colapsar_espaciado("A B S T R A C T") == "ABSTRACT"
        # Un titulo normal no debe colapsarse.
        assert _colapsar_espaciado("Results and discussion") == "Results and discussion"

    def test_introduccion_espaciada(self):
        assert _clasificar_linea("I N T R O D U C T I O N") == "introduccion"


class TestEncabezadosSinNumerar:
    """Regresion: el limpiador de numeracion se comia la primera letra.

    `[IVXLC]+` con comparacion insensible a mayusculas devoraba la inicial de
    cualquier titulo que empezara por esas letras, de modo que un encabezado
    sin numerar no se reconocia: "Conclusions" quedaba en "onclusions".
    """

    def test_conclusions_sin_numerar(self):
        assert _clasificar_linea("Conclusions") == "conclusion"

    def test_introduction_sin_numerar(self):
        assert _clasificar_linea("Introduction") == "introduccion"

    def test_limitations_sin_numerar(self):
        assert _clasificar_linea("Limitations") == "limitaciones"

    def test_conclusiones_en_espanol_sin_numerar(self):
        assert _clasificar_linea("Conclusiones") == "conclusion"

    def test_introduccion_en_espanol_sin_numerar(self):
        assert _clasificar_linea("Introducción") == "introduccion"

    def test_el_numero_romano_con_separador_si_se_retira(self):
        assert _clasificar_linea("IV. Results") == "resultados"
        assert _clasificar_linea("II. Methods") == "metodo"


class TestVariantesDeEncabezado:
    """Formas encontradas en los articulos reales."""

    def test_methods_and_materials_en_orden_inverso(self):
        assert _clasificar_linea("2. Methods and materials") == "metodo"

    def test_materials_and_methods(self):
        assert _clasificar_linea("2. Materials and Methods") == "metodo"

    def test_results_and_discussions_en_plural(self):
        assert _clasificar_linea("4. Results and discussions") == "resultados"

    def test_experimental_methodology(self):
        assert _clasificar_linea("4. Experimental methodology") == "metodo"

    def test_proposed_approach(self):
        assert _clasificar_linea("3. Proposed approach") == "metodo"

    def test_conclusiones_en_plural(self):
        assert _clasificar_linea("7. Conclusions") == "conclusion"


class TestSeccionesDeDominio:
    """Los articulos de ingenieria titulan segun el dominio, no un vocabulario fijo."""

    def test_titulo_tecnico_numerado_es_cuerpo(self):
        assert _clasificar_linea("2. Finite element analysis") == "cuerpo"
        assert _clasificar_linea("3. Machine learning framework") == "cuerpo"
        assert _clasificar_linea("2. System description") == "cuerpo"

    def test_cuerpo_cuenta_como_seccion_sustantiva(self):
        assert "cuerpo" in SECCIONES_SUSTANTIVAS

    def test_una_frase_del_cuerpo_no_es_encabezado(self):
        assert _clasificar_linea(
            "2. En este apartado se describe el procedimiento seguido para el analisis.") is None

    def test_numeracion_alta_no_es_encabezado(self):
        # Suele ser una lista o una referencia numerada.
        assert _clasificar_linea("47. Otro elemento de la lista") is None

    def test_titulo_demasiado_largo_no_es_encabezado(self):
        assert _clasificar_linea(
            "2. Un titulo excesivamente largo que en realidad es una frase completa") is None


class TestArticuloEstiloElsevier:
    ARTICULO = """Original Research Article
Metabolic state-driven monitoring and control of abnormal pigment formation
Jingchun Sun a,b, Yuanyuan Jiang a,b, Xing Jiang a,b
a State Key Laboratory of Bioreactor Engineering, Shanghai, China
A R T I C L E  I N F O
Keywords:
Sodium gluconate fermentation
Soft sensor
A B S T R A C T
Abnormal pigment formation during late-stage fungal fermentation poses a
significant challenge for product quality. This study established an integrated
framework to understand and control it in Aspergillus niger fermentation,
combining metabolic characterization with intelligent monitoring y validacion.
1. Introduction
Sodium gluconate is widely used in industry and its production depends on
fermentation processes that remain difficult to control in practice.
2. Methods and materials
Se empleo un diseno de escalado con trayectorias industriales de consumo.
3. Machine learning framework
Se entreno un sensor blando con entradas cineticas en tiempo real.
4. Results and discussions
La estrategia suprimio la pigmentacion anomala en las condiciones evaluadas.
5. Conclusions
El marco propuesto es transferible a otras fermentaciones industriales.
References
[1] Autor A. Titulo. Revista, 2023.
"""

    def test_extrae_el_abstract(self):
        ab = extraer_abstract(self.ARTICULO)
        assert ab is not None
        assert "Abnormal pigment formation" in ab
        # No debe arrastrar la portada ni las palabras clave.
        assert "Keywords" not in ab
        assert "Jingchun" not in ab

    def test_reconoce_las_secciones_del_cuerpo(self):
        nombres = nombres_detectados(detectar_secciones(self.ARTICULO))
        assert {"resumen", "introduccion", "metodo", "resultados",
                "conclusion", "referencias"} <= nombres

    def test_cubre_varias_secciones_sustantivas(self):
        nombres = nombres_detectados(detectar_secciones(self.ARTICULO))
        assert len(nombres & set(SECCIONES_SUSTANTIVAS)) >= 3

    def test_la_portada_queda_fuera_de_las_secciones(self):
        secs = detectar_secciones(self.ARTICULO)
        assert secs[0].nombre == "otro"
        assert "Jingchun" in self.ARTICULO[secs[0].inicio:secs[0].fin]
