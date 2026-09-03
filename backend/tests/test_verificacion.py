# tests/test_verificacion.py
"""Nivel N2: fidelidad de la brecha a sus fuentes.

Las pruebas se centran en la interpretacion de la respuesta del juez y en el
calculo de las metricas derivadas. La calidad del juicio en si depende del
modelo y solo puede comprobarse en modo real; aqui se comprueba que el
sistema no acepta como valido lo que no lo es.
"""

import json

import pytest

from app.services import verificacion as V


FRAGMENTOS = [
    {"seccion": "metodo", "texto": "Se empleo un diseno cuasi experimental con una "
                                   "muestra de sesenta articulos seleccionados por "
                                   "muestreo intencional."},
    {"seccion": "resultados", "texto": "El sistema alcanzo una precision de 0.71 y "
                                       "una exhaustividad de 0.58."},
]


def _respuesta(afirmaciones):
    return json.dumps({"afirmaciones": afirmaciones})


class TestInterpretacion:
    def test_lee_una_respuesta_bien_formada(self):
        v = V._interpretar(_respuesta([
            {"texto": "El estudio uso muestreo intencional.", "tipo": "evidencial",
             "respaldada": True, "fragmento": 1, "cita": "muestreo intencional",
             "motivo": "aparece literal"},
            {"texto": "Falta validacion externa.", "tipo": "inferencial",
             "respaldada": None, "fragmento": None, "cita": None, "motivo": "conclusion"},
        ]), {}, len(FRAGMENTOS))
        assert v.disponible is True
        assert len(v.afirmaciones) == 2
        assert len(v.evidenciales) == 1
        assert len(v.inferenciales) == 1

    def test_descarta_un_fragmento_fuera_de_rango(self):
        """Citar un fragmento inexistente es inventarse la fuente."""
        v = V._interpretar(_respuesta([
            {"texto": "Afirmacion.", "tipo": "evidencial", "respaldada": True,
             "fragmento": 99, "cita": "algo", "motivo": ""},
        ]), {}, len(FRAGMENTOS))
        assert v.afirmaciones[0].fragmento is None

    def test_una_inferencial_nunca_queda_respaldada(self):
        """No puede verificarse contra el articulo: afirma lo que no contiene."""
        v = V._interpretar(_respuesta([
            {"texto": "Falta evidencia.", "tipo": "inferencial", "respaldada": True,
             "fragmento": 1, "cita": "x", "motivo": ""},
        ]), {}, len(FRAGMENTOS))
        a = v.afirmaciones[0]
        assert a.respaldada is None and a.fragmento is None

    def test_sin_respaldo_no_conserva_cita(self):
        v = V._interpretar(_respuesta([
            {"texto": "Afirmacion.", "tipo": "evidencial", "respaldada": False,
             "fragmento": 1, "cita": "una cita", "motivo": ""},
        ]), {}, len(FRAGMENTOS))
        a = v.afirmaciones[0]
        assert a.fragmento is None and a.cita is None

    def test_tipo_desconocido_se_trata_como_evidencial(self):
        # Conviene errar del lado de exigir comprobacion.
        v = V._interpretar(_respuesta([
            {"texto": "Afirmacion.", "tipo": "opinion", "respaldada": True,
             "fragmento": 1, "cita": "c", "motivo": ""},
        ]), {}, len(FRAGMENTOS))
        assert v.afirmaciones[0].tipo == V.EVIDENCIAL

    def test_json_invalido_no_queda_disponible(self):
        v = V._interpretar("esto no es json", {}, 2)
        assert v.disponible is False
        assert "JSON" in v.motivo

    def test_json_envuelto_en_marcas_de_codigo(self):
        bruto = "```json\n" + _respuesta([
            {"texto": "Afirmacion.", "tipo": "evidencial", "respaldada": False,
             "fragmento": None, "cita": None, "motivo": ""}]) + "\n```"
        assert V._interpretar(bruto, {}, 2).disponible is True

    def test_lista_vacia_no_queda_disponible(self):
        assert V._interpretar(_respuesta([]), {}, 2).disponible is False


