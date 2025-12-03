# app/routers/metrics_plots.py
import io
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run_item import RunItem
from app.models.articulo import Articulo

# Forzar backend no interactivo para servidores
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

router = APIRouter(prefix="/proyectos", tags=["metrics-plots"])


def _q_base(db: Session, proyecto_id: str):
    return (
        db.query(ResultadoBrecha, RunItem, Articulo)
        .join(RunItem, ResultadoBrecha.run_item_id == RunItem.id)
        .join(Articulo, RunItem.articulo_id == Articulo.id)
        .filter(Articulo.proyecto_id == proyecto_id)
    )


@router.get("/{proyecto_id}/metrics/plots")
def generar_graficos(proyecto_id: str, db: Session = Depends(get_db)):
    q = _q_base(db, proyecto_id)
    total_rows = q.count()
    if total_rows == 0:
        raise HTTPException(status_code=404, detail="No hay datos para generar métricas")

    # --- Datos base ---
    por_tipo_rows = (
        q.with_entities(ResultadoBrecha.tipo_brecha, func.count())
        .group_by(ResultadoBrecha.tipo_brecha)
        .all()
    )
    por_tipo = {k or "": int(v) for k, v in por_tipo_rows}

    por_estado_rows = (
        q.with_entities(ResultadoBrecha.estado_validacion, func.count())
        .group_by(ResultadoBrecha.estado_validacion)
        .all()
    )
    por_estado = {k or "": int(v) for k, v in por_estado_rows}

    serie_rows = (
        q.with_entities(func.date(ResultadoBrecha.created_at), func.count())
        .group_by(func.date(ResultadoBrecha.created_at))
        .all()
    )
    serie = [(str(d), int(n)) for d, n in serie_rows]

    # Promedios (pueden venir como Decimal)
    avg_ent = q.with_entities(func.avg(ResultadoBrecha.entropia)).scalar() or 0.0
    avg_sim = q.with_entities(func.avg(ResultadoBrecha.sim_promedio)).scalar() or 0.0
    avg_val = q.with_entities(func.avg(ResultadoBrecha.val_score)).scalar() or 0.0
    avg_ent = float(avg_ent)
    avg_sim = float(avg_sim)
    avg_val = float(avg_val)

    # --- Crear buffer ZIP ---
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:

        # 1) Distribución por tipo de brecha
        fig, ax = plt.subplots(figsize=(6, 4))
        tipos = list(por_tipo.keys())
        vals = [int(v) for v in por_tipo.values()]
        ax.bar(tipos, vals)
        ax.set_title("Distribución por Tipo de Brecha")
        ax.set_ylabel("Cantidad")
        plt.xticks(rotation=25)
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png")
        plt.close(fig)
        zf.writestr("brechas_por_tipo.png", buf.getvalue())

        # 2) Distribución por estado de validación
        fig, ax = plt.subplots(figsize=(6, 4))
        estados = list(por_estado.keys())
        vals_estado = [int(v) for v in por_estado.values()]
        if sum(vals_estado) > 0:
            ax.pie(vals_estado, labels=estados, autopct="%1.1f%%", startangle=90)
        else:
            ax.bar(["sin datos"], [0])
        ax.set_title("Distribución por Estado de Validación")
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png")
        plt.close(fig)
        zf.writestr("estado_validacion.png", buf.getvalue())

        # 3) Serie temporal
        if serie:
            fechas = [d for d, _ in serie]
            brechas = [int(n) for _, n in serie]
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.plot(fechas, brechas, marker="o")
            ax.set_title("Brechas Generadas por Día")
            ax.set_xlabel("Fecha")
            ax.set_ylabel("Cantidad")
            plt.xticks(rotation=30)
            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format="png")
            plt.close(fig)
            zf.writestr("brechas_por_dia.png", buf.getvalue())

        # 4) Promedios de métricas
        fig, ax = plt.subplots(figsize=(6, 4))
        labels = ["Entropía", "Similitud", "Score Validación"]
        valores = [float(avg_ent), float(avg_sim), float(avg_val)]
        ax.bar(labels, valores)
        ax.set_ylim(0, 1)
        ax.set_title("Promedio de Métricas del Proyecto")
        for i, v in enumerate(valores):
            v = float(v)
            ax.text(i, v + 0.02, f"{v:.2f}", ha="center")
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png")
        plt.close(fig)
        zf.writestr("promedio_metricas.png", buf.getvalue())

        # 5) Tasa de aceptación general
        aceptadas = por_estado.get("aceptada", 0)
        total_estado = sum(por_estado.values()) or 1
        tasa = (aceptadas / total_estado) * 100.0
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.barh(["Tasa de Aceptación"], [tasa])
        ax.set_xlim(0, 100)
        ax.set_xlabel("%")
        ax.set_title("Tasa de Aceptación Global")
        ax.text(tasa / 2.0, 0, f"{tasa:.1f}%", ha="center", va="center", color="white", fontweight="bold")
        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png")
        plt.close(fig)
        zf.writestr("tasa_aceptacion.png", buf.getvalue())

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="metricas_{proyecto_id}.zip"'},
    )
