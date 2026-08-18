from pydantic import BaseModel

class ArticuloOut(BaseModel):
    id: str
    titulo: str | None
    doi: str | None
    # Si hay resultados guardados de este artículo: brechas o resumen.
    #
    # Lo consume la confirmación de borrado, que antes enumeraba «análisis,
    # brechas, resúmenes, embeddings y métricas» para cualquier artículo. En un
    # proyecto recién cargado eso no existe todavía, así que la advertencia
    # asustaba con la pérdida de algo que no había. Sin este dato la pantalla
    # no tiene forma de distinguir los dos casos.
    tiene_analisis: bool = False

    class Config:
        from_attributes = True
