# tests/test_metricas.py
"""Capa de medición v2: niveles N1, N3 y N4, y descripción de distribuciones."""

import pytest

from app.services.metricas import distribucion as D
from app.services.metricas import niveles as N
from app.services.metricas import texto as T
from app.services.metricas.catalogo import ficha_para_version


# ------------------------------------------------------------------ texto
class TestTokenizacion:
    def test_normaliza_tildes(self):
        assert T.tokenizar("Metodología") == T.tokenizar("metodologia")

    def test_conserva_cifras(self):
        assert "0.71" in T.tokenizar("precision de 0.71 obtenida")

    def test_tokens_contenido_descarta_vacias(self):
        toks = T.tokens_contenido("el estudio de la muestra en los datos")
        assert "estudio" in toks and "muestra" in toks
        assert "el" not in toks and "de" not in toks

    def test_lista_de_vacias_es_de_tamano_realista(self):
        # La anterior tenia ~65 entradas mezclando idiomas (M-06).
        assert len(T.VACIAS_ES) > 130
        assert len(T.VACIAS_EN) > 100

    def test_las_listas_no_contienen_caracteres_de_otros_alfabetos(self):
        for palabra in T.VACIAS:
            assert palabra.isascii() or all(c in "áéíóúüñ" for c in palabra if not c.isascii())


class TestRouge:
    def test_texto_identico_da_uno(self):
        t = "el sistema no realizo validacion cruzada sobre la muestra"
        assert T.rouge_n(t, t, 1)[2] == pytest.approx(1.0)
        assert T.rouge_l(t, t)[2] == pytest.approx(1.0)

    def test_textos_disjuntos_dan_cero(self):
        assert T.rouge_n("gato perro loro", "avion barco tren", 1)[2] == 0.0

    def test_rouge2_es_mas_exigente_que_rouge1(self):
        ref = "la validacion cruzada no fue aplicada en el estudio"
        gen = "el estudio no aplico la validacion cruzada"
        assert T.rouge_n(ref, gen, 1)[2] > T.rouge_n(ref, gen, 2)[2]

    def test_rougeL_tolera_las_inserciones(self):
        """La propiedad util de ROUGE-L para resumenes abstractivos.

        Al no exigir contiguidad, reconoce el contenido comun aunque el
        resumen intercale palabras. ROUGE-2 lo pierde por completo: cada
        insercion rompe los dos bigramas que tocaba.

        (Ante un intercambio de bloques contiguos ocurre lo contrario: los
        bigramas sobreviven y ROUGE-2 puntua mas alto. No es que una variante
        sea mejor: miden cosas distintas y por eso se reportan las dos.)
        """
        ref = "no se aplico validacion cruzada"
        gen = "no siempre se logro aplico externa validacion previa cruzada"
        assert T.rouge_l(ref, gen)[2] > T.rouge_n(ref, gen, 2)[2]

    def test_rouge2_premia_la_contiguidad(self):
        ref = "no se aplico validacion cruzada"
        gen = "validacion cruzada no se aplico"
        # Intercambio de bloques: los bigramas internos sobreviven.
        assert T.rouge_n(ref, gen, 2)[2] > T.rouge_l(ref, gen)[2]

    def test_referencia_vacia_no_rompe(self):
        assert T.rouge_n("", "algo", 1) == (0.0, 0.0, 0.0)
        assert T.rouge_l("", "algo") == (0.0, 0.0, 0.0)


class TestDensidadYAnclajes:
    def test_densidad_lexica_en_rango(self):
        v = T.densidad_lexica("el estudio de la muestra fue realizado con datos")
        assert 0.0 < v < 1.0

    def test_texto_generico_tiene_pocos_anclajes(self):
        generico = ("Se requiere mayor investigacion en contextos diversos para "
                    "comprender mejor el fenomeno estudiado en el futuro")
        concreto = ("No hay validacion externa en cohortes latinoamericanas ni se "
                    "reporta el kappa entre los 3 anotadores del estudio de 2023")
        assert T.densidad_anclajes(concreto) > T.densidad_anclajes(generico)

    def test_anclajes_con_texto_muy_corto(self):
        assert T.densidad_anclajes("dos") == 0.0


class TestContenidoInformativo:
    def test_termino_raro_puntua_mas_que_uno_frecuente(self):
        corpus = [T.tokens_contenido("estudio sobre educacion y aprendizaje") for _ in range(9)]
        corpus.append(T.tokens_contenido("cohortes latinoamericanas heterocedasticidad"))
        tabla = T.idf(corpus)
        raro = T.contenido_informativo("heterocedasticidad", tabla)
        comun = T.contenido_informativo("estudio", tabla)
        assert raro > comun

    def test_sin_corpus_devuelve_cero(self):
        assert T.contenido_informativo("cualquier cosa", {}) == 0.0


