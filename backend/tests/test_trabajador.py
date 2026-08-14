# tests/test_trabajador.py
"""
El trabajador, de principio a fin.

Es la prueba de cierre del paso: encolar un analisis, cortar el trabajador a
mitad, arrancarlo de nuevo y que termine sin repetir lo ya hecho ni gastar
cuota de mas.

Corre en modo simulado, como toda la suite: no llama a la API ni consume
cuota, y los embeddings son deterministas.
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)

pytestmark = pytest.mark.bd


@pytest.fixture
def encolado(db, proyecto_indexado):
    """Una ejecucion en cola sobre los tres articulos de la fixture."""
    from app.models.run import EstadoRun, Run
    from app.models.run_item import EstadoRunItem, RunItem

    pid = proyecto_indexado["proyecto_id"]
    rid = str(uuid.uuid4())
    db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.creado,
               n_items_total=3, n_items_ok=0, genera_estado_arte=False))
    db.flush()
    for clave in ("pertinente", "duplicado", "ajeno"):
        db.add(RunItem(id=str(uuid.uuid4()), run_id=rid,
                       articulo_id=proyecto_indexado[clave],
                       estado=EstadoRunItem.pendiente))
    db.commit()

    try:
        yield rid
    finally:
        db.rollback()
        _limpiar(db, rid)


def _limpiar(db, rid):
    from app.models.metrica import Metrica
    from app.models.rag_log import RagLog
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.run import Run
    from app.models.run_item import RunItem

    items = [i[0] for i in db.query(RunItem.id).filter(RunItem.run_id == rid).all()]
    brechas = [b[0] for b in db.query(ResultadoBrecha.id)
               .filter(ResultadoBrecha.run_item_id.in_(items)).all()] if items else []
    if brechas:
        db.query(Metrica).filter(Metrica.referencia_id.in_(brechas)).delete(
            synchronize_session=False)
        db.query(ResultadoBrecha).filter(ResultadoBrecha.id.in_(brechas)).delete(
            synchronize_session=False)
    db.query(RagLog).filter(RagLog.run_id == rid).delete(synchronize_session=False)
    db.query(RunItem).filter(RunItem.run_id == rid).delete(synchronize_session=False)
    db.query(Run).filter(Run.id == rid).delete()
    db.commit()


def _brechas(db, rid) -> int:
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.run_item import RunItem

    sub = db.query(RunItem.id).filter(RunItem.run_id == rid).subquery()
    return (db.query(ResultadoBrecha)
              .filter(ResultadoBrecha.run_item_id.in_(sub.select())).count())


class TestVaciadoDeLaCola:
    def test_el_trabajador_termina_el_lote(self, db, encolado):
        from app.models.run import EstadoRun, Run
        from trabajador import _cerrar_terminadas, _procesar_uno

        vueltas = 0
        while _procesar_uno(db) and vueltas < 10:
            vueltas += 1
        _cerrar_terminadas(db)

        db.rollback()
        run = db.query(Run).filter(Run.id == encolado).first()
        assert run.estado == EstadoRun.completado
        assert run.n_items_ok == 3
        assert _brechas(db, encolado) == 3

    def test_retomar_a_mitad_no_repite_lo_hecho(self, db, encolado):
        """La prueba de cierre del paso.

        Se procesan dos articulos y se corta, como si el trabajador muriera.
        Al arrancar de nuevo debe terminar el que falta y solo ese: si
        reprocesara los anteriores, cada reinicio costaria generaciones de
        mas y duplicaria las brechas guardadas.
        """
        from app.models.run import EstadoRun, Run
        from app.models.run_item import EstadoRunItem, RunItem
        from trabajador import _cerrar_terminadas, _procesar_uno

        _procesar_uno(db)
        _procesar_uno(db)

        db.rollback()
        hechas = _brechas(db, encolado)
        assert hechas == 2, "la preparacion no dejo dos articulos analizados"
        assert db.query(RunItem).filter(
            RunItem.run_id == encolado,
            RunItem.estado == EstadoRunItem.pendiente).count() == 1

        # "Reinicio": el estado vive en la base, no en el proceso.
        vueltas = 0
        while _procesar_uno(db) and vueltas < 10:
            vueltas += 1
        _cerrar_terminadas(db)

        db.rollback()
        run = db.query(Run).filter(Run.id == encolado).first()
        assert run.estado == EstadoRun.completado
        assert _brechas(db, encolado) == 3, "se reanalizo algo ya hecho"

    def test_sin_trabajo_devuelve_falso(self, db, encolado):
        from trabajador import _procesar_uno

        vueltas = 0
        while _procesar_uno(db) and vueltas < 10:
            vueltas += 1
        assert _procesar_uno(db) is False

    def test_un_articulo_sin_archivo_se_descarta_sin_reintentos(self, db, encolado,
                                                                proyecto_indexado):
        """Un fallo definitivo no debe consumir los tres intentos: reintentar
        un articulo sin PDF es gastar tiempo en algo que no puede salir bien.

        El articulo se crea de verdad, sin archivo asociado. Apuntar el item a
        un identificador inventado no vale: la clave foranea lo impide, que es
        justo lo que debe hacer.
        """
        from app.models.articulo import Articulo
        from app.models.run_item import EstadoRunItem, RunItem
        from trabajador import _procesar_uno

        aid, iid = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(Articulo(id=aid, proyecto_id=proyecto_indexado["proyecto_id"],
                        doi=None, titulo="Articulo sin PDF"))
        db.flush()
        db.query(RunItem).filter(RunItem.run_id == encolado).delete(
            synchronize_session=False)
        db.add(RunItem(id=iid, run_id=encolado, articulo_id=aid,
                       estado=EstadoRunItem.pendiente))
        db.commit()

        try:
            _procesar_uno(db)
            db.rollback()

            fila = db.query(RunItem).filter(RunItem.id == iid).first()
            assert fila.estado == EstadoRunItem.fallido
            assert fila.intentos == 1, "un fallo definitivo no debe reintentarse"
        finally:
            db.rollback()
            db.query(RunItem).filter(RunItem.id == iid).delete()
            db.query(Articulo).filter(Articulo.id == aid).delete()
            db.commit()

    def test_el_lote_se_cierra_aunque_haya_fallidos(self, db, encolado):
        from app.models.run import EstadoRun, Run
        from app.models.run_item import EstadoRunItem, RunItem
        from trabajador import _cerrar_terminadas, _procesar_uno

        # Uno se marca fallido de antemano; el resto se procesa.
        primero = db.query(RunItem).filter(RunItem.run_id == encolado).first()
        primero.estado = EstadoRunItem.fallido
        primero.error_msg = "sin texto utilizable"
        db.commit()

        vueltas = 0
        while _procesar_uno(db) and vueltas < 10:
            vueltas += 1
        _cerrar_terminadas(db)

        db.rollback()
        run = db.query(Run).filter(Run.id == encolado).first()
        assert run.estado == EstadoRun.completado
        assert run.n_items_ok == 2
