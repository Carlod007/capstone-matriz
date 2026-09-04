#!/usr/bin/env bash
#
# Respaldo recuperable de Matriz Capstone.
#
# Genera un paquete con la base MySQL, los PDF y sus sumas SHA-256. Si se
# configuran OCI_RESPALDOS_BUCKET y OCI_RESPALDOS_NAMESPACE, también lo sube a
# un bucket privado de Oracle Object Storage mediante la identidad de la
# instancia. No guarda credenciales de Oracle en disco.
#
# Uso manual:
#     ./respaldar.sh
#
# Cron de producción (después de configurar Object Storage):
#     15 3 * * * cd /home/ubuntu/capstone-matriz && mkdir -p respaldos && ./respaldar.sh >> respaldos/registro.log 2>&1

set -Eeuo pipefail

# El volcado contiene correos y hashes de contraseña. Solo el usuario que
# ejecuta el respaldo debe poder leer los archivos locales.
umask 077

RAIZ="${RAIZ_PROYECTO:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
RAIZ="$(cd "$RAIZ" && pwd)"
cd "$RAIZ"

DESTINO="${DESTINO_RESPALDOS:-$RAIZ/respaldos}"
DIAS="${DIAS_RESPALDO:-7}"
TEMPORAL=""

# Imagen oficial fijada por digest para que el cron no cambie de herramienta
# de una noche a otra. Puede sustituirse de forma explícita desde .env.
OCI_CLI_IMAGE_POR_DEFECTO="ghcr.io/oracle/oci-cli@sha256:c73a9f92ea9800a8178ad249d9a757985856da13e512b24fa04faa0a9b9b5470"

oci_cli() {
    docker run --rm --user 0:0 --network host \
        -e OCI_CLI_AUTH=instance_principal \
        "${OCI_RESPALDOS_CLI_IMAGE:-$OCI_CLI_IMAGE_POR_DEFECTO}" "$@"
}

notificar_fallo() {
    local codigo="$1"
    local linea="$2"
    local mensaje="Falló el respaldo de Matriz Capstone en $(hostname), línea $linea, código $codigo. Revisa $DESTINO/registro.log."

    mkdir -p "$DESTINO"
    printf '[%s] %s\n' "$(date '+%F %T')" "$mensaje" >&2
    printf '%s\n' "$mensaje" > "$DESTINO/ULTIMO_ERROR"

    if [ -n "${OCI_RESPALDOS_TOPIC_OCID:-}" ]; then
        oci_cli ons message publish \
            --topic-id "$OCI_RESPALDOS_TOPIC_OCID" \
            --title "Falló el respaldo de Matriz Capstone" \
            --body "$mensaje" >/dev/null 2>&1 || \
            echo "Tampoco se pudo enviar la alerta por OCI Notifications." >&2
    fi
}

al_fallar() {
    local codigo="$?"
    local linea="${BASH_LINENO[0]:-desconocida}"
    trap - ERR
    notificar_fallo "$codigo" "$linea"
    exit "$codigo"
}

limpiar() {
    if [ -n "$TEMPORAL" ] && [ -d "$TEMPORAL" ]; then
        rm -rf -- "$TEMPORAL"
    fi
}

trap al_fallar ERR
trap limpiar EXIT

if [ ! -f .env ]; then
    echo "No se encuentra .env en $RAIZ" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

