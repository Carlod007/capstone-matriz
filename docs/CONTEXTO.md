# Contexto completo del proyecto

Documento único de referencia: qué es esto, cómo está construido, en qué
estado se encuentra y qué falta. Escrito para que alguien que no ha visto el
repositorio —persona o herramienta— pueda opinar con criterio sin tener que
reconstruirlo leyendo código.

**Si vienes a retomar el trabajo, empieza por la sección 0.** Dice dónde se
quedó todo, qué se hizo lo último y qué toca ahora.

**Actualizado:** 19 de agosto de 2026
**Rama de trabajo:** `CarlosDev` · **Rama principal:** `main` (33 commits por
detrás — todo el trabajo vive en `CarlosDev`, conviene fusionar antes de seguir)

**Referencia de métricas:** [`Metricas.md`](Metricas.md), generado desde el
catálogo del código. Es la fuente vigente; el PDF de especificación es anterior
a N2.5.

---

## 0. Dónde nos quedamos

*Esta sección se actualiza al cerrar cada avance. Es lo primero que hay que
leer al retomar el proyecto o al abrir una conversación nueva.*

**Última actualización:** 29 de agosto de 2026 · commit `ceef6b3`

### Estado comprobado

| | |
|---|---|
| Integración continua | verde, **417 pruebas** |
| Servidor | `ceef6b3`, contenedores en marcha, HTTPS |
| Respaldos | diarios, verificados |
| Rama `main` | **35 commits por detrás** de `CarlosDev` |
| Anotación humana (N6) | **0 de 5 brechas** |

**La construcción está terminada.** El sistema hace de punta a punta lo que
prometía: ingesta, RAG, brechas, verificación de fidelidad, detección de
contradicciones, síntesis, métricas, exportaciones, cuentas, cola y despliegue.
No hay funcionalidad pendiente de construir.

### Lo último que se hizo

Una revisión externa encontró cinco problemas reales, todos ciertos. Se
corrigieron en una primera etapa:

- **N2.5 y la ventana ampliada no estaban en el análisis normal**, solo al
  reverificar a la fuerza. La construcción de la ventana pasa a un servicio
  compartido, `ventana_evidencia.py`, que usan los dos recorridos.
- **N5.3 y N5.5 se calculaban y el panel no las encontraba**: se guardan contra
  el identificador del estado del arte, que no estaba entre las referencias
  consultadas. Ahora se incluye, atado al análisis vigente.
- **El resumen de N6 mezclaba ejecuciones**: contaba todas las brechas
  históricas del proyecto aunque la pantalla mostrara solo las del último
  análisis.
- **`anotadores` era la constante 1**: un campo que decía contar y no contaba.
  Ahora cuenta personas reales.

### Lo siguiente, en este orden

1. **Fusionar `main`.** Todo vive en `CarlosDev` desde hace 35 commits.
2. **Anotar las 5 brechas.** No cuesta cuota y desbloquea la mitad de la lista:
   sin juicio humano no se puede calibrar nada.
3. **Afinar métricas** — etapas 2 a 6 del plan, detalladas en la deuda de más
   abajo. El versionado de fórmulas va primero: `N1.2`, `N2.2` y `N3.4` cambian
   de significado numérico y mezclar mediciones viejas con nuevas falsearía el
   historial.

### Lo que se sabe que está mal y aún no se ha tocado

- `N3.4` marca solo el segundo elemento de cada pareja duplicada: tres brechas
  idénticas dan 0.667 en vez de 1.0, y el resultado depende del orden.
- `N2.4` declara «mayor es mejor» y `N5.2` «menor es mejor», sin que ninguna de
  las dos direcciones esté demostrada.
- `N1.2` divide entre seis secciones teóricas y no entre las que el artículo
  realmente tiene.
- El umbral de IQR `0.05` se aplica igual a métricas con escalas distintas.
- **Cero pruebas de frontend.** La integración continua pasa lint y compila,
  nada más. Todos los fallos de interfaz encontrados hasta ahora los vio una
  persona mirando la pantalla.

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

16 tablas. `usuario` → `proyecto` → (`articulo`, `run`) → (`run_item`,
`archivo`) → (`resultado_brecha`, `embedding_doc`, `metrica`, `rag_log`,
`estado_arte`, `resultado_resumen`, `articulo_meta`, `llamada_api`), y
`validacion_humana` colgando de `resultado_brecha` y de `usuario`.

**Todo cuelga del proyecto**, y el proyecto tiene dueño: esa única columna
(`proyecto.usuario_id`) es la que separa las cuentas.

`validacion_humana` es la excepción deliberada: apunta a la persona que emite
el juicio y no al dueño del proyecto, porque su razón de ser es poder tener
varios anotadores sobre la misma brecha.

---

## 3. Estado actual

### Funciona y está probado

