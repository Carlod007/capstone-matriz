# tests/test_registro_api.py
"""Registro de llamadas a la API.

El contador anterior estimaba el consumo a partir de los resultados
guardados, con lo que dejaba fuera las llamadas fallidas. Y una llamada que
falla con 429 consume cuota igual, de modo que el indicador se quedaba corto
justo despues de una racha de errores, que es cuando mas importa acertar.
"""

import uuid

import pytest

from app.services import registro_api as R

pytestmark = pytest.mark.bd


@pytest.fixture
def limpiar(db):
    """Elimina los registros de prueba al terminar."""
    from app.models.llamada_api import LlamadaAPI

    marcas = []
    yield marcas
    if marcas:
        db.query(LlamadaAPI).filter(LlamadaAPI.motivo.in_(marcas)).delete(
            synchronize_session=False)
        db.commit()


class TestAnotar:
    def test_registra_una_llamada_con_exito(self, db, limpiar):
        from app.models.llamada_api import LlamadaAPI

        marca = "prueba-%s" % uuid.uuid4()
        limpiar.append(marca)
        R.anotar(R.OP_ANALISIS, modelo="m", exito=True, tokens_in=10,
                 tokens_out=5, motivo=marca)
        db.commit()
        fila = db.query(LlamadaAPI).filter(LlamadaAPI.motivo == marca).first()
        assert fila is not None
        assert fila.exito is True
        assert fila.tokens_in == 10

    def test_registra_tambien_las_fallidas(self, db, limpiar):
        from app.models.llamada_api import LlamadaAPI

        marca = "fallo-%s" % uuid.uuid4()
        limpiar.append(marca)
        R.anotar(R.OP_SINTESIS, modelo="m", exito=False, motivo=marca)
        db.commit()
        fila = db.query(LlamadaAPI).filter(LlamadaAPI.motivo == marca).first()
        assert fila is not None
        assert fila.exito is False

    def test_nunca_lanza_excepcion(self):
        """Perder una linea del contador es preferible a perder el analisis."""
        R.anotar("operacion-inexistente" * 40, modelo="x" * 500, unidades=-3)

    def test_los_embeddings_cuentan_por_unidades(self, db, limpiar):
        from app.models.llamada_api import LlamadaAPI

        marca = "emb-%s" % uuid.uuid4()
        limpiar.append(marca)
        # Una sola llamada HTTP, pero el servicio contabiliza cada texto.
        R.anotar(R.OP_EMBEDDING, unidades=32, motivo=marca)
        db.commit()
        fila = db.query(LlamadaAPI).filter(LlamadaAPI.motivo == marca).first()
        assert fila.unidades == 32


class TestConsumo:
    def test_separa_generaciones_de_embeddings(self, db, limpiar):
        """Solo las generaciones gastan la cuota diaria."""
        marca = "sep-%s" % uuid.uuid4()
        limpiar.append(marca)
        antes = R.consumo(horas=24)
        R.anotar(R.OP_ANALISIS, motivo=marca)
        R.anotar(R.OP_EMBEDDING, unidades=10, motivo=marca)
        despues = R.consumo(horas=24)
        assert despues["generaciones"] == antes["generaciones"] + 1
        assert despues["embeddings"] == antes["embeddings"] + 10

    def test_cuenta_las_fallidas_dentro_del_total(self, db, limpiar):
        marca = "tot-%s" % uuid.uuid4()
        limpiar.append(marca)
        antes = R.consumo(horas=24)
        R.anotar(R.OP_ANALISIS, exito=False, motivo=marca)
        despues = R.consumo(horas=24)
        assert despues["generaciones"] == antes["generaciones"] + 1
        assert despues["fallidas"] == antes["fallidas"] + 1


class TestEndpointConsumo:
    def test_declara_su_alcance(self, db, proyecto_indexado):
        from fastapi.testclient import TestClient
        import main

        c = TestClient(main.app)
        r = c.get("/proyectos/%s/consumo" % proyecto_indexado["proyecto_id"])
        assert r.status_code == 200
        d = r.json()
        # El indicador debe decir de donde sale el numero y que no ve.
        assert "exactitud" in d
        assert d["exactitud"]["no_cuenta"]
        assert "ai.dev" in d["exactitud"]["fuente_oficial"]
        assert d["fuente"] in ("registro de llamadas", "resultados guardados")
