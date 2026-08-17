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
#     15 3 * * * cd /home/ubuntu/capstone-matriz && ./respaldar.sh >> respaldos/registro.log 2>&1
#
# Los volcados van fuera del repositorio y no se versionan.

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