BASE="${MYSQL_BASE:-capstone}"
if [[ ! "$BASE" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "MYSQL_BASE solo puede contener letras, números y guion bajo." >&2
    exit 1
fi
if [[ ! "$DIAS" =~ ^[1-9][0-9]*$ ]]; then
    echo "DIAS_RESPALDO debe ser un número entero mayor que cero." >&2
    exit 1
fi

mkdir -p "$DESTINO"
# Corrige también la exposición de los volcados creados por versiones
# anteriores del script, que podían quedar legibles por otros usuarios.
find "$DESTINO" -maxdepth 1 -type f \
    \( -name 'capstone_*.sql.gz' -o -name 'capstone_*.backup.tar' \) \
    -exec chmod 600 {} +
TEMPORAL="$(mktemp -d "$DESTINO/.respaldo.XXXXXX")"

marca="$(date -u '+%Y-%m-%d_%H%M%S')"
nombre_base="capstone_${marca}.sql.gz"
nombre_pdfs="capstone_${marca}_pdfs.tar.gz"
nombre_paquete="capstone_${marca}.backup.tar"

archivo_base="$TEMPORAL/$nombre_base"
archivo_pdfs="$TEMPORAL/$nombre_pdfs"
archivo_paquete="$DESTINO/$nombre_paquete"

echo "[$(date '+%F %T')] Preparando respaldo completo de $BASE ..."

# Los PDF viven en un volumen Docker distinto de MySQL. Sin esta copia, una
# base restaurada conservaría referencias a archivos que ya no existen.
# Se copian antes del volcado: un PDF eliminado durante la pequeña ventana
# queda como extra inocuo, en vez de dejar una referencia sin archivo.
docker compose exec -T backend \
    tar -C /app/storage/pdfs -czf - . > "$archivo_pdfs"
tar -tzf "$archivo_pdfs" >/dev/null

# El volcado usa una transacción coherente y no bloquea la aplicación.
docker compose exec -T -e MYSQL_PWD="$MYSQL_PASSWORD" mysql \
    mysqldump -uroot \
        --single-transaction \
        --routines \
        --databases "$BASE" \
    | gzip > "$archivo_base"

gzip -t "$archivo_base"
tam_base="$(stat -c%s "$archivo_base")"
if [ "$tam_base" -lt 1024 ]; then
    echo "El volcado MySQL salió vacío ($tam_base bytes)." >&2
    exit 1
fi

revision="${APP_REVISION:-$(git rev-parse --short HEAD 2>/dev/null || echo desconocida)}"
cat > "$TEMPORAL/metadata.txt" <<EOF
formato=capstone-backup-v1
creado_utc=$marca
base=$BASE
revision=$revision
EOF

(
    cd "$TEMPORAL"
    sha256sum "$nombre_base" "$nombre_pdfs" > SHA256SUMS
    tar -cf "$nombre_paquete" \
        metadata.txt SHA256SUMS "$nombre_base" "$nombre_pdfs"
)
mv "$TEMPORAL/$nombre_paquete" "$archivo_paquete"
tar -tf "$archivo_paquete" >/dev/null

tam_paquete="$(stat -c%s "$archivo_paquete")"
echo "[$(date '+%F %T')] Paquete local listo: $archivo_paquete ($((tam_paquete / 1024 / 1024)) MB)"

bucket="${OCI_RESPALDOS_BUCKET:-}"
namespace="${OCI_RESPALDOS_NAMESPACE:-}"
externo_requerido="${RESPALDO_EXTERNO_REQUERIDO:-false}"

if [ -z "$bucket" ] || [ -z "$namespace" ]; then
    if [ "$externo_requerido" = "true" ]; then
        echo "Faltan OCI_RESPALDOS_BUCKET u OCI_RESPALDOS_NAMESPACE." >&2
        exit 1
    fi
    echo "AVISO: Object Storage no está configurado; el respaldo quedó solo en esta instancia."
else
    subir_objeto() {
        local prefijo="$1"
        local objeto="$prefijo/$nombre_paquete"
        local tam_remoto
        echo "[$(date '+%F %T')] Subiendo $objeto ..."
        docker run --rm --user 0:0 --network host \
            -e OCI_CLI_AUTH=instance_principal \
            -v "$DESTINO:/backups:ro" \
            "${OCI_RESPALDOS_CLI_IMAGE:-$OCI_CLI_IMAGE_POR_DEFECTO}" \
            os object put \
                --namespace "$namespace" \
                --bucket-name "$bucket" \
                --name "$objeto" \
                --file "/backups/$nombre_paquete" \
                --verify-checksum \
                --force >/dev/null
        tam_remoto="$(oci_cli os object head \
            --namespace "$namespace" \
            --bucket-name "$bucket" \
            --name "$objeto" \
            --query '"content-length"' \
            --raw-output)"
        if [ "$tam_remoto" != "$tam_paquete" ]; then
            echo "Object Storage devolvió $tam_remoto bytes; se esperaban $tam_paquete." >&2
            return 1
        fi
        echo "[$(date '+%F %T')] Copia externa verificada: $objeto"
    }

    subir_objeto "daily/$(date -u '+%Y-%m-%d')"
    if [ "$(date -u '+%u')" = "7" ]; then
        subir_objeto "weekly/$(date -u '+%G-W%V')"
    fi

    printf '[%s] %s\n' "$(date '+%F %T')" "$nombre_paquete" \
        > "$DESTINO/ULTIMO_EXITO_EXTERNO"
    rm -f -- "$DESTINO/ULTIMO_ERROR"
fi

# La rotación local es independiente de la del bucket. Object Storage aplica
# sus propias reglas y la instancia no recibe permiso para borrar copias.
borrados="$({
    find "$DESTINO" -maxdepth 1 -type f -name 'capstone_*.backup.tar' -mtime "+$((DIAS - 1))" -print -delete
    find "$DESTINO" -maxdepth 1 -type f -name 'capstone_*.sql.gz' -mtime "+$((DIAS - 1))" -print -delete
} | wc -l)"
if [ "$borrados" -gt 0 ]; then
    echo "Retirados $borrados respaldo(s) locales antiguos."
fi

echo "Respaldos completos locales: $(find "$DESTINO" -maxdepth 1 -type f -name 'capstone_*.backup.tar' | wc -l)"
