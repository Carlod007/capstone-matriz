# Matriz de brechas de investigación

[![CI](https://github.com/Carlod007/capstone-matriz/actions/workflows/ci.yml/badge.svg?branch=CarlosDev)](https://github.com/Carlod007/capstone-matriz/actions/workflows/ci.yml)

Herramienta que lee artículos científicos en PDF y ayuda a un investigador a
responder dos preguntas: **qué se ha hecho ya** en su tema y **qué falta por
hacer**. A partir de los PDF construye una matriz de brechas —limitaciones,
vacíos metodológicos, líneas abiertas— y un borrador de estado del arte, y
mide la calidad de lo que produce en lugar de pedir que se le crea.

Proyecto de capstone universitario. Backend en FastAPI, frontend en React,
base de datos MySQL y modelos de Gemini para la generación.

---

## Índice

- [Qué hace, en concreto](#qué-hace-en-concreto)
- [Requisitos](#requisitos)
- [Arrancar todo con Docker](#arrancar-todo-con-docker)
- [Instalación desde cero](#instalación-desde-cero)
- [Arrancar el sistema a mano](#arrancar-el-sistema-a-mano)
- [Modo simulado y modo real](#modo-simulado-y-modo-real)
- [Flujo de uso](#flujo-de-uso)
- [Cuentas](#cuentas)
- [Pruebas](#pruebas)
- [Qué miden las métricas y qué no](#qué-miden-las-métricas-y-qué-no)
- [Límites de la API](#límites-de-la-api)
- [OCR para PDF escaneados](#ocr-para-pdf-escaneados)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Problemas frecuentes](#problemas-frecuentes)
- [Estado del proyecto](#estado-del-proyecto)

---

## Qué hace, en concreto

Cada PDF pasa por esta cadena:

| Etapa | Qué ocurre |
|---|---|
| **Ingesta** | Se extrae el texto del PDF. Si el PDF es una imagen escaneada, se recurre a OCR. Se detectan las secciones (resumen, introducción, metodología, resultados, discusión, limitaciones, conclusiones, referencias). |
| **Indexado** | El texto se parte en fragmentos y cada uno se convierte en un vector (*embedding*). Es lo que permite después buscar por significado y no por palabra exacta. |
| **Recuperación** | Ante una pregunta se recuperan los fragmentos relevantes, con diversidad (MMR) y con cuota por sección, para que el modelo no lea siempre la introducción. |
| **Análisis** | El modelo redacta las brechas de ese artículo apoyándose únicamente en los fragmentos recuperados, y cita de cuál sale cada afirmación. |
| **Verificación** | Cada brecha se descompone en afirmaciones atómicas. Las que dicen *«el artículo dice X»* se contrastan contra los fragmentos; las que son interpretación del modelo se marcan como tales. Una afirmación sin respaldo pierde su cita y queda señalada. |
| **Estado del arte** | Con las brechas de todos los artículos se sintetiza un borrador de estado del arte. |
| **Medición** | Siete niveles de métricas, desde la calidad de la extracción hasta la fabricación de citas. |

La verificación es la pieza que distingue esto de pedirle un resumen a un
chatbot: sobre los cinco artículos de la prueba real, **tres de cinco brechas
contenían al menos una afirmación sin respaldo en el texto** —una de ellas
inventaba una condición experimental que el artículo no mencionaba—. Sin esa
capa, esas tres habrían llegado al investigador con apariencia de hecho.

---

## Requisitos

| | Versión probada | Nota |
|---|---|---|
| Python | 3.13.7 | 3.11 o superior debería servir |
| Node.js | 22.19.0 | con npm 11 |
| MySQL | 8.x | servidor local en `localhost:3306` |
| Tesseract OCR | 5.x | **opcional**, solo para PDF escaneados |
| Clave de Gemini | — | **opcional**, solo para el modo real |

Sin clave de API y sin Tesseract el sistema arranca y se puede recorrer
entero en modo simulado.

**Con Docker no necesitas nada de lo anterior**, solo Docker Desktop: la
imagen ya trae Python, Tesseract con español e inglés, y MySQL viene en su
propio contenedor. Ver [Arrancar todo con Docker](#arrancar-todo-con-docker).

---

## Instalación desde cero

### 1. Clonar

```bash
git clone <url-del-repositorio> capstone-matriz
```

### 2. Crear la base de datos

Con el servidor MySQL en marcha, crea la base vacía (desde MySQL Workbench o
desde la consola de MySQL). Las tablas **no** se crean aquí: las crea Alembic
en el paso 5.

```sql
CREATE DATABASE capstone CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 3. Preparar el backend

```bash
cd backend
python -m venv .venv
```

Activar el entorno virtual:

```bash
.venv\Scripts\Activate.ps1
```

En Linux o macOS es `source .venv/bin/activate`. Si PowerShell bloquea el
script, ver [Problemas frecuentes](#problemas-frecuentes).

```bash
pip install -r requirements.txt
```

### 4. Configurar el entorno

Copia el archivo de ejemplo y edítalo:

```bash
copy .env.example .env
```

Lo mínimo es apuntar `MYSQL_URI` a tu base y poner un secreto de sesión:

```ini
MYSQL_URI=mysql+pymysql://root:TU_CONTRASENA@localhost:3306/capstone
GEMINI_MODE=mock
JWT_SECRETO=
```

`JWT_SECRETO` firma las sesiones y **no tiene valor por defecto a propósito**:
uno de relleno parece configurado y permitiría a cualquiera que lea el código
firmar tokens válidos. Genera el tuyo:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Si falta, el backend se niega a arrancar y dice qué falta. Es deliberado:
mejor no arrancar que arrancar mal.

`.env` está en `.gitignore` y no debe versionarse nunca: contiene la
contraseña de la base, el secreto de sesión y, si lo usas, la clave de la API.

### 5. Crear las tablas

```bash
alembic upgrade head
```

Debe terminar sin errores y dejar 13 tablas más `alembic_version`. Este es el
único modo admitido de crear o actualizar el esquema; el detalle está en
[`backend/migraciones/README`](backend/migraciones/README).

### 6. Preparar el frontend

Desde otra terminal, en la raíz del repositorio:

```bash
cd frontend
npm install
```

```bash
copy .env.example .env
```

El valor por defecto (`VITE_API_BASE=http://localhost:8000`) ya apunta al
backend local.

---

## Arrancar todo con Docker

La vía corta. Un solo comando levanta las cuatro piezas, y lo que corre aquí
es lo mismo que correrá en el servidor.

Necesitas [Docker Desktop](https://www.docker.com/products/docker-desktop/)
—gratis, sin cuenta— y nada más: ni Python, ni Node, ni MySQL instalados.

```bash
copy .env.example .env
```

Rellena `MYSQL_PASSWORD` y `JWT_SECRETO` (el archivo explica cada variable) y:

```bash
docker compose up --build
```

La aplicación queda en <http://localhost:8080>. El esquema se crea solo: un
servicio aparte ejecuta `alembic upgrade head` y los demás esperan a que
termine.

La API se sirve **por el mismo origen, bajo `/api`**. No hace falta abrir el
puerto del backend: Caddy hace de intermediario, y por eso tampoco hay CORS
que configurar.

Para crear la primera cuenta, con todo en marcha:

```bash
docker compose exec backend python crear_cuenta.py
```

Para analizar más artículos a la vez, levanta más trabajadores. No hay nada
que configurar: cada uno pide a la base el siguiente artículo libre.

```bash
docker compose up --scale trabajador=3
```

Parar sin perder nada:

```bash
docker compose down
```

Los datos —base y PDF— viven en volúmenes con nombre y sobreviven a `down`.
Para borrarlos también hay que pedirlo explícitamente con `down -v`.

**En Windows, limita WSL.** Docker corre sobre él y, sin límite, se reserva la
mitad de la RAM de la máquina y no la devuelve. Crea `C:\Users\TU_USUARIO\
.wslconfig` con:

```ini
[wsl2]
memory=5GB
processors=4
swap=2GB

[experimental]
autoMemoryReclaim=gradual
```

`autoMemoryReclaim` va en `[experimental]`: bajo `[wsl2]`, WSL avisa de que la
clave es desconocida y la ignora, así que el límite se aplica pero la memoria
sigue sin devolverse.

Luego `wsl --shutdown` para que surta efecto.

**Esta instalación es independiente de la que corre a mano.** Docker trae su
propio MySQL, así que empieza sin cuentas ni proyectos aunque tengas datos en
el MySQL de tu sistema. No es un fallo.

### Desplegar en un servidor con HTTPS

En el `.env` del servidor, define el dominio y los puertos reales:

```ini
DOMINIO=mi-dominio.com
PUERTO_HTTP=80
PUERTO_HTTPS=443
```

Con eso, **Caddy consigue el certificado de Let's Encrypt y lo renueva solo**.
No hay que instalar certbot ni programar nada: pide el certificado al arrancar
y lo renueva cada dos meses. El puerto 80 tiene que estar abierto aunque uses
HTTPS, porque por ahí comprueba Let's Encrypt que el dominio es tuyo.

**¿Sin dominio propio?** `sslip.io` convierte cualquier IP en un nombre, sin
registrarse en ningún sitio: para `203.0.113.10` sería
`DOMINIO=203-0-113-10.sslip.io`.

Los certificados viven en un volumen. Si lo borras, Caddy los vuelve a pedir, y
Let's Encrypt limita cuántas veces se puede hacer eso por semana.

### Copias de seguridad

En el servidor, los datos ya no están también en tu equipo. `respaldar.sh`
vuelca la base comprimida y conserva los últimos siete días:

```bash
./respaldar.sh
```

Para que corra solo cada noche, con `crontab -e`:

```bash
15 3 * * * cd /home/ubuntu/capstone-matriz && mkdir -p respaldos && ./respaldar.sh >> respaldos/registro.log 2>&1
```

El `mkdir -p` no sobra: la shell abre el fichero de registro **antes** de
ejecutar el script, así que en una instalación recién hecha la redirección
falla y la tarea no llega a arrancar — y en el cron, falla en silencio.

Los volcados no se versionan: contienen correos y hashes de contraseña.

**Dos límites que conviene tener presentes.** Los respaldos viven en la misma
máquina que la base: protegen de un borrado accidental o de una migración que
salga mal, pero **no de perder la instancia**. Bájalos de vez en cuando:

```bash
scp -i TU_CLAVE ubuntu@TU_IP:capstone-matriz/respaldos/*.sql.gz .
```

Y un respaldo que nunca se ha restaurado no es un respaldo, es un archivo del
que se supone algo. El procedimiento para comprobarlo sobre una base aparte,
sin tocar la real, está al final de `respaldar.sh`.

---

## Arrancar el sistema a mano

La vía larga, útil para desarrollar: recarga automática al guardar y registros
directos en tu terminal. Hacen falta cuatro cosas encendidas: MySQL, el
backend, el **trabajador** y el frontend.

**MySQL** — el servicio de Windows suele arrancar solo. Para comprobarlo:

```bash
Get-Service -Name MySQL* | Select-Object Name, Status
```

**Backend** — desde `backend/`, con el entorno virtual activado:

```bash
python -m uvicorn main:app --reload --port 8000
```

**Trabajador** — en otra terminal, desde `backend/` y con el entorno activado:

```bash
python trabajador.py
```

Es quien analiza. El backend solo apunta el trabajo en la cola y responde al
instante; sin el trabajador en marcha, los análisis se quedan esperando para
siempre. Se para con Ctrl+C, que termina el artículo en curso antes de salir
para no perder una generación ya pagada.

Pueden correr varios a la vez. No se coordinan entre sí: cada uno pide a la
base el siguiente artículo libre, y MySQL se encarga de que no cojan el
mismo.

**Frontend** — desde `frontend/`:

```bash
npm run dev
```

La aplicación queda en <http://localhost:5173> y la documentación
interactiva de la API en <http://localhost:8000/docs>.

Al arrancar, el backend compara la revisión de la base con la última
migración y avisa por el log si está atrasada. Es un aviso, no un bloqueo.

---

## Modo simulado y modo real

Lo decide `GEMINI_MODE` en `backend/.env`. Hay que reiniciar el backend
después de cambiarlo.

| | `mock` | `real` |
|---|---|---|
| Llamadas a la red | ninguna | a la API de Gemini |
| Coste y cuota | ninguno | consume cuota |
| Textos generados | plantillas fijas | los del modelo |
| Embeddings | deterministas | los del modelo |
| Verificación de brechas | se declara no disponible | activa |

El modo simulado no es un juguete: sirve para desarrollar, para las pruebas
automáticas y para enseñar el sistema sin gastar cuota. Lo que **no** hace es
producir contenido con valor: los textos son de relleno. Para resultados
reales hace falta `GEMINI_MODE=real` y una clave en `GEMINI_API_KEY`, que se
obtiene en [Google AI Studio](https://aistudio.google.com/apikey).

---

## Flujo de uso

1. **Crear un proyecto** con su tema principal, objetivo de investigación,
   sector y metodología. Ese contexto es lo que orienta todo el análisis
   posterior, así que conviene escribirlo con cuidado y no en dos palabras.
2. **Subir los PDF** de los artículos (arrastrándolos o desde el selector).
3. **Indexar**: prepara los artículos para la búsqueda por significado.
4. **Analizar todo**: pone el proyecto en cola. La respuesta es inmediata y
   **puedes cerrar el navegador**: el trabajador sigue por su cuenta y al
   volver encontrarás el avance donde iba.
5. **Verificar**: contrasta cada afirmación contra el texto fuente. Aquí es
   donde aparece el porcentaje de fidelidad y las afirmaciones sin respaldo.
6. **Generar el estado del arte** a partir del conjunto.
7. **Exportar**: matriz en PDF o JSON, brechas en CSV, estado del arte en
   Markdown, panel en PDF.

Un consejo de uso, no del sistema: la salida es un borrador que **acelera**
la revisión de literatura, no la sustituye. Las brechas señaladas hay que
contrastarlas con el artículo antes de citarlas en un trabajo.

---

## Pruebas

Las pruebas necesitan un paquete más, que no hace falta para servir la
aplicación y por eso va aparte:

```bash
pip install -r requirements-dev.txt
```

Desde `backend/`, con el entorno activado:

```bash
python -m pytest
```

Son 378 pruebas y corren en modo simulado, sin gastar cuota. Las que
necesitan MySQL están marcadas con `bd` y **se saltan solas** si no hay
conexión, de modo que la suite pasa igual en una máquina sin base de datos.

Para excluirlas explícitamente:

```bash
python -m pytest -m "not bd"
```

Cinco de ellas (`tests/test_esquema.py`) comprueban que los modelos y la base
sigan coincidiendo: si alguien cambia un modelo y olvida generar la
migración, falla ahí y no en producción.

### Integración continua

Cada `push` dispara [el flujo de CI](.github/workflows/ci.yml), que hace en
GitHub lo mismo que harías a mano:

- levanta un MySQL vacío y construye el esquema con `alembic upgrade head`,
  de modo que una migración mal escrita se rompe ahí;
- ejecuta `alembic check` y las 378 pruebas contra esa base recién creada,
  sin los datos acumulados de una máquina de desarrollo;
- instala el frontend con `npm ci`, pasa el lint y compila.

Si el distintivo de arriba está en rojo, el repositorio no está en
condiciones de clonarse.

---

## Qué miden las métricas y qué no

El sistema reporta siete niveles de métricas. Merece la pena decir con
franqueza qué significan, porque una métrica mal entendida es peor que
ninguna.

| Nivel | Mide |
|---|---|
| N0 | Calidad de la ingesta: texto extraído, secciones detectadas, si hizo falta OCR |
| N1 | Recuperación: de qué secciones salieron los fragmentos, cuánta diversidad tienen |
| N2 | **Fidelidad**: qué proporción de las afirmaciones evidenciales está respaldada por el texto |
| N3 | Especificidad: si las brechas distinguen un artículo de otro o son intercambiables |
| N4 | Resumen: solapamiento léxico con el resumen original del artículo |
| N5 | Síntesis: cobertura del estado del arte y **citas fabricadas** |
| N6 | Anclaje humano: contraste contra un conjunto anotado por expertos |

Tres advertencias honestas:

- **N4 (ROUGE) no aplica entre idiomas.** ROUGE cuenta palabras compartidas.
  Si el resumen se genera en español y el resumen original del artículo está
  en inglés, el valor es cercano a cero por construcción, no por mala
  calidad. El sistema detecta el idioma y declara la métrica *no aplicable*
  en vez de mostrar un número engañoso.
- **N6 todavía no está anclado.** Requiere un conjunto de brechas anotado por
  expertos que aún no existe. Hasta entonces, las métricas dicen si el
  sistema es *consistente*, no si *acierta* según un experto humano.
- **Una métrica que sale siempre igual no mide nada.** Las que resultan
  cuasiconstantes (recorrido intercuartílico menor que 0.05) se retiran en
  lugar de exhibirse como si informaran.

Los valores se reportan como mediana y recorrido intercuartílico, no como
promedio: con pocos artículos, un caso extremo arrastra la media entera.

La especificación completa está en
[`docs/Especificacion_Capa_Medicion_v2.pdf`](docs/Especificacion_Capa_Medicion_v2.pdf).

---

## Límites de la API

El nivel gratuito de Gemini impone cuotas que se agotan antes de lo que
parece. El sistema las respeta él mismo, con una ventana deslizante, en vez
de descubrirlas cuando la API devuelve error 429.

| | Por minuto | Por día |
|---|---|---|
| Generación | 4 (el tope real es 5) | 20 |
| Embeddings | 70 (el tope real es 100) | 1000 |

Se configuran con `LIMITE_GENERACION_MIN`, `LIMITE_GENERACION_DIA`,
`LIMITE_EMBEDDINGS_MIN` y `LIMITE_EMBEDDINGS_DIA` en `.env`. Los valores por
defecto van deliberadamente por debajo del tope real: agotar el límite diario
deja el sistema inutilizable hasta la medianoche del Pacífico (UTC−8), que es
cuando Google reinicia la cuota.

El frontend muestra el consumo del día y cuánto falta para el reinicio,
contado contra el reloj del servidor y no contra el del navegador.

Analizar un artículo cuesta aproximadamente una generación; verificarlo,
otra; el estado del arte, una más. Con veinte al día alcanza para un
proyecto de unos ocho artículos por jornada.

---

## OCR para PDF escaneados

Solo hace falta si vas a subir PDF que son imágenes en vez de texto. Instala
[Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) y, si no queda en
el `PATH` del sistema, indica la ruta del ejecutable en `.env`:

```ini
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Sin Tesseract, un PDF escaneado se ingiere sin texto y el análisis no tendrá
de dónde partir. Los PDF normales no lo necesitan.

---

## Estructura del repositorio

```
docker-compose.yml    levanta las cuatro piezas con un comando
respaldar.sh          volcado diario de la base, con rotación
backend/
  Dockerfile          imagen compartida por el backend y el trabajador
  main.py             arranque de FastAPI y comprobación del esquema
  trabajador.py       proceso que vacía la cola de análisis
  crear_cuenta.py     alta de la primera cuenta desde la terminal
  alembic.ini         configuración de migraciones (sin credenciales)
  migraciones/        única fuente de verdad del esquema
  app/
    models/           tablas, en SQLAlchemy
    routers/          endpoints HTTP
    services/         ingesta, RAG, verificación, métricas, límites de cuota
    utils/            extracción de texto y OCR
  tests/              378 pruebas
  storage/pdfs/       PDF subidos, en una carpeta por usuario (no se versionan)
frontend/
  Caddyfile           servidor web, proxy a la API y HTTPS automático
  src/App.jsx         rutas y pantallas
  src/sesion.js       token de sesión y llamadas a la API
  src/components/     interfaz
  src/index.css       tokens de diseño y tema oscuro
database/
  schema.sql          referencia de lectura; el esquema lo gobierna Alembic
docs/
  CONTEXTO.md         qué es, cómo está, qué falta: la visión de conjunto
  Plan_Fase_2.md      los ocho pasos hacia el despliegue
  *.pdf               especificación de métricas y plan de evolución
```

---

## Problemas frecuentes

**`uvicorn : El término 'uvicorn' no se reconoce...`**
El entorno virtual no está activado. Actívalo, o invoca el módulo
directamente: `python -m uvicorn main:app --reload`.

**PowerShell no deja activar el entorno virtual**
Permite los scripts para tu usuario, una sola vez:

```bash
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

**`Failed to fetch` en el navegador**
El frontend no encuentra el backend. Comprueba que responde
—<http://localhost:8000/health> debe devolver `{"ok": true}`— y que
`VITE_API_BASE` en `frontend/.env` apunta a ese puerto. Si el frontend se
sirve desde otro origen, añádelo a `CORS_ORIGENES` en `backend/.env`.

**Error 429 de la API**
Se agotó la cuota. Si es la del minuto, el sistema espera solo; si es la
diaria, no hay espera que valga y conviene pasar a `GEMINI_MODE=mock` hasta
la medianoche del Pacífico.

**El backend avisa de que el esquema está atrasado**
Ejecuta `alembic upgrade head` desde `backend/`.

**Al desplegar, recargar una dirección profunda da 404**
El frontend usa rutas propias (`/proyectos/<id>/brechas`). En desarrollo Vite
las resuelve solo; un servidor estático necesita que todas las rutas
desconocidas devuelvan `index.html`. En nginx:

```bash
try_files $uri /index.html;
```

**El análisis se queda en 0 y no avanza**
No hay ningún trabajador en marcha. El backend solo encola; quien analiza es
`python trabajador.py`, en su propia terminal.

**«Este proyecto ya tiene un análisis en curso» (409)**
Hay una ejecución sin terminar. Si el trabajador está encendido, espera; si
se cayó a mitad, arráncalo otra vez y recogerá lo que quedó pendiente por sí
solo, sin repetir lo ya hecho.

**Las pruebas marcadas `bd` se saltan todas**
No hay conexión a MySQL. Revisa que el servicio esté arriba y que
`MYSQL_URI` sea correcta.

---

## Cuentas

Cada proyecto tiene dueño, y **todo lo demás cuelga del proyecto**: artículos,
ejecuciones, brechas y métricas. Una cuenta solo ve lo suyo.

Crea la primera desde la terminal, en `backend/`:

```bash
python crear_cuenta.py
```

Pide correo, nombre y contraseña —esta última sin mostrarla al escribir— y,
si es la primera cuenta, adopta los proyectos que existieran antes de que
hubiera usuarios.

El alta por HTTP está **cerrada** por defecto (`REGISTRO_ABIERTO=false`). La
cuota de la API es de la clave y se reparte entre todos los usuarios de la
instancia, así que una cuenta de más es cuota de menos para las demás.

Dos decisiones que conviene conocer:

- **Lo ajeno responde 404, no 403.** Un 403 confirmaría que ese identificador
  existe, y con eso se puede averiguar qué hay en la base probando
  identificadores.
- **Un proyecto sin dueño no lo ve nadie.** Los anteriores a las cuentas
  quedaron así; no son "de todos", son de nadie. El fallo es cerrado.

El frontend pide correo y contraseña al entrar y recuerda la sesión ocho
horas. Para salir, el botón *Salir* de los controles de arriba a la derecha.

---

## Estado del proyecto

Funciona de principio a fin en una máquina local y está medido. Lo que
todavía no tiene:

- Despliegue: los PDF se guardan en el disco local y el origen del frontend
  está fijado en el código.
- Anclaje humano de las métricas (N6).

Es decir: sirve como herramienta personal de investigación, no como servicio
publicado. Esos cuatro puntos son, en ese orden, lo que falta para que lo
sea.
