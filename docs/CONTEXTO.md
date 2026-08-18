# Contexto completo del proyecto

Documento único de referencia: qué es esto, cómo está construido, en qué
estado se encuentra y qué falta. Escrito para que alguien que no ha visto el
repositorio —persona o herramienta— pueda opinar con criterio sin tener que
reconstruirlo leyendo código.

**Actualizado:** 14 de agosto de 2026
**Rama de trabajo:** `CarlosDev` · **Rama principal:** `main` (unos 30 commits
por detrás)

---

## 1. Qué es y para qué sirve

Herramienta que lee artículos científicos en PDF y ayuda a un investigador a
responder dos preguntas: **qué se ha hecho ya** en su tema y **qué falta por
hacer**. Produce una matriz de brechas —limitaciones, vacíos metodológicos,
líneas abiertas— y un borrador de estado del arte.

Proyecto de capstone universitario. La metodología declarada en el artículo
académico asociado es **DSRM** (Design Science Research Methodology).

**Lo que lo distingue de pedirle un resumen a un chatbot** es la capa de
verificación: cada afirmación generada se contrasta contra el texto fuente y
las que no se sostienen quedan señaladas. Sobre los cinco artículos de la
primera prueba real, **tres de cinco brechas contenían al menos una afirmación
sin respaldo** —una inventaba una condición experimental que el artículo no
mencionaba—. Sin esa capa, esas tres habrían llegado al investigador con
apariencia de hecho.

**Uso previsto:** herramienta personal de investigación, con posibilidad de
abrirla a más usuarios más adelante. No es un servicio publicado.

---

## 2. Arquitectura

| Capa | Tecnología |
|---|---|
| Backend | FastAPI · SQLAlchemy 2.0 · PyMySQL |
| Base de datos | MySQL 8, esquema gobernado por Alembic |
| Frontend | React 19 · Vite 7 · Tailwind 4 |
| Modelos | Gemini (`gemini-2.5-flash`, `gemini-embedding-001`) vía `google-genai` |
| Trabajo de fondo | Proceso propio (`trabajador.py`) sobre cola en la propia base |

### Piezas que hay que levantar

MySQL · backend (`uvicorn`) · **trabajador** (`python trabajador.py`) ·
frontend (`npm run dev`). Sin el trabajador, los análisis se encolan y no
avanzan.

### Cadena de procesamiento

```
PDF → ingesta (texto + OCR si hace falta + detección de secciones)
    → indexado (fragmentos → embeddings)
    → recuperación (MMR + cuota por sección)
    → análisis (brechas, citando el fragmento de origen)
    → verificación (afirmación por afirmación contra el texto)
    → estado del arte (síntesis del conjunto)
    → medición (7 niveles de métricas)
```

### Modelo de datos

15 tablas. `usuario` → `proyecto` → (`articulo`, `run`) → (`run_item`,
`archivo`) → (`resultado_brecha`, `embedding_doc`, `metrica`, `rag_log`,
`estado_arte`, `resultado_resumen`, `articulo_meta`, `llamada_api`).

**Todo cuelga del proyecto**, y el proyecto tiene dueño: esa única columna
(`proyecto.usuario_id`) es la que separa las cuentas.

---

## 3. Estado actual

### Funciona y está probado

- Ingesta de PDF con OCR de respaldo y detección de secciones
- RAG real: recuperación por relevancia con diversidad y cuota por sección
- Análisis de brechas con cita del fragmento de origen
- **Verificación de fidelidad** (N2): afirmaciones evidenciales contrastadas
- Síntesis de estado del arte
- Siete niveles de métricas, con distribución (mediana + IQR)
- Exportación: matriz PDF/JSON, brechas CSV, estado del arte MD, panel PDF
- Cuentas, sesión por token, aislamiento entre usuarios
- Cola de trabajos con reintentos y recuperación de trabajadores caídos
- Limitador de cuota propio (ventana deslizante) antes de chocar con la API
- **328 pruebas automáticas**, integración continua en verde
- Esquema gobernado por Alembic, verificado desde base vacía

