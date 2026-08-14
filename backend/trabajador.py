"""
Proceso que vacia la cola de analisis.

Se ejecuta aparte del servidor web:

    python trabajador.py

Existe porque el analisis no cabe en una peticion HTTP. Con cinco articulos y
el limitador en cuatro generaciones por minuto son varios minutos; con diez,
el doble. Cualquier proxy corta a los treinta o sesenta segundos, asi que en
un servidor el analisis no fallaria a veces: fallaria siempre, y ademas
gastando cuota en un trabajo cuyo resultado nadie recibe.

Puede haber varios trabajadores a la vez. No se reparten el trabajo entre
ellos ni hablan entre si: cada uno pide a la base el siguiente articulo libre
con SELECT ... FOR UPDATE SKIP LOCKED, que es justo la operacion que evita
que dos cojan el mismo.

Parar con Ctrl+C. El articulo en curso se devuelve a la cola antes de salir,
de modo que no queda bloqueado esperando a que venza el plazo de abandono.
"""

import logging
import os
import signal
import sys
import time

RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

# Sin trabajo, cuanto esperar antes de volver a mirar. Cinco segundos es
# imperceptible para quien acaba de pulsar "analizar" y no castiga a la base.
ESPERA = 5.0

_parar = False


def _pedir_parada(_sig, _frame):
    """Ctrl+C no corta a mitad de un articulo.

    Interrumpir el analisis en marcha significaria perder la generacion ya
    pagada a la API. Se termina el articulo en curso y se sale despues.
    """
    global _parar
    if _parar:
        log.warning("Segunda interrupcion: saliendo de inmediato.")
        sys.exit(1)
    _parar = True
    log.info("Parada pedida. Se termina el articulo en curso y se sale.")


def _configurar_registro() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("trabajador")


log = _configurar_registro()


def _procesar_uno(db) -> bool:
    """Toma un articulo y lo analiza. Devuelve si habia alguno."""
    from app.models.run import Run
    from app.models.run_item import EstadoRunItem
    from app.routers.runs import FalloDefinitivo, procesar_item
    from app.services import cola
    from app.services.limitador import CuotaDiariaAgotada

    item = cola.tomar_pendiente(db)
    if item is None:
        return False

    run = db.query(Run).filter(Run.id == item.run_id).first()
    if run is None:
        # La ejecucion se borro mientras tanto; el articulo ya no lleva a
        # ninguna parte.
        item.estado = EstadoRunItem.fallido
        item.error_msg = "La ejecucion a la que pertenecia ya no existe."
        db.commit()
        return True

    cola.marcar_en_progreso(db, run)
    log.info("Analizando el articulo %s (ejecucion %s, intento %d)",
             item.articulo_id, run.id[:8], item.intentos)

    inicio = time.monotonic()
    try:
        procesar_item(db, run, item)
        log.info("  hecho en %.1f s", time.monotonic() - inicio)

    except FalloDefinitivo as e:
        # Reintentar no cambiaria nada: un PDF sin texto seguira sin texto.
        db.rollback()
        item.estado = EstadoRunItem.fallido
        item.error_msg = str(e)[:2000]
        db.commit()
        log.error("  descartado: %s", e)

    except CuotaDiariaAgotada as e:
        # No es culpa del articulo y no se arregla insistiendo. Se devuelve a
        # la cola sin gastarle un intento y se para: seguir solo produciria
        # una fila de fallos identicos hasta medianoche.
        db.rollback()
        item.intentos = max(0, (item.intentos or 0) - 1)
        item.estado = EstadoRunItem.pendiente
        item.tomado_en = None
        run.error_msg = str(e)[:2000]
        db.commit()
        log.error("Cuota diaria agotada. El trabajo queda en la cola: %s", e)
        raise

    except Exception as e:  # noqa: BLE001
        # Todo lo demas se trata como pasajero. Si no lo era, los intentos se
        # agotan y `devolver` lo marca como fallido con el ultimo motivo.
        db.rollback()
        cola.devolver(db, item, str(e))

    return True


def _cerrar_terminadas(db) -> None:
    """Cierra las ejecuciones cuyos articulos estan todos resueltos.

    Va aparte y no dentro del trabajador que acaba el ultimo articulo: si ese
    proceso muriera justo despues de guardarlo, la ejecucion se quedaria en
    progreso para siempre.
    """
    from app.routers.estado_arte import generar_estado_arte
    from app.routers.runs import cerrar_run
    from app.services import cola

    for run in cola.runs_por_cerrar(db):
        cerrar_run(db, run)
        log.info("Ejecucion %s completada (%d de %d articulos)",
                 run.id[:8], run.n_items_ok, run.n_items_total)

        if run.genera_estado_arte:
            try:
                from app.models.proyecto import Proyecto

                proyecto = (db.query(Proyecto)
                              .filter(Proyecto.id == run.proyecto_id).first())
                generar_estado_arte(proyecto, db)
                log.info("  estado del arte generado")
            except Exception as e:  # noqa: BLE001
                # Que falle la sintesis no invalida el analisis ya hecho: las
                # brechas estan guardadas y se puede pedir de nuevo.
                db.rollback()
                run.error_msg = ("El analisis termino, pero no se pudo generar "
                                 "el estado del arte: %s" % e)[:2000]
                db.commit()
                log.error("  no se pudo generar el estado del arte: %s", e)


def main() -> int:
    from app.config import revisar
    from app.database import SessionLocal
    from app.services import cola
    from app.services.limitador import CuotaDiariaAgotada

    revisar()
    signal.signal(signal.SIGINT, _pedir_parada)
    signal.signal(signal.SIGTERM, _pedir_parada)

    modo = os.getenv("GEMINI_MODE", "mock")
    log.info("Trabajador en marcha (modo %s). Ctrl+C para parar.", modo)

    ocioso = False
    while not _parar:
        db = SessionLocal()
        try:
            hubo = _procesar_uno(db)
            _cerrar_terminadas(db)
        except CuotaDiariaAgotada:
            db.close()
            log.info("Se espera a que la cuota se renueve.")
            for _ in range(60):
                if _parar:
                    break
                time.sleep(ESPERA)
            continue
        except Exception as e:  # noqa: BLE001
            # Un fallo aqui —la base caida, por ejemplo— no debe tumbar el
            # proceso: se avisa y se vuelve a intentar en la vuelta siguiente.
            log.exception("Fallo inesperado en el ciclo: %s", e)
            hubo = False
        finally:
            db.close()

        if hubo:
            ocioso = False
        else:
            if not ocioso:
                log.info("Sin trabajo pendiente. A la espera.")
                ocioso = True
            time.sleep(ESPERA)

    log.info("Trabajador detenido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
