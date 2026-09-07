"""Eliminar un proyecto completo sin dejar datos o archivos huérfanos."""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

pytestmark = pytest.mark.bd


@pytest.fixture(scope="module", autouse=True)
def modelos_cargados():
    import main  # noqa: F401


def _nuevo_proyecto(db, usuario_id, tema="Proyecto para borrar"):
    from app.models.proyecto import Proyecto

    pid = str(uuid.uuid4())
    db.add(Proyecto(
        id=pid,
        usuario_id=usuario_id,
        tema_principal=tema,
        objetivo="Comprobar el borrado completo del proyecto",
        n_articulos_objetivo=5,
        estado_arte_generado=False,
    ))
    db.commit()
    return pid


def _limpiar_si_existe(db, pid):
    from app.models.estado_arte import EstadoDelArte
    from app.models.proyecto import Proyecto

    db.rollback()
    db.query(EstadoDelArte).filter(
        EstadoDelArte.proyecto_id == pid).delete(synchronize_session=False)
    db.query(Proyecto).filter(Proyecto.id == pid).delete(
        synchronize_session=False)
    db.commit()


class TestBorradoProyecto:
    def test_elimina_un_proyecto_vacio(self, db, cliente, usuario_prueba):
        from app.models.proyecto import Proyecto

        pid = _nuevo_proyecto(db, usuario_prueba["id"], "Proyecto vacío")
        try:
            r = cliente.delete(f"/proyectos/{pid}")
            assert r.status_code == 200, r.text
            assert r.json()["borrado"] is True
            db.expire_all()
            assert db.query(Proyecto).filter(Proyecto.id == pid).count() == 0
        finally:
            _limpiar_si_existe(db, pid)

    def test_elimina_datos_y_pdf_de_un_proyecto_completo(
        self, db, cliente, usuario_prueba, tmp_path, monkeypatch,
    ):
        from app.models.archivo import Archivo
        from app.models.articulo import Articulo
        from app.models.embedding_doc import EmbeddingDoc
        from app.models.estado_arte import EstadoDelArte
        from app.models.metrica import Metrica
        from app.models.proyecto import Proyecto
        from app.models.resultado_brecha import ResultadoBrecha
        from app.models.resultado_resumen import ResultadoResumen
        from app.models.run import EstadoRun, Run
        from app.models.run_item import EstadoRunItem, RunItem
        from app.services import almacenamiento

        monkeypatch.setattr(almacenamiento, "STORAGE_DIR", str(tmp_path))
        pid = _nuevo_proyecto(db, usuario_prueba["id"], "Proyecto completo")
        aid, rid, iid, bid = (str(uuid.uuid4()) for _ in range(4))
        clave = almacenamiento.nueva_clave(usuario_prueba["id"])
        almacenamiento.guardar(clave, b"%PDF-1.4 proyecto completo")

        db.add(Articulo(id=aid, proyecto_id=pid, titulo="Artículo", doi=None))
        db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
                   n_items_total=1, n_items_ok=1, genera_estado_arte=True))
        db.flush()
        db.add(Archivo(id=str(uuid.uuid4()), proyecto_id=pid,
                       articulo_id=aid, nombre="a.pdf", ruta=clave,
                       hash_sha256="f" * 64, bytes=27))
        db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                       estado=EstadoRunItem.analizado))
        db.add(EmbeddingDoc(id=str(uuid.uuid4()), articulo_id=aid,
                            chunk_orden=0, seccion="metodo", texto="texto",
                            embedding=[0.1, 0.2]))
        db.add(ResultadoResumen(id=str(uuid.uuid4()), articulo_id=aid,
                                resumen_generado="resumen",
                                resumen_referencia="abstract"))
        db.flush()
        db.add(ResultadoBrecha(id=bid, run_item_id=iid,
                               tipo_brecha="otra", brecha="brecha",
                               oportunidad="oportunidad", rag_hits=[]))
        db.add(Metrica(id=str(uuid.uuid4()), proyecto_id=pid,
                       ambito="brecha", referencia_id=bid, codigo="N2.1",
                       valor=0.8))
        db.add(EstadoDelArte(id=str(uuid.uuid4()), proyecto_id=pid,
                             run_id=rid, version=1, texto="Síntesis"))
        db.commit()

        try:
            assert almacenamiento.existe(clave)
            r = cliente.delete(f"/proyectos/{pid}")
            assert r.status_code == 200, r.text

            db.expire_all()
            assert db.query(Proyecto).filter(Proyecto.id == pid).count() == 0
            assert db.query(Articulo).filter(Articulo.id == aid).count() == 0
            assert db.query(Run).filter(Run.id == rid).count() == 0
            assert db.query(ResultadoBrecha).filter(
                ResultadoBrecha.id == bid).count() == 0
            assert db.query(Metrica).filter(
                Metrica.proyecto_id == pid).count() == 0
            assert db.query(EstadoDelArte).filter(
                EstadoDelArte.proyecto_id == pid).count() == 0
            assert not almacenamiento.existe(clave)
        finally:
            almacenamiento.borrar(clave)
            _limpiar_si_existe(db, pid)

    @pytest.mark.parametrize("fase", ["analizando", "sintetizando"])
    def test_no_interrumpe_un_proceso_en_marcha(
        self, db, cliente, usuario_prueba, fase,
    ):
        from app.models.proyecto import Proyecto
        from app.models.run import EstadoRun, Run

        pid = _nuevo_proyecto(db, usuario_prueba["id"], "Proyecto en curso")
        rid = str(uuid.uuid4())
        db.add(Run(
            id=rid,
            proyecto_id=pid,
            estado=(EstadoRun.en_progreso
                    if fase == "analizando" else EstadoRun.completado),
            n_items_total=1,
            n_items_ok=0 if fase == "analizando" else 1,
            genera_estado_arte=fase == "sintetizando",
        ))
        db.commit()
        try:
            r = cliente.delete(f"/proyectos/{pid}")
            assert r.status_code == 409, r.text
            assert "curso" in r.json()["detail"] or "estado del arte" in r.json()["detail"]
            db.expire_all()
            assert db.query(Proyecto).filter(Proyecto.id == pid).count() == 1
        finally:
            _limpiar_si_existe(db, pid)

    def test_no_elimina_un_proyecto_ajeno(self, db, cliente):
        from app.models.usuario import Usuario
        from app.services import seguridad

        uid = str(uuid.uuid4())
        db.add(Usuario(id=uid, correo=f"ajeno-{uid[:8]}@x.com",
                       contrasena_hash=seguridad.cifrar("clave-ajena"),
                       nombre="Otra cuenta", activo=True))
        db.commit()
        pid = _nuevo_proyecto(db, uid, "Proyecto ajeno")
        try:
            assert cliente.delete(f"/proyectos/{pid}").status_code == 404
        finally:
            _limpiar_si_existe(db, pid)
            db.query(Usuario).filter(Usuario.id == uid).delete()
            db.commit()
