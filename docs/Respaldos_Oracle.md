# Respaldos externos en Oracle Cloud

**Estado:** completado y verificado. Los scripts y la restauración temporal se
validaron el 3 de septiembre de 2026. El bucket, la retención, los permisos de
mínimo privilegio, el cron, dos cargas externas, una restauración desde el
bucket y la alerta por correo quedaron comprobados el 4 de septiembre.

## Qué se protege

Cada ejecución de `respaldar.sh` construye un único paquete que contiene:

- un volcado transaccional de MySQL;
- el volumen de PDF originales;
- la revisión de la aplicación y la fecha UTC;
- sumas SHA-256 de ambos contenidos.

No incluye `.env`. Sus secretos deben conservarse fuera del servidor, por
ejemplo en un gestor de contraseñas. Los certificados de Caddy tampoco se
incluyen porque pueden emitirse otra vez.

El paquete local queda con permisos `600`. Object Storage cifra los objetos en
tránsito y en reposo. La copia externa protege frente a la pérdida completa de
la instancia, pero no frente a la pérdida o cancelación de toda la cuenta de
Oracle.

## Frecuencia y conservación

- `daily/`: una copia cada día; Object Storage elimina las de más de 7 días.
- `weekly/`: cada domingo se duplica la copia bajo este prefijo; se elimina
  después de 28 días.
- Localmente se conservan los siete días más recientes.
- Una vez al mes se descarga un paquete del bucket y se ejecuta una
  restauración temporal completa.

Los nombres llevan fecha y hora y no se reutilizan. La instancia no necesita
permisos para leer, sobrescribir o borrar respaldos.

## Recursos creados en la consola

Los nombres propuestos son deliberadamente específicos para no mezclar esta
copia con otros recursos de la cuenta:

1. Bucket privado Standard `capstone-respaldos`, sin acceso público, sin
   versionado y con cifrado administrado por Oracle. Vive en la región
   `sa-valparaiso-1` y el namespace es `axhhd4zawgua`.
2. Regla habilitada `eliminar-diarios-7d`: elimina objetos cuyo nombre empieza
   por `daily/` después de 7 días.
3. Regla habilitada `eliminar-semanales-28d`: elimina objetos cuyo nombre
   empieza por `weekly/` después de 28 días.
4. Grupo dinámico `capstone-respaldos-instancia`, limitado por OCID a la única
   instancia existente de Capstone. No se creó ni reemplazó ninguna instancia.
5. Tema de OCI Notifications `capstone-respaldos-alertas`, con una suscripción
   por correo confirmada. La dirección personal no se publica en el repositorio.
6. Política `capstone-respaldos-policy`, con estos tres permisos mínimos:

   ```text
   Allow dynamic-group capstone-respaldos-instancia to manage objects in tenancy where all {target.bucket.name='capstone-respaldos', any {request.permission='OBJECT_CREATE', request.permission='OBJECT_INSPECT'}}
   Allow service objectstorage-sa-valparaiso-1 to manage object-family in tenancy where all {target.bucket.name='capstone-respaldos', any {request.permission='BUCKET_INSPECT', request.permission='BUCKET_READ', request.permission='OBJECT_INSPECT', request.permission='OBJECT_DELETE'}}
   Allow dynamic-group capstone-respaldos-instancia to use ons-topics in tenancy where request.operation='PublishMessage'
   ```

La primera sentencia permite a la instancia crear objetos y comprobar su
existencia y tamaño solo en ese bucket; no le permite descargarlos, modificarlos
ni borrarlos. La segunda permite al servicio de Object Storage aplicar las dos
reglas de eliminación solo dentro del mismo bucket. La tercera permite a la
instancia publicar mensajes, pero no administrar temas ni suscripciones porque
la condición limita la operación a `PublishMessage`. Ninguna de estas reglas
alcanza la base MySQL, los PDF del volumen Docker ni otros datos funcionales.

La regla del grupo dinámico será:

```text
ALL {instance.id = '<OCID_DE_LA_INSTANCIA>'}
```

## Variables del servidor

Después de crear los recursos se agregan al `.env` de producción:

```dotenv
OCI_RESPALDOS_BUCKET=capstone-respaldos
OCI_RESPALDOS_NAMESPACE=axhhd4zawgua
RESPALDO_EXTERNO_REQUERIDO=true
OCI_RESPALDOS_TOPIC_OCID=<OCID_DEL_TEMA>
```

No se agrega una clave OCI: la imagen oficial de OCI CLI usa
`instance_principal`. Está fijada por digest en `.env.example` para que el cron
no cambie silenciosamente de versión.

