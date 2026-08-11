# tests/test_estructura.py
"""Detección de secciones, corte de bibliografía (M-09) y fragmentación."""

import re

from app.services.document_structure import (
    detectar_secciones,
    extraer_abstract,
    inicio_referencias,
    nombres_detectados,
    seccion_en,
)
from app.utils.chunker import fragmentar
from app.utils.text_extractor import clean_text, legibilidad


TEXTO = """Revista de Prueba doi 10.1000/x Recibido marzo 2024

Abstract
Este estudio evalua el analisis automatico de literatura cientifica mediante
modelos de lenguaje sobre un corpus de articulos indexados en la region.

1. Introduccion
La revision es costosa. Muchas de las references citadas por trabajos previos
se limitan a un unico idioma, lo que restringe su alcance.

3. Metodologia
Diseno cuasi experimental con muestreo intencional y dos evaluadores.

4. Resultados
Precision de 0.71 y exhaustividad de 0.58 sobre el conjunto evaluado.

5. Discusion
El rendimiento depende del dominio disciplinar analizado en cada caso.

Referencias
[1] Smith J. Automated screening. 2023.
[2] Lopez M. Text mining aplicado. 2022.
"""


class TestSecciones:
    def test_reconoce_las_secciones_canonicas(self):
        nombres = nombres_detectados(detectar_secciones(TEXTO))
        assert {"resumen", "introduccion", "metodo", "resultados",
                "discusion", "referencias"} <= nombres

    def test_texto_previo_al_primer_encabezado_es_otro(self):
        secs = detectar_secciones(TEXTO)
        assert secs[0].nombre == "otro"
        assert secs[0].inicio == 0

    def test_las_secciones_cubren_todo_el_texto_sin_solaparse(self):
        secs = detectar_secciones(TEXTO)
        assert secs[0].inicio == 0
        assert secs[-1].fin == len(TEXTO)
        for a, b in zip(secs, secs[1:]):
            assert a.fin == b.inicio

    def test_una_mencion_en_prosa_no_es_un_encabezado(self):
        # "references" aparece dentro de un parrafo de la introduccion.
        secs = detectar_secciones(TEXTO)
        pos = TEXTO.lower().index("references citadas")
        assert seccion_en(secs, pos) == "introduccion"

    def test_ignora_lineas_largas_aunque_empiecen_por_la_palabra(self):
        texto = "Results obtained in this work are discussed at length below " * 3
        assert nombres_detectados(detectar_secciones(texto)) == set()


class TestCorteBibliografia:
    """M-09: el corte no debe activarse con una mención en el cuerpo."""

    def test_conserva_las_secciones_sustantivas(self):
        limpio = clean_text(TEXTO)
        for palabra in ("Metodologia", "Resultados", "Discusion"):
            assert palabra in limpio

    def test_elimina_la_bibliografia(self):
        limpio = clean_text(TEXTO)
        assert "[1] Smith" not in limpio
        assert "[2] Lopez" not in limpio

    def test_mejora_sobre_la_implementacion_anterior(self):
        anterior = re.sub(r"References\b.*", "", TEXTO, flags=re.IGNORECASE | re.DOTALL)
        nuevo = clean_text(TEXTO)
        assert len(nuevo) > len(anterior) * 2

    def test_no_corta_si_la_bibliografia_esta_al_principio(self):
        # Un encabezado en el primer tercio no puede ser la bibliografia real.
        texto = "Referencias\n" + ("contenido sustancial del articulo. " * 200)
        assert inicio_referencias(texto) is None

    def test_sin_bibliografia_devuelve_none(self):
        assert inicio_referencias("Solo texto plano sin encabezados. " * 30) is None


class TestAbstract:
    """Base de la corrección de M-02: la referencia correcta para ROUGE."""

    def test_extrae_el_resumen_y_no_la_portada(self):
        ab = extraer_abstract(TEXTO, min_chars=50)
        assert ab is not None
        assert "analisis automatico" in ab
        assert "doi" not in ab.lower()
        assert "Recibido" not in ab

    def test_devuelve_none_si_no_hay_resumen(self):
        assert extraer_abstract("Texto sin encabezados de ninguna clase. " * 20) is None


class TestFragmentacion:
    def test_las_posiciones_apuntan_al_texto_original(self):
        for f in fragmentar(TEXTO, max_chars=200, overlap=50):
            assert 0 <= f.inicio < f.fin <= len(TEXTO)

    def test_el_solapamiento_se_aplica_realmente(self):
        # Antes `max(cut - overlap, cut)` se resolvia siempre en `cut` y el
        # solapamiento configurado nunca llegaba a aplicarse.
        texto = "palabra " * 800
        frs = fragmentar(texto, max_chars=400, overlap=150)
        assert len(frs) >= 3
        avances = [b.inicio - a.inicio for a, b in zip(frs, frs[1:])]
        assert all(av < 400 for av in avances), avances

    def test_no_pierde_contenido(self):
        frs = fragmentar(TEXTO, max_chars=300, overlap=60)
        unido = " ".join(f.texto for f in frs)
        for termino in ("Metodologia", "0.71", "dominio disciplinar"):
            assert termino in unido

    def test_texto_vacio_no_rompe(self):
        assert fragmentar("") == []
        assert fragmentar("   \n  ") == []


class TestLegibilidad:
    """N0.4"""

    def test_prosa_normal_puntua_alto(self):
        assert legibilidad(TEXTO) >= 0.6

    def test_texto_degradado_puntua_bajo(self):
        assert legibilidad("xkq zzt mmm ppp qqq rrr sss " * 100) < 0.2

    def test_texto_muy_corto_no_puntua(self):
        assert legibilidad("dos palabras") == 0.0
