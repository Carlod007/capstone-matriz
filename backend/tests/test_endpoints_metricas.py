# tests/test_endpoints_metricas.py
"""Endpoints de la capa de medicion v2 y catalogo."""

import pytest

from app.services.metricas.catalogo import CATALOGO, ficha, nombre


class TestCatalogo:
    def test_toda_ficha_declara_su_direccion_de_lectura(self):
        """Sin esto un panel puede pintar de verde justo lo que va mal."""
        for f in CATALOGO.values():
            assert f.mejor in ("alto", "bajo", "neutro"), f.codigo

    def test_toda_ficha_tiene_nombre_y_descripcion(self):
        for f in CATALOGO.values():
            assert f.nombre and f.nombre != f.codigo
            assert len(f.descripcion) > 20
            assert len(f.interpretacion) > 20

    def test_la_redundancia_se_lee_al_reves(self):
        assert ficha("N3.4").mejor == "bajo"

    def test_la_densidad_lexica_es_descriptiva(self):
        # No es una nota: una densidad alta no implica un resumen mejor.
        assert ficha("N4.4").mejor == "neutro"

    def test_codigo_desconocido_devuelve_el_propio_codigo(self):
        assert ficha("XX.9") is None
        assert nombre("XX.9") == "XX.9"

    def test_las_metricas_que_registra_el_pipeline_estan_catalogadas(self):
        """Si el pipeline guarda un codigo sin ficha, la interfaz lo mostraria
        crudo y sin explicacion."""
        registradas = {
            "N1.2", "N1.3", "N3.1", "N3.2", "N3.3", "N3.4",
            "N4.1a", "N4.1b", "N4.1c", "N4.1d", "N4.1e",
            "N4.2", "N4.4", "N4.ref",
        }
        faltan = registradas - set(CATALOGO)
        assert not faltan, "sin ficha en el catalogo: %s" % sorted(faltan)


@pytest.mark.bd
class TestEndpoints:
    # `cliente` viene de conftest y llega con la sesion iniciada: desde que
    # los proyectos tienen dueno, una llamada sin token no pasa de 401.

    def test_proyecto_inexistente_da_404(self, cliente):
        r = cliente.get("/proyectos/no-existe-0000/metricas")
        assert r.status_code == 404

    def test_proyecto_sin_analizar_avisa_en_lugar_de_fallar(self, cliente, db,
                                                            proyecto_indexado):
        # El proyecto de la fixture esta indexado pero no analizado.
        r = cliente.get("/proyectos/%s/metricas" % proyecto_indexado["proyecto_id"])
        assert r.status_code == 200
        d = r.json()
        assert d["run"] is None
        assert "aviso" in d

    def test_consumo_informa_del_limite_diario(self, cliente, proyecto_indexado):
        from app.services import verificacion

        r = cliente.get("/proyectos/%s/consumo" % proyecto_indexado["proyecto_id"])
        assert r.status_code == 200
        d = r.json()
        assert d["limite_diario_nivel_gratuito"] == 20

        # Una llamada por articulo para analizarlo, otra para verificar su
        # fidelidad si esta activada, y una final para la sintesis. Se deriva
        # del ajuste en lugar de fijarse a mano, para que activar o desactivar
        # la verificacion no deje la prueba comprobando una formula obsoleta.
        n = 3  # articulos de la fixture
        esperado = n * (2 if verificacion.VERIFICAR else 1) + 1
        assert d["coste_de_una_ejecucion"] == esperado
        assert isinstance(d["alcanza_para_otra_ejecucion"], bool)

    def test_el_desglose_suma_el_coste_total(self, cliente, proyecto_indexado):
        """Si el desglose no cuadra con el total, uno de los dos miente."""
        r = cliente.get("/proyectos/%s/consumo" % proyecto_indexado["proyecto_id"])
        d = r.json()
        assert sum(x["cantidad"] for x in d["desglose"]) == d["coste_de_una_ejecucion"]

    def test_brechas_de_articulo_sin_analizar_devuelve_lista_vacia(self, cliente,
                                                                   proyecto_indexado):
        r = cliente.get("/articulos/%s/brechas" % proyecto_indexado["pertinente"])
        assert r.status_code == 200
        assert r.json() == []
