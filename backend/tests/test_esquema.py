# tests/test_esquema.py
"""
Coherencia entre los modelos y el esquema de la base.

Convivian tres fuentes de verdad —los modelos, schema.sql y los ALTER TABLE
sueltos— y ninguna coincidia con las otras. El primer autogenerate de Alembic
proponia borrar una tabla, cambiar el tipo de todos los identificadores y
eliminar catorce claves foraneas, porque los modelos describian un esquema
mucho mas pobre que el real.

Estas pruebas evitan que vuelva a separarse sin que nadie se entere.
"""

import pytest

pytestmark = pytest.mark.bd


@pytest.fixture(scope="module")
def metadata():
    from app.database import Base
    import main  # noqa: F401  (importa todos los modelos)

    return Base.metadata


class TestModelosCompletos:
    def test_todas_las_tablas_de_la_base_tienen_modelo(self, db, metadata):
        """Una tabla sin modelo es una tabla que autogenerate propondria borrar."""
        from sqlalchemy import text

        reales = {t[0] for t in db.execute(text(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE()"))}
        reales.discard("alembic_version")  # la gestiona Alembic, no los modelos

        declaradas = set(metadata.tables)
        sin_modelo = reales - declaradas
        assert not sin_modelo, "tablas sin modelo: %s" % sorted(sin_modelo)

    def test_los_identificadores_son_char(self, metadata):
        """CHAR y no VARCHAR: declararlo distinto hacia que Alembic viera una
        diferencia inexistente en cada columna de cada tabla."""
        from sqlalchemy import CHAR

        for nombre, tabla in metadata.tables.items():
            for col in tabla.columns:
                if col.name == "id" or col.name.endswith("_id"):
                    assert isinstance(col.type, CHAR), (
                        "%s.%s deberia ser CHAR" % (nombre, col.name))

    def test_las_claves_foraneas_estan_declaradas(self, metadata):
        """Sin la clave foranea en el modelo, SQLAlchemy desconoce la
        dependencia y ordena los INSERT de forma arbitraria: insertar un
        articulo y su archivo en la misma transaccion fallaba por eso."""
        esperadas = {
            ("articulo", "proyecto_id"),
            ("archivo", "proyecto_id"),
            ("archivo", "articulo_id"),
            ("run", "proyecto_id"),
            ("run_item", "run_id"),
            ("run_item", "articulo_id"),
            ("resultado_brecha", "run_item_id"),
            ("resultado_resumen", "articulo_id"),
            ("estado_arte", "proyecto_id"),
            ("estado_arte", "run_id"),
            ("embedding_doc", "articulo_id"),
            ("rag_log", "proyecto_id"),
            ("metrica", "proyecto_id"),
            ("articulo_meta", "articulo_id"),
        }
        declaradas = {
            (nombre, col.name)
            for nombre, tabla in metadata.tables.items()
            for col in tabla.columns
            if col.foreign_keys
        }
        faltan = esperadas - declaradas
        assert not faltan, "claves foraneas sin declarar: %s" % sorted(faltan)


class TestMigraciones:
    def test_la_base_esta_en_la_ultima_revision(self, db):
        from sqlalchemy import text
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        import os

        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg = Config(os.path.join(raiz, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(raiz, "migraciones"))
        ultima = ScriptDirectory.from_config(cfg).get_current_head()

        actual = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert actual == ultima, (
            "la base esta en %s y la ultima revision es %s; ejecuta "
            "'alembic upgrade head'" % (actual, ultima))

    def test_no_quedan_cambios_pendientes(self, db):
        """El equivalente a 'alembic check': si los modelos y la base
        difieren, esta prueba lo dice antes de que lo diga produccion."""
        import os

        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext

        from app.database import Base, engine
        import main  # noqa: F401

        with engine.connect() as cn:
            contexto = MigrationContext.configure(cn, opts={"compare_type": True})
            diferencias = compare_metadata(contexto, Base.metadata)

        assert not diferencias, (
            "modelos y base divergen en %d puntos; el primero: %s"
            % (len(diferencias), diferencias[0]))
