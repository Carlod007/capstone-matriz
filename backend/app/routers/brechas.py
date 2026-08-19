from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencias import articulo_propio
from app.models.articulo import Articulo
from app.models.metrica import Metrica
from app.models.resultado_brecha import ResultadoBrecha
from app.models.run_item import RunItem
from app.services.metricas.catalogo import ficha

router = APIRouter(prefix="/articulos", tags=["brechas"])


@router.get("/{articulo_id}/brechas")
def listar_brechas(
    articulo: Articulo = Depends(articulo_propio),
    db: Session = Depends(get_db),
):
    """Brechas de un artículo con sus métricas y su respaldo documental.

    Ya no se devuelven `sim_promedio`, `entropia` ni `val_score`: eran las
    métricas retiradas y llegaban siempre en cero, con lo que la interfaz
    parecía averiada. En su lugar van las métricas vigentes, cada una con su
    nombre y su interpretación, y los fragmentos del artículo en los que se
    apoyó el análisis.
    """
    run_items = db.query(RunItem.id).filter(RunItem.articulo_id == articulo.id).subquery()
    # El mismo desempate que `export._brechas_vigentes`: fecha y, a igualdad de
    # fecha, identificador. La pantalla destaca la primera de esta lista como
    # la vigente, así que ordenar solo por fecha bastaba para que en un empate
    # —posible: el trabajador guarda varias seguidas— la interfaz señalara una
    # brecha y la matriz exportada otra, sin que nadie lo notara hasta
    # compararlas.
    rows = (
        db.query(ResultadoBrecha)
        .filter(ResultadoBrecha.run_item_id.in_(run_items.select()))
        .order_by(ResultadoBrecha.created_at.desc(), ResultadoBrecha.id.desc())
        .all()
    )
    if not rows:
        return []

    ids = [r.id for r in rows]
    por_brecha: dict[str, list] = {}
    # La verificacion de fidelidad se guarda con su detalle completo: es lo
    # que permite mostrar afirmacion por afirmacion cual se sostiene y en que
    # fragmento, en lugar de un unico numero sin explicacion.
    verificaciones: dict[str, dict] = {}
    # Ordenado por fecha y quedandose con la ultima: una misma brecha puede
    # tener varias mediciones del mismo codigo si se verifico mas de una vez.
    # Sin este orden se elegia una arbitrariamente, de modo que una brecha
    # verificada de verdad podia mostrarse con el resultado de un intento
    # anterior y aparecer como "sin verificar".
    por_codigo: dict[tuple[str, str], Metrica] = {}
    for m in (db.query(Metrica)
              .filter(Metrica.referencia_id.in_(ids))
              .order_by(Metrica.creado_en.asc()).all()):
        por_codigo[(m.referencia_id, m.codigo)] = m

    for m in por_codigo.values():
        if m.codigo == "N2.verificada":
            verificaciones[m.referencia_id] = m.detalle or {}
            continue
        f = ficha(m.codigo)
        por_brecha.setdefault(m.referencia_id, []).append({
            "codigo": m.codigo,
            "nombre": f.nombre if f else m.codigo,
            "valor": m.valor,
            "mejor": f.mejor if f else "neutro",
            "rango": f.rango if f else "",
            "descripcion": f.descripcion if f else "",
            "interpretacion": f.interpretacion if f else "",
            "detalle": m.detalle,
        })

    salida = []
    for r in rows:
        metricas = sorted(por_brecha.get(r.id, []), key=lambda x: x["codigo"])
        # rag_hits guarda los fragmentos que sustentaron el analisis: es lo
        # que permite al investigador comprobar de donde sale cada afirmacion.
        respaldo = r.rag_hits if isinstance(r.rag_hits, list) else []
        salida.append({
            "id": r.id,
            "tipo_brecha": r.tipo_brecha,
            "brecha": r.brecha,
            "oportunidad": r.oportunidad,
            "estado_validacion": r.estado_validacion,
            "val_reason": r.val_reason,
            "validacion_calibrada": False,
            "metricas": metricas,
            "verificacion": verificaciones.get(r.id),
            "respaldo": respaldo,
            "secciones_consultadas": sorted({h.get("seccion") for h in respaldo
                                             if isinstance(h, dict) and h.get("seccion")}),
            "creado_en": r.created_at,
        })
    return salida