### Verificado con datos reales

Cinco artículos de ingeniería descargados de Scopus, en modo real:

| Medida | Resultado |
|---|---|
| Extracción de resumen | 5/5 (era 0/5 antes de las correcciones) |
| Cobertura de secciones | 65 % (era 42 %) |
| N3.1 discriminabilidad | 0.345 |
| N5.3 cobertura de síntesis | 1.0 |
| N5.5 citas fabricadas | 0.0 |
| N2 fidelidad | 3 de 5 brechas con una afirmación sin respaldo |

---

## 4. Historia técnica que conviene conocer

No son anécdotas: explican por qué el código tiene la forma que tiene, y
evitan que alguien "arregle" algo que ya se arregló por una razón.

**Las métricas publicadas en el artículo académico no medían nada.** Tres
causas apiladas: la referencia para ROUGE era la portada del PDF y no el
resumen; se comparaba español contra inglés, donde ROUGE es cero por
construcción; y varias métricas eran cuasi-constantes. Se rehízo la capa
entera (v2, siete niveles) y las cuasi-constantes se retiran en lugar de
exhibirse.

**La "R" de RAG no existía.** `get_top_chunks()` devolvía los primeros ocho
fragmentos por posición, así que el modelo solo leía resumen e introducción, y
nunca método, resultados ni discusión. Eso explica por qué los resultados
salían casi idénticos entre artículos.

**Tres fuentes de verdad para un solo esquema.** Los modelos, `schema.sql` y
`ALTER TABLE` sueltos, y ninguna coincidía: los modelos no declaraban ni una
de las catorce claves foráneas reales. Ahora manda Alembic, y una prueba
comprueba en cada ejecución que modelos y base siguen de acuerdo.

**La validación automática está desactivada a propósito.** Sus umbrales
estaban por debajo del piso de ruido, de modo que casi todo terminaba en
"aceptada" sin haber sido validado. Un estado honesto ("pendiente") es
preferible a un sello de goma. Volverá cuando haya juicio experto con el que
calibrarla (N6).

**Otros hallazgos ya corregidos:** `text-embedding-004` retirado por Google
(el sistema habría estado roto en modo real); desfase de huso horario entre
MySQL y Python que ponía el contador de cuota a cero; deduplicación de PDF por
hash que era global y con varias cuentas habría filtrado artículos ajenos.

---

## 5. Lo que falta

### Fase 2 — para que se use desde un enlace y en el celular

| Paso | Estado |
|---|---|
| 1. Usuarios y sesión | ✅ hecho |
| 2. Propiedad de los datos | ✅ hecho |
| 3. Cola en segundo plano | ✅ hecho |
| 4. Almacenamiento tras una interfaz | ✅ hecho |
| 5. Configuración por entorno (CORS, secretos) | ✅ hecho |
| 6. Rutas en el frontend | ✅ hecho |
| 7. Docker | ✅ hecho |
| 8. Despliegue | ✅ hecho |

**Fase 2 cerrada.** El sistema vive en un servidor Oracle Cloud (nivel Always
Free, coste cero) en **https://147-224-233-59.sslip.io**, con certificado de
Let's Encrypt que Caddy renueva solo, arranque automático comprobado con un
reinicio real, y copia de seguridad diaria de la base con rotación de siete
días. El detalle completo, incluidos los cinco problemas que aparecieron y
cómo se resolvieron, está en `Despliegue_Oracle_Cloud.pdf`.

`docker compose up` levanta las cinco piezas —MySQL, migraciones, backend,
trabajador y frontend— y aplica el esquema solo. Verificado de extremo a
extremo: alta de cuenta, sesión, creación de proyecto, aislamiento entre
cuentas, CORS y rutas profundas del frontend.

En Windows conviene limitar WSL con un `.wslconfig`: sin él se reserva la
mitad de la RAM de la máquina y no la devuelve.

**Infraestructura:** máquina Oracle Cloud "Always Free" (4 OCPU ARM, 24 GB) en
Chile West, con Docker Compose y Caddy. Coste cero y permanente.

