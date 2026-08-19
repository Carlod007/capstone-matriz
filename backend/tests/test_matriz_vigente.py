# tests/test_matriz_vigente.py
"""
La matriz muestra una brecha por articulo; el CSV conserva el historico.

Cada analisis genera una brecha nueva y conserva las anteriores. La pantalla de
detalle ya decidia esa pregunta -destaca la ultima y pliega el resto-, pero las
exportaciones no: la matriz repetia el articulo una vez por analisis, sin decir
cual valia, y el PDF acababa contradiciendo a la interfaz sobre los mismos
datos.

Son dos cosas distintas y se tratan distinto. La matriz es un documento para
leer y su unidad es el articulo. El CSV es un conjunto de datos: quitarle las
brechas anteriores destruiria el material con el que se compara como cambio un
analisis entre dos ejecuciones. Lo que le faltaba era poder distinguirlas.
"""

import csv
import io
import os
import re
import uuid
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

pytestmark = pytest.mark.bd


@pytest.fixture(scope="module", autouse=True)
def modelos_cargados():
    import main  # noqa: F401


@pytest.fixture
def proyecto_reanalizado(db, usuario_prueba):
    """Dos articulos analizados dos veces: cuatro brechas, dos vigentes."""
    from app.models.articulo import Articulo
    from app.models.proyecto import Proyecto
    from app.models.resultado_brecha import ResultadoBrecha
    from app.models.run import EstadoRun, Run
    from app.models.run_item import EstadoRunItem, RunItem

    pid = str(uuid.uuid4())
    aids = [str(uuid.uuid4()), str(uuid.uuid4())]
    ahora = datetime.now()

    db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                    tema_principal="Reanalizado",
                    objetivo="Comprobar la brecha vigente en las exportaciones",
                    n_articulos_objetivo=2, estado_arte_generado=False))
    db.flush()
    for i, aid in enumerate(aids):
        db.add(Articulo(id=aid, proyecto_id=pid, doi="10.0/%d" % i,
                        titulo="Articulo %d" % i))
    db.flush()

    creados = {"runs": [], "items": [], "brechas": [], "vigentes": {}}
    for vuelta in (1, 2):
        rid = str(uuid.uuid4())
        creados["runs"].append(rid)
        db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
                   n_items_total=2, n_items_ok=2))
        db.flush()
        for aid in aids:
            iid = str(uuid.uuid4())
            creados["items"].append(iid)
            db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                           estado=EstadoRunItem.analizado))
            db.flush()
            bid = str(uuid.uuid4())
            creados["brechas"].append(bid)
            db.add(ResultadoBrecha(
                id=bid, run_item_id=iid, tipo_brecha="otra",
                brecha="Brecha de la vuelta %d" % vuelta,
                oportunidad="Oportunidad %d" % vuelta, rag_hits=[],
                created_at=ahora + timedelta(hours=vuelta)))
            if vuelta == 2:
                creados["vigentes"][aid] = bid
    db.commit()

    try:
        yield {"proyecto": pid, "articulos": aids, **creados}
    finally:
        db.rollback()
        db.query(ResultadoBrecha).filter(
            ResultadoBrecha.id.in_(creados["brechas"])).delete(
            synchronize_session=False)
        db.query(RunItem).filter(RunItem.id.in_(creados["items"])).delete(
            synchronize_session=False)
        db.query(Run).filter(Run.id.in_(creados["runs"])).delete(
            synchronize_session=False)
        db.query(Articulo).filter(Articulo.proyecto_id == pid).delete(
            synchronize_session=False)
        db.query(Proyecto).filter(Proyecto.id == pid).delete()
        db.commit()