- Ingesta de PDF con OCR de respaldo y detección de secciones
- RAG real: recuperación por relevancia con diversidad y cuota por sección
- Análisis de brechas con cita del fragmento de origen
- **Verificación de fidelidad** (N2): afirmaciones evidenciales contrastadas
- **Detección de contradicciones** (N2.5): afirmaciones a las que un fragmento
  lleva la contraria, incluidas las conclusiones, que no se verifican pero sí
  pueden ser incompatibles con lo que el artículo afirma
- **Anotación humana** (N6): pantalla de revisión con veredicto y justificación
  por brecha, guardando quién lo emitió
- Síntesis de estado del arte
- Siete niveles de métricas (22 en el catálogo), con distribución (mediana + IQR)
- Exportación: matriz PDF/JSON, brechas CSV, estado del arte MD, panel PDF
- Cuentas, sesión por token, aislamiento entre usuarios
- Cola de trabajos con reintentos y recuperación de trabajadores caídos
- Limitador de cuota propio (ventana deslizante) antes de chocar con la API
- **417 pruebas automáticas**, integración continua en verde
- Esquema gobernado por Alembic, verificado desde base vacía

### Verificado con datos reales

Cinco artículos de ingeniería descargados de Scopus, en modo real:

| Medida | Resultado |
|---|---|
| Extracción de resumen | 5/5 (era 0/5 antes de las correcciones) |
| N4.ref abstract localizado | 5 de 5 |
| N2.verificada | 5 de 5 |
| N1.2 cobertura seccional | mediana 0.500 (IQR 0.167) |
| N2.1 fidelidad | mediana 0.714 (IQR 0.333) |
| N2.2 trazabilidad | mediana 0.625 |
| N2.5 contradicciones | 1 detectada sobre 39 afirmaciones |
| N3.1 discriminabilidad | 0.399 |
| N4.2 similitud semántica | mediana 0.905 (IQR 0.009) |
| N4.1a–e ROUGE | no aplicable: resumen y abstract en idiomas distintos |
| N5.2 reetiquetado | mediana 1.0 — *menor es mejor*: 4 de 5 brechas |

**La contradicción detectada**, porque ilustra lo que la capa aporta: la brecha
afirmaba que omitir ciertos factores «resulta en una subestimación de la
capacidad», y el artículo advierte que en un régimen concreto ocurre lo
contrario («*the DNV standard still produces some dangerous results under small
bending moments*»). Las dos cosas son ciertas en regímenes distintos y la
brecha presentaba una como si valiera siempre. Ese fragmento no estaba entre
los ocho originales: apareció al ampliar la ventana a los párrafos contiguos.

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

1. **N6: el anclaje humano ya tiene dónde vivir, pero falta anotar.**
   *(Herramienta construida; el dato depende de leer los artículos.)*

   La pantalla «Tu revisión de las brechas» permite marcar cada una como
   correcta, parcial o incorrecta con su justificación, y guarda quién la
   emitió y cuándo. Los veredictos van en `validacion_humana`, una tabla
   aparte de `estado_validacion` —que es de la validación automática
   desactivada— para no dejar dos verdades conviviendo, y con una fila por
   (brecha, persona) para poder medir el acuerdo entre jueces el día que haya
   más de uno.

   **La limitación que queda es de método, no de código:** con un solo
   anotador no hay acuerdo entre jueces. La pantalla lo dice en su cabecera en
   lugar de esconderlo, porque es lo primero que pregunta un tribunal. Lo
   defendible con un solo autor es anotar con protocolo escrito, antes de
   mirar las métricas del sistema, y declarar la limitación.

   *No usar otro modelo de lenguaje para contrastar.* Validar un LLM con otro
   LLM es circular y anula el capítulo entero. Sirve para localizar pasajes;
   el juicio tiene que ser humano.
2. **La ventana de evidencia son unos pocos fragmentos, no el artículo.**
   *(Resuelto en parte: N2.5 ya detecta contradicciones y la ventana se amplió
   a los párrafos contiguos. Se conserva porque el límite de fondo sigue.)*

   La verificación se hace contra los fragmentos recuperados, así que una
   afirmación cuya prueba —a favor o en contra— viva fuera de ellos es
   indetectable por diseño. El troceado agrava el problema cortando a mitad de
   frase: en un caso real el fragmento entregado empezaba por «*, particularly
   for MLPs, as it neglects material hardening…*» y el trozo anterior, no
   entregado, terminaba con «*the DNV formula **underestimates** the
   load-bearing capacity*». Faltaban las palabras que decidían la dirección del
   error.

   **Corrección de una versión anterior de este documento.** Aquí se afirmaba
   que el sistema había alucinado al escribir «posibles diseños inseguros»,
   porque *unsafe* no aparecía en el artículo. Era la palabra equivocada: el
   artículo dice, literalmente, «*even with the safety factor considered, the
   DNV standard still produces some **dangerous** results under small bending
   moments*». La brecha era correcta y el ejemplo estaba mal. Se deja escrito
   porque ilustra el riesgo de dar por falsa una afirmación buscando un término
   y no el concepto, que es exactamente el error que N2.5 puede cometer al
   revés.

   Lo que sí encontró N2.5 al ampliar la ventana: la afirmación «la omisión de
   estos factores resulta en una subestimación de la capacidad» quedó marcada
   como contradicha por ese mismo fragmento. Es un buen hallazgo — el artículo
   sostiene las dos cosas en regímenes distintos, conservador en general y
   peligroso a momentos flectores pequeños, y la brecha lo generalizaba.