### Deuda conocida, en orden de importancia

1. **N6 sin anclaje humano.** Falta un conjunto de brechas anotado por
   expertos. Hasta entonces las métricas dicen si el sistema es *consistente*,
   no si *acierta*. Es la mayor debilidad de cara a una defensa académica.
2. **N2 no detecta contradicciones.** Comprueba si una afirmación evidencial
   está respaldada, pero una inferencia que *contradice* la fuente queda fuera
   del cálculo por diseño. Medido con datos reales: sobre un artículo de
   tuberías el sistema escribió «posibles diseños inseguros» cuando el
   artículo califica el estándar de conservador y la palabra *unsafe* no
   aparece en el texto. Contradecir es peor que no estar respaldado.
3. **Aviso de SQLAlchemy** en `estado_arte.py:44` (subconsulta sin `select()`
   explícito). Inofensivo hoy, romperá en una versión futura.
4. **Sin renovación silenciosa de sesión.** A las ocho horas hay que volver a
   entrar, y si eso ocurre a mitad de algo, se pierde lo que hubiera en el
   formulario. La dirección sí se recuerda.
5. **Cuota compartida.** Los 20 análisis diarios del nivel gratuito son de la
   clave, no del usuario: con el registro abierto, unos pocos desconocidos
   dejarían al dueño sin cuota. Por eso el alta está cerrada.

### Aplazado por decisión explícita

Cuotas por usuario, facturación y textos legales (Fase 4). El autor no
pretende publicarlo abiertamente por ahora.

---

## 6. Cómo juzgar este proyecto

Si el objetivo es **nivel académico sólido**, lo que más pesa:

- La capa de medición v2 y la distinción entre afirmación evidencial e
  inferencial son el aporte real, y están documentadas en
  `Especificacion_Capa_Medicion_v2.pdf`.
- **El punto flojo es N6**: sin conjunto anotado por expertos no se puede
  afirmar que el sistema acierta, solo que es consistente. Un tribunal
  preguntará por eso.
- La honestidad metodológica está cuidada: las métricas que no aplican se
  declaran no aplicables (ROUGE entre idiomas) y las cuasi-constantes se
  retiran.

Si el objetivo es **proyecto profesional presentable**, lo que más pesa:

- **A favor:** desplegado y accesible con HTTPS, migraciones con Alembic,
  integración continua, 328 pruebas, aislamiento entre cuentas probado
  endpoint por endpoint, cola de trabajos con reintentos, copias de seguridad
  programadas y un README que instala desde cero.
- Lo que se echa en falta: dominio propio en lugar de un nombre derivado de la
  IP, y observabilidad (hoy los fallos se ven mirando registros a mano).
- Queda pendiente la deuda enumerada arriba, con N6 a la cabeza.

---

## 7. Convenciones del repositorio

- **Idioma:** todo en español —código, comentarios, mensajes de commit,
  nombres de tabla—. Los comentarios explican *por qué*, no *qué*.
- **Esquema:** solo se cambia con Alembic. `database/schema.sql` es lectura.
- **Pruebas:** en modo simulado, sin gastar cuota. Las que necesitan MySQL van
  marcadas `bd` y se saltan solas si no hay base.
- **Secretos:** `.env` nunca se versiona. `JWT_SECRETO` no tiene valor por
  defecto: sin él, el backend se niega a arrancar.
- **Commits:** título y descripción explicando el porqué del cambio.

## 8. Documentos relacionados

| Archivo | Contenido |
|---|---|
| `README.md` | Instalación desde cero, arranque, problemas frecuentes |
| `docs/Plan_Fase_2.md` | Plan de los ocho pasos hacia el despliegue |
| `docs/Especificacion_Capa_Medicion_v2.pdf` | Los siete niveles de métricas |
| `docs/Plan_Evolucion_Tecnica_Matriz_IAG.pdf` | Diagnóstico inicial y hoja de ruta |
| `backend/migraciones/README` | Cómo cambiar el esquema |
