#!/usr/bin/env bash
#
# Verifica y restaura un paquete de respaldo en recursos temporales.
# Nunca escribe en la base de producción ni en el volumen real de PDF.
#
# Uso:
#     ./restaurar_respaldo.sh /ruta/capstone_FECHA.backup.tar

set -Eeuo pipefail
umask 077

RAIZ="${RAIZ_PROYECTO:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
RAIZ="$(cd "$RAIZ" && pwd)"
cd "$RAIZ"

if [ "$#" -ne 1 ]; then
    echo "Uso: $0 /ruta/capstone_FECHA.backup.tar" >&2
    exit 2
fi

PAQUETE="$(realpath "$1")"
if [ ! -f "$PAQUETE" ]; then
    echo "No existe el paquete: $PAQUETE" >&2
    exit 1
fi
if [ ! -f .env ]; then
    echo "No se encuentra .env en $RAIZ" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

TEMPORAL="$(mktemp -d)"
BASE_PRUEBA="prueba_restauracion_$(date -u '+%Y%m%d%H%M%S')_$$"
BASE_CREADA=false

mysql_temporal() {
    docker compose exec -T -e MYSQL_PWD="$MYSQL_PASSWORD" mysql \
        mysql -uroot "$@"
}

limpiar() {
    local codigo="$?"
    trap - EXIT
    if [ "$BASE_CREADA" = "true" ]; then
        mysql_temporal -e "DROP DATABASE IF EXISTS \`$BASE_PRUEBA\`" \
            >/dev/null 2>&1 || true
    fi
    rm -rf -- "$TEMPORAL"
    exit "$codigo"
}
trap limpiar EXIT

# Rechaza nombres absolutos o con `..` antes de extraer un archivo descargado.
if tar -tf "$PAQUETE" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then
    echo "El paquete contiene una ruta insegura." >&2
    exit 1
fi
tar -xf "$PAQUETE" -C "$TEMPORAL"

if [ ! -f "$TEMPORAL/metadata.txt" ] || [ ! -f "$TEMPORAL/SHA256SUMS" ]; then
    echo "El paquete no tiene metadatos o sumas de integridad." >&2
    exit 1
fi
if ! grep -qx 'formato=capstone-backup-v1' "$TEMPORAL/metadata.txt"; then
    echo "Formato de respaldo desconocido." >&2
    exit 1
fi

BASE_ORIGEN="$(sed -n 's/^base=//p' "$TEMPORAL/metadata.txt" | head -n 1)"
if [[ ! "$BASE_ORIGEN" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "El paquete declara un nombre de base no válido." >&2
    exit 1
fi

(
    cd "$TEMPORAL"
    sha256sum -c SHA256SUMS
)

mapfile -t volcados < <(find "$TEMPORAL" -maxdepth 1 -type f -name 'capstone_*.sql.gz')
mapfile -t archivos_pdf < <(find "$TEMPORAL" -maxdepth 1 -type f -name 'capstone_*_pdfs.tar.gz')
if [ "${#volcados[@]}" -ne 1 ] || [ "${#archivos_pdf[@]}" -ne 1 ]; then
    echo "El paquete debe contener exactamente un volcado y un archivo de PDF." >&2
    exit 1
fi

gzip -t "${volcados[0]}"
tar -tzf "${archivos_pdf[0]}" >/dev/null
if tar -tzf "${archivos_pdf[0]}" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then
    echo "El archivo de PDF contiene una ruta insegura." >&2
    exit 1
fi

mysql_temporal -e "CREATE DATABASE \`$BASE_PRUEBA\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
BASE_CREADA=true

SQL_TEMPORAL="$TEMPORAL/base.sql"
gzip -dc "${volcados[0]}" > "$SQL_TEMPORAL"
if ! grep -Fq "USE \`$BASE_ORIGEN\`;" "$SQL_TEMPORAL"; then
    echo "El volcado no selecciona la base declarada en sus metadatos." >&2
    exit 1
fi
sed "s/\`$BASE_ORIGEN\`/\`$BASE_PRUEBA\`/g" "$SQL_TEMPORAL" \
    | docker compose exec -T -e MYSQL_PWD="$MYSQL_PASSWORD" mysql mysql -uroot

RAIZ_PDFS="$TEMPORAL/pdfs"
mkdir -p "$RAIZ_PDFS"
tar -xzf "${archivos_pdf[0]}" -C "$RAIZ_PDFS"

faltantes=0
incorrectos=0
while IFS=$'\t' read -r ruta hash; do
    [ -n "$ruta" ] || continue
    if [[ "$ruta" = /* ]]; then
        echo "AVISO: ruta histórica absoluta no verificable: $ruta" >&2
        continue
    fi
    if [[ "$ruta" = *..* ]] || [ ! -f "$RAIZ_PDFS/$ruta" ]; then
        echo "Falta el PDF referenciado: $ruta" >&2
        faltantes=$((faltantes + 1))
        continue
    fi
    real="$(sha256sum "$RAIZ_PDFS/$ruta" | cut -d' ' -f1)"
    if [ "$real" != "$hash" ]; then
        echo "El PDF no coincide con su hash: $ruta" >&2
        incorrectos=$((incorrectos + 1))
    fi
done < <(mysql_temporal --batch --skip-column-names \
    -e "SELECT ruta, hash_sha256 FROM \`$BASE_PRUEBA\`.archivo ORDER BY id")

if [ "$faltantes" -ne 0 ] || [ "$incorrectos" -ne 0 ]; then
    echo "La restauración tiene $faltantes PDF faltantes y $incorrectos alterados." >&2
    exit 1
fi

echo "Restauración temporal correcta:"
mysql_temporal --table -e "
    SELECT 'proyectos' AS entidad, COUNT(*) AS cantidad FROM \`$BASE_PRUEBA\`.proyecto
    UNION ALL SELECT 'articulos', COUNT(*) FROM \`$BASE_PRUEBA\`.articulo
    UNION ALL SELECT 'archivos', COUNT(*) FROM \`$BASE_PRUEBA\`.archivo
    UNION ALL SELECT 'brechas', COUNT(*) FROM \`$BASE_PRUEBA\`.resultado_brecha;"
echo "Todos los PDF relativos existen y coinciden con su SHA-256."
echo "La base y la carpeta temporales se eliminarán ahora; producción no fue modificada."
