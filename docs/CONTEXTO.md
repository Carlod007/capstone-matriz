# Contexto completo del proyecto

Documento único de referencia: qué es esto, cómo está construido, en qué
estado se encuentra y qué falta. Escrito para que alguien que no ha visto el
repositorio —persona o herramienta— pueda opinar con criterio sin tener que
reconstruirlo leyendo código.

**Si vienes a retomar el trabajo, empieza por la sección 0.** Dice dónde se
quedó todo, qué se hizo lo último y qué toca ahora.

**Actualizado:** 30 de agosto de 2026
**Rama de trabajo:** `CarlosDev` · **Rama principal:** `main`, al día
(las dos apuntan al mismo commit)

**Referencia de métricas:** [`Metricas.md`](Metricas.md), generado desde el
catálogo del código. Es la fuente vigente; el PDF de especificación es anterior
a N2.5 y N2.6.

---

## 0. Dónde nos quedamos

*Esta sección se actualiza al cerrar cada avance. Es lo primero que hay que
leer al retomar el proyecto o al abrir una conversación nueva.*

**Última actualización:** 3 de septiembre de 2026

### Estado comprobado

| | |
|---|---|
| Backend | **462 pruebas** en verde contra MySQL real temporal, `alembic check` verde |
| Frontend | **6 pruebas de componentes + 3 recorridos en navegador**, lint y compilación en verde |
| Migraciones | hasta `0010` |
| Rama de trabajo | `CarlosDev`; la integración en `main` sigue pendiente |
| Anotación humana (N6) | **5 de 5**, prueba piloto |

**La construcción está terminada.** No hay funcionalidad pendiente. Lo que
queda es afinar la medición con evidencia.

### El resultado de anotar, y lo que destapó

Las cinco brechas del proyecto de prueba se revisaron: **tres correctas y dos
parciales**, acierto ponderado **0.80**.

El número importa menos que lo que salió de las justificaciones. **Las dos
parciales fallaban por lo mismo**: presentaban la aportación del propio
artículo como si fuera un vacío abierto. Una pedía desarrollar una fórmula que
el artículo ya había desarrollado y validado; la otra planteaba como pendiente
la integración que el artículo demuestra en su título.

**Ninguna métrica podía verlo**, y menos que ninguna la fidelidad: los
artículos motivan su aportación explicando qué faltaba antes, así que esas
frases están en el texto y salen respaldadas una a una. Una de las dos brechas
tenía `N2.1 = 1.000`.

También se comprobó lo contrario: **ninguna métrica separa las correctas de las
parciales**. `N2.2` v1 incluso iba al revés — sus dos valores más bajos
correspondían a brechas correctas—, antes de corregir su denominador. Por eso
**no se movió ningún umbral**: con cinco casos se puede detectar un umbral
claramente mal puesto, y no había ninguno. Lo que había era una métrica que
faltaba.

### `N2.6`, y hasta dónde llega lo que demuestra

De ese hallazgo salió una comprobación nueva: **¿la brecha pide como pendiente
algo que el artículo ya hizo?** Como en `N2.5`, sin un fragmento que lo
demuestre no se acepta — decir que una brecha ya está resuelta la invalida
entera.

Reverificado en modo real sobre las mismas cinco brechas:

| Tu juicio | `N2.6` | `N2.1` |
|---|---|---|
| correcta | no | 1.000 |
| **parcial** | **sí** | 0.833 |
| **parcial** | **sí** | 0.875 |
| correcta | no | 1.000 |
| correcta | no | 1.000 |

**Dos de dos, sin falsos positivos.** Y lo que más pesa: el juez señaló la
frase exacta donde cada artículo anuncia su aportación —«*To overcome these
limitations, a new empirical formulation was developed*» y «*To overcome the
limitations of current hybrid models…, we proposed the EINN framework*»—. No
acertó por casualidad: encontró la prueba correcta.

