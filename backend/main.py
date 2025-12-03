from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# -------------------------------
# Routers
# -------------------------------
from app.routers import proyectos
from app.routers import archivos
from app.routers import articulos
from app.routers import runs
from app.routers import brechas
from app.routers import estado_arte
from app.routers import embeddings
from app.routers import metrics
from app.routers import export
from app.routers import metrics_plots
from app.routers import batch
from app.routers import dashboard
from app.routers import pipeline

# -------------------------------
# Base y engine
# -------------------------------
from app.database import Base, engine

# -------------------------------
# IMPORTAR TODOS LOS MODELOS PARA create_all
# -------------------------------
from app.models.articulo import Articulo
from app.models.run import Run
from app.models.run_item import RunItem
from app.models.embedding_doc import EmbeddingDoc
from app.models.resultado_brecha import ResultadoBrecha
from app.models.estado_arte import EstadoDelArte
from app.models.resultado_resumen import ResultadoResumen   # <--- NUEVO

# -------------------------------
# CREAR TABLAS SI NO EXISTEN
# -------------------------------
Base.metadata.create_all(bind=engine)  # crea todas las tablas conocidas por los modelos

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
app.include_router(proyectos.router)
app.include_router(archivos.router)
app.include_router(articulos.router)
app.include_router(runs.router)
app.include_router(brechas.router)
app.include_router(estado_arte.router)
app.include_router(embeddings.router)
app.include_router(metrics.router)
app.include_router(export.router)
app.include_router(metrics_plots.router)
app.include_router(batch.router)
app.include_router(dashboard.router)
app.include_router(pipeline.router)
