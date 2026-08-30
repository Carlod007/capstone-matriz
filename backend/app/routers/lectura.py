# app/routers/lectura.py
"""
Servir el PDF original de un articulo.

Para juzgar si una brecha es correcta hay que leer el articulo, y hasta ahora
el PDF entraba en el sistema y no volvia a salir: quedaba en el disco del
servidor sin ninguna forma de abrirlo. Quien anotaba tenia que buscar su copia
en el ordenador, con el riesgo de revisar una version distinta de la que el
sistema analizo.

Se sirve el archivo tal cual, en linea, para que el navegador lo muestre con su
propio visor. No hace falta empotrar una libreria de PDF: todos los navegadores
actuales traen una, y una dependencia mas es una dependencia mas que mantener.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencias import articulo_propio
from app.models.archivo import Archivo
from app.models.articulo import Articulo
from app.services import almacenamiento

router = APIRouter(prefix="/articulos", tags=["lectura"])


@router.get("/{articulo_id}/pdf")
def leer_pdf(articulo: Articulo = Depends(articulo_propio),
             db: Session = Depends(get_db)):
    """Devuelve el PDF que se subio para este articulo.

    La dependencia comprueba el dueno del proyecto: sin ella este endpoint
    serviria cualquier PDF del servidor a quien conociera un identificador.
    """
    arc = (db.query(Archivo)
             .filter(Archivo.articulo_id == articulo.id)
             .order_by(Archivo.creado_en.desc())
             .first())
    if not arc:
        raise HTTPException(status_code=404,
                            detail="Este artículo no tiene PDF guardado.")

    try:
        ruta = almacenamiento.ruta_local(arc.ruta)
    except almacenamiento.ClaveInvalida:
        raise HTTPException(
            status_code=404,
            detail="La referencia del archivo no es válida.") from None

    if not os.path.exists(ruta):
        # La fila existe y el archivo no: pasa si se restauro la base sin los
        # PDF. Decirlo asi evita que parezca un problema de permisos.
        raise HTTPException(
            status_code=404,
            detail="El PDF ya no está en el servidor, aunque el artículo sigue "
                   "registrado. Habría que volver a subirlo.")

    # `inline` y no `attachment`: se quiere leer, no descargar. El nombre
    # original se conserva por si el navegador acaba guardandolo.
    return FileResponse(
        ruta,
        media_type="application/pdf",
        headers={"Content-Disposition":
                 'inline; filename="%s"' % (arc.nombre or "articulo.pdf")},
    )