## Activación y comprobación

Después del despliegue se ejecuta manualmente una vez:

```bash
mkdir -p respaldos
./respaldar.sh
```

Debe aparecer un paquete en `daily/AAAA-MM-DD/`, su tamaño remoto debe coincidir
con el local y `respaldos/ULTIMO_EXITO_EXTERNO` debe registrar el éxito.

El cron definitivo es:

```cron
15 3 * * * cd /home/ubuntu/capstone-matriz && mkdir -p respaldos && ./respaldar.sh >> respaldos/registro.log 2>&1
```

## Restauración mensual

La cuenta administradora descarga un paquete desde Object Storage. La instancia
no puede descargarlo por sí sola: esta separación evita que una intrusión en el
servidor permita leer o borrar los respaldos.

Después de copiar el paquete a una ruta temporal del servidor:

```bash
bash ./restaurar_respaldo.sh /ruta/capstone_FECHA.backup.tar
```

El script comprueba las sumas, restaura MySQL bajo un nombre nuevo, extrae los
PDF a una carpeta temporal y verifica cada archivo contra el hash registrado en
la base. Muestra los conteos principales y elimina automáticamente la base y la
carpeta temporales. Nunca modifica producción.

## Evidencia de la primera prueba

Antes de conectar Object Storage se probó el formato completo contra la
instancia real, usando exclusivamente recursos temporales:

- paquete: 59 MB;
- proyectos restaurados: 2;
- artículos: 5;
- archivos registrados: 5;
- brechas: 5;
- todos los PDF relativos presentes y con SHA-256 correcto;
- base y archivos temporales eliminados al finalizar.

Esta prueba validó inicialmente la creación y restauración del formato. La
misma comprobación se repitió después con un paquete descargado del bucket.

## Evidencia de la primera carga externa

El 4 de septiembre de 2026 la instancia existente creó y subió, mediante su
identidad dinámica, el objeto:

```text
daily/2026-09-04/capstone_2026-09-04_010326.backup.tar
```

- tamaño local calculado: 62 402 560 bytes;
- tamaño mostrado en la consola: 59.51 MiB;
- la consulta posterior a Object Storage devolvió exactamente el tamaño local;
- clase de almacenamiento: Standard;
- no se reinició la aplicación ni se modificó la base;
- el servidor conserva solo una copia local tras aplicar su rotación.

La instancia quedó con las variables del bucket en `.env` y con el cron de las
03:15 corregido para crear la carpeta de registro antes de redirigir la salida.
Primero se probó una copia temporal del script y, después del resultado
correcto, se desplegó la revisión `d938db1`. La versión definitiva generó y
verificó un segundo objeto de 62 402 560 bytes. Tras reconstruir los
contenedores, MySQL quedó saludable, backend, frontend y trabajador en
ejecución, y el sitio público respondió HTTP 200.

## Evidencia de restauración desde Object Storage

Se descargó desde la consola el primer objeto de `daily/`. El archivo recibido
medía 62 402 560 bytes, exactamente lo mismo que el paquete local y el tamaño
consultado mediante la API de Object Storage. Se copió temporalmente a la
instancia y se ejecutó `restaurar_respaldo.sh`:

- las dos sumas SHA-256 fueron correctas;
- se restauraron 2 proyectos, 5 artículos, 5 archivos y 5 brechas;
- todos los PDF relativos existían y coincidían con su hash;
- la base de prueba y la carpeta temporal se eliminaron automáticamente;
- la base, los PDF y los servicios de producción no se modificaron.

## Evidencia de la alerta visible

El 4 de septiembre de 2026 se creó el tema
`capstone-respaldos-alertas`, se confirmó una suscripción por correo y se
guardó su OCID únicamente en el `.env` privado de la instancia. La política IAM
se amplió con una sola operación autorizada: `PublishMessage`.

La prueba se publicó desde la instancia mediante `instance_principal`, el mismo
mecanismo que usa `respaldar.sh` cuando captura un error. Oracle Monitoring
registró:

- 1 mensaje publicado;
- 1 mensaje entregado al endpoint de correo;
- 0 mensajes fallidos en el intervalo comprobado.

El mensaje indicaba explícitamente que era una prueba y que no se había
detectado ningún fallo. Con esto queda verificada la cadena completa:
producción, paquete, bucket, descarga, restauración aislada y aviso visible. El
paso 7 queda cerrado sin modificar la base ni los datos de la aplicación.
