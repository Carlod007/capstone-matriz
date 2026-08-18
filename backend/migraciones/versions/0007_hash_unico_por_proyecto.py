"""El hash del archivo es unico por proyecto, no en todo el sistema

`archivos.py` deduplica los PDF por contenido acotando la busqueda al
proyecto, y lo hace a proposito: la version anterior era global, de modo que
subir un articulo que otra persona ya habia subido devolvia *su* articulo_id.
Con varias cuentas eso es una fuga.

Pero el esquema se quedo con `UNIQUE (hash_sha256)` sobre toda la tabla, y las
dos reglas no dicen lo mismo. La consulta previa no encontraba nada —porque
filtra por proyecto— y el INSERT chocaba despues contra el indice global:

    Duplicate entry '...' for key 'archivo.uq_archivo_hash'

El usuario veia un 500 sin explicacion al subir a un proyecto nuevo un PDF que
ya tenia en otro. Y entre cuentas distintas el fallo delataba que alguien mas
habia subido ese mismo articulo, que es justo lo que la correccion del codigo
pretendia evitar.

Esta revision alinea el esquema con la regla que el codigo ya aplica.

Es una restriccion estrictamente mas debil que la anterior: si los hashes eran
unicos en toda la tabla, con mas razon lo son dentro de cada proyecto. No hay
datos que puedan violarla, asi que no hace falta limpiar nada antes.

La vuelta atras si puede fallar, y es correcto que falle: restaurar la
unicidad global sobre datos donde ya conviven dos proyectos con el mismo PDF
exigiria borrar uno de los dos, y una migracion no debe decidir cual.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-18

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # El orden importa: primero el indice nuevo y despues se retira el viejo.
    # Al reves quedaria una ventana, por breve que sea, en la que dos peticiones
    # simultaneas podrian insertar el mismo PDF dos veces en el mismo proyecto.
    op.create_unique_constraint(
        "uq_archivo_proyecto_hash", "archivo", ["proyecto_id", "hash_sha256"]
    )
    op.drop_constraint("uq_archivo_hash", "archivo", type_="unique")


def downgrade() -> None:
    # Puede fallar con un duplicado, y debe hacerlo: ver la nota de cabecera.
    op.create_unique_constraint("uq_archivo_hash", "archivo", ["hash_sha256"])
    op.drop_constraint("uq_archivo_proyecto_hash", "archivo", type_="unique")
