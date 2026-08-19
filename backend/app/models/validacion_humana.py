"""El juicio de una persona sobre una brecha.

Tabla aparte y no una columna en `resultado_brecha`, por dos razones.

La primera es que ahi ya existe `estado_validacion`, de la capa de validacion
automatica que esta desactivada a proposito hasta poder calibrarla. Guardar el
juicio humano en la misma columna dejaria dos verdades distintas conviviendo
sin poder distinguirlas, que es exactamente el fallo que aparecio dos veces en
este proyecto: la unicidad del hash y el indicador de estado del arte.

La segunda es que N6 pide, cuando se pueda, mas de un anotador. Con una fila
por (brecha, persona) el acuerdo entre jueces se calcula sin migrar nada; con
una columna en la brecha habria que rehacer el esquema el dia que aparezca el
segundo.
"""

from sqlalchemy import (
    CHAR, DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.proyecto import Base

CORRECTA = "correcta"
PARCIAL = "parcial"
INCORRECTA = "incorrecta"
VEREDICTOS = (CORRECTA, PARCIAL, INCORRECTA)


class ValidacionHumana(Base):
    __tablename__ = "validacion_humana"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    brecha_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("resultado_brecha.id", ondelete="CASCADE",
                   onupdate="RESTRICT"),
        nullable=False,
    )
    # Quien juzga. Sin esto la anotacion no es auditable: una defensa academica
    # pregunta quien decidio, no solo que se decidio.
    usuario_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )

    # Tres valores y no dos. Un si o no obliga a llamar «incorrecta» a una
    # brecha que acierta en el problema y se equivoca en un matiz, y esa
    # distincion es la mitad de lo que se quiere medir.
    veredicto: Mapped[str] = mapped_column(
        Enum(*VEREDICTOS, name="veredicto_humano"), nullable=False)

    # Por que. En una brecha marcada como incorrecta es el dato que vale: sin
    # el, la anotacion dice que algo fallo pero no que, y no sirve para
    # corregir el sistema ni para defender la evaluacion.
    justificacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    creado_en: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=True)
    actualizado_en: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(), nullable=True)

    __table_args__ = (
        # Un veredicto vigente por persona y brecha. Cambiar de opinion
        # sustituye el propio, no anade uno nuevo; el de otra persona no se
        # toca, que es lo que permitira medir el acuerdo entre jueces.
        UniqueConstraint("brecha_id", "usuario_id",
                         name="uq_validacion_brecha_usuario"),
        Index("idx_validacion_brecha", "brecha_id"),
        Index("idx_validacion_usuario", "usuario_id"),
    )
