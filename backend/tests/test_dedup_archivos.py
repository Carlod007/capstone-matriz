# tests/test_dedup_archivos.py
"""
El alcance de la deduplicacion de PDF es el proyecto, no el sistema entero.

`archivos.py` busca duplicados filtrando por hash Y por proyecto. El esquema,
en cambio, declaraba `UNIQUE (hash_sha256)` sobre toda la tabla. Las dos reglas
no dicen lo mismo, y el desacuerdo solo se manifestaba al subir a un proyecto
un PDF que ya existia en otro: la consulta previa no encontraba nada y el
INSERT chocaba despues contra el indice global, con un 500 sin explicacion.

Ninguna prueba lo detecto porque todas subian archivos distintos. Estas
comprueban la regla desde los dos lados —el que deduplica y el que rechaza—,
que es lo unico que impide que vuelvan a separarse.
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRETO", "secreto-de-pruebas-" + "x" * 40)
os.environ.setdefault("GEMINI_MODE", "mock")

pytestmark = pytest.mark.bd

HASH = "d" * 64


@pytest.fixture(scope="module", autouse=True)
def modelos_cargados():
    """Carga el mapa completo de modelos antes de tocar `Archivo`.

    `archivo.articulo_id` apunta a `articulo`, y SQLAlchemy resuelve esa clave
    foranea por nombre contra el registro de metadatos: si solo se importa
    `Archivo`, la tabla destino no existe todavia y falla al resolverla.

    Sin esta fixture el archivo pasaba al correr la suite entera —otras pruebas
    ya habian importado los modelos— y fallaba al correrlo solo. Una prueba que
    depende de lo que hizo otra antes no comprueba lo que dice comprobar.
    """
    import main  # noqa: F401  (importa todos los modelos)


@pytest.fixture
def dos_proyectos(db, usuario_prueba):
    """Dos proyectos de la misma cuenta, sin artículos ni archivos."""
    from app.models.proyecto import Proyecto

    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    for i, pid in enumerate(ids, start=1):
        db.add(Proyecto(id=pid, usuario_id=usuario_prueba["id"],
                        tema_principal="Proyecto %d" % i,
                        objetivo="Comprobar el alcance de la deduplicacion",
                        n_articulos_objetivo=1, estado_arte_generado=False))
    db.commit()
    try:
        yield ids
    finally:
        from app.models.archivo import Archivo

        db.rollback()
        db.query(Archivo).filter(Archivo.proyecto_id.in_(ids)).delete(
            synchronize_session=False)
        db.query(Proyecto).filter(Proyecto.id.in_(ids)).delete(
            synchronize_session=False)
        db.commit()


def _archivo(pid, hash_=HASH):
    from app.models.archivo import Archivo

    return Archivo(id=str(uuid.uuid4()), proyecto_id=pid, articulo_id=None,
                   nombre="articulo.pdf", ruta="x/%s.pdf" % uuid.uuid4(),
                   hash_sha256=hash_, bytes=1234)


class TestAlcanceDeLaRestriccion:
    def test_el_mismo_pdf_puede_estar_en_dos_proyectos(self, db, dos_proyectos):
        """El caso que fallaba en producción con un 500.

        Es normal reutilizar un artículo entre proyectos: la misma referencia
        sirve para dos revisiones distintas.
        """
        from sqlalchemy.exc import IntegrityError

        a, b = dos_proyectos
        db.add(_archivo(a))
        db.commit()

        db.add(_archivo(b))
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            pytest.fail(
                "el mismo PDF en dos proyectos distintos debe poder existir: %s"
                % e.orig)

    def test_repetirlo_en_el_mismo_proyecto_sigue_prohibido(self, db,
                                                            dos_proyectos):
        """El límite del arreglo: aflojar la restricción no es quitarla.

        Sin esta, cambiar el índice por uno que no restrinja nada también
        pasaría la prueba anterior.
        """
        from sqlalchemy.exc import IntegrityError

        a, _ = dos_proyectos
        db.add(_archivo(a))
        db.commit()

        db.add(_archivo(a))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


class TestElCodigoYElEsquemaDicenLoMismo:
    """La causa de fondo: la consulta y el índice discrepaban.

    Mientras `archivos.py` filtre por proyecto, el índice tiene que incluir esa
    columna. Si alguien vuelve a estrechar uno de los dos sin tocar el otro,
    esto lo dice antes de que un usuario se encuentre un 500.
    """

    def test_el_indice_unico_incluye_el_proyecto(self):
        from app.models.archivo import Archivo

        unicas = [c for c in Archivo.__table__.constraints
                  if c.__class__.__name__ == "UniqueConstraint"]
        sobre_hash = [c for c in unicas
                      if any(col.name == "hash_sha256" for col in c.columns)]

        assert sobre_hash, "no hay restriccion de unicidad sobre el hash"
        for c in sobre_hash:
            nombres = {col.name for col in c.columns}
            assert "proyecto_id" in nombres, (
                "la unicidad del hash debe acotarse al proyecto, porque es "
                "asi como deduplica archivos.py; columnas: %s" % sorted(nombres))

    def test_la_consulta_de_duplicados_filtra_por_proyecto(self):
        """Leido del propio codigo: el filtro de proyecto no puede perderse."""
        import inspect

        from app.routers import archivos

        fuente = inspect.getsource(archivos.subir_pdf)
        assert "Archivo.proyecto_id == proyecto_id" in fuente, (
            "la busqueda de duplicados debe acotarse al proyecto")
