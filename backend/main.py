from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# -------------------------------
# Routers
# -------------------------------
from app.routers import auth
from app.routers import proyectos
from app.routers import archivos
from app.routers import articulos
from app.routers import runs
from app.routers import brechas
from app.routers import estado_arte
from app.routers import embeddings
from app.routers import metrics
from app.routers import metricas_v2
from app.routers import verificacion_rt
from app.routers import export
from app.routers import metrics_plots
from app.routers import dashboard
from app.routers import pipeline

# -------------------------------
# Base y engine
# -------------------------------
from app.database import Base, engine

# -------------------------------
# IMPORTAR TODOS LOS MODELOS PARA create_all
# -------------------------------
from app.models.proyecto import Proyecto
from app.models.archivo import Archivo
from app.models.articulo import Articulo
from app.models.articulo_meta import ArticuloMeta
from app.models.run import Run
from app.models.run_item import RunItem
from app.models.embedding_doc import EmbeddingDoc
from app.models.resultado_brecha import ResultadoBrecha
from app.models.estado_arte import EstadoDelArte
from app.models.resultado_resumen import ResultadoResumen
from app.models.rag_log import RagLog
from app.models.metrica import Metrica
from app.models.llamada_api import LlamadaAPI
from app.models.usuario import Usuario

# -------------------------------
# CONFIGURACION
# -------------------------------
# Se revisa antes que nada: una variable ausente debe impedir arrancar, no
# aparecer como un error confuso en la primera peticion que la necesite.
from app import config

config.revisar()

# -------------------------------
# ESTADO DEL ESQUEMA
# -------------------------------
# Ya no se llama a create_all(). Creaba tablas a partir de los modelos, que
# describian un esquema mas pobre que el real —sin claves foraneas ni
# indices— y ademas convivia con schema.sql y con ALTER TABLE sueltos: tres
# fuentes de verdad para una sola base (A-05). El esquema lo gobierna Alembic.
#
# Aqui solo se comprueba en que revision esta la base y se avisa si no
# coincide con la ultima. Arrancar contra un esquema desactualizado produce
# errores confusos mas adelante, y es mejor saberlo al inicio.
def _revisar_esquema() -> None:
    import logging
    import os

    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect, text

    log = logging.getLogger("uvicorn.error")
    raiz = os.path.dirname(os.path.abspath(__file__))
    try:
        cfg = Config(os.path.join(raiz, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(raiz, "migraciones"))
        ultima = ScriptDirectory.from_config(cfg).get_current_head()

        with engine.connect() as cn:
            if "alembic_version" not in inspect(engine).get_table_names():
                log.warning(
                    "La base no tiene historial de migraciones. Ejecuta "
                    "'alembic upgrade head' desde backend/ para crear el esquema."
                )
                return
            actual = cn.execute(text("SELECT version_num FROM alembic_version")).scalar()

        if actual != ultima:
            log.warning(
                "El esquema esta en la revision %s y la ultima es %s. "
                "Ejecuta 'alembic upgrade head' desde backend/.", actual, ultima
            )
    except Exception as exc:  # noqa: BLE001
        # Comprobar el esquema no debe impedir arrancar: si algo falla aqui,
        # se avisa y se sigue.
        log.warning("No se pudo comprobar el estado del esquema: %s", exc)


_revisar_esquema()

# -------------------------------
# App FastAPI
# -------------------------------
app = FastAPI(title="Capstone Backend", swagger_ui_parameters={"theme": "flattop"})

# -------------------------------
# CORS
# -------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# Healthcheck
# -------------------------------
@app.get("/health")
def health():
    return {"ok": True}

# -------------------------------
# Include Routers
# -------------------------------
app.include_router(auth.router)
app.include_router(proyectos.router)
app.include_router(archivos.router)
app.include_router(articulos.router)
app.include_router(runs.router)
app.include_router(brechas.router)
app.include_router(estado_arte.router)
app.include_router(embeddings.router)
app.include_router(metrics.router)
app.include_router(metricas_v2.router)
app.include_router(metricas_v2.router_global)
app.include_router(verificacion_rt.router)
app.include_router(export.router)
app.include_router(metrics_plots.router)
app.include_router(dashboard.router)
app.include_router(pipeline.router)
