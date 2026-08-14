# tests/test_cola.py
"""
Mecanica de la cola de trabajos.

Lo que hay que demostrar no es que el analisis funcione —eso ya se probaba—
sino que la cola aguanta lo que pasa de verdad en un servidor: dos
trabajadores a la vez, uno que se cae a mitad, y fallos que a veces conviene
reintentar y a veces no.
"""

import os
import uuid
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)

pytestmark = pytest.mark.bd


@pytest.fixture
def lote(db, usuario_prueba):
    """Una ejecucion con tres articulos pendientes."""
    from app.models.articulo import Articulo
    from app.models.proyecto import Proyecto
    from app.models.run import EstadoRun, Run
    from app.models.run_item import EstadoRunItem, RunItem

    pid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Cola de trabajos",
                    objetivo="Comprobar el reparto entre trabajadores",
                    n_articulos_objetivo=3, estado_arte_generado=False))
    db.flush()

    articulos, items = [], []
    for i in range(3):
        aid = str(uuid.uuid4())
        db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="Articulo %d" % i))
        articulos.append(aid)
    db.flush()

    db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.creado,
               n_items_total=3, n_items_ok=0, genera_estado_arte=False))
    db.flush()

    for aid in articulos:
        iid = str(uuid.uuid4())
        db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                       estado=EstadoRunItem.pendiente))
        items.append(iid)
    db.commit()

    try:
        yield {"proyecto": pid, "run": rid, "articulos": articulos, "items": items}
    finally:
        db.rollback()
        db.query(RunItem).filter(RunItem.run_id == rid).delete(synchronize_session=False)
        db.query(Run).filter(Run.id == rid).delete()
        db.query(Articulo).filter(Articulo.proyecto_id == pid).delete(
            synchronize_session=False)
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.commit()


class TestReparto:
    def test_tomar_marca_el_articulo_y_cuenta_el_intento(self, db, lote):
        from app.models.run_item import EstadoRunItem
        from app.services import cola

        item = cola.tomar_pendiente(db, run_id=lote["run"])
        assert item is not None
        assert item.estado == EstadoRunItem.en_proceso
        assert item.intentos == 1
        assert item.tomado_en is not None

    def test_dos_trabajadores_no_cogen_el_mismo(self, db, lote):
        """Es la razon de ser de SKIP LOCKED. Sin el, el segundo esperaria al
        primero o se llevaria el mismo articulo y se analizaria dos veces,
        gastando dos generaciones para un solo resultado."""
        from app.database import SessionLocal
        from app.services import cola

        otra = SessionLocal()
        try:
            primero = cola.tomar_pendiente(db, run_id=lote["run"])
            segundo = cola.tomar_pendiente(otra, run_id=lote["run"])
            assert primero is not None and segundo is not None
            assert primero.id != segundo.id
        finally:
            otra.rollback()
            otra.close()

    def test_cuando_no_queda_nada_devuelve_None(self, db, lote):
        from app.services import cola

        for _ in range(3):
            assert cola.tomar_pendiente(db, run_id=lote["run"]) is not None
        assert cola.tomar_pendiente(db, run_id=lote["run"]) is None

    def test_no_invade_ejecuciones_ajenas(self, db, lote):
        """Pedir trabajo de una ejecucion concreta no debe traer el de otra."""
        from app.services import cola

        otro_run = str(uuid.uuid4())
        assert cola.tomar_pendiente(db, run_id=otro_run) is None