**Lo que esto NO demuestra.** La métrica se escribió a partir de esos dos
casos, así que detectarlos confirma que la implementación captura el patrón
descrito, no que generalice. La prueba real es un proyecto con artículos que no
ha visto, y es la primera pregunta que hará un tribunal.

Lo defendible con estos datos: *se detectó un modo de fallo por revisión
humana, se implementó una comprobación específica, y reprodujo el diagnóstico
sobre los mismos casos*. Es un ciclo DSRM completo, declarando el alcance.

`N2.1` del EINN bajó de 1.000 a 0.875 en esta corrida. No es un empeoramiento:
la ventana incluye ahora los párrafos contiguos, se evalúan más afirmaciones y
una quedó sin respaldo. Medir más fino baja los números.

### Revisión a ciegas

La anotación estaba **debajo del panel de métricas**, así que quien bajaba a
anotar ya había visto que el sistema se daba un 1.000 de fidelidad. Juzgar
después de eso no es juzgar, es confirmar — y entonces comparar las dos
columnas deja de medir el acierto del sistema para medir su eco.

Pasa a una pantalla propia, `/proyectos/:id/revisar`, con solo la brecha, el
artículo y el enlace al PDF.

**La ceguera la impone el servidor.** Mientras falten brechas, el backend no
envía el acierto ni el desglose por veredicto: devuelve `null`. Ocultarlo en el
frontend no bastaría —el dato habría viajado igual y cualquiera podría leerlo—,
y la ceguera dejaría de ser una propiedad del procedimiento para ser una
decisión de maquetación.

Se reserva también el conteo por veredicto: saber que se llevan cuatro
«correcta» condiciona la quinta tanto como el porcentaje. Y si se retira un
veredicto, el resultado vuelve a ocultarse; de lo contrario bastaría anotar
todo y borrar uno para verlo.

Al terminar aparece la comparación brecha por brecha contra `N2.1`, `N2.5` y
`N2.6`. Es el momento en que las dos columnas se ven por primera vez, y solo
entonces significan algo.

Ocho pruebas nuevas, verificadas contra MySQL en la integración continua. El
cambio dejó una lección: el primer intento salió rojo porque `acierto` pasó de
significar «lo acertado hasta ahora» a «el resultado, cuando lo hay», y dos
pruebas antiguas lo comprobaban a mitad de anotar. Cambiar el significado de un
dato rompe a quien dependía del anterior, aunque el cálculo siga siendo
correcto; las dos pruebas se reescribieron sobre la regla nueva en vez de
borrarlas, porque lo que protegían —que una brecha parcial valga medio punto—
sigue vigente.

### Lo demás que se hizo

- **Visor del artículo**: el PDF entraba al sistema y no volvía a salir. Ahora
  se abre desde la pantalla de anotación, de modo que se juzga contra la misma
  versión que el sistema analizó.
- **Origen de cada revisión** (`0009`): si el veredicto se emitió leyendo el
  artículo o con ayuda de una herramienta. Las dos formas cuentan igual en el
  porcentaje; es un dato del procedimiento, y sin registrarlo se pierde.
- **`N3.4` contaba mal**: marcaba solo el segundo elemento de cada pareja, así
  que tres brechas idénticas daban 0.667 y el resultado dependía del orden.
  Ahora marca los dos, con orden fijo y **versión de fórmula** en el detalle.
- **`N2.4` y `N5.2` pasan a descriptivas.** Declaraban una dirección que nadie
  había comprobado.
- **Procedencia reproducible** (`0010`): cada ejecución y cada métrica nueva
  guarda revisión del código, modelos, versiones de prompts y parámetros de
  recuperación. Cada métrica conserva además su versión de fórmula. Los datos
  anteriores quedan como legado/desconocido; no se les inventa procedencia.
- **`N1.2` usa el artículo real (fórmula v2):** el denominador ya no son seis
  categorías teóricas, sino las secciones sustantivas detectadas e indexadas
  en cada PDF. Sin secciones reconocibles queda sin valor y explica el motivo.
