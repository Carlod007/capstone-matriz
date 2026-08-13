from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import (
    CHAR, Boolean, DateTime, Enum, ForeignKey, Index, String, func,
)
from sqlalchemy.dialects.mysql import DECIMAL as MySQLDECIMAL
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.dialects.mysql import LONGTEXT
from app.models.proyecto import Base


class ResultadoBrecha(Base):
    __tablename__ = "resultado_brecha"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    run_item_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("run_item.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    tipo_brecha: Mapped[str] = mapped_column(
        Enum("metodológica", "temática", "teórica", "tecnológica", "otra"),
        nullable=False,
    )
    brecha: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    oportunidad: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    evidencia: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    estado_validacion: Mapped[str] = mapped_column(
        Enum("pendiente", "aceptada", "rechazada"), default="pendiente", nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True)

    # Fragmentos que sustentaron el analisis: base de la trazabilidad.
    rag_hits: Mapped[dict | None] = mapped_column(MySQLJSON, nullable=True)

    # --- columnas de la capa de metricas retirada ---
    # Se conservan porque contienen datos historicos de analisis anteriores.
    # El pipeline ya no las escribe: entropia y val_score eran cuasi-constantes
    # y sus umbrales nunca llegaban a activarse. Sus sustitutas viven en la
    # tabla metrica.
    sim_promedio: Mapped[float] = mapped_column(MySQLDECIMAL(5, 4), default=0.0, nullable=True)
    entropia: Mapped[float] = mapped_column(MySQLDECIMAL(6, 3), default=0.0, nullable=True)
    val_score: Mapped[float] = mapped_column(MySQLDECIMAL(5, 4), default=0.0, nullable=True)
    val_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    es_duplicada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    dup_de: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)

    __table_args__ = (
        Index("idx_brecha_run_item", "run_item_id"),
        Index("idx_brecha_tipo", "tipo_brecha"),
        Index("idx_brecha_estado", "estado_validacion"),
        Index("idx_brecha_val", "estado_validacion", "val_score"),
    )
