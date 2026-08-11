# tests/test_limitador.py
"""Control de ritmo y reintentos (A-02)."""

import time

import pytest

from app.services import limitador as L


class ErrorFalso(Exception):
    def __init__(self, mensaje, code=None):
        super().__init__(mensaje)
        self.code = code


class TestLimitador:
    def test_no_frena_dentro_de_la_capacidad(self):
        lim = L.Limitador(por_minuto=600)
        inicio = time.monotonic()
        for _ in range(10):
            lim.adquirir(1)
        assert time.monotonic() - inicio < 0.3

    def test_frena_al_agotar_las_fichas(self):
        # 60 por minuto = 1 por segundo. Agotadas las fichas iniciales, la
        # siguiente debe esperar aproximadamente un segundo.
        lim = L.Limitador(por_minuto=60)
        lim.adquirir(60)
        inicio = time.monotonic()
        lim.adquirir(1)
        assert time.monotonic() - inicio >= 0.5

    def test_pide_tantas_fichas_como_textos(self):
        """El servicio cuenta cada texto, no cada llamada HTTP."""
        lim = L.Limitador(por_minuto=120)
        lim.adquirir(100)
        inicio = time.monotonic()
        lim.adquirir(20)
        assert time.monotonic() - inicio > 0.0

    def test_una_peticion_mayor_que_la_capacidad_no_bloquea_para_siempre(self):
        lim = L.Limitador(por_minuto=10)
        inicio = time.monotonic()
        lim.adquirir(50)
        assert time.monotonic() - inicio < 1.0


class TestRecuperable:
    def test_429_es_recuperable(self):
        assert L.es_recuperable(ErrorFalso("429 RESOURCE_EXHAUSTED", code=429))

    def test_503_es_recuperable(self):
        assert L.es_recuperable(ErrorFalso("503 UNAVAILABLE"))

    def test_400_no_es_recuperable(self):
        assert not L.es_recuperable(ErrorFalso("400 INVALID_ARGUMENT", code=400))

    def test_404_no_es_recuperable(self):
        # El caso del modelo retirado: reintentar no lo va a resucitar.
        assert not L.es_recuperable(ErrorFalso("404 NOT_FOUND", code=404))


class TestEsperaSugerida:
    def test_extrae_el_retry_delay_del_mensaje(self):
        msg = ("429 RESOURCE_EXHAUSTED. {'error': {'details': "
               "[{'@type': 'type.googleapis.com/google.rpc.RetryInfo', "
               "'retryDelay': '14s'}]}}")
        assert L.espera_sugerida(ErrorFalso(msg)) == pytest.approx(15.0)

    def test_sin_retry_delay_devuelve_none(self):
        assert L.espera_sugerida(ErrorFalso("algo fallo")) is None

    def test_acota_la_espera(self):
        assert L.espera_sugerida(ErrorFalso("'retryDelay': '9999s'")) <= L.ESPERA_MAXIMA


class TestConReintentos:
    def test_devuelve_a_la_primera_si_no_falla(self):
        assert L.con_reintentos(lambda: 42) == 42

    def test_reintenta_y_acaba_bien(self, monkeypatch):
        monkeypatch.setattr(L.time, "sleep", lambda s: None)
        intentos = {"n": 0}

        def flaky():
            intentos["n"] += 1
            if intentos["n"] < 3:
                raise ErrorFalso("429 RESOURCE_EXHAUSTED", code=429)
            return "ok"

        assert L.con_reintentos(flaky, intentos=5) == "ok"
        assert intentos["n"] == 3

    def test_no_reintenta_errores_definitivos(self, monkeypatch):
        monkeypatch.setattr(L.time, "sleep", lambda s: None)
        intentos = {"n": 0}

        def fijo():
            intentos["n"] += 1
            raise ErrorFalso("400 INVALID_ARGUMENT", code=400)

        with pytest.raises(ErrorFalso):
            L.con_reintentos(fijo, intentos=5)
        assert intentos["n"] == 1

    def test_agota_los_intentos_y_propaga(self, monkeypatch):
        monkeypatch.setattr(L.time, "sleep", lambda s: None)
        intentos = {"n": 0}

        def siempre_falla():
            intentos["n"] += 1
            raise ErrorFalso("429 RESOURCE_EXHAUSTED", code=429)

        with pytest.raises(ErrorFalso):
            L.con_reintentos(siempre_falla, intentos=3)
        assert intentos["n"] == 3


class TestIndexacionIdempotente:
    """Reintentar tras un fallo no debe duplicar fragmentos ni gastar cuota."""

    pytestmark = pytest.mark.bd

    def test_segunda_indexacion_no_duplica(self, db, proyecto_indexado):
        from app.models.embedding_doc import EmbeddingDoc
        from app.services.embedding_service import index_articulo

        aid = proyecto_indexado["pertinente"]
        antes = db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id == aid).count()
        devuelto = index_articulo(db, aid)
        despues = db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id == aid).count()
        assert devuelto == antes == despues

    def test_reindexar_reemplaza_sin_acumular(self, db, proyecto_indexado):
        from app.models.embedding_doc import EmbeddingDoc
        from app.services.embedding_service import index_articulo

        aid = proyecto_indexado["pertinente"]
        antes = db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id == aid).count()
        index_articulo(db, aid, reindexar=True)
        despues = db.query(EmbeddingDoc).filter(EmbeddingDoc.articulo_id == aid).count()
        assert despues == antes