- **`N2.1` declara su alcance y `N2.2` usa fórmula v2:** el respaldo se nombra
  como lo que realmente es —afirmaciones evidenciales autónomas contrastadas
  contra la ventana consultada— y no como corrección total de la brecha. La
  trazabilidad ya no penaliza inferencias que no necesitan cita; si no hay
  afirmaciones elegibles, queda sin valor. Las fórmulas históricas no se
  mezclan con la actual.
- **El IQR vuelve a ser descriptivo:** se conservan mediana, P25, P75, IQR y
  tamaño de muestra, pero se retiró el umbral universal `0.05`. Ya no se afirma
  que una métrica «separa los casos» o es «casi constante» sin una calibración
  específica contra revisión humana N6.
- **El frontend ya tiene una red de seguridad automática:** seis pruebas de
  componentes fijan los estados de métricas, la revisión ciega y la sesión;
  tres recorridos Playwright comprueban creación, eliminación y apertura
  autenticada del PDF. La integración continua los ejecuta en cada `push`.

### Lo siguiente, en este orden

1. **Paso 7:** sacar los respaldos fuera de la instancia de Oracle y comprobar
   una restauración desde esa copia externa.

### Lo que se sabe que está mal y aún no se ha tocado

- **Cobertura de frontend todavía inicial.** Ya protege los recorridos de mayor
  riesgo conocidos, pero faltan casos automáticos para carga de archivos,
  exportaciones y estados de error o cuota. El diseño y la accesibilidad siguen
  requiriendo revisión visual humana.

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