# ------------------------------------------------------------------ niveles
class TestN1:
    def test_cada_version_conserva_su_explicacion(self):
        v1 = ficha_para_version("N1.2", 1)
        v2 = ficha_para_version("N1.2", 2)
        legado = ficha_para_version("N1.2", None)

        assert "seis categorías" in v1.descripcion
        assert "detectadas e indexadas" in v2.descripcion
        assert "no quedó registrada" in legado.descripcion

    def test_cobertura_seccional_completa(self):
        disponibles = {"metodo", "resultados", "discusion"}
        rec = [{"seccion": s} for s in disponibles]
        valor, detalle = N.n1_2_cobertura_seccional(rec, disponibles)
        assert valor == 1.0
        assert detalle["n_recuperadas"] == detalle["n_disponibles"] == 3

    def test_cobertura_seccional_parcial(self):
        disponibles = {"metodo", "resultados"}
        rec = [{"seccion": "metodo"}, {"seccion": "introduccion"}]
        valor, detalle = N.n1_2_cobertura_seccional(rec, disponibles)
        assert valor == 0.5
        assert detalle["secciones_recuperadas"] == ["metodo"]

    def test_no_penaliza_secciones_que_el_articulo_no_tiene(self):
        valor, detalle = N.n1_2_cobertura_seccional(
            [{"seccion": "metodo"}], {"metodo"}
        )
        assert valor == 1.0
        assert detalle["n_disponibles"] == 1

    def test_cobertura_seccional_solo_introduccion(self):
        rec = [{"seccion": "introduccion"}, {"seccion": "otro"}]
        valor, _ = N.n1_2_cobertura_seccional(rec, {"metodo", "resultados"})
        assert valor == 0.0

    def test_cobertura_con_contexto_vacio(self):
        valor, detalle = N.n1_2_cobertura_seccional([], {"metodo"})
        assert valor == 0.0
        assert detalle["n_recuperadas"] == 0

    def test_sin_secciones_reconocibles_no_inventa_un_cero(self):
        valor, detalle = N.n1_2_cobertura_seccional(
            [{"seccion": "introduccion"}], {"introduccion", "otro"}
        )
        assert valor is None
        assert detalle["motivo"]
        assert detalle["n_disponibles"] == 0

    def test_diversidad_vectores_identicos_es_cero(self):
        v = [1.0, 0.0, 0.0]
        assert N.n1_3_diversidad_contexto([v, v, v]) == pytest.approx(0.0, abs=1e-6)

    def test_diversidad_vectores_ortogonales_es_uno(self):
        vs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        assert N.n1_3_diversidad_contexto(vs) == pytest.approx(1.0, abs=1e-6)

    def test_diversidad_con_un_solo_vector(self):
        assert N.n1_3_diversidad_contexto([[1.0, 0.0]]) == 0.0


class TestN2:
    def test_n21_declara_que_no_evalua_la_brecha_completa(self):
        actual = ficha_para_version("N2.1", 1)
        assert actual.nombre == "Respaldo de afirmaciones evidenciales"
        assert "no la corrección total" in actual.interpretacion

    def test_cada_version_de_n22_conserva_su_denominador(self):
        v1 = ficha_para_version("N2.2", 1)
        v2 = ficha_para_version("N2.2", 2)
        legado = ficha_para_version("N2.2", None)

        assert "todas las afirmaciones" in v1.descripcion
        assert "evidenciales autónomas" in v2.descripcion
        assert "no quedó registrada" in legado.descripcion


class TestN3:
    def test_discriminabilidad_detecta_brechas_identicas(self):
        """El fallo que N3.1 existe para atrapar."""
        generica = "Se requiere mayor investigacion en contextos diversos"
        valor, detalle = N.n3_1_discriminabilidad({"a": generica, "b": generica, "c": generica})
        assert valor == pytest.approx(0.0, abs=1e-3)
        assert detalle["similitud_media"] > 0.99

    def test_discriminabilidad_premia_brechas_distintas(self):
        brechas = {
            "a": "Falta validacion externa en cohortes latinoamericanas del modelo",
            "b": "No se reporta el consumo energetico del entrenamiento distribuido",
            "c": "Ausencia de estudios longitudinales sobre retencion en primaria",
        }
        identicas = {k: "Se requiere mas investigacion futura" for k in brechas}
        assert N.n3_1_discriminabilidad(brechas)[0] > N.n3_1_discriminabilidad(identicas)[0]

    def test_discriminabilidad_necesita_dos_articulos(self):
        assert N.n3_1_discriminabilidad({"a": "una brecha"})[0] == 0.0

    def test_redundancia_marca_los_duplicados(self):
        misma = "No se realizo validacion cruzada en el estudio analizado"
        valor, detalle = N.n3_4_redundancia({"a": misma, "b": misma})
        assert valor > 0.0
        assert detalle["pares_duplicados"]

    def test_redundancia_cero_con_brechas_distintas(self):
        brechas = {
            "a": "Falta validacion externa en cohortes latinoamericanas",
            "b": "No se documenta el consumo energetico del entrenamiento",
        }
        assert N.n3_4_redundancia(brechas)[0] == 0.0


