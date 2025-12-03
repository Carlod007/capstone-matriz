# app/routers/export.py
import csv, io
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
from sqlalchemy.orm import Session

# ---- ReportLab (PDF) ----
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Table, TableStyle, Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # <- agregado

# (Opcional) Gráficos: si no existen, degradamos sin romper
try:
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics import renderPDF
    _HAS_GRAPHICS = True
except Exception:
    _HAS_GRAPHICS = False

from app.database import get_db
from app.models.proyecto import Proyecto
    # noqa
from app.models.run_item import RunItem
from app.models.resultado_brecha import ResultadoBrecha
from app.models.estado_arte import EstadoDelArte
from app.models.run import Run
from app.models.articulo import Articulo  # <-- agregado
from app.services import metrics

router = APIRouter(prefix="/export", tags=["export"])

# ----------------------------------------
# Utilidad común
# ----------------------------------------
def _proj_or_404(db: Session, proyecto_id: str) -> Proyecto:
    pr = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return pr

# ----------------------------------------
# Exportar brechas a CSV
# ----------------------------------------
@router.get("/proyectos/{proyecto_id}/brechas.csv")
def export_brechas_csv(proyecto_id: str, db: Session = Depends(get_db)):
    _proj_or_404(db, proyecto_id)

    q = (
        db.query(ResultadoBrecha, RunItem)
        .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
        .join(Run, Run.id == RunItem.run_id)
        .filter(Run.proyecto_id == proyecto_id)
        .order_by(ResultadoBrecha.created_at.asc())
    )
    rows = q.all()
    if not rows:
        raise HTTPException(status_code=404, detail="Sin brechas para exportar")

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "resultado_id",
            "proyecto_id",
            "articulo_id",
            "run_item_id",
            "tipo_brecha",
            "brecha",
            "oportunidad",
            "evidencia",
            "estado_validacion",
            "created_at",
            "rag_hits",
            "sim_promedio",
            "entropia",
            "val_score",
            "val_reason",
            "es_duplicada",
            "dup_de",
        ]
    )

    for rb, ri in rows:
        # Limpiar saltos de línea para que no rompan el CSV
        brecha = (rb.brecha or "").replace("\n", " ").replace("\r", " ")
        oportunidad = (rb.oportunidad or "").replace("\n", " ").replace("\r", " ")
        w.writerow(
            [
                rb.id,
                proyecto_id,
                ri.articulo_id,
                rb.run_item_id,
                rb.tipo_brecha,
                brecha,
                oportunidad,
                (rb.evidencia or ""),
                rb.estado_validacion,
                rb.created_at,
                getattr(rb, "rag_hits", ""),
                getattr(rb, "sim_promedio", ""),
                getattr(rb, "entropia", ""),
                getattr(rb, "val_score", ""),
                getattr(rb, "val_reason", ""),
                getattr(rb, "es_duplicida", ""),
                getattr(rb, "dup_de", ""),
            ]
        )

    buf.seek(0)
    filename = f"brechas_{proyecto_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ----------------------------------------
# Exportar estado del arte a Markdown
# ----------------------------------------
@router.get("/proyectos/{proyecto_id}/estado_arte.md")
def export_estado_arte_md(proyecto_id: str, db: Session = Depends(get_db)):
    _proj_or_404(db, proyecto_id)
    ea = (
        db.query(EstadoDelArte)
        .filter(EstadoDelArte.proyecto_id == proyecto_id)
        .order_by(EstadoDelArte.created_at.desc())
        .first()
    )
    if not ea:
        raise HTTPException(
            status_code=404, detail="No existe estado del arte generado"
        )

    header = (
        f"# Estado del Arte\n\n"
        f"Proyecto: {proyecto_id}\n\n"
        f"Versión: {ea.version}\nEstado: {ea.estado}\nFecha: {ea.created_at}\n\n---\n\n"
    )
    body = (ea.texto or "").strip()
    md = header + body + "\n"

    return PlainTextResponse(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="estado_arte_{proyecto_id}.md"'
        },
    )

