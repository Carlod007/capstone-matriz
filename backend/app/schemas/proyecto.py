from pydantic import BaseModel, Field
from typing import Optional

class ProyectoCreate(BaseModel):
    tema_principal: str = Field(min_length=3, max_length=200)
    objetivo: str = Field(min_length=10, max_length=4000)
    metodologia_txt: Optional[str] = None
    sector_txt: Optional[str] = None
    n_articulos_objetivo: int

class ProyectoOut(BaseModel):
    id: str
    tema_principal: str
    n_articulos_objetivo: int

    # OJO: esta columna no la mantiene nadie. Se escribe `False` al crear el
    # proyecto y no vuelve a tocarse ni cuando la síntesis se genera de verdad,
    # así que es siempre falsa. Se conserva porque está en el esquema desde el
    # principio, pero no sirve para saber si hay estado del arte: para eso está
    # `tiene_estado_arte`, que se deriva de la tabla `estado_arte`.
    estado_arte_generado: bool

    # Si existe alguna versión del estado del arte, mirando la tabla en vez de
    # un indicador que hay que acordarse de actualizar. Dos fuentes para el
    # mismo hecho es exactamente lo que dejó la columna de arriba mintiendo.
    tiene_estado_arte: bool = False

    # Resumen para la tarjeta del listado. Se calcula en el servidor con una
    # consulta agrupada por proyecto; antes la pantalla pedía los artículos y
    # el estado del arte de cada proyecto por separado, y las brechas no las
    # pedía en absoluto: la tarjeta mostraba un guion fijo donde deberia ir el
    # numero, que se lee como «no se detecto ninguna».
    #
    # Valores por defecto porque `crear_proyecto` y `obtener_proyecto`
    # devuelven el modelo tal cual, sin este recuento.
    n_articulos: int = 0
    # Articulos con al menos una brecha. No son las brechas en bruto: cada
    # analisis genera una nueva y se conservan las anteriores, asi que la suma
    # directa creceria al reanalizar aunque el proyecto siguiera teniendo los
    # mismos articulos.
    #
    # Tampoco es el numero de filas de la matriz exportada, que hoy devuelve
    # una fila por brecha historica. Son dos preguntas distintas y no deben
    # confundirse: cuantos articulos han dado brecha, y cuantos analisis se
    # han acumulado.
    n_brechas: int = 0

    class Config:
        from_attributes = True