class TestAbandono:
    def test_se_recupera_lo_que_dejo_un_trabajador_caido(self, db, lote):
        """Un proceso que muere a mitad deja su articulo en `en_proceso`. Sin
        recuperarlo, ese articulo no se analizaria jamas y la ejecucion se
        quedaria a medias para siempre."""
        from app.models.run_item import EstadoRunItem, RunItem
        from app.services import cola

        item = cola.tomar_pendiente(db, run_id=lote["run"])
        # Se envejece la marca para simular que el trabajador no volvio.
        (db.query(RunItem).filter(RunItem.id == item.id)
           .update({"tomado_en": datetime.now() - cola.ABANDONO - timedelta(minutes=1)},
                   synchronize_session=False))
        db.commit()

        recuperado = None
        for _ in range(4):
            candidato = cola.tomar_pendiente(db, run_id=lote["run"])
            if candidato is not None and candidato.id == item.id:
                recuperado = candidato
                break
        assert recuperado is not None, "el articulo abandonado no se recupero"
        assert recuperado.intentos == 2
        assert recuperado.estado == EstadoRunItem.en_proceso

    def test_no_se_toca_lo_que_sigue_en_curso(self, db, lote):
        """El plazo de abandono existe para no robarle el trabajo a un
        trabajador que sigue vivo, solo que tardando."""
        from app.services import cola

        item = cola.tomar_pendiente(db, run_id=lote["run"])
        siguientes = set()
        for _ in range(3):
            otro = cola.tomar_pendiente(db, run_id=lote["run"])
            if otro:
                siguientes.add(otro.id)
        assert item.id not in siguientes


class TestReintentos:
    def test_devolver_lo_deja_disponible(self, db, lote):
        from app.models.run_item import EstadoRunItem
        from app.services import cola

        item = cola.tomar_pendiente(db, run_id=lote["run"])
        cola.devolver(db, item, "se cayo la red")

        assert item.estado == EstadoRunItem.pendiente
        assert item.tomado_en is None
        assert item.error_msg == "se cayo la red"

    def test_agotados_los_intentos_se_da_por_fallido(self, db, lote):
        """Insistir sin limite convierte un fallo en un bucle infinito, y con
        la API de por medio, en gasto de cuota infinito."""
        from app.models.run_item import EstadoRunItem
        from app.services import cola

        item = None
        for _ in range(cola.MAX_INTENTOS):
            item = cola.tomar_pendiente(db, run_id=lote["run"])
            cola.devolver(db, item, "fallo que se repite")

        assert item.estado == EstadoRunItem.fallido
        assert "%d intentos" % cola.MAX_INTENTOS in item.error_msg
        assert "fallo que se repite" in item.error_msg

    def test_un_fallido_no_se_vuelve_a_tomar(self, db, lote):
        from app.services import cola

        vistos = []
        for _ in range(cola.MAX_INTENTOS):
            it = cola.tomar_pendiente(db, run_id=lote["run"])
            cola.devolver(db, it, "no hay manera")
            vistos.append(it.id)
        agotado = vistos[-1]

        restantes = set()
        for _ in range(6):
            it = cola.tomar_pendiente(db, run_id=lote["run"])
            if it is None:
                break
            restantes.add(it.id)
        assert agotado not in restantes