class TestN4:
    ABSTRACT = ("Este estudio evalua un sistema de analisis automatico de literatura "
                "cientifica mediante modelos de lenguaje. Se procesaron sesenta "
                "articulos y se midio la calidad de los resumenes generados frente "
                "a referencias humanas elaboradas por dos evaluadores.")

    def test_sin_abstract_no_calcula_rouge(self):
        """M-02: mejor no dar cifra que dar una sin significado."""
        m = N.n4_calidad_resumen("un resumen cualquiera del articulo", None)
        assert m.referencia_valida is False
        assert m.rouge1_f1 == 0.0
        assert "abstract" in m.motivo.lower()

    def test_con_abstract_calcula_todas_las_variantes(self):
        m = N.n4_calidad_resumen(self.ABSTRACT, self.ABSTRACT)
        assert m.referencia_valida is True
        assert m.rouge1_f1 == pytest.approx(1.0)
        assert m.rougeL_f1 == pytest.approx(1.0)
        assert m.similitud_semantica > 0.99

    def test_resumen_ajeno_puntua_bajo(self):
        m = N.n4_calidad_resumen(
            "Las ballenas jorobadas migran miles de kilometros cada temporada",
            self.ABSTRACT)
        assert m.referencia_valida is True
        assert m.rouge1_f1 < 0.2

    def test_sin_resumen_generado(self):
        m = N.n4_calidad_resumen("", self.ABSTRACT)
        assert m.referencia_valida is False
        assert "resumen generado" in m.motivo.lower()


class TestIdiomaYRouge:
    """ROUGE mide solape lexico: entre idiomas distintos no significa nada."""

    ABSTRACT_EN = ("Predicting cellular metabolism from molecular data is a central "
                   "challenge in systems biology, with direct implications for the "
                   "engineering of microbial cell factories and their applications.")
    RESUMEN_ES = ("El articulo introduce un marco de modelado hibrido que integra "
                  "modelos metabolicos a escala genomica con restricciones "
                  "enzimaticas en arquitecturas de redes neuronales profundas.")

    def test_detecta_espanol(self):
        assert T.idioma(self.RESUMEN_ES) == "es"

    def test_detecta_ingles(self):
        assert T.idioma(self.ABSTRACT_EN) == "en"

    def test_texto_corto_es_indeterminado(self):
        assert T.idioma("dos palabras") == "indeterminado"

    def test_no_calcula_rouge_entre_idiomas_distintos(self):
        m = N.n4_calidad_resumen(self.RESUMEN_ES, self.ABSTRACT_EN)
        assert m.referencia_valida is True
        assert m.rouge_aplicable is False
        assert m.rouge1_f1 == 0.0
        assert "no es aplicable" in m.motivo.lower()

    def test_la_similitud_semantica_si_se_calcula(self):
        """Se calcula aunque ROUGE quede descartado.

        Aqui solo se comprueba que la ruta se ejecuta. Su valor no es
        interpretable en las pruebas: en modo simulado los embeddings son
        lexicos por construccion, asi que entre idiomas distintos rondan
        cero. Con embeddings reales, este mismo par dio 0.90 sobre el lote
        de articulos.
        """
        m = N.n4_calidad_resumen(self.RESUMEN_ES, self.ABSTRACT_EN)
        assert isinstance(m.similitud_semantica, float)
        assert m.rouge_aplicable is False

    def test_calcula_rouge_cuando_coincide_el_idioma(self):
        m = N.n4_calidad_resumen(self.ABSTRACT_EN, self.ABSTRACT_EN)
        assert m.rouge_aplicable is True
        assert m.rouge1_f1 == pytest.approx(1.0)


# ------------------------------------------------------------ distribucion
class TestDistribucion:
    def test_describe_una_distribucion_estrecha_sin_juzgarla(self):
        """Un IQR pequeño es un dato; sin calibración no es un veredicto."""
        d = D.describir("entropia_norm", [0.518, 0.521, 0.519, 0.520, 0.522, 0.518])
        assert d.iqr < 0.05
        assert "discrimina" not in d.dict()
        assert "veredicto" not in d.dict()

    def test_describe_una_distribucion_amplia(self):
        d = D.describir("N3.1", [0.10, 0.35, 0.52, 0.68, 0.81, 0.95])
        assert d.iqr >= 0.05

    def test_muestra_pequena_conserva_sus_estadisticos(self):
        d = D.describir("x", [0.1, 0.9])
        assert d.n == 2
        assert d.mediana == pytest.approx(0.5)
        assert d.iqr == pytest.approx(0.4)

    def test_sin_datos(self):
        d = D.describir("x", [])
        assert d.n == 0

    def test_ignora_valores_no_numericos(self):
        d = D.describir("x", [0.1, None, "abc", 0.9, 0.5, 0.3, 0.7])
        assert d.n == 5

    def test_percentiles_coherentes(self):
        d = D.describir("x", [0.0, 0.25, 0.5, 0.75, 1.0])
        assert d.minimo == 0.0 and d.maximo == 1.0
        assert d.mediana == pytest.approx(0.5)

    def test_la_tabla_se_genera(self):
        t = D.tabla([D.describir("N3.1", [0.1, 0.4, 0.6, 0.8, 0.9])])
        assert "N3.1" in t and "mediana" in t