3. ~~**Aviso de SQLAlchemy**~~ *(resuelto: `estado_arte.py` y `metrics.py`
   pasan la subconsulta con `.select()` explícito).*
4. ~~**Sin renovación silenciosa de sesión**~~ *(resuelto).* La sesión se
   renueva sola cada media hora y al volver a la pestaña, así que ya no corta
   a mitad de un formulario. Con un techo absoluto de siete días desde que se
   escribió la contraseña: sin él, encadenar renovaciones volvería permanente
   cualquier token filtrado, y aquí no hay revocación.
5. **Cuota compartida.** *(Mitigado, no resuelto.)* Los 20 análisis diarios
   del nivel gratuito son de la **clave** de Gemini, no del usuario, y eso no
   se puede cambiar desde aquí: repartir no crea capacidad.

   Lo que faltaba era poder repartirla. El consumo se atribuye ahora a cada
   cuenta —a través del dueño del proyecto— y existe un tope por cuenta,
   `LIMITE_GENERACION_DIA_USUARIO`, que se comprueba **antes** de encolar. Nace
   en cero, es decir desactivado: con una sola persona el techo real es el de
   la clave y un segundo tope solo estorbaría.

   El alta sigue cerrada por decisión, pero abrirla ya no significa regalar el
   día al primero que llegue.

### Sobre la numeración: no hay Fase 3

Las fases se nombraron sobre la marcha, no de un plan previo. La 1 fue poner
los cimientos —Alembic como fuente única del esquema, README que instala desde
cero, integración continua—; la 2, pasar de herramienta local a servicio
accesible desde un enlace. «Fase 4» se escribió en `Plan_Fase_2.md` para
etiquetar lo que se apartaba a propósito, y ese salto dejó el hueco.

No se definió ninguna Fase 3, no se canceló y no falta nada por ella. Se
documenta aquí porque el hueco invita a buscar un plan perdido que no existe.

### Fase 4 — abrir el sistema a más usuarios *(aplazada por decisión)*

No está empezada, y no la bloquea la arquitectura: las cuentas, el aislamiento
entre ellas y el reparto de cuota ya están. Lo que falta es lo que convierte
una herramienta personal en un servicio de cara al público.

| Pendiente | Por qué hace falta |
|---|---|
| **Cuota que no dependa de una sola clave** | Hoy las 20 generaciones diarias son de la clave de Gemini. Repartirlas entre cuentas evita que una se lleve el día, pero no crea capacidad: con varios usuarios reales hace falta una clave de pago o una por cuenta. |
| **Facturación** | Si hay clave de pago, alguien paga. Sin un modelo de cobro, abrir el alta es asumir un coste abierto. |
| **Textos legales** | Se suben PDF con derechos de autor y se guardan correos. Términos de uso y política de privacidad dejan de ser opcionales en cuanto entra alguien que no sea el autor. |
| **Registro abierto y recuperación de contraseña** | `REGISTRO_ABIERTO` existe pero está en `false`, y no hay forma de recuperar una contraseña olvidada: hoy la resolvería el autor a mano. |
| **Borrado de cuenta y de datos** | Un usuario debe poder irse con sus datos. Hoy se puede borrar un artículo, no una cuenta. |

**No se empieza hasta que N6 esté anclado.** Sin saber si el sistema acierta,
abrirlo a desconocidos es repartir un resultado que nadie ha comprobado.

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
  integración continua, 417 pruebas, aislamiento entre cuentas probado
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

| Archivo | Contenido | Vigencia |
|---|---|---|
| `README.md` | Instalación desde cero, arranque, problemas frecuentes | al día |
| `docs/Metricas.md` | **Las 22 métricas una por una**, con escala y dirección | se genera desde el catálogo |
| `docs/Despliegue_Oracle_Cloud.pdf` | Qué se hizo en el servidor y qué falló | al día |
| `docs/Plan_Fase_2.md` | Plan de los ocho pasos hacia el despliegue | histórico: se ejecutó entero |
| `docs/Especificacion_Capa_Medicion_v2.pdf` | Por qué se rehízo la medición | **anterior a N2.5**: no es el listado actual |
| `docs/Plan_Evolucion_Tecnica_Matriz_IAG.pdf` | Diagnóstico inicial y hoja de ruta | histórico |
| `backend/migraciones/README` | Cómo cambiar el esquema | al día |

Los marcados como históricos se conservan a propósito: describen decisiones en
su momento y sirven para entender por qué el código tiene la forma que tiene.
Leerlos como estado actual lleva a conclusiones equivocadas, y por eso la
columna de vigencia.

`Metricas.md` se regenera con:

```bash
cd backend && python scripts/generar_doc_metricas.py
```
