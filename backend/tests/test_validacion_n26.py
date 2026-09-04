"""Validacion ciega y externa del clasificador binario N2.6."""

import uuid

import pytest

from app.routers.validacion_n26 import _intervalo_wilson

@pytest.fixture(scope="module")
def modelos_cargados():
    import main  # noqa: F401


@pytest.fixture
def proyecto_n26(db, usuario_prueba):
    from app.models.articulo import Articulo
    from app.models.metrica import AMBITO_BRECHA, Metrica
    from app.models.proyecto import Proyecto
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.run import EstadoRun, Run
    from app.models.run_item import EstadoRunItem, RunItem

    pid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Validar N2.6", objetivo="Datos nuevos",
                    n_articulos_objetivo=4, estado_arte_generado=False))
    db.flush()
    db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
               n_items_total=4, n_items_ok=4))
    db.flush()

    predicciones = [1.0, 1.0, 0.0, 0.0]
    brechas = []
    procedencia = {
        "esquema": 1, "pipeline": 1, "revision_codigo": "prueba-n26",
        "modelos": {"generacion": "mock"},
        "prompts": {"analisis": 1, "sintesis": 1, "verificacion": 1},
    }
    for i, prediccion in enumerate(predicciones):
        aid, iid, bid = (str(uuid.uuid4()) for _ in range(3))
        db.add(Articulo(id=aid, proyecto_id=pid, doi=None,
                        titulo="Artículo N2.6 %d" % i))
        db.flush()
        db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                       estado=EstadoRunItem.analizado))
        db.flush()
        db.add(ResultadoBrecha(id=bid, run_item_id=iid, tipo_brecha="otra",
                               brecha="Brecha %d" % i, oportunidad="o",
                               rag_hits=[]))
        db.add(Metrica(id=str(uuid.uuid4()), proyecto_id=pid,
                       ambito=AMBITO_BRECHA, referencia_id=bid,
                       codigo="N2.6", version_formula=1, valor=prediccion,
                       detalle={}, procedencia=procedencia))
        brechas.append(bid)
    db.commit()

    try:
        yield {"proyecto": pid, "run": rid, "brechas": brechas}
    finally:
        from app.models.validacion_n26 import ItemValidacionN26, LoteValidacionN26

        db.rollback()
        lotes = [x for x, in db.query(LoteValidacionN26.id).filter(
            LoteValidacionN26.proyecto_id == pid).all()]
        db.query(ItemValidacionN26).filter(
            ItemValidacionN26.lote_id.in_(lotes or ["-"])).delete(
                synchronize_session=False)
        db.query(LoteValidacionN26).filter(
            LoteValidacionN26.proyecto_id == pid).delete(synchronize_session=False)
        db.query(Metrica).filter(Metrica.proyecto_id == pid).delete(
            synchronize_session=False)
        db.query(ResultadoBrecha).filter(
            ResultadoBrecha.id.in_(brechas)).delete(synchronize_session=False)
        db.query(RunItem).filter(RunItem.run_id == rid).delete(
            synchronize_session=False)
        db.query(Run).filter(Run.id == rid).delete()
        db.query(Articulo).filter(Articulo.proyecto_id == pid).delete(
            synchronize_session=False)
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.commit()


def test_wilson_no_inventa_resultado_sin_denominador():
    assert _intervalo_wilson(0, 0) is None


def test_wilson_declara_incertidumbre_de_muestra_pequena():
    intervalo = _intervalo_wilson(1, 1)
    assert intervalo["valor"] == 1.0
    assert intervalo["inferior"] < 0.3
    assert intervalo["superior"] == 1.0


@pytest.mark.bd
def test_no_inicia_con_procedencias_mezcladas(
        cliente, db, proyecto_n26, modelos_cargados):
    """Una sola matriz no puede atribuirse a dos verificadores distintos."""
    from app.models.metrica import Metrica

    metrica = (db.query(Metrica)
               .filter(Metrica.proyecto_id == proyecto_n26["proyecto"],
                       Metrica.codigo == "N2.6").first())
    distinta = dict(metrica.procedencia)
    distinta["revision_codigo"] = "otra-revision"
    metrica.procedencia = distinta
    db.commit()

    r = cliente.post("/proyectos/%s/validacion-n26/iniciar"
                     % proyecto_n26["proyecto"])
    assert r.status_code == 409, r.text
    assert "versiones distintas" in r.json()["detail"]


@pytest.mark.bd
def test_protocolo_congela_oculta_y_bloquea(
        cliente, db, proyecto_n26, modelos_cargados):
    from app.models.metrica import Metrica
    from app.models.validacion_n26 import ItemValidacionN26

    pid = proyecto_n26["proyecto"]
    inicio = cliente.post("/proyectos/%s/validacion-n26/iniciar" % pid)
    assert inicio.status_code == 200, inicio.text
    datos = inicio.json()
    assert datos["lote"]["estado"] == "abierto"
    assert datos["resultado"] is None
    assert all("prediccion_ya_resuelta" not in i for i in datos["items"])

    # Cambiar la tabla de métricas después no cambia lo que se está validando.
    db.query(Metrica).filter(Metrica.proyecto_id == pid,
                             Metrica.codigo == "N2.6").update(
        {Metrica.valor: 0.0}, synchronize_session=False)
    db.commit()
    congeladas = [i.prediccion_ya_resuelta for i in
                  db.query(ItemValidacionN26).order_by(
                      ItemValidacionN26.creado_en,
                      ItemValidacionN26.id).all()
                  if i.brecha_id in proyecto_n26["brechas"]]
    assert sorted(congeladas) == [False, False, True, True]

    vacia = cliente.put(
        "/proyectos/%s/validacion-n26/%s" % (pid, proyecto_n26["brechas"][0]),
        json={"ya_resuelta": True, "justificacion": " "})
    assert vacia.status_code == 422
    assert cliente.post("/proyectos/%s/validacion-n26/cerrar" % pid).status_code == 409

    # Etiquetas humanas [si, no, si, no] frente a predicciones [si, si, no, no].
    etiquetas = [True, False, True, False]
    for bid, etiqueta in zip(proyecto_n26["brechas"], etiquetas):
        r = cliente.put(
            "/proyectos/%s/validacion-n26/%s" % (pid, bid),
            json={"ya_resuelta": etiqueta,
                  "justificacion": "Comprobado en el artículo."})
        assert r.status_code == 200, r.text
        assert r.json()["resultado"] is None

    cierre = cliente.post("/proyectos/%s/validacion-n26/cerrar" % pid)
    assert cierre.status_code == 200, cierre.text
    final = cierre.json()
    assert final["lote"]["estado"] == "cerrado"
    assert final["resultado"]["matriz"] == {
        "verdadero_positivo": 1, "falso_positivo": 1,
        "falso_negativo": 1, "verdadero_negativo": 1,
    }
    assert all("prediccion_ya_resuelta" in i for i in final["items"])

    bloqueada = cliente.put(
        "/proyectos/%s/validacion-n26/%s" % (pid, proyecto_n26["brechas"][0]),
        json={"ya_resuelta": False, "justificacion": "Intento posterior."})
    assert bloqueada.status_code == 409