# ----------------------------------------
# Helper: construir gráfico de barras (0..1) con ReportLab
# ----------------------------------------
def _chart_indicadores_0_1(promedios: dict, width=500, height=240):
    """
    Construye un Drawing con un VerticalBarChart para indicadores normalizados (0..1):
      - avg_sim_promedio
      - avg_val_score
      - avg_entropia_norm  (nota: menor es mejor)
      - avg_rouge1_rec     (ROUGE-1 recall, métrica prioritaria)
      - avg_lexical_density
    Si no hay gráficos disponibles, devuelve None.
    """
    if not _HAS_GRAPHICS or not promedios:
        return None

    def get_float(key: str) -> float:
        try:
            return float(promedios.get(key, 0.0) or 0.0)
        except Exception:
            return 0.0

    # Valores en bruto desde el diccionario de promedios
    sim = get_float("avg_sim_promedio")
    vsc = get_float("avg_val_score")
    ent = get_float("avg_entropia_norm")
    rouge_rec = get_float("avg_rouge1_rec")          # <-- recall
    lex = get_float("avg_lexical_density")

    # clamp 0..1
    clamp = lambda x: max(0.0, min(1.0, x))
    sim = clamp(sim)
    vsc = clamp(vsc)
    ent = clamp(ent)
    rouge_rec = clamp(rouge_rec)
    lex = clamp(lex)

    drawing = Drawing(width, height)

    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 30
    chart.height = height - 60
    chart.width = width - 80

    # Una sola serie con 5 barras
    chart.data = [[sim, vsc, ent, rouge_rec, lex]]

    chart.valueAxis.valueMin = 0.0
    chart.valueAxis.valueMax = 1.0
    chart.valueAxis.valueStep = 0.1
    chart.categoryAxis.categoryNames = [
        "Similitud",
        "Val. Score",
        "Entropía (norm)",
        "ROUGE-1 recall",
        "Densidad léxica",
    ]

    chart.barWidth = 20
    chart.groupSpacing = 10
    chart.barSpacing = 10

    # Color de la serie (opcional)
    chart.bars[0].fillColor = colors.lightblue

    drawing.add(chart)
    # Título chico dentro del drawing
    drawing.add(
        String(
            40,
            height - 18,
            "Indicadores (0–1) — en entropía normalizada, menor es mejor",
            fontName="Helvetica",
            fontSize=9,
        )
    )
    return drawing

