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
- [Instalación desde cero](#instalación-desde-cero)
- [Arrancar el sistema](#arrancar-el-sistema)
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

## Arrancar el sistema

Hacen falta tres cosas encendidas: MySQL, el backend y el frontend.

**MySQL** — el servicio de Windows suele arrancar solo. Para comprobarlo:

```bash
Get-Service -Name MySQL* | Select-Object Name, Status
```

**Backend** — desde `backend/`, con el entorno virtual activado:

```bash
python -m uvicorn main:app --reload --port 8000
```

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
4. **Analizar todo**: genera las brechas de cada artículo.
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

Son 238 pruebas y corren en modo simulado, sin gastar cuota. Las que
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
- ejecuta `alembic check` y las 238 pruebas contra esa base recién creada,
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
backend/
  main.py             arranque de FastAPI y comprobación del esquema
  alembic.ini         configuración de migraciones (sin credenciales)
  migraciones/        única fuente de verdad del esquema
  app/
    models/           tablas, en SQLAlchemy
    routers/          endpoints HTTP
    services/         ingesta, RAG, verificación, métricas, límites de cuota
    utils/            extracción de texto y OCR
  tests/              238 pruebas
  storage/pdfs/       PDF subidos (no se versionan)
frontend/
  src/components/     interfaz
  src/index.css       tokens de diseño y tema oscuro
database/
  schema.sql          referencia de lectura; el esquema lo gobierna Alembic
docs/                 especificación de métricas y plan de evolución
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
`VITE_API_BASE` en `frontend/.env` apunta a ese puerto. Si el backend está en
otro origen, hay que añadirlo a la lista de CORS en `backend/main.py`.

**Error 429 de la API**
Se agotó la cuota. Si es la del minuto, el sistema espera solo; si es la
diaria, no hay espera que valga y conviene pasar a `GEMINI_MODE=mock` hasta
la medianoche del Pacífico.

**El backend avisa de que el esquema está atrasado**
Ejecuta `alembic upgrade head` desde `backend/`.

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

- Ejecución en segundo plano: el análisis bloquea la petición HTTP.
- Despliegue: los PDF se guardan en el disco local y el origen del frontend
  está fijado en el código.
- Anclaje humano de las métricas (N6).

Es decir: sirve como herramienta personal de investigación, no como servicio
publicado. Esos cuatro puntos son, en ese orden, lo que falta para que lo
sea.