class TestMetricas:
    def _v(self, afirmaciones):
        return V._interpretar(_respuesta(afirmaciones), {}, len(FRAGMENTOS))

    def test_fidelidad_total(self):
        v = self._v([
            {"texto": "A.", "tipo": "evidencial", "respaldada": True, "fragmento": 1,
             "cita": "c", "motivo": ""},
            {"texto": "B.", "tipo": "evidencial", "respaldada": True, "fragmento": 2,
             "cita": "c", "motivo": ""},
        ])
        assert v.fidelidad == 1.0

    def test_fidelidad_detecta_la_alucinacion(self):
        """Una evidencial sin respaldo es, por definicion, inventada."""
        v = self._v([
            {"texto": "A.", "tipo": "evidencial", "respaldada": True, "fragmento": 1,
             "cita": "c", "motivo": ""},
            {"texto": "B.", "tipo": "evidencial", "respaldada": False,
             "fragmento": None, "cita": None, "motivo": ""},
        ])
        assert v.fidelidad == 0.5

    def test_las_inferenciales_no_entran_en_la_fidelidad(self):
        v = self._v([
            {"texto": "A.", "tipo": "evidencial", "respaldada": True, "fragmento": 1,
             "cita": "c", "motivo": ""},
            {"texto": "B.", "tipo": "inferencial", "respaldada": None,
             "fragmento": None, "cita": None, "motivo": ""},
            {"texto": "C.", "tipo": "inferencial", "respaldada": None,
             "fragmento": None, "cita": None, "motivo": ""},
        ])
        assert v.fidelidad == 1.0

    def test_equilibrio_detecta_la_especulacion(self):
        """Una brecha solo de conclusiones no tiene nada que verificar."""
        v = self._v([
            {"texto": "A.", "tipo": "inferencial", "respaldada": None,
             "fragmento": None, "cita": None, "motivo": ""},
            {"texto": "B.", "tipo": "inferencial", "respaldada": None,
             "fragmento": None, "cita": None, "motivo": ""},
        ])
        assert v.equilibrio_evidencial == 0.0
        # Y la fidelidad no debe salir alta por no tener nada que comprobar.
        assert v.fidelidad == 0.0

    def test_una_inferencia_sin_cita_no_reduce_la_trazabilidad_v2(self):
        v = self._v([
            {"texto": "A.", "tipo": "evidencial", "respaldada": True, "fragmento": 1,
             "cita": "una cita", "motivo": ""},
            {"texto": "B.", "tipo": "inferencial", "respaldada": None,
             "fragmento": None, "cita": None, "motivo": ""},
        ])
        assert v.trazabilidad == 1.0
        assert v.detalle_trazabilidad()["n_excluidas_inferenciales"] == 1

    def test_una_evidencial_sin_fragmento_reduce_la_trazabilidad_v2(self):
        v = self._v([
            {"texto": "A.", "tipo": "evidencial", "respaldada": True,
             "fragmento": 1, "cita": "una cita", "motivo": ""},
            {"texto": "B.", "tipo": "evidencial", "respaldada": False,
             "fragmento": None, "cita": None, "motivo": "no aparece"},
        ])
        assert v.trazabilidad == 0.5
        detalle = v.detalle_trazabilidad()
        assert detalle["n_elegibles"] == 2
        assert detalle["n_sin_fragmento_o_cita"] == 1

    def test_sin_evidenciales_autonomas_la_trazabilidad_no_aplica(self):
        v = self._v([
            {"texto": "Por tanto falta validación externa.",
             "tipo": "inferencial", "respaldada": None,
             "fragmento": None, "cita": None, "motivo": "conclusión"},
        ])
        assert v.trazabilidad is None
        detalle = v.detalle_trazabilidad()
        assert detalle["n_elegibles"] == 0
        assert "motivo" in detalle

    def test_evidencial_dependiente_se_excluye_pero_queda_en_el_detalle(self):
        v = self._v([
            {"texto": "Esto limita su fiabilidad.", "tipo": "evidencial",
             "respaldada": False, "fragmento": None, "cita": None,
             "motivo": "sin sujeto"},
        ])
        assert v.trazabilidad is None
        assert v.detalle_trazabilidad()["n_excluidas_dependientes_evidenciales"] == 1
        assert v.resumen()["n_dependientes"] == 1

    def test_el_resumen_incluye_las_no_respaldadas(self):
        v = self._v([
            {"texto": "Inventada.", "tipo": "evidencial", "respaldada": False,
             "fragmento": None, "cita": None, "motivo": "no aparece"},
        ])
        r = v.resumen()
        assert r["n_sin_respaldo"] == 1
        assert r["fidelidad"] == 0.0


