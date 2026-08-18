# tests/test_listado_proyectos.py
"""
La tarjeta del listado muestra numeros, no un guion fijo.

El indicador «Brechas detectadas» tenia el valor escrito a mano en el frontend
porque el listado nunca sirvio ese dato: solo devolvia id, tema, objetivo y si
habia estado del arte. Un guion en una columna de resultados no se lee como «no
consultado», se lee como «no se detecto ninguna», que es lo contrario de lo que
pasaba en un proyecto ya analizado.

El recuento se hace en el servidor y agrupado. Antes la pantalla pedia los
articulos de cada proyecto por separado: tantas peticiones como tarjetas.
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

pytestmark = pytest.mark.bd


@pytest.fixture(scope="module", autouse=True)
def modelos_cargados():
    import main  # noqa: F401


@pytest.fixture
def proyecto_analizado(db, usuario_prueba):
    """Un proyecto con tres articulos, dos de ellos con brecha."""
    from app.models.articulo import Articulo
    from app.models.proyecto import Proyecto
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.run import EstadoRun, Run
    from app.models.run_item import EstadoRunItem, RunItem

    pid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    aids = [str(uuid.uuid4()) for _ in range(3)]

    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Con brechas",
                    objetivo="Comprobar los recuentos del listado",
                    n_articulos_objetivo=3, estado_arte_generado=False))
    db.flush()
    db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
               n_items_total=3, n_items_ok=2))
    for aid in aids:
        db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="A"))
    db.flush()

    items = []
    for aid in aids:
        iid = str(uuid.uuid4())
        items.append(iid)
        db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                       estado=EstadoRunItem.analizado))
    db.flush()
    # Solo los dos primeros dejan brecha; el tercero se analizo sin resultado.
    for iid in items[:2]:
        db.add(ResultadoBrecha(id=str(uuid.uuid4()), run_item_id=iid,
                               tipo_brecha="otra", brecha="b",
                               oportunidad="o", rag_hits=[]))
    db.commit()

    try:
        yield {"proyecto": pid, "run": rid, "articulos": aids, "items": items}
    finally:
        from app.models.proyecto import Proyecto as P

        db.rollback()
        db.query(ResultadoBrecha).filter(
            ResultadoBrecha.run_item_id.in_(items)).delete(
            synchronize_session=False)
        db.query(RunItem).filter(RunItem.run_id == rid).delete(
            synchronize_session=False)
        db.query(Run).filter(Run.id == rid).delete()
        db.query(Articulo).filter(Articulo.proyecto_id == pid).delete(
            synchronize_session=False)
        db.query(P).filter(P.id == pid).delete()
        db.commit()


def _fila(cliente, pid):
    r = cliente.get("/proyectos")
    assert r.status_code == 200, r.text
    return next(p for p in r.json() if p["id"] == pid)


class TestRecuentos:
    def test_cuenta_articulos_y_brechas(self, cliente, proyecto_analizado):
        fila = _fila(cliente, proyecto_analizado["proyecto"])

        assert fila["n_articulos"] == 3
        assert fila["n_brechas"] == 2, (
            "solo dos articulos dejaron brecha; el tercero se analizo sin "
            "resultado y no debe contarse")

    def test_dice_si_hay_estado_del_arte(self, db, cliente,
                                         proyecto_analizado):
        """Se deriva de la tabla, no de `proyecto.estado_arte_generado`.

        Esa columna se escribe False al crear el proyecto y nadie la actualiza
        cuando la sintesis se genera de verdad, asi que es siempre falsa.
        Fiarse de ella hizo desaparecer el «Generado» y el enlace «ver» de un
        proyecto que si tenia su estado del arte.
        """
        from app.models.estado_arte import EstadoDelArte

        pid = proyecto_analizado["proyecto"]
        assert _fila(cliente, pid)["tiene_estado_arte"] is False

        eid = str(uuid.uuid4())
        db.add(EstadoDelArte(id=eid, proyecto_id=pid,
                             run_id=proyecto_analizado["run"], version=1,
                             texto="Sintesis de prueba"))
        db.commit()
        try:
            fila = _fila(cliente, pid)
            assert fila["tiene_estado_arte"] is True
            # Y la columna sigue mintiendo, que es justamente el motivo de que
            # no se use: si algun dia se mantuviera, esta prueba lo diria.
            assert fila["estado_arte_generado"] is False
        finally:
            db.rollback()
            db.query(EstadoDelArte).filter(EstadoDelArte.id == eid).delete()
            db.commit()

    def test_un_proyecto_vacio_cuenta_cero(self, db, cliente, usuario_prueba):
        """El caso que hacia dudar: sin nada, la cifra es cero, no un guion."""
        from app.models.proyecto import Proyecto

        pid = str(uuid.uuid4())
        db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                        tema_principal="Vacio", objetivo="Sin articulos aun",
                        n_articulos_objetivo=5, estado_arte_generado=False))
        db.commit()
        try:
            fila = _fila(cliente, pid)
            assert fila["n_articulos"] == 0
            assert fila["n_brechas"] == 0
        finally:
            db.rollback()
            db.query(Proyecto).filter(Proyecto.id == pid).delete()
            db.commit()

    def test_reanalizar_no_infla_la_cifra(self, db, cliente,
                                          proyecto_analizado):
        """El motivo de contar articulos con brecha y no brechas sueltas.

        Cada analisis genera una brecha nueva y conserva las anteriores. Con la
        suma directa, reanalizar el mismo proyecto duplicaria el numero sin que
        la matriz tuviera una fila mas.
        """
        from app.models.resultado_brecha import ResultadoBrecha
        from app.models.run import EstadoRun, Run
        from app.models.run_item import EstadoRunItem, RunItem

        pid = proyecto_analizado["proyecto"]
        antes = _fila(cliente, pid)["n_brechas"]

        rid2 = str(uuid.uuid4())
        db.add(Run(id=rid2, proyecto_id=pid, estado=EstadoRun.completado,
                   n_items_total=2, n_items_ok=2))
        db.flush()
        nuevos = []
        for aid in proyecto_analizado["articulos"][:2]:
            iid = str(uuid.uuid4())
            nuevos.append(iid)
            db.add(RunItem(id=iid, run_id=rid2, articulo_id=aid,
                           estado=EstadoRunItem.analizado))
        db.flush()
        for iid in nuevos:
            db.add(ResultadoBrecha(id=str(uuid.uuid4()), run_item_id=iid,
                                   tipo_brecha="otra", brecha="b2",
                                   oportunidad="o2", rag_hits=[]))
        db.commit()

        try:
            assert _fila(cliente, pid)["n_brechas"] == antes, (
                "el segundo analisis de los mismos articulos no anade filas a "
                "la matriz, asi que la cifra no debe cambiar")
        finally:
            db.rollback()
            db.query(ResultadoBrecha).filter(
                ResultadoBrecha.run_item_id.in_(nuevos)).delete(
                synchronize_session=False)
            db.query(RunItem).filter(RunItem.run_id == rid2).delete(
                synchronize_session=False)
            db.query(Run).filter(Run.id == rid2).delete()
            db.commit()

    def test_el_proyecto_suelto_da_los_mismos_numeros(self, cliente,
                                                      proyecto_analizado):
        """GET /proyectos/{id} devolvia los valores por defecto.

        Comparte esquema con el listado, asi que respondia cero articulos, cero
        brechas y sin estado del arte para proyectos que si los tenian: el
        mismo contrato decia la verdad o no segun por que puerta se pidiera.
        """
        pid = proyecto_analizado["proyecto"]
        del_listado = _fila(cliente, pid)

        r = cliente.get(f"/proyectos/{pid}")
        assert r.status_code == 200, r.text
        suelto = r.json()

        for campo in ("n_articulos", "n_brechas", "tiene_estado_arte"):
            assert suelto[campo] == del_listado[campo], (
                "%s difiere entre el listado y el proyecto suelto: %r vs %r"
                % (campo, del_listado[campo], suelto[campo]))
        assert suelto["n_articulos"] == 3

    def test_no_cuenta_lo_de_otras_cuentas(self, db, cliente, usuario_prueba,
                                           proyecto_analizado):
        """Los recuentos van por proyecto; el listado ya filtra por dueno, pero
        una agrupacion mal escrita podria mezclarlos."""
        from app.models.proyecto import Proyecto
        from app.models.usuario import Usuario
        from app.services import seguridad

        otro, pid_ajeno = str(uuid.uuid4()), str(uuid.uuid4())
        db.add(Usuario(id=otro, correo="ajeno-%s@x.com" % otro[:8],
                       contrasena_hash=seguridad.cifrar("clave-de-otra-cuenta"),
                       nombre="Otra", activo=True))
        db.flush()
        db.add(Proyecto(id=pid_ajeno, usuario_id=otro,
                        tema_principal="Ajeno", objetivo="No sale",
                        n_articulos_objetivo=1, estado_arte_generado=False))
        db.commit()

        try:
            r = cliente.get("/proyectos")
            ids = {p["id"] for p in r.json()}
            assert pid_ajeno not in ids
            assert proyecto_analizado["proyecto"] in ids
        finally:
            db.rollback()
            db.query(Proyecto).filter(Proyecto.id == pid_ajeno).delete()
            db.query(Usuario).filter(Usuario.id == otro).delete()
            db.commit()
