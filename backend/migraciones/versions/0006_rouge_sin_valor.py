"""Los ROUGE no aplicables dejan de valer cero

Cuando el resumen se genera en español y el abstract del artículo está en
inglés, ROUGE no aplica: mide palabras compartidas, así que daría un valor
cercano a cero por fiel que fuera el resumen. La capa ya detectaba el caso,
pero los campos se quedaban en su 0.0 por defecto y se guardaban así. La
pantalla mostraba «0.000», que se lee como «el resumen no se parece en nada al
abstract» cuando lo que ocurre es que la métrica no mide nada aquí.

El cálculo ya está corregido, pero las mediciones anteriores siguen con el
cero guardado. Esta revisión las pasa a «sin valor». Corre una sola vez: no
vuelve a tocar nada, ni con datos nuevos ni con otras cuentas.

Se actualizan únicamente las brechas cuyas CINCO variantes de ROUGE valen
exactamente cero. Ese patrón solo aparece cuando los campos quedaron en su
valor por defecto: una medición real entre textos del mismo idioma daría cinco
cifras distintas, y acertar cinco ceros exactos es prácticamente imposible.
Así una brecha con un ROUGE legítimamente bajo no se toca.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CODIGOS = ("N4.1a", "N4.1b", "N4.1c", "N4.1d", "N4.1e")

MOTIVO = (
    "ROUGE no era aplicable: mide palabras compartidas y el resumen y el "
    "abstract estaban en idiomas distintos. El cero que había guardado no era "
    "una medición, sino el valor por defecto del campo."
)


def upgrade() -> None:
    cn = op.get_bind()

    # Brechas cuyas cinco variantes valen cero exacto.
    candidatas = [r[0] for r in cn.execute(sa.text("""
        SELECT referencia_id
        FROM metrica
        WHERE codigo IN :codigos AND valor = 0
        GROUP BY referencia_id
        HAVING COUNT(DISTINCT codigo) = 5
    """).bindparams(sa.bindparam("codigos", value=CODIGOS, expanding=True)))]

    if not candidatas:
        return

    # Se conserva `referencia_valida`, que N4.1a guarda en su detalle: dice si
    # se encontró el abstract del artículo, y eso sigue siendo cierto.
    cn.execute(sa.text("""
        UPDATE metrica
        SET valor = NULL,
            detalle = JSON_SET(
                COALESCE(detalle, JSON_OBJECT()),
                '$.aplicable', CAST('false' AS JSON),
                '$.motivo', :motivo
            )
        WHERE codigo IN :codigos
          AND valor = 0
          AND referencia_id IN :refs
    """).bindparams(
        sa.bindparam("codigos", value=CODIGOS, expanding=True),
        sa.bindparam("refs", value=candidatas, expanding=True),
        sa.bindparam("motivo", value=MOTIVO),
    ))


def downgrade() -> None:
    """Devuelve el cero a las que esta revisión dejó sin valor.

    No restaura el estado exacto anterior —el cero original y este son
    indistinguibles—, pero eso es precisamente lo que hace la vuelta atrás
    segura: el cero no era un dato, era la ausencia de uno.
    """
    cn = op.get_bind()
    cn.execute(sa.text("""
        UPDATE metrica
        SET valor = 0,
            detalle = JSON_REMOVE(detalle, '$.aplicable', '$.motivo')
        WHERE codigo IN :codigos
          AND valor IS NULL
          AND JSON_EXTRACT(detalle, '$.aplicable') = CAST('false' AS JSON)
    """).bindparams(sa.bindparam("codigos", value=CODIGOS, expanding=True)))