# ----------------------------------------
# Exportar dashboard unificado a PDF (robusto ante faltantes)
# ----------------------------------------
@router.get("/proyectos/{proyecto_id}/dashboard.pdf")
def export_dashboard_pdf(proyecto_id: str, db: Session = Depends(get_db)):
    pr = _proj_or_404(db, proyecto_id)

    # Intentar calcular indicadores; si falla, devolver detalle explícito
    try:
        resumen = metrics.project_indicators(db, proyecto_id) or {}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error al calcular indicadores: {e!s}"
        )

    promedios = resumen.get("promedios", {}) or {}
    dimensiones = resumen.get("dimensiones", {}) or {}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    elements = []

    # Título
    elements.append(
        Paragraph("<b>Dashboard de Indicadores del Proyecto</b>", styles["Title"])
    )
    elements.append(Spacer(1, 12))

    # Datos generales del proyecto
    elements.append(
        Paragraph(f"Tema: {pr.tema_principal or '—'}", styles["Normal"])
    )
    elements.append(Paragraph(f"Objetivo: {pr.objetivo or '—'}", styles["Normal"]))
    elements.append(
        Paragraph(f"Metodología: {pr.metodologia_txt or '—'}", styles["Normal"])
    )
    elements.append(
        Paragraph(
            f"Artículos objetivo: {pr.n_articulos_objetivo or '—'}", styles["Normal"]
        )
    )
    elements.append(Spacer(1, 12))

    # --- Tabla de métricas principales (promedios) ---
    elements.append(Paragraph("<b>Métricas generales</b>", styles["Heading2"]))

    pretty_names = {
        "avg_sim_promedio": "Similitud promedio (brechas vs. contexto)",
        "avg_entropia": "Entropía promedio del texto (bits)",
        "avg_entropia_norm": "Entropía normalizada (0–1)",
        "avg_val_score": "Score de validación promedio",
        "pct_brechas_aceptadas": "% de brechas aceptadas",
        "avg_rouge1_prec": "ROUGE-1 precisión promedio",
        "avg_rouge1_rec": "ROUGE-1 recall promedio",
        "avg_rouge1_f1": "ROUGE-1 F1 (calidad de resúmenes)",
        "avg_lexical_density": "Densidad léxica promedio",
        "aceptadas": "Brechas aceptadas (n)",
        "rechazadas": "Brechas rechazadas (n)",
        "pendientes": "Brechas pendientes (n)",
        "total": "Total de brechas detectadas (n)",
    }

    ordered_keys = [
        "avg_sim_promedio",
        "avg_val_score",
        "avg_entropia",
        "avg_entropia_norm",
        "avg_rouge1_rec",       # <-- recall adelantado
        "avg_lexical_density",
        "pct_brechas_aceptadas",
        "avg_rouge1_f1",
        "avg_rouge1_prec",
        "aceptadas",
        "rechazadas",
        "pendientes",
        "total",
    ]

    data = [["Indicador", "Valor promedio"]]
    if promedios:
        for key in ordered_keys:
            if key not in promedios:
                continue
            label = pretty_names.get(key, key)
            v = promedios[key]
            if isinstance(v, (int, float)):
                data.append([label, f"{v:.3f}"])
            else:
                data.append([label, str(v)])

        # otros indicadores no incluidos en ordered_keys
        for k, v in promedios.items():
            if k in ordered_keys:
                continue
            label = pretty_names.get(k, k)
            if isinstance(v, (int, float)):
                data.append([label, f"{v:.3f}"])
            else:
                data.append([label, str(v)])
    else:
        data.append(["(sin datos)", "—"])

    t = Table(data, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(t)

    # Nota centrada en ROUGE-1 recall
    if "avg_rouge1_rec" in promedios:
        try:
            rouge_rec_val = float(promedios["avg_rouge1_rec"])
            elements.append(Spacer(1, 6))
            elements.append(
                Paragraph(
                    "Nota: ROUGE-1 recall mide qué porcentaje del contenido de referencia "
                    "es cubierto por los resúmenes generados. "
                    f"Valor promedio: {rouge_rec_val:.3f} (0–1).",
                    styles["Italic"],
                )
            )
        except Exception:
            pass

    elements.append(Spacer(1, 12))

    # --- Tabla por dimensión (porcentajes normalizados) ---
    elements.append(
        Paragraph("<b>Indicadores normalizados por dimensión</b>", styles["Heading2"])
    )
    data_dim = [["Dimensión", "Puntaje (%)"]]
    if dimensiones:
        for d, val in dimensiones.items():
            try:
                data_dim.append([d, f"{float(val):.1f}%"])
            except Exception:
                data_dim.append([d, str(val)])
    else:
        data_dim.append(["(sin datos)", "—"])
    td = Table(data_dim, hAlign="LEFT")
    td.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(td)
    elements.append(Spacer(1, 12))

    # --- Gráfico de barras real (0–1) para KPIs ---
    chart = _chart_indicadores_0_1(promedios)
    if chart is not None:
        elements.append(Paragraph("<b>Gráfico de barras (0–1)</b>", styles["Heading2"]))
        elements.append(chart)
        elements.append(
            Paragraph(
                "Nota: en entropía normalizada (0–1), valores menores indican mejor síntesis.",
                styles["Italic"],
            )
        )
        elements.append(Spacer(1, 12))
    else:
        # Si no hay módulo de gráficos, mantenemos la visualización textual
        elements.append(
            Paragraph("<b>Visualización textual (aproximada)</b>", styles["Heading2"])
        )
        if dimensiones:
            for d, val in dimensiones.items():
                try:
                    v = max(0.0, min(100.0, float(val)))  # clamp 0–100
                except Exception:
                    v = 0.0
                bar_len = int(v / 5)  # 0–20 bloques
                bar = "█" * bar_len + "░" * (20 - bar_len)
                elements.append(
                    Paragraph(f"{d}: {bar} {v:.1f}%", styles["Code"])
                )

    elements.append(Spacer(1, 24))
    elements.append(
        Paragraph(
            f"Generado el {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            styles["Normal"],
        )
    )

    # Construcción del PDF
    doc.build(elements)
    buf.seek(0)

    filename = f"dashboard_{proyecto_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ======================================================================
# MATRIZ DE BRECHAS (Artículo | DOI | Brecha | Oportunidad) JSON + PDF
# ======================================================================

def _matrix_rows(db: Session, proyecto_id: str):
    """
    Devuelve filas con (titulo, doi, brecha, oportunidad) del proyecto.
    Une ResultadoBrecha -> RunItem -> Run (filtro por proyecto) -> Articulo.
    """
    q = (
        db.query(ResultadoBrecha, RunItem, Articulo)
        .join(RunItem, RunItem.id == ResultadoBrecha.run_item_id)
        .join(Run, Run.id == RunItem.run_id)
        .join(Articulo, Articulo.id == RunItem.articulo_id)
        .filter(Run.proyecto_id == proyecto_id)
        .order_by(Articulo.titulo.asc(), ResultadoBrecha.created_at.asc())
    )
    rows = q.all()
    result = []
    for rb, ri, ar in rows:
        result.append(
            {
                "titulo": ar.titulo or "(sin título)",
                "doi": ar.doi or "—",
                "brecha": rb.brecha or "",
                "oportunidad": rb.oportunidad or "",
            }
        )
    return result

@router.get("/proyectos/{proyecto_id}/matriz.json")
def export_matriz_json(proyecto_id: str, db: Session = Depends(get_db)):
    _proj_or_404(db, proyecto_id)
    data = _matrix_rows(db, proyecto_id)
    if not data:
        raise HTTPException(
            status_code=404, detail="No hay brechas para construir la matriz"
        )
    return JSONResponse(content=data)

@router.get("/proyectos/{proyecto_id}/matriz.pdf")
def export_matriz_pdf(proyecto_id: str, db: Session = Depends(get_db)):
    pr = _proj_or_404(db, proyecto_id)
    rows = _matrix_rows(db, proyecto_id)
    if not rows:
        raise HTTPException(
            status_code=404, detail="No hay brechas para construir la matriz"
        )

    # PDF en A4 apaisado para mayor anchura
    buf = io.BytesIO()
    LEFT = RIGHT = TOP = BOTTOM = 1.0 * cm
    page_w, page_h = landscape(A4)
    inner_w = page_w - (LEFT + RIGHT)

    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        rightMargin=RIGHT,
        leftMargin=LEFT,
        topMargin=TOP,
        bottomMargin=BOTTOM,
    )
    styles = getSampleStyleSheet()

    # Estilos compactos con wrap (muy importante para que no se corte el texto)
    pstyle = ParagraphStyle(
        "Cell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=11,
        wordWrap="CJK",  # fuerza quiebre de palabras largas
        spaceBefore=0,
        spaceAfter=0,
    )
    header_style = ParagraphStyle(
        "Header",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12,
        wordWrap="CJK",
    )

    elements = []
    elements.append(Paragraph("<b>Matriz de Brechas</b>", styles["Title"]))
    elements.append(Spacer(1, 6))
    elements.append(
        Paragraph(f"Tema: {pr.tema_principal or '—'}", styles["Normal"])
    )
    elements.append(
        Paragraph(f"Proyecto: {proyecto_id}", styles["Normal"])
    )
    elements.append(Spacer(1, 10))

    # Encabezado
    data = [
        [
            Paragraph("Artículo", header_style),
            Paragraph("DOI", header_style),
            Paragraph("Brecha", header_style),
            Paragraph("Oportunidad de innovación", header_style),
        ]
    ]

    # Filas con Paragraph (wrap)
    for r in rows:
        data.append(
            [
                Paragraph(r["titulo"], pstyle),
                Paragraph(r["doi"], pstyle),
                Paragraph(r["brecha"], pstyle),
                Paragraph(r["oportunidad"], pstyle),
            ]
        )

    # Distribución proporcional (26% | 10% | 32% | 32%) del ancho útil
    col_widths = [
        inner_w * 0.26,  # Artículo
        inner_w * 0.10,  # DOI
        inner_w * 0.32,  # Brecha
        inner_w * 0.32,  # Oportunidad
    ]

    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    elements.append(table)
    elements.append(Spacer(1, 10))
    elements.append(
        Paragraph(
            f"Generado el {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            styles["Normal"],
        )
    )

    doc.build(elements)
    buf.seek(0)

    filename = f"matriz_{proyecto_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