class TestLaMatrizNoRepiteArticulos:
    def test_una_fila_por_articulo(self, cliente, proyecto_reanalizado):
        pid = proyecto_reanalizado["proyecto"]
        r = cliente.get(f"/export/proyectos/{pid}/matriz.json")
        assert r.status_code == 200, r.text

        filas = r.json()
        filas = filas.get("rows", filas) if isinstance(filas, dict) else filas
        titulos = [f["titulo"] for f in filas]

        assert len(filas) == 2, (
            "dos articulos analizados dos veces son dos filas, no cuatro: %r"
            % titulos)
        assert len(set(titulos)) == 2, "hay articulos repetidos: %r" % titulos

    def test_la_fila_es_la_del_ultimo_analisis(self, cliente,
                                               proyecto_reanalizado):
        """Que no repita no basta: tiene que quedarse con la buena."""
        pid = proyecto_reanalizado["proyecto"]
        filas = cliente.get(f"/export/proyectos/{pid}/matriz.json").json()
        filas = filas.get("rows", filas) if isinstance(filas, dict) else filas

        for f in filas:
            assert "vuelta 2" in f["brecha"], (
                "quedo la brecha del primer analisis: %r" % f["brecha"])

    def test_el_pdf_avisa_de_las_que_no_muestra(self, cliente,
                                                proyecto_reanalizado):
        """Recortar en silencio dejaria un documento que parece contenerlo
        todo, y quien lo comparase con el CSV veria filas de mas."""
        import fitz

        pid = proyecto_reanalizado["proyecto"]
        r = cliente.get(f"/export/proyectos/{pid}/matriz.pdf")
        assert r.status_code == 200, r.text

        with fitz.open(stream=r.content, filetype="pdf") as d:
            texto = "\n".join(p.get_text() for p in d)

        assert "vigente" in texto
        # Lo que se cuenta son brechas, no analisis: un reanalisis de dos
        # articulos deja dos brechas fuera, no dos analisis.
        assert "2 brechas de análisis anteriores" in texto, texto[-400:]
        # El numero pegado a «de» es la version rota: «Hay 2 de análisis
        # anteriores», sin sustantivo. Se busca ese patron y no la frase
        # entera, que tambien aparece dentro de la version correcta.
        assert not re.search(r"\d+\s+de análisis anteriores", texto), (
            "la frase se quedo sin sustantivo")


class TestElCsvConservaTodo:
    def _filas(self, cliente, pid):
        r = cliente.get(f"/export/proyectos/{pid}/brechas.csv")
        assert r.status_code == 200, r.text
        return list(csv.DictReader(io.StringIO(r.text)))

    def test_estan_las_cuatro(self, cliente, proyecto_reanalizado):
        """El limite del cambio: el dataset no pierde filas.

        Es el material con el que se compara como cambio una brecha entre dos
        analisis; recortarlo lo haria mas bonito y menos util.
        """
        filas = self._filas(cliente, proyecto_reanalizado["proyecto"])
        assert len(filas) == 4

    def test_solo_una_vigente_por_articulo(self, cliente,
                                           proyecto_reanalizado):
        filas = self._filas(cliente, proyecto_reanalizado["proyecto"])

        for aid in proyecto_reanalizado["articulos"]:
            suyas = [f for f in filas if f["articulo_id"] == aid]
            vigentes = [f for f in suyas if f["vigente"] == "sí"]
            assert len(suyas) == 2, "faltan brechas del articulo %s" % aid
            assert len(vigentes) == 1, (
                "el articulo %s tiene %d vigentes" % (aid, len(vigentes)))
            assert vigentes[0]["resultado_id"] == \
                proyecto_reanalizado["vigentes"][aid]

    def test_la_vigente_es_la_misma_que_en_la_matriz(self, cliente,
                                                     proyecto_reanalizado):
        """La condicion que hace util el resto: los tres formatos comparten la
        funcion que decide. Si cada uno ordenara por su cuenta, la matriz y el
        CSV podrian senalar brechas distintas y nadie lo notaria."""
        pid = proyecto_reanalizado["proyecto"]

        filas = cliente.get(f"/export/proyectos/{pid}/matriz.json").json()
        filas = filas.get("rows", filas) if isinstance(filas, dict) else filas
        en_matriz = {f["brecha"] for f in filas}

        del_csv = {f["brecha"] for f in self._filas(cliente, pid)
                   if f["vigente"] == "sí"}

        assert en_matriz == del_csv


