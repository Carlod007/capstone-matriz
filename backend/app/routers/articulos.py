from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencias import proyecto_propio
from app.models.archivo import Archivo
from app.models.articulo import Articulo
from app.models.metrica import Metrica
from app.models.proyecto import Proyecto
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run_item import EstadoRunItem, RunItem
from app.schemas.articulo import ArticuloOut
from app.services import almacenamiento

router = APIRouter(prefix="/proyectos", tags=["articulos"])

# Mientras un artículo esté en la cola o en manos de un trabajador, borrarlo
# dejaría a ese trabajador escribiendo resultados de algo que ya no existe.
ESTADOS_EN_MARCHA = (EstadoRunItem.pendiente, EstadoRunItem.en_proceso)


@router.get("/{proyecto_id}/articulos", response_model=list[ArticuloOut])
def listar_articulos(
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    # La dependencia ya resolvió el proyecto y comprobó el dueño; si no fuera
    # suyo, la petición no habría llegado hasta aquí.
    return (db.query(Articulo)
              .filter(Articulo.proyecto_id == proyecto.id)
              .order_by(Articulo.creado_en.asc())
              .all())


@router.delete("/{proyecto_id}/articulos/{articulo_id}")
def borrar_articulo(
    articulo_id: str,
    proyecto: Proyecto = Depends(proyecto_propio),
    db: Session = Depends(get_db),
):
    """Retira un artículo del proyecto y todo lo que colgaba de él.

    El filtro por proyecto no es redundante con la dependencia: sin él bastaría
    con conocer el identificador de un artículo ajeno para borrarlo desde un
    proyecto propio.
    """
    art = (db.query(Articulo)
             .filter(Articulo.id == articulo_id,
                     Articulo.proyecto_id == proyecto.id)
             .first())
    if not art:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    en_marcha = (db.query(RunItem)
                   .filter(RunItem.articulo_id == articulo_id,
                           RunItem.estado.in_(ESTADOS_EN_MARCHA))
                   .first())
    if en_marcha:
        raise HTTPException(
            status_code=409,
            detail="El artículo está en un análisis en curso. Espera a que "
                   "termine para poder quitarlo.")

    # El PDF del disco se borra primero y por separado. Las filas se van solas
    # en cascada, pero el archivo no: quedaría ocupando espacio sin que ninguna
    # fila lo mencione, y entonces no hay forma de saber que sobra.
    archivos = (db.query(Archivo)
                  .filter(Archivo.articulo_id == articulo_id,
                          Archivo.proyecto_id == proyecto.id)
                  .all())
    for arc in archivos:
        try:
            almacenamiento.borrar(arc.ruta)
        except Exception:
            # Un PDF que no se puede borrar no justifica dejar el artículo a
            # medio quitar: la base es la que manda y el archivo huérfano es
            # un problema de espacio, no de coherencia.
            pass
        db.delete(arc)

    # `metrica` referencia por ámbito e identificador, sin clave foránea, así
    # que la cascada no la alcanza. Se limpian las del artículo y las de sus
    # brechas, que de otro modo seguirían contando en los promedios del
    # proyecto como si el artículo siguiera ahí.
    #
    # Las de ámbito «brecha» se guardan contra el id de la brecha, no el del
    # run_item, así que hay que resolverlas pasando por ella.
    ids_item = db.query(RunItem.id).filter(
        RunItem.articulo_id == articulo_id).subquery()
    ids_brecha = [r[0] for r in db.query(ResultadoBrecha.id)
                                  .filter(ResultadoBrecha.run_item_id.in_(
                                      db.query(ids_item.c.id)))
                                  .all()]
    (db.query(Metrica)
       .filter(Metrica.proyecto_id == proyecto.id,
               Metrica.referencia_id.in_([articulo_id] + ids_brecha))
       .delete(synchronize_session=False))

    # El resto —run_item, brechas, resúmenes, embeddings, metadatos— cae por
    # las claves foráneas en cascada declaradas en los modelos.
    db.delete(art)
    db.commit()

    return {"articulo_id": articulo_id, "borrado": True}
