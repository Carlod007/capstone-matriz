# tests/test_recuperacion.py
"""M-10: la recuperación debe leer el artículo entero, no solo su inicio."""

import pytest

from app.services.document_structure import SECCIONES_SUSTANTIVAS
from app.services.embedding_service import (
    construir_consulta,
    get_top_chunks,
    recuperar_contexto,
)
from app.utils.text_extractor import extraer_con_diagnostico

pytestmark = pytest.mark.bd


class TestConsulta:
    def test_incluye_el_contexto_del_proyecto(self, contexto_propio):
        q = construir_consulta(contexto_propio)
        assert contexto_propio["tema_principal"] in q
        assert contexto_propio["objetivo"] in q

    def test_tolera_un_contexto_vacio(self):
        assert construir_consulta({}).strip() != ""


class TestRecuperacion:
    def test_devuelve_el_numero_pedido(self, db, proyecto_indexado, contexto_propio):
        r = recuperar_contexto(db, proyecto_indexado["pertinente"], contexto_propio, k=6)
        assert len(r) == 6

    def test_cubre_secciones_sustantivas(self, db, proyecto_indexado, contexto_propio):
        r = recuperar_contexto(db, proyecto_indexado["pertinente"], contexto_propio, k=8)
        secciones = {x["seccion"] for x in r}
        cubiertas = secciones & set(SECCIONES_SUSTANTIVAS)
        assert len(cubiertas) >= 3, "solo cubre %s" % sorted(secciones)

    def test_supera_al_corte_posicional(self, db, proyecto_indexado, contexto_propio):
        """El contraste que motiva M-10."""
        from app.models.embedding_doc import EmbeddingDoc

        k = 8
        primeros = (db.query(EmbeddingDoc)
                    .filter(EmbeddingDoc.articulo_id == proyecto_indexado["pertinente"])
                    .order_by(EmbeddingDoc.chunk_orden.asc()).limit(k).all())
        sus_viejo = {f.seccion for f in primeros} & set(SECCIONES_SUSTANTIVAS)

        nuevo = recuperar_contexto(db, proyecto_indexado["pertinente"],
                                   contexto_propio, k=k)
        sus_nuevo = {x["seccion"] for x in nuevo} & set(SECCIONES_SUSTANTIVAS)

        assert len(sus_nuevo) > len(sus_viejo), (
            "nuevo=%s viejo=%s" % (sorted(sus_nuevo), sorted(sus_viejo)))

    def test_devuelve_los_fragmentos_en_orden_de_aparicion(self, db, proyecto_indexado,
                                                           contexto_propio):
        r = recuperar_contexto(db, proyecto_indexado["pertinente"], contexto_propio, k=8)
        ordenes = [x["orden"] for x in r]
        assert ordenes == sorted(ordenes)

    def test_no_repite_fragmentos(self, db, proyecto_indexado, contexto_propio):
        r = recuperar_contexto(db, proyecto_indexado["pertinente"], contexto_propio, k=8)
        ids = [x["embedding_id"] for x in r]
        assert len(ids) == len(set(ids))

    def test_incluye_trazabilidad_hacia_el_pdf(self, db, proyecto_indexado,
                                               contexto_propio):
        r = recuperar_contexto(db, proyecto_indexado["pertinente"], contexto_propio, k=4)
        for x in r:
            assert x["char_inicio"] is not None
            assert x["char_fin"] > x["char_inicio"]

    def test_articulo_sin_indexar_devuelve_vacio(self, db, contexto_propio):
        assert recuperar_contexto(db, "inexistente-0000", contexto_propio) == []

    def test_n12_usa_como_denominador_las_secciones_indexadas(
        self, db, proyecto_indexado, contexto_propio
    ):
        from app.services.metricas import niveles as N

        articulo_id = proyecto_indexado["pertinente"]
        recuperados = recuperar_contexto(db, articulo_id, contexto_propio, k=8)
        disponibles = N.secciones_sustantivas_indexadas(db, articulo_id)
        valor, detalle = N.n1_2_cobertura_seccional(recuperados, disponibles)

        esperadas = {r["seccion"] for r in recuperados} & disponibles
        assert detalle["secciones_disponibles"] == sorted(disponibles)
        assert detalle["secciones_recuperadas"] == sorted(esperadas)
        assert valor == round(len(esperadas) / len(disponibles), 4)


class TestIndexacion:
    def test_etiqueta_cada_fragmento_con_su_seccion(self, db, proyecto_indexado):
        from app.models.embedding_doc import EmbeddingDoc

        filas = (db.query(EmbeddingDoc)
                 .filter(EmbeddingDoc.articulo_id == proyecto_indexado["pertinente"])
                 .all())
        assert filas
        assert all(f.seccion for f in filas)
        assert {"metodo", "resultados"} <= {f.seccion for f in filas}


class TestDiagnosticoIngesta:
    """Nivel N0."""

    def test_articulo_normal_es_utilizable(self, pdf_articulo):
        d = extraer_con_diagnostico(pdf_articulo)
        assert d.utilizable
        assert d.legibilidad >= 0.6
        assert d.ratio_truncamiento > 0.3
        assert {"metodo", "resultados"} <= d.secciones

    def test_reporta_el_metodo_de_extraccion(self, pdf_articulo):
        assert extraer_con_diagnostico(pdf_articulo).metodo in ("pymupdf", "pdfminer", "ocr")

    def test_pdf_vacio_no_es_utilizable_y_explica_por_que(self, tmp_path):
        import fitz

        ruta = str(tmp_path / "vacio.pdf")
        doc = fitz.open()
        doc.new_page()
        doc.save(ruta)
        doc.close()

        d = extraer_con_diagnostico(ruta)
        assert not d.utilizable
        assert d.avisos, "debe explicar el motivo del rechazo"
