"""La procedencia distingue resultados que ya no son metodologicamente iguales."""

import csv
import io
import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")


class _DbFalsa:
    def __init__(self):
        self.registros = []

    def add(self, registro):
        self.registros.append(registro)


def test_la_fotografia_reune_modelos_prompts_y_parametros(monkeypatch):
    from app.services.procedencia import capturar_procedencia

    monkeypatch.setenv("APP_REVISION", "abc1234")
    p = capturar_procedencia()

    assert p["revision_codigo"] == "abc1234"
    assert p["pipeline"] >= 1
    assert p["modelos"]["generacion"]
    assert p["modelos"]["embedding"]
    assert p["prompts"] == {"analisis": 1, "sintesis": 1, "verificacion": 1}
    assert p["fragmentacion"]["caracteres"] > 0
    assert p["recuperacion"]["top_k"] == 8


def test_cada_formula_toma_la_version_del_catalogo():
    from app.services.registro_metricas import registrar_metrica
    from app.services.metricas.niveles import FORMULA_N3_4

    db = _DbFalsa()
    normal = registrar_metrica(db, "p", "brecha", "b", "N1.2", 0.5)
    trazabilidad = registrar_metrica(db, "p", "brecha", "b", "N2.2", 1.0)
    cambiada = registrar_metrica(db, "p", "run", "r", "N3.4", 0.0)

    assert normal.version_formula == 2
    assert trazabilidad.version_formula == 2
    assert cambiada.version_formula == 2
    assert cambiada.version_formula == FORMULA_N3_4
    assert normal.procedencia["prompts"]["analisis"] == 1


def test_un_codigo_desconocido_no_recibe_una_version_inventada():
    from app.services.registro_metricas import registrar_metrica

    db = _DbFalsa()
    desconocida = registrar_metrica(db, "p", "run", "r", "N?.?", None)
    assert desconocida.version_formula is None


@pytest.mark.bd
def test_run_metricas_y_exportaciones_conservan_la_procedencia(
    db, cliente, usuario_prueba
):
    from app.models.articulo import Articulo
    from app.models.metrica import Metrica
    from app.models.proyecto import Proyecto
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.run import Run
    from app.models.run_item import RunItem
    from app.services.registro_metricas import registrar_metrica

    pid = str(uuid.uuid4())
    articulos = [str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())]
    db.add(Proyecto(
        id=pid,
        usuario_id=usuario_prueba["id"],
        tema_principal="Procedencia",
        objetivo="Distinguir formulas y configuraciones",
        n_articulos_objetivo=3,
        estado_arte_generado=False,
    ))
    db.flush()
    for i, aid in enumerate(articulos):
        db.add(Articulo(
            id=aid, proyecto_id=pid, doi=f"10.0/procedencia-{i}", titulo=f"A{i}"
        ))
    db.commit()

    try:
        respuesta = cliente.post(f"/proyectos/{pid}/analizar_todo")
        assert respuesta.status_code == 200, respuesta.text
        run_id = respuesta.json()["run_id"]
        run = db.query(Run).filter(Run.id == run_id).one()
        assert run.procedencia
        assert respuesta.json()["procedencia"] == run.procedencia

        items = (db.query(RunItem).filter(RunItem.run_id == run_id)
                 .order_by(RunItem.articulo_id).all())
        registrar_metrica(db, pid, "articulo", articulos[0], "N3.2", 1.0)
        # Simula una formula futura en otra entidad del mismo lote. La API no
        # puede promediarla con v1 como si fueran la misma serie.
        futura = dict(run.procedencia)
        futura["prompts"] = dict(futura["prompts"], analisis=99)
        db.add(Metrica(
            id=str(uuid.uuid4()), proyecto_id=pid, ambito="articulo",
            referencia_id=articulos[1], codigo="N3.2", version_formula=1,
            valor=9.0, procedencia=futura,
        ))
        db.add(Metrica(
            id=str(uuid.uuid4()), proyecto_id=pid, ambito="articulo",
            referencia_id=articulos[2], codigo="N3.2", version_formula=99,
            valor=99.0, procedencia=run.procedencia,
        ))
        db.add(ResultadoBrecha(
            id=str(uuid.uuid4()), run_item_id=items[0].id, tipo_brecha="otra",
            brecha="Brecha trazable", oportunidad="Oportunidad trazable",
            rag_hits=[],
        ))
        db.commit()

        metricas = cliente.get(f"/proyectos/{pid}/metricas")
        assert metricas.status_code == 200, metricas.text
        series = [m for m in metricas.json()["metricas"] if m["codigo"] == "N3.2"]
        identificadores = {
            (m["version_formula"], m["procedencia"]["prompts"]["analisis"], m["n"])
            for m in series
        }
        assert identificadores == {(1, 1, 1), (1, 99, 1), (99, 1, 1)}
        assert metricas.json()["run"]["procedencia"] == run.procedencia

        matriz = cliente.get(f"/export/proyectos/{pid}/matriz.json")
        assert matriz.status_code == 200, matriz.text
        assert matriz.json()[0]["run_id"] == run_id
        assert matriz.json()[0]["procedencia"] == run.procedencia

        csv_r = cliente.get(f"/export/proyectos/{pid}/brechas.csv")
        assert csv_r.status_code == 200, csv_r.text
        fila = next(csv.DictReader(io.StringIO(csv_r.text)))
        assert fila["run_id"] == run_id
        assert fila["pipeline_version"] == str(run.procedencia["pipeline"])
    finally:
        db.rollback()
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.commit()