class TestCierre:
    def test_una_ejecucion_con_pendientes_no_se_cierra(self, db, lote):
        from app.services import cola

        assert cola.quedan_pendientes(db, lote["run"]) is True
        assert lote["run"] not in [r.id for r in cola.runs_por_cerrar(db)]

    def test_un_articulo_en_proceso_cuenta_como_pendiente(self, db, lote):
        """Cerrar la ejecucion con uno en curso daria por completo un lote que
        no lo esta, y las metricas del lote saldrian sobre datos a medias."""
        from app.models.run_item import EstadoRunItem, RunItem
        from app.services import cola

        (db.query(RunItem).filter(RunItem.run_id == lote["run"])
           .update({"estado": EstadoRunItem.analizado}, synchronize_session=False))
        db.commit()
        item = db.query(RunItem).filter(RunItem.run_id == lote["run"]).first()
        item.estado = EstadoRunItem.en_proceso
        db.commit()

        assert cola.quedan_pendientes(db, lote["run"]) is True

    def test_con_todo_resuelto_la_ejecucion_queda_por_cerrar(self, db, lote):
        from app.models.run_item import EstadoRunItem, RunItem
        from app.services import cola

        (db.query(RunItem).filter(RunItem.run_id == lote["run"])
           .update({"estado": EstadoRunItem.analizado}, synchronize_session=False))
        db.commit()

        assert cola.quedan_pendientes(db, lote["run"]) is False
        assert lote["run"] in [r.id for r in cola.runs_por_cerrar(db)]

    def test_un_lote_con_fallidos_tambien_se_cierra(self, db, lote):
        """Si un articulo no hay manera de analizarlo, la ejecucion tiene que
        terminar igual; si no, se quedaria en progreso indefinidamente."""
        from app.models.run_item import EstadoRunItem, RunItem
        from app.services import cola

        ids = lote["items"]
        (db.query(RunItem).filter(RunItem.id.in_(ids[:2]))
           .update({"estado": EstadoRunItem.analizado}, synchronize_session=False))
        (db.query(RunItem).filter(RunItem.id == ids[2])
           .update({"estado": EstadoRunItem.fallido}, synchronize_session=False))
        db.commit()

        assert cola.quedan_pendientes(db, lote["run"]) is False
        assert cola.contar_ok(db, lote["run"]) == 2

    def test_cerrar_dos_veces_no_duplica_nada(self, db, lote):
        """Quien cierra es un barrido periodico, no el trabajador que acaba el
        ultimo articulo, asi que puede tocarle dos veces la misma ejecucion."""
        from app.models.metrica import Metrica
        from app.models.run import EstadoRun, Run
        from app.models.run_item import EstadoRunItem, RunItem
        from app.routers.runs import cerrar_run

        (db.query(RunItem).filter(RunItem.run_id == lote["run"])
           .update({"estado": EstadoRunItem.analizado}, synchronize_session=False))
        db.commit()

        run = db.query(Run).filter(Run.id == lote["run"]).first()
        cerrar_run(db, run)
        n1 = db.query(Metrica).filter(Metrica.proyecto_id == lote["proyecto"]).count()
        cerrar_run(db, run)
        n2 = db.query(Metrica).filter(Metrica.proyecto_id == lote["proyecto"]).count()

        assert run.estado == EstadoRun.completado
        assert n1 == n2


class TestEncolado:
    def test_analizar_todo_responde_sin_analizar(self, cliente, db, lote):
        """La prueba de que ya no bloquea: responde con la ejecucion creada y
        sin ningun articulo procesado todavia."""
        from app.models.run import EstadoRun, Run
        from app.models.run_item import RunItem

        # La fixture ya dejo una ejecucion en curso; se retira para que el
        # endpoint no responda 409.
        db.query(RunItem).filter(RunItem.run_id == lote["run"]).delete(
            synchronize_session=False)
        db.query(Run).filter(Run.id == lote["run"]).delete()
        db.commit()

        r = cliente.post("/proyectos/%s/analizar_todo" % lote["proyecto"])
        assert r.status_code == 200
        d = r.json()
        assert d["estado"] == EstadoRun.creado.value
        assert d["n_items_ok"] == 0
        assert d["n_items_total"] == 3

        try:
            assert db.query(RunItem).filter(RunItem.run_id == d["run_id"]).count() == 3
        finally:
            db.rollback()
            db.query(RunItem).filter(RunItem.run_id == d["run_id"]).delete(
                synchronize_session=False)
            db.query(Run).filter(Run.id == d["run_id"]).delete()
            db.commit()

    def test_no_se_encola_dos_veces_el_mismo_proyecto(self, cliente, lote):
        """Encolar dos veces duplicaria el gasto de cuota sin dar nada nuevo."""
        r = cliente.post("/proyectos/%s/analizar_todo" % lote["proyecto"])
        assert r.status_code == 409
        assert r.json()["detail"]["run_id"] == lote["run"]

    def test_el_avance_se_consulta_por_la_ejecucion(self, cliente, lote):
        r = cliente.get("/proyectos/runs/%s" % lote["run"])
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == lote["run"]
        assert d["n_items_total"] == 3