class TestLaPantallaSenalaLaMisma:
    """La interfaz destaca la primera brecha que le llega y pliega el resto.

    Si su orden no coincide con el de la exportacion, en un empate de fecha la
    pantalla puede destacar una brecha y la matriz otra. Nadie lo notaria hasta
    compararlas, que es justo cuando mas dano hace: al revisar el PDF de la
    tesis contra lo que se vio en pantalla.
    """

    def test_la_primera_de_la_lista_es_la_vigente(self, cliente,
                                                  proyecto_reanalizado):
        from app.routers.export import _brechas_vigentes

        for aid in proyecto_reanalizado["articulos"]:
            r = cliente.get(f"/articulos/{aid}/brechas")
            assert r.status_code == 200, r.text
            filas = r.json()
            assert len(filas) == 2, "deberian estar las dos, la vieja plegada"
            assert filas[0]["id"] == proyecto_reanalizado["vigentes"][aid]

    def test_con_fechas_empatadas_coinciden(self, db, cliente, usuario_prueba):
        """El caso raro que motiva el desempate por identificador."""
        from app.models.articulo import Articulo
        from app.models.proyecto import Proyecto
        from app.models.resultado_brecha import ResultadoBrecha
        from app.models.run import EstadoRun, Run
        from app.models.run_item import EstadoRunItem, RunItem
        from app.routers.export import _brechas_vigentes

        pid, aid, rid, iid = (str(uuid.uuid4()) for _ in range(4))
        instante = datetime.now()
        db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                        tema_principal="Empate en pantalla",
                        objetivo="Que la interfaz y la matriz coincidan",
                        n_articulos_objetivo=1, estado_arte_generado=False))
        db.flush()
        db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="A"))
        db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
                   n_items_total=1, n_items_ok=1))
        db.flush()
        db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                       estado=EstadoRunItem.analizado))
        db.flush()
        ids = [str(uuid.uuid4()) for _ in range(4)]
        for bid in ids:
            db.add(ResultadoBrecha(id=bid, run_item_id=iid, tipo_brecha="otra",
                                   brecha="b", oportunidad="o", rag_hits=[],
                                   created_at=instante))
        db.commit()

        try:
            en_pantalla = cliente.get(f"/articulos/{aid}/brechas").json()[0]["id"]
            en_matriz = _brechas_vigentes(db, pid)[aid]
            assert en_pantalla == en_matriz, (
                "la pantalla destaca %s y la exportacion %s"
                % (en_pantalla, en_matriz))
        finally:
            db.rollback()
            db.query(ResultadoBrecha).filter(
                ResultadoBrecha.run_item_id == iid).delete(
                synchronize_session=False)
            db.query(RunItem).filter(RunItem.id == iid).delete()
            db.query(Run).filter(Run.id == rid).delete()
            db.query(Articulo).filter(Articulo.id == aid).delete()
            db.query(Proyecto).filter(Proyecto.id == pid).delete()
            db.commit()


class TestElDesempate:
    def test_a_igual_fecha_gana_el_mismo_siempre(self, db, cliente,
                                                 usuario_prueba):
        """Dos brechas del mismo instante son posibles -el trabajador escribe
        varias seguidas-. Sin un segundo criterio, la elegida dependeria del
        orden en que la base devolviera las filas, que no esta garantizado."""
        from app.models.articulo import Articulo
        from app.models.proyecto import Proyecto
        from app.models.resultado_brecha import ResultadoBrecha
        from app.models.run import EstadoRun, Run
        from app.models.run_item import EstadoRunItem, RunItem
        from app.routers.export import _brechas_vigentes

        pid, aid, rid = (str(uuid.uuid4()) for _ in range(3))
        instante = datetime.now()
        db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                        tema_principal="Empate", objetivo="Desempate estable",
                        n_articulos_objetivo=1, estado_arte_generado=False))
        db.flush()
        db.add(Articulo(id=aid, proyecto_id=pid, doi=None, titulo="A"))
        db.add(Run(id=rid, proyecto_id=pid, estado=EstadoRun.completado,
                   n_items_total=1, n_items_ok=1))
        db.flush()
        iid = str(uuid.uuid4())
        db.add(RunItem(id=iid, run_id=rid, articulo_id=aid,
                       estado=EstadoRunItem.analizado))
        db.flush()
        ids = sorted(str(uuid.uuid4()) for _ in range(3))
        for bid in ids:
            db.add(ResultadoBrecha(id=bid, run_item_id=iid, tipo_brecha="otra",
                                   brecha="b", oportunidad="o", rag_hits=[],
                                   created_at=instante))
        db.commit()

        try:
            elegidas = {_brechas_vigentes(db, pid)[aid] for _ in range(5)}
            assert len(elegidas) == 1, "la eleccion cambia entre llamadas"
            assert elegidas.pop() == ids[-1], (
                "a igual fecha debe ganar el identificador mayor, de forma "
                "que el criterio sea reproducible y no dependa de la base")
        finally:
            db.rollback()
            db.query(ResultadoBrecha).filter(
                ResultadoBrecha.run_item_id == iid).delete(
                synchronize_session=False)
            db.query(RunItem).filter(RunItem.id == iid).delete()
            db.query(Run).filter(Run.id == rid).delete()
            db.query(Articulo).filter(Articulo.id == aid).delete()
            db.query(Proyecto).filter(Proyecto.id == pid).delete()
            db.commit()