15 tablas funcionales, más `alembic_version`. `usuario` → `proyecto` →
(`articulo`, `run`) → (`run_item`,
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
- **Brecha ya resuelta** (N2.6): si la brecha pide como pendiente algo que el
  propio artículo ya hizo. Es el único error que no se ve mirando afirmación
  por afirmación, porque cada una está respaldada y lo que falla es el tiempo
  verbal del conjunto
- **Anotación humana** (N6): pantalla de revisión con veredicto y justificación
  por brecha, guardando quién lo emitió y cómo se revisó
- **Visor del artículo**: el PDF original se abre desde la pantalla de
  anotación, para juzgar contra la misma versión que el sistema analizó
- Síntesis de estado del arte
- Siete niveles de métricas (23 en el catálogo), con distribución (mediana + IQR)
- Exportación: matriz PDF/JSON, brechas CSV, estado del arte MD, panel PDF
- Cuentas, sesión por token, aislamiento entre usuarios
- Cola de trabajos con reintentos y recuperación de trabajadores caídos
- Limitador de cuota propio (ventana deslizante) antes de chocar con la API
- **462 pruebas automáticas de backend**, verificadas localmente contra MySQL real
- **6 pruebas de componentes y 3 recorridos críticos de frontend**
- Esquema gobernado por Alembic, verificado desde base vacía

### Verificado con datos reales

Cinco artículos de ingeniería descargados de Scopus, en modo real:

| Medida | Resultado |
|---|---|
| Extracción de resumen | 5/5 (era 0/5 antes de las correcciones) |
| N4.ref abstract localizado | 5 de 5 |
| N2.verificada | 5 de 5 |
| N1.2 cobertura seccional v1 (histórica) | mediana 0.500 (IQR 0.167) |
| N2.1 respaldo evidencial | mediana 0.714 (IQR 0.333) |
| N2.2 trazabilidad v1 (histórica) | mediana 0.625 |
| N2.5 contradicciones | 1 detectada sobre 39 afirmaciones |
| N2.6 brecha ya resuelta | 2 de 5, coincidiendo con las dos que un humano marcó como parciales |
| N3.1 discriminabilidad | 0.399 |
| N4.2 similitud semántica | mediana 0.905 (IQR 0.009) |
| N4.1a–e ROUGE | no aplicable: resumen y abstract en idiomas distintos |
| N5.2 reetiquetado | mediana 1.0 — *descriptiva*: 4 de 5 brechas |
| **N6 acierto humano** | **0.80** — 3 correctas, 2 parciales (prueba piloto) |

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

**Las métricas publicadas en el artículo académico no medían lo declarado.**
Tres causas apiladas: la referencia para ROUGE era la portada del PDF y no el
resumen; se comparaba español contra inglés, donde ROUGE es cero por
construcción; y varias métricas devolvían prácticamente el mismo valor en los
casos estudiados. Se rehízo la capa entera (v2, siete niveles). Aquellas
métricas se retiraron tras revisar su diseño; el IQR actual se informa como
descriptivo y no decide por sí solo qué conservar.

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

1. **N6: el piloto está anotado; falta ampliar la evidencia.**
   *(Cinco brechas, una persona y todavía sin acuerdo entre jueces.)*

   La pantalla «Tu revisión de las brechas» permite marcar cada una como
   correcta, parcial o incorrecta con su justificación, y guarda quién la
   emitió y cuándo. Los veredictos van en `validacion_humana`, una tabla
   aparte de `estado_validacion` —que es de la validación automática
   desactivada— para no dejar dos verdades conviviendo, y con una fila por
   (brecha, persona) para poder medir el acuerdo entre jueces el día que haya
   más de uno.

   El piloto de cinco brechas ya terminó: tres correctas y dos parciales, con
   acierto ponderado 0.80. **La limitación que queda es de método, no de
   código:** con un solo anotador no hay acuerdo entre jueces y cinco casos no
   permiten generalizar. La pantalla lo declara en lugar de esconderlo. El
   siguiente paso defendible es revisar artículos nuevos con el mismo protocolo
   ciego y, después, incorporar un segundo juicio independiente.

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

**No se empieza hasta que N6 supere el piloto actual.** Ya existe un primer
anclaje, pero cinco casos y un solo anotador no justifican abrir el resultado a
desconocidos. Antes hace falta probar artículos nuevos y ampliar el juicio
humano.

---

## 6. Cómo juzgar este proyecto

Si el objetivo es **nivel académico sólido**, lo que más pesa:

- La capa de medición v2 y la distinción entre afirmación evidencial e
  inferencial son el aporte real, y están documentadas en
  `Especificacion_Capa_Medicion_v2.pdf`.
- **El punto flojo sigue siendo N6, pero ya no está vacío.** Hay una prueba
  piloto de cinco brechas con acierto 0.80, y de ella salió una métrica nueva
  (`N2.6`) que reprodujo el diagnóstico humano. Lo que falta es alcance: cinco
  casos, un anotador y sin acuerdo entre jueces. Un tribunal preguntará por
  eso, y la respuesta honesta es declararlo como limitación en vez de
  presentarlo como validación.
- **`N2.6` está probada sobre los casos que la originaron.** Detectarlos
  confirma que la implementación captura el patrón, no que generalice; hace
  falta un proyecto con artículos que no haya visto.
- La honestidad metodológica está cuidada: las métricas que no aplican se
  declaran no aplicables (ROUGE entre idiomas) y el IQR se muestra sin una
  clasificación universal hasta disponer de calibración humana suficiente.

Si el objetivo es **proyecto profesional presentable**, lo que más pesa:

- **A favor:** desplegado y accesible con HTTPS, migraciones con Alembic,
  integración continua, 462 pruebas, aislamiento entre cuentas probado
  endpoint por endpoint, cola de trabajos con reintentos, copias de seguridad
  programadas y un README que instala desde cero.
- Lo que se echa en falta: dominio propio en lugar de un nombre derivado de la
  IP, y observabilidad (hoy los fallos se ven mirando registros a mano).
- Queda pendiente la deuda enumerada arriba: ampliar N6, probar N2.6 con casos
  nuevos y calibrar las métricas que todavía no tienen respaldo humano.

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
| `docs/Metricas.md` | **Las 23 métricas una por una**, con escala y dirección | se genera desde el catálogo |
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
