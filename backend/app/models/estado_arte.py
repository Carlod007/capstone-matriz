from app.models.proyecto import Base
from sqlalchemy import Column, String, Text, Enum, BigInteger, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

class EstadoDelArte(Base):
    __tablename__ = "estado_arte"

    id = Column(String(36), primary_key=True)
    proyecto_id = Column(String(36), ForeignKey("proyecto.id", ondelete="CASCADE", onupdate="RESTRICT"), nullable=False)
    run_id = Column(String(36), ForeignKey("run.id", ondelete="RESTRICT", onupdate="RESTRICT"), nullable=True)
    version = Column(Integer, nullable=False)
    texto = Column(Text, nullable=False)
    estado = Column(Enum("generado", "validado", name="estado_arte_estado"), default="generado")
    tokens_in = Column(BigInteger, default=0)
    tokens_out = Column(BigInteger, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    proyecto = relationship("Proyecto", backref="estados_arte")
    run = relationship("Run", backref="estado_arte")
