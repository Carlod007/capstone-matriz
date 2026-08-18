#!/usr/bin/env bash
#
# Copia de seguridad de la base de datos.
#
# Desde que el sistema vive en un servidor, los datos ya no estan tambien en la
# laptop: si se pierde el volumen de MySQL, se pierde todo. Este script vuelca
# la base a un archivo comprimido y conserva los ultimos dias.
#
# Uso manual:
#     ./respaldar.sh
#
# Programado, todos los dias a las 03:15 (crontab -e):
#
#     15 3 * * * cd /home/ubuntu/capstone-matriz && mkdir -p respaldos && ./respaldar.sh >> respaldos/registro.log 2>&1
#
# El `mkdir -p` de esa linea no sobra: la shell abre el fichero de registro
# ANTES de ejecutar el script, asi que en una instalacion recien hecha, donde
# la carpeta todavia no existe, la redireccion falla y la tarea no llega a
# arrancar. Y al fallar en el cron, falla en silencio.
#
# Los volcados van fuera del repositorio y no se versionan.
#
# AVISO: estos respaldos viven en la misma maquina que la base. Protegen de un
# borrado accidental o de una migracion que salga mal, pero NO de perder la
# instancia. Para eso hay que bajarlos de vez en cuando, desde tu equipo:
#
#     scp -i TU_CLAVE ubuntu@TU_IP:capstone-matriz/respaldos/*.sql.gz .
#
# Y un respaldo que nunca se ha restaurado no es un respaldo: ver al final de
# este archivo como comprobarlo.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

DESTINO="${DESTINO_RESPALDOS:-$RAIZ/respaldos}"
DIAS="${DIAS_RESPALDO:-7}"

# Las credenciales salen del mismo .env que usa la aplicacion, para no tenerlas
# escritas en dos sitios y que se desincronicen.
if [ ! -f .env ]; then
    echo "No se encuentra .env en $RAIZ" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

BASE="${MYSQL_BASE:-capstone}"
mkdir -p "$DESTINO"

marca="$(date +%Y-%m-%d_%H%M)"
archivo="$DESTINO/capstone_$marca.sql.gz"

echo "[$(date '+%F %T')] Respaldando $BASE ..."

# --single-transaction para no bloquear la base mientras se copia: el volcado
# se toma de una instantanea coherente y la aplicacion sigue funcionando.
# El resultado se comprime al vuelo; sin comprimir ocupa varias veces mas.
docker compose exec -T mysql \
    mysqldump -uroot -p"$MYSQL_PASSWORD" \
        --single-transaction \
        --routines \
        --databases "$BASE" \
    | gzip > "$archivo"

# Un volcado fallido deja un .gz valido pero casi vacio, que pasaria por bueno
# hasta el dia que hiciera falta. Se comprueba el tamano y se descarta.
tam=$(stat -c%s "$archivo")
if [ "$tam" -lt 1024 ]; then
    echo "El respaldo salio vacio ($tam bytes). Se descarta." >&2
    rm -f "$archivo"
    exit 1
fi

echo "[$(date '+%F %T')] Listo: $archivo ($((tam / 1024)) KB)"

# Rotacion: se borran los mas viejos que el plazo.
borrados=$(find "$DESTINO" -name 'capstone_*.sql.gz' -mtime +"$DIAS" -print -delete | wc -l)
if [ "$borrados" -gt 0 ]; then
    echo "Retirados $borrados respaldo(s) de mas de $DIAS dias."
fi

echo "Respaldos guardados: $(find "$DESTINO" -name 'capstone_*.sql.gz' | wc -l)"

# ---------------------------------------------------------------------------
# COMO COMPROBAR QUE UN RESPALDO SIRVE
#
# Un volcado que nunca se ha restaurado no es un respaldo: es un archivo del
# que se supone algo. La comprobacion no toca la base real, levanta una aparte:
#
#   docker compose exec -T mysql mysql -uroot -p"$MYSQL_PASSWORD" \
#       -e "CREATE DATABASE IF NOT EXISTS prueba_restauracion"
#
#   gunzip -c respaldos/capstone_FECHA.sql.gz \
#     | sed 's/`capstone`/`prueba_restauracion`/g' \
#     | docker compose exec -T mysql mysql -uroot -p"$MYSQL_PASSWORD"
#
#   docker compose exec -T mysql mysql -uroot -p"$MYSQL_PASSWORD" \
#       -e "SELECT COUNT(*) AS proyectos FROM prueba_restauracion.proyecto;
#           SELECT COUNT(*) AS brechas FROM prueba_restauracion.resultado_brecha"
#
# Si esos recuentos coinciden con los de la base real, el respaldo vale. Y al
# terminar:
#
#   docker compose exec -T mysql mysql -uroot -p"$MYSQL_PASSWORD" \
#       -e "DROP DATABASE prueba_restauracion"
# ---------------------------------------------------------------------------
