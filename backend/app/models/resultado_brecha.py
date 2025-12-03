from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, Enum, DateTime, func, DECIMAL, JSON, Boolean
from app.models.proyecto import Base

class ResultadoBrecha(Base):
    __tablename__ = "resultado_brecha"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_item_id: Mapped[str] = mapped_column(String(36))
    tipo_brecha: Mapped[str] = mapped_column(
        Enum("metodológica", "temática", "teórica", "tecnológica", "otra"),
        nullable=False
    )
    brecha: Mapped[str] = mapped_column(Text, nullable=False)
    oportunidad: Mapped[str] = mapped_column(Text, nullable=False)
    evidencia: Mapped[str] = mapped_column(Text)
    estado_validacion: Mapped[str] = mapped_column(
        Enum("pendiente", "aceptada", "rechazada"), default="pendiente"
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.current_timestamp())

    # --- nuevos campos para validación automática ---
    rag_hits: Mapped[dict | None] = mapped_column(JSON, nullable=True)              # fragmentos RAG relevantes
    sim_promedio: Mapped[float] = mapped_column(DECIMAL(5, 4), default=0.0000)      # similitud media con RAG
    entropia: Mapped[float] = mapped_column(DECIMAL(6, 3), default=0.000)           # entropía Shannon
    val_score: Mapped[float] = mapped_column(DECIMAL(5, 4), default=0.0000)         # puntuación final de validación
    val_reason: Mapped[str | None] = mapped_column(String(300))                     # motivo del estado
    es_duplicada: Mapped[bool] = mapped_column(Boolean, default=False)              # flag si está repetida
    dup_de: Mapped[str | None] = mapped_column(String(36))                          # referencia al duplicado original
