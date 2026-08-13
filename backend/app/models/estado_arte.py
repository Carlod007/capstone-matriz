from sqlalchemy import (
    CHAR, BigInteger, Column, DateTime, Enum, ForeignKey, Index, Integer,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship

from app.models.proyecto import Base


class EstadoDelArte(Base):
    __tablename__ = "estado_arte"

    id = Column(CHAR(36), primary_key=True)
    proyecto_id = Column(
        CHAR(36),
        ForeignKey("proyecto.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    # NOT NULL, igual que en la base: un estado del arte sin ejecución de la
    # que proceda no es rastreable. El modelo lo declaraba opcional y no lo es.
    run_id = Column(
        CHAR(36),
        ForeignKey("run.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    texto = Column(LONGTEXT, nullable=False)
    estado = Column(Enum("generado", "validado", name="estado_arte_estado"),
                    default="generado")
    tokens_in = Column(BigInteger, default=0)
    tokens_out = Column(BigInteger, default=0)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp(),
                        onupdate=func.current_timestamp())

    proyecto = relationship("Proyecto", backref="estados_arte")
    run = relationship("Run", backref="estado_arte")

    __table_args__ = (
        UniqueConstraint("proyecto_id", "version", name="uq_estado_arte_version"),
        Index("idx_estado_arte_proy", "proyecto_id"),
    )