class TestGuardas:
    def test_brecha_vacia(self):
        v = V.verificar("", FRAGMENTOS)
        assert v.disponible is False and "vacía" in v.motivo

    def test_sin_fragmentos(self):
        v = V.verificar("una brecha cualquiera", [])
        assert v.disponible is False and "fragmentos" in v.motivo

    def test_modo_simulado_no_se_declara_disponible(self):
        """Una heuristica por palabras clave no es una medicion."""
        v = V.verificar(
            "El estudio empleo muestreo intencional sobre sesenta articulos. "
            "Falta validacion externa en otras poblaciones.", FRAGMENTOS)
        assert v.disponible is False
        assert "simulada" in v.motivo.lower()
        # Aun asi ejercita el recorrido completo.
        assert len(v.afirmaciones) == 2
        assert {a.tipo for a in v.afirmaciones} == {V.EVIDENCIAL, V.INFERENCIAL}


class TestMedicionVigente:
    """Regresion: con varias mediciones del mismo codigo hay que quedarse con
    la ultima.

    Al verificar dos veces la misma brecha convivian dos filas de
    N2.verificada. El endpoint de brechas no ordenaba por fecha, asi que
    elegia una arbitrariamente y una brecha verificada de verdad podia
    mostrarse con el resultado de un intento anterior y aparecer como "sin
    verificar".
    """

    pytestmark = pytest.mark.bd

    def test_el_endpoint_devuelve_la_verificacion_mas_reciente(self, db, cliente,
                                                               proyecto_indexado):
        import uuid

        from app.models.metrica import Metrica, AMBITO_BRECHA
        from app.models.resultado_brecha import ResultadoBrecha
        from app.models.run_item import RunItem, EstadoRunItem
        from app.models.run import Run, EstadoRun

        pid = proyecto_indexado["proyecto_id"]
        aid = proyecto_indexado["pertinente"]

        run = Run(id=str(uuid.uuid4()), proyecto_id=pid, estado=EstadoRun.completado,
                  n_items_total=1, n_items_ok=1)
        db.add(run)
        db.flush()
        item = RunItem(id=str(uuid.uuid4()), run_id=run.id, articulo_id=aid,
                       estado=EstadoRunItem.analizado)
        db.add(item)
        db.flush()
        rb = ResultadoBrecha(id=str(uuid.uuid4()), run_item_id=item.id,
                             tipo_brecha="otra", brecha="una brecha",
                             oportunidad="una oportunidad", rag_hits=[])
        db.add(rb)
        db.flush()

        def _m(valor, detalle):
            db.add(Metrica(id=str(uuid.uuid4()), proyecto_id=pid,
                           ambito=AMBITO_BRECHA, referencia_id=rb.id,
                           codigo="N2.verificada", valor=valor, detalle=detalle))
            db.flush()

        _m(0.0, {"disponible": False, "motivo": "intento anterior"})
        _m(1.0, {"disponible": True, "n_afirmaciones": 3})
        db.commit()

        try:
            b = cliente.get("/articulos/%s/brechas" % aid).json()[0]
            assert b["verificacion"]["disponible"] is True
            assert b["verificacion"]["n_afirmaciones"] == 3
        finally:
            db.query(Run).filter(Run.id == run.id).delete()
            db.commit()


class TestCatalogo:
    def test_las_metricas_n2_estan_catalogadas(self):
        from app.services.metricas.catalogo import CATALOGO, FORMULA_N2_2

        for c in ("N2.1", "N2.2", "N2.4", "N2.verificada"):
            assert c in CATALOGO, "falta la ficha de %s" % c
        assert CATALOGO["N2.2"].version_formula == FORMULA_N2_2 == 2

    def test_la_verificacion_cuenta_contra_la_cuota_diaria(self):
        from app.services.registro_api import OP_VERIFICACION, OPERACIONES_DE_GENERACION

        assert OP_VERIFICACION in OPERACIONES_DE_GENERACION
