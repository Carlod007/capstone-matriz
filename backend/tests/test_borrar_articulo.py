# tests/test_borrar_articulo.py
"""
Quitar un articulo del proyecto.

Un articulo arrastra archivo en disco, embeddings, resumenes, run_items,
brechas y metricas. La mayoria cae por las claves foraneas en cascada, pero dos
cosas no: el PDF del disco, que ninguna fila menciona, y las filas de `metrica`,
que referencian por ambito e identificador sin clave foranea.

Un borrado que deje cualquiera de las dos parece correcto y no lo es: el PDF
ocupa espacio que nadie sabe que sobra, y las metricas siguen contando en los
promedios del proyecto como si el articulo estuviera.
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

pytestmark = pytest.mark.bd


@pytest.fixture(scope="module", autouse=True)
def modelos_cargados():
    import main  # noqa: F401  (importa todos los modelos y resuelve las FK)


@pytest.fixture
def proyecto(db, usuario_prueba):
    from app.models.proyecto import Proyecto

    pid = str(uuid.uuid4())
    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Borrado de articulos",
                    objetivo="Comprobar que quitar un articulo no deja restos",
                    n_articulos_objetivo=1, estado_arte_generado=False))
    db.commit()
    try:
        yield pid
    finally:
        from app.models.archivo import Archivo
        from app.models.articulo import Articulo
        from app.models.metrica import Metrica

        db.rollback()
        for modelo in (Archivo, Articulo, Metrica):
            db.query(modelo).filter(modelo.proyecto_id == pid).delete(
                synchronize_session=False)
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.commit()


@pytest.fixture
def articulo_completo(db, proyecto, usuario_prueba, tmp_path, monkeypatch):
    """Un articulo con todo lo que puede colgar de el, y su PDF en disco."""
    from app.models.archivo import Archivo
    from app.models.articulo import Articulo
    from app.models.embedding_doc import EmbeddingDoc
    from app.models.metrica import Metrica
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.resultado_resumen import ResultadoResumen
    from app.models.run import EstadoRun, Run
    from app.models.run_item import EstadoRunItem, RunItem
    from app.services import almacenamiento

    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

    aid, rid, iid, bid = (str(uuid.uuid4()) for _ in range(4))
    clave = almacenamiento.nueva_clave(usuario_prueba["id"])
    almacenamiento.guardar(clave, b"%PDF-1.4 fingido")

    db.add(Articulo(id=aid, proyecto_id=proyecto, doi=None, titulo="Articulo"))
    db.add(Run(id=rid, proyecto_id=proyecto, estado=EstadoRun.completado,
               n_items_total=1, n_items_ok=1))
    db.flush()
    db.add(Archivo(id=str(uuid.uuid4()), proyecto_id=proyecto, articulo_id=aid,
                   nombre="a.pdf", ruta=clave, hash_sha256="e" * 64, bytes=16))
    db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                   estado=EstadoRunItem.analizado))
    db.add(EmbeddingDoc(id=str(uuid.uuid4()), articulo_id=aid, chunk_orden=0,
                        seccion="metodo", texto="t", embedding=[0.1, 0.2]))
    db.add(ResultadoResumen(id=str(uuid.uuid4()), articulo_id=aid,
                            resumen_generado="r", resumen_referencia="a"))
    db.flush()
    db.add(ResultadoBrecha(id=bid, run_item_id=iid, tipo_brecha="otra",
                           brecha="b", oportunidad="o", rag_hits=[]))
    db.add(Metrica(id=str(uuid.uuid4()), proyecto_id=proyecto,
                   ambito="articulo", referencia_id=aid, codigo="N4.ref",
                   valor=1.0))
    db.add(Metrica(id=str(uuid.uuid4()), proyecto_id=proyecto,
                   ambito="brecha", referencia_id=bid, codigo="N4.2",
                   valor=0.8))
    db.commit()

    return {"articulo": aid, "run_item": iid, "brecha": bid, "clave": clave}


class TestBorradoCompleto:
    def test_no_deja_filas_sueltas(self, db, cliente, proyecto,
                                   articulo_completo):
        from app.models.archivo import Archivo
        from app.models.articulo import Articulo
        from app.models.embedding_doc import EmbeddingDoc
        from app.models.metrica import Metrica
        from app.models.resultado_brecha import ResultadoBrecha
        from app.models.resultado_resumen import ResultadoResumen
        from app.models.run_item import RunItem

        aid = articulo_completo["articulo"]
        r = cliente.delete(f"/proyectos/{proyecto}/articulos/{aid}")
        assert r.status_code == 200, r.text

        db.expire_all()
        assert db.query(Articulo).filter(Articulo.id == aid).count() == 0
        assert db.query(Archivo).filter(Archivo.articulo_id == aid).count() == 0
        assert db.query(RunItem).filter(RunItem.articulo_id == aid).count() == 0
        assert db.query(EmbeddingDoc).filter(
            EmbeddingDoc.articulo_id == aid).count() == 0
        assert db.query(ResultadoResumen).filter(
            ResultadoResumen.articulo_id == aid).count() == 0
        assert db.query(ResultadoBrecha).filter(
            ResultadoBrecha.id == articulo_completo["brecha"]).count() == 0

        # Las dos que la cascada no alcanza.
        restantes = (db.query(Metrica)
                       .filter(Metrica.referencia_id.in_(
                           [aid, articulo_completo["brecha"]]))
                       .count())
        assert restantes == 0, (
            "quedan %d metricas apuntando a un articulo que ya no existe; "
            "seguirian contando en los promedios del proyecto" % restantes)

    def test_borra_el_pdf_del_disco(self, cliente, proyecto,
                                    articulo_completo):
        """Ninguna fila lo menciona despues, asi que si no se borra aqui no hay
        forma de saber que sobra."""
        from app.services import almacenamiento

        clave = articulo_completo["clave"]
        assert almacenamiento.existe(clave), "la prueba no preparo el PDF"

        r = cliente.delete(
            f"/proyectos/{proyecto}/articulos/{articulo_completo['articulo']}")
        assert r.status_code == 200, r.text
        assert not almacenamiento.existe(clave)

    def test_el_proyecto_sobrevive(self, db, cliente, proyecto,
                                   articulo_completo):
        """El limite: se quita el articulo, no el proyecto ni su ejecucion."""
        from app.models.proyecto import Proyecto

        cliente.delete(
            f"/proyectos/{proyecto}/articulos/{articulo_completo['articulo']}")

        db.expire_all()
        assert db.query(Proyecto).filter(Proyecto.id == proyecto).count() == 1


class TestCuandoNoSeDebeBorrar:
    def test_un_analisis_en_marcha_lo_impide(self, db, cliente, proyecto,
                                             articulo_completo):
        """Un trabajador que tiene el articulo escribiria resultados de algo
        que ya no existe."""
        from app.models.articulo import Articulo
        from app.models.run_item import EstadoRunItem, RunItem

        (db.query(RunItem)
           .filter(RunItem.id == articulo_completo["run_item"])
           .update({"estado": EstadoRunItem.en_proceso}))
        db.commit()

        aid = articulo_completo["articulo"]
        r = cliente.delete(f"/proyectos/{proyecto}/articulos/{aid}")

        assert r.status_code == 409, r.text
        assert "análisis en curso" in r.json()["detail"]
        db.expire_all()
        assert db.query(Articulo).filter(Articulo.id == aid).count() == 1

    def test_un_articulo_inexistente_da_404(self, cliente, proyecto):
        r = cliente.delete(
            f"/proyectos/{proyecto}/articulos/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_no_se_puede_borrar_el_de_otra_cuenta(self, db, cliente, proyecto):
        """El filtro por proyecto no es redundante con el guardian de dueno.

        Sin el, conocer el identificador de un articulo ajeno bastaria para
        borrarlo pidiendolo desde un proyecto propio.
        """
        from app.models.articulo import Articulo
        from app.models.proyecto import Proyecto
        from app.models.usuario import Usuario
        from app.services import seguridad

        otro, pid_ajeno, aid_ajeno = (str(uuid.uuid4()) for _ in range(3))
        db.add(Usuario(id=otro, correo="ajeno-%s@x.com" % otro[:8],
                       contrasena_hash=seguridad.cifrar("otra-clave"),
                       nombre="Otra cuenta", activo=True))
        db.flush()
        db.add(Proyecto(id=pid_ajeno, usuario_id=otro,
                        tema_principal="Ajeno", objetivo="No tocar",
                        n_articulos_objetivo=1, estado_arte_generado=False))
        db.flush()
        db.add(Articulo(id=aid_ajeno, proyecto_id=pid_ajeno, doi=None,
                        titulo="Articulo ajeno"))
        db.commit()

        try:
            # Se pide desde el proyecto propio, con el id del articulo ajeno.
            r = cliente.delete(f"/proyectos/{proyecto}/articulos/{aid_ajeno}")
            assert r.status_code == 404, r.text

            db.expire_all()
            assert db.query(Articulo).filter(
                Articulo.id == aid_ajeno).count() == 1, (
                "se borro un articulo de otra cuenta")
        finally:
            db.rollback()
            db.query(Articulo).filter(Articulo.id == aid_ajeno).delete()
            db.query(Proyecto).filter(Proyecto.id == pid_ajeno).delete()
            db.query(Usuario).filter(Usuario.id == otro).delete()
            db.commit()
