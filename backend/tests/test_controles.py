# tests/test_controles.py
"""Controles negativos C1 a C6.

Comprueban que el sistema responde de verdad al artículo y al contexto del
proyecto. Los controles de la capa de generación quedan como
`no_concluyente` en modo simulado, que es lo correcto: un control que no se
pudo ejecutar no es un control superado.
"""

import pytest

from app.services import controles as C
from app.services.controles import FALLA, NO_CONCLUYENTE, PASA

pytestmark = pytest.mark.bd


class TestUtilidades:
    def test_spearman_detecta_orden_identico(self):
        a = [0.1, 0.5, 0.9, 0.3]
        assert C.spearman(a, a) == pytest.approx(1.0)

    def test_spearman_detecta_orden_inverso(self):
        assert C.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)

    def test_spearman_con_pocos_datos_devuelve_cero(self):
        assert C.spearman([1, 2], [2, 1]) == 0.0

    def test_barajar_conserva_el_vocabulario(self):
        texto = "Uno dos tres. Cuatro cinco seis. Siete ocho nueve."
        barajado = C.barajar_oraciones(texto)
        assert sorted(texto.split()) == sorted(barajado.split())
        assert barajado != texto

    def test_jaccard(self):
        assert C.jaccard_conjuntos(["a", "b"], ["a", "b"]) == 1.0
        assert C.jaccard_conjuntos(["a"], ["b"]) == 0.0
        assert C.jaccard_conjuntos([], []) == 1.0


class TestC1PermutacionContexto:
    def test_el_contexto_influye_en_la_recuperacion(self, db, proyecto_indexado,
                                                    contexto_propio, contexto_ajeno):
        r = C.c1_permutacion_contexto(
            db, proyecto_indexado["pertinente"], contexto_propio, contexto_ajeno)
        assert r.veredicto == PASA, r.detalle
        assert r.valor < 0.95

    def test_el_mismo_contexto_da_el_mismo_orden(self, db, proyecto_indexado,
                                                 contexto_propio):
        # Control del control: con contextos idénticos la correlación debe ser
        # 1.0, y el control debe reportar FALLA. Si no lo hiciera, C1 no
        # detectaría nunca una recuperación que ignora el contexto.
        r = C.c1_permutacion_contexto(
            db, proyecto_indexado["pertinente"], contexto_propio, dict(contexto_propio))
        assert r.valor == pytest.approx(1.0, abs=1e-6)
        assert r.veredicto == FALLA


class TestC3ArticuloAjeno:
    def test_distingue_un_articulo_de_otro_dominio(self, db, proyecto_indexado,
                                                   contexto_propio):
        r = C.c3_articulo_ajeno(
            db, proyecto_indexado["pertinente"], proyecto_indexado["ajeno"],
            contexto_propio)
        assert r.veredicto == PASA, r.detalle
        assert r.extra["media_pertinente"] > r.extra["media_ajeno"]


class TestC4DuplicadoExacto:
    def test_dos_copias_recuperan_el_mismo_contexto(self, db, proyecto_indexado,
                                                    contexto_propio):
        r = C.c4_duplicado_exacto(
            db, proyecto_indexado["pertinente"], proyecto_indexado["duplicado"],
            contexto_propio)
        assert r.veredicto == PASA, r.detalle
        assert r.extra["misma_secuencia_secciones"] is True


class TestC5Estabilidad:
    def test_la_recuperacion_es_determinista(self, db, proyecto_indexado,
                                             contexto_propio):
        r = C.c5_estabilidad(db, proyecto_indexado["pertinente"], contexto_propio,
                             repeticiones=5)
        assert r.veredicto == PASA, r.detalle
        assert r.valor == 1.0


class TestControlesDeGeneracion:
    """C2 y C6 dependen del modelo real; en simulado no pueden concluir."""

    def test_c2_sin_generador_es_no_concluyente(self):
        r = C.c2_texto_barajado("texto cualquiera")
        assert r.veredicto == NO_CONCLUYENTE
        assert r.capa == "generacion"

    def test_c6_sin_generador_es_no_concluyente(self):
        r = C.c6_articulo_exhaustivo()
        assert r.veredicto == NO_CONCLUYENTE

    def test_c2_detecta_un_generador_insensible(self):
        # Un generador que devuelve siempre lo mismo debe hacer FALLAR el
        # control: es exactamente el fallo que C2 existe para atrapar.
        r = C.c2_texto_barajado("un texto de prueba. otra oracion aqui. y una mas.",
                                analizar=lambda t: "brecha generica identica siempre")
        assert r.veredicto == FALLA

    def test_c2_acepta_un_generador_sensible(self):
        r = C.c2_texto_barajado(
            "un texto de prueba. otra oracion aqui. y una mas.",
            analizar=lambda t: "brecha sobre " + t[:25])
        assert r.veredicto == PASA


class TestResumen:
    def test_agrega_los_veredictos(self):
        rs = [
            C.ResultadoControl("C1", "x", "recuperacion", PASA),
            C.ResultadoControl("C2", "y", "generacion", NO_CONCLUYENTE),
            C.ResultadoControl("C3", "z", "recuperacion", FALLA),
        ]
        r = C.resumen(rs)
        assert (r["total"], r["pasa"], r["falla"], r["no_concluyente"]) == (3, 1, 1, 1)
