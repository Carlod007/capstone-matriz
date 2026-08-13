# migraciones/env.py
"""
Configuración de Alembic.

La dirección de la base se lee del mismo .env que usa la aplicación, en lugar
de duplicarla en alembic.ini: tener la contraseña en dos sitios acaba con los
dos desincronizados, y uno de ellos versionado.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# El paquete de la aplicación tiene que ser importable para que
# Base.metadata conozca todas las tablas.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(RAIZ, ".env"))

from app.database import Base  # noqa: E402

# Importar los modelos registra sus tablas en el metadata; sin esto,
# autogenerate creeria que hay que borrarlas todas.
from app.models import (  # noqa: E402,F401
    archivo, articulo, articulo_meta, embedding_doc, estado_arte, llamada_api,
    metrica, proyecto, rag_log, resultado_brecha, resultado_resumen, run,
    run_item,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

uri = os.getenv("MYSQL_URI")
if not uri:
    raise RuntimeError(
        "Falta MYSQL_URI en backend/.env. Alembic necesita saber sobre qué "
        "base actuar."
    )
config.set_main_option("sqlalchemy.url", uri.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse, para revisarlo antes de aplicarlo."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with conectable.connect() as conexion:
        context.configure(
            connection=conexion,
            target_metadata=target_metadata,
            # Detecta tambien los cambios de tipo, no solo las columnas
            # nuevas: la divergencia entre CHAR y VARCHAR ya causo problemas.
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
