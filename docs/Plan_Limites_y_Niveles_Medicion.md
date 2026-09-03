# Plan para resolver los límites actuales y guía de niveles N0–N6

**Fecha de revisión:** 1 de septiembre de 2026
**Estado:** propuesta de trabajo; este documento no implica que las tareas estén implementadas.

**Progreso:** pasos 1 a 4 completados el 2 de septiembre de 2026. El versionado,
N1.2 v2 y N2.2 v2 se verificaron con migraciones desde una base MySQL vacía,
`alembic check` y las 461 pruebas sin omisiones. Los documentos históricos se
conservaron sin reescribirlos.

Este documento reúne dos cosas que conviene mantener separadas:

1. El orden recomendado para resolver los límites técnicos y metodológicos que
   siguen abiertos.
2. Una guía breve de qué significa cada nivel `N#` y cada indicador que existe
   actualmente.

La fuente de verdad de las métricas mostradas por la aplicación sigue siendo
`backend/app/services/metricas/catalogo.py`. `docs/Metricas.md` se genera desde
ese catálogo y contiene la explicación extensa de cada indicador. Esta guía no
lo sustituye: sirve como mapa del sistema y plan de trabajo.

## Reglas para realizar los cambios

- No cambiar una fórmula sin registrar su versión. Los valores anteriores no
  deben mezclarse silenciosamente con los nuevos.
- Una medición ausente o no aplicable se guarda y muestra sin valor; nunca como
  cero.
- No definir umbrales de calidad a partir de intuición. Se calibran contra N6 y
  se validan con casos distintos de los usados para diseñarlos.
- Mantener la revisión humana ciega: el anotador no debe ver las métricas ni el
  veredicto automático antes de decidir.
- Verificar cada etapa con MySQL real, migraciones desde una base vacía y la
  suite completa. Los cambios visibles también requieren comprobación del
  frontend en navegador.

## Orden recomendado: de menor a mayor esfuerzo

El versionado aparece antes que algunas correcciones más pequeñas porque es un
prerrequisito: cambiar primero las fórmulas volvería incomparables las mediciones
sin dejar constancia.

### 1. Unificar la documentación vigente

**Estado:** completado el 2 de septiembre de 2026.
**Esfuerzo:** muy bajo, unas horas.
**Dependencias:** ninguna.

**Problema.** Algunas secciones históricas todavía dicen que N6 está pendiente,
aunque el piloto de cinco artículos ya fue anotado. El README también conserva
un recuento antiguo de tablas.

**Solución.** Marcar explícitamente las secciones históricas, corregir las
afirmaciones vigentes y mantener un único bloque de “estado comprobado”. No
reescribir cifras históricas fechadas.

**Criterio de terminado.** README, CONTEXTO y el esquema describen el mismo
estado: 15 tablas funcionales más `alembic_version`, N6 piloto 5/5 y la misma
revisión de Alembic.

### 2. Versionar la procedencia de cada medición

**Estado:** completado y verificado localmente el 2 de septiembre de 2026;
pendiente únicamente de publicación.
**Esfuerzo:** bajo a medio, uno o dos días.
**Dependencias:** debe preceder los pasos 3 y 4.

**Problema.** Solo N3.4 conserva actualmente una versión de fórmula. No queda
unida a cada resultado toda la combinación de fórmula, prompts, modelo y
configuración de recuperación que lo produjo.

**Solución.** Añadir mediante Alembic una instantánea de ejecución que guarde,
como mínimo:

- versión del pipeline y revisión de código;
- modelo de generación y modelo de embeddings;
- versión de los prompts de análisis, síntesis y verificación;
- versión de las fórmulas de métricas;
- parámetros relevantes de fragmentación y recuperación.

La versión de fórmula debe poder consultarse por cada fila de `metrica`. Los
datos antiguos se marcan `legacy` o `desconocida`; no se les inventa una versión
por inferencia. Los resultados continúan vinculados a su `run`.

**Implementación.** La revisión `0010` añade una fotografía técnica tanto a
`run` como a cada `metrica`, porque una verificación o síntesis puede ejecutarse
después del análisis bajo otro despliegue. Cada métrica guarda además su versión
de fórmula. Las respuestas técnicas separan series por código, fórmula y
procedencia; el CSV, JSON, Markdown y los PDF exportados identifican el run y/o
la configuración que produjo sus datos. `APP_REVISION` se inyecta al desplegar;
si no está definida queda como desconocida.

**Criterio de terminado.** Dos mediciones con fórmulas o prompts distintos se
pueden separar mediante una consulta y las exportaciones identifican con qué
versión fueron producidas.

### 3. Corregir N1.2: cobertura seccional

**Estado:** completado y verificado localmente el 2 de septiembre de 2026;
pendiente únicamente de publicación.
**Esfuerzo:** bajo, aproximadamente un día.
**Dependencias:** paso 2.

**Problema.** El denominador actual son todas las secciones sustantivas
teóricas, aunque un artículo real no contenga algunas de ellas.

**Solución.** Usar como denominador las secciones sustantivas efectivamente
detectadas e indexadas en ese artículo. El numerador serán las que aparecieron
en los fragmentos recuperados. Si no se detectó ninguna sección sustantiva, el
resultado será no calculable y se conservará el motivo, no `0.0`. Registrar la
nueva fórmula como N1.2 v2.

**Implementación.** La fórmula toma como denominador las categorías
sustantivas presentes en `embedding_doc` para ese artículo y como numerador su
intersección con los fragmentos recuperados. Guarda ambas listas y sus conteos
en el detalle. El catálogo y la interfaz explican esta lectura y la columna
`version_formula` registra v2.

**Criterio de terminado.** Las pruebas cubren artículos con estructuras
distintas, ausencia de secciones reconocibles y una recuperación parcial. Los
valores v1 y v2 no se mezclan en una misma distribución.

### 4. Precisar N2.1 y corregir N2.2

**Esfuerzo:** bajo a medio, uno o dos días.
**Dependencias:** paso 2.
**Estado:** implementado. `N2.2` quedó registrado como fórmula v2 y las
mediciones anteriores conservan su definición histórica.

**Problema.** El nombre “fidelidad evidencial” puede interpretarse como una
evaluación total de la brecha, aunque N2.1 solo evalúa afirmaciones evidenciales
autónomas. N2.2 divide actualmente entre todas las afirmaciones, incluso las
inferenciales que por diseño pueden no requerir una cita.

**Solución.** Mantener el código estable `N2.1`, pero mostrarlo como “Respaldo de
afirmaciones evidenciales” y explicar su alcance. Para N2.2, usar como
denominador las afirmaciones que realmente deben ser citables —las evidenciales
autónomas— y contar cuántas tienen fragmento y cita válidos. Las afirmaciones
dependientes excluidas deben seguir apareciendo en el detalle. Si no hay ninguna
afirmación elegible, devolver sin valor. Registrar N2.2 v2.

**Criterio de terminado.** Una inferencia legítima sin cita no reduce N2.2; una
afirmación factual sin fragmento sí lo reduce; y la interfaz explica que N2.1 no
decide por sí sola si la brecha completa es correcta.

### 5. Dejar el IQR como descriptivo hasta poder calibrarlo

**Esfuerzo inmediato:** bajo, menos de un día.
**Calibración definitiva:** depende de los pasos 8 y 9.

**Problema.** El mismo umbral `0.05` se usa para métricas con escalas y
distribuciones distintas. La frase “discrimina” o “casi constante” puede parecer
una evaluación metodológica ya validada cuando no lo es.

**Solución inmediata.** Mostrar mediana, P25, P75, IQR y tamaño de muestra, pero
retirar la clasificación universal. Explicar que IQR es la amplitud del 50 %
central de los resultados y no una nota de calidad.

**Solución definitiva.** Después de reunir N6 suficiente, definir reglas
específicas por métrica o conservar el IQR únicamente como estadística
descriptiva si no aporta capacidad predictiva estable.

**Criterio de terminado.** Ningún color o texto convierte `IQR < 0.05` en una
conclusión universal. Un valor puede ser bajo o alto sin ser presentado como
bueno o malo.

### 6. Añadir una base de pruebas del frontend

**Esfuerzo:** medio, entre dos y cuatro días para la primera cobertura útil.
**Dependencias:** ninguna, aunque conviene incorporar los cambios de los pasos
3–5 a los casos de prueba.

**Problema.** La integración continua solo comprueba lint y compilación. No
detecta regresiones de comportamiento en pantalla.

**Solución.** Incorporar Vitest y React Testing Library para componentes y
Playwright para pocos recorridos críticos. Priorizar:

- distinguir cero real de dato no aplicable;
- revisión ciega y revelado solo al completarla;
- creación de proyecto y carga/eliminación de artículos;
- resultados, detalle de métricas y barras de interpretación;
- apertura autenticada del PDF;
- exportaciones y estados de error o cuota.

**Criterio de terminado.** La integración continua falla si se filtra un
veredicto antes de tiempo, si un nulo se muestra como cero o si un recorrido
principal deja de funcionar. La revisión visual manual se conserva para diseño
y accesibilidad.

### 7. Sacar los respaldos fuera de la instancia

**Esfuerzo:** medio, uno o dos días más una prueba de restauración.
**Dependencias:** credenciales de un almacenamiento externo.

**Problema.** Los respaldos actuales están en la misma máquina que MySQL; no
protegen contra pérdida o corrupción completa de la instancia de Oracle.

**Solución.** Copiar cada respaldo cifrado a Oracle Object Storage u otro
almacenamiento independiente, con credenciales de mínimo privilegio. Conservar,
por ejemplo, siete copias diarias y cuatro semanales. Registrar fallos y probar
mensualmente la restauración en una base temporal.

**Criterio de terminado.** Se puede eliminar una base temporal, restaurarla
solo desde la copia externa y comprobar conteos y relaciones principales. Una
falla de respaldo produce una alerta visible.

### 8. Validar N2.6 con datos no usados para construirla

**Esfuerzo:** medio en código, pero varios días de lectura y anotación.
**Dependencias:** congelar antes la versión del verificador y del prompt.

**Problema.** N2.6 detectó los dos casos que motivaron su creación. Eso confirma
que reproduce el patrón conocido, no que generalice.

**Solución.** Congelar la versión actual y evaluar primero un proyecto nuevo de
cinco artículos sin ajustar el prompt al ver los resultados. La revisión humana
se hace a ciegas. Registrar verdaderos positivos, falsos positivos, falsos
negativos y verdaderos negativos. Como evidencia más sólida, ampliar luego a
20–30 artículos de más de un área y separar los casos de desarrollo de los de
validación.

**Criterio de terminado.** Se informa la matriz de confusión y sus intervalos de
incertidumbre; no solo cuántos casos coincidieron. Cualquier ajuste posterior
crea una versión nueva y se vuelve a evaluar sobre casos no usados para el
ajuste.

### 9. Ampliar N6 y calibrar N3, N5 e IQR

**Esfuerzo:** alto; normalmente varias semanas por la participación humana.
**Dependencias:** pasos 2 y 8.

**Problema.** Hay cinco juicios de una sola persona. No se puede calcular
acuerdo entre anotadores ni derivar umbrales confiables para N3.2, N3.3, N5.3,
N5.5 o para la lectura del IQR.

**Solución de evaluación.** Preparar un protocolo escrito y un conjunto más
amplio y diverso. Dos investigadores anotan de forma independiente y ciega;
los desacuerdos se resuelven después, sin borrar los juicios originales. Con dos
anotadores se puede calcular kappa ponderado; con más, usar una medida adecuada
como Krippendorff alfa. El puntaje 1/0.5/0 se informa junto con los conteos, no
como única cifra.

No hace falta construir ahora permisos e invitaciones multiusuario. En esta
etapa puede usarse un paquete de evaluación ciego y una importación controlada.
El flujo completo de colaboración pertenece a una fase posterior.

**Solución de calibración.** Con las etiquetas humanas:

- comprobar si N3.2 y N3.3 realmente separan brechas correctas de genéricas;
- anotar manualmente qué brechas aparecen en la síntesis para calibrar el
  umbral de N5.3;
- anotar citas reales e inventadas para medir precisión y recall de N5.5;
- estimar reglas por métrica con validación separada o validación cruzada;
- informar intervalos de confianza y conservar como descriptiva cualquier
  métrica que no muestre relación estable con N6.

**Criterio de terminado.** Existe acuerdo entre anotadores reportado, las reglas
se probaron fuera de los datos usados para elegirlas y el panel solo presenta
como “alto/bajo” aquello que tenga respaldo empírico.

### 10. Preparar escalabilidad solo cuando las mediciones lo justifiquen

**Esfuerzo:** alto, entre una y varias semanas si se requiere migrar el índice
vectorial.
**Dependencias:** evidencia de que el volumen actual ya produce problemas.

**Problema.** Los embeddings se leen desde MySQL y la similitud se calcula en
Python por fuerza bruta. Es coherente para proyectos pequeños de 5–10 artículos,
pero no para grandes corpus o muchos usuarios simultáneos.

**Solución gradual.** Primero medir latencia, memoria, número de fragmentos y
concurrencia. Añadir paginación e índices relacionales donde corresponda. Solo
si se supera un límite acordado —por ejemplo, búsquedas que excedan de forma
sostenida el tiempo objetivo— trasladar la búsqueda a un motor vectorial con
índice aproximado, manteniendo MySQL como fuente de verdad y los identificadores
de trazabilidad.

**Criterio de terminado.** La decisión de migrar se apoya en pruebas de carga;
la nueva búsqueda mantiene aislamiento por usuario/proyecto, trazabilidad y una
calidad de recuperación comparable a la actual.

## Qué significa cada nivel N#

`N#` representa una capa de evaluación del flujo. `N#.x` es un indicador dentro
de esa capa. Los huecos de numeración son deliberados o históricos: si un código
no aparece abajo, no debe suponerse que existe actualmente.

| Nivel | Pregunta que responde | Naturaleza |
|---|---|---|
| **N0 — Ingesta** | ¿El PDF se convirtió en texto utilizable? | Diagnóstico técnico previo al análisis. |
| **N1 — Recuperación** | ¿Qué partes del artículo llegaron al modelo? | Calidad del contexto RAG. |
| **N2 — Fidelidad** | ¿Lo que afirma la brecha se sostiene en el artículo? | Verificación y trazabilidad. |
| **N3 — Especificidad** | ¿La brecha es concreta y distinta para ese artículo? | Comparación textual y semántica. |
| **N4 — Resumen** | ¿Cómo se relaciona el resumen generado con el abstract? | Solape, significado y descripción léxica. |
| **N5 — Tipificación y síntesis** | ¿Cómo se clasifican y reúnen las brechas en el estado del arte? | Cobertura y control de referencias. |
| **N6 — Anclaje humano** | ¿Un investigador que leyó el artículo considera correcta la brecha? | Juicio humano, no cálculo automático. |

### N0 — Calidad de ingesta

N0 es operativo y todavía no forma parte del catálogo de 23 métricas mostrado
en el panel.

- **N0.1 Cobertura de extracción:** compara los caracteres extraídos con una
  cantidad esperada según las páginas del PDF.
- **N0.2 Ratio de truncamiento:** indica qué proporción del texto bruto quedó
  después de limpiar y cortar referencias o límites de tamaño.
- **N0.3 Secciones reconocidas:** registra qué secciones, como método,
  resultados o discusión, pudieron identificarse.
- **N0.4 Legibilidad:** estima si el texto extraído parece prosa en español o
  inglés y no ruido de OCR.

### N1 — Recuperación

- **N1.2 Cobertura seccional:** proporción de las secciones sustantivas
  detectadas e indexadas en ese artículo que estuvo presente en el contexto
  entregado al modelo.
- **N1.3 Diversidad del contexto:** mide si los fragmentos recuperados aportan
  contenido diferente o repiten la misma idea.

### N2 — Fidelidad y trazabilidad

- **N2.1 Respaldo de afirmaciones evidenciales:** proporción de afirmaciones
  evidenciales autónomas respaldadas por los fragmentos consultados. No evalúa
  por sí sola la corrección total de la brecha.
- **N2.2 Trazabilidad:** proporción de afirmaciones evidenciales autónomas
  vinculadas a un fragmento y una cita comprobable. La fórmula v2 excluye las
  inferencias que no necesitan cita y queda sin valor si no hay elegibles.
- **N2.4 Composición evidencial:** qué parte de la brecha describe hechos del
  artículo frente a inferencias. Es descriptiva; ni cero ni uno son
  universalmente mejores.
- **N2.5 Contradicciones:** proporción de afirmaciones a las que el artículo
  contradice. Menor es mejor.
- **N2.6 Brecha ya resuelta:** indica si la brecha pide como trabajo futuro algo
  que el artículo ya realizó. Cero significa no detectada y uno detectada.
- **N2.verificada Verificación realizada:** indica si la verificación pudo
  ejecutarse. Si no se ejecutó, debe conservarse el motivo y no fingir un cero.

### N3 — Especificidad

- **N3.1 Discriminabilidad:** cuánto se diferencian las brechas de artículos
  distintos del proyecto.
- **N3.2 Densidad de anclajes:** cantidad de cifras, siglas, nombres y términos
  metodológicos por cada 100 palabras.
- **N3.3 Contenido informativo:** rareza media de los términos de la brecha en el
  corpus del proyecto, expresada mediante IDF.
- **N3.4 Redundancia:** proporción de brechas casi idénticas a otra. Menor es
  mejor; la fórmula vigente marca ambos miembros de una pareja duplicada.

### N4 — Resumen

- **N4.1a ROUGE-1 precisión:** parte de las palabras del resumen que también
  aparece en el abstract.
- **N4.1b ROUGE-1 recall:** parte del vocabulario relevante del abstract que fue
  recuperada en el resumen.
- **N4.1c ROUGE-1 F1:** equilibrio entre la precisión y el recall de palabras.
- **N4.1d ROUGE-2 F1:** solape de pares de palabras consecutivas.
- **N4.1e ROUGE-L F1:** similitud basada en la subsecuencia común más larga.
- **N4.2 Similitud semántica:** cercanía de significado entre resumen y
  abstract; puede ser útil aunque estén en idiomas distintos.
- **N4.4 Densidad léxica:** proporción de palabras con contenido en el resumen.
  Es descriptiva, no una nota de calidad.
- **N4.ref Abstract localizado:** indica si el abstract real pudo extraerse. Si
  no existe, ROUGE queda no aplicable.

ROUGE solo se interpreta cuando resumen y abstract están en el mismo idioma.
Un valor ausente por idioma o falta de abstract no equivale a cero.

### N5 — Tipificación y síntesis

- **N5.2 Reetiquetado automático:** frecuencia con la que la heurística de
  palabras clave cambia el tipo asignado por el modelo. Es descriptiva hasta
  compararla con etiquetas humanas.
- **N5.3 Cobertura de la síntesis:** proporción de brechas representadas en el
  estado del arte generado.
- **N5.5 Citas sin correspondencia:** proporción de referencias de la síntesis
  que no puede vincularse a un artículo del proyecto. Menor es mejor.

### N6 — Anclaje humano

N6 no lo calcula el sistema. Una persona que revisó el artículo marca la brecha
como:

- **correcta:** 1 punto;
- **parcial:** 0.5 puntos y justificación obligatoria;
- **incorrecta:** 0 puntos y justificación obligatoria.

También se conserva si el juicio provino de lectura directa o de una revisión
asistida. La tabla permite una fila por persona y brecha, pero con un solo
anotador únicamente puede informarse un piloto; no existe todavía acuerdo entre
jueces.

## Resultado esperado del plan

Al terminar los pasos 1–7, el sistema será más reproducible y seguro sin
cambiar todavía las conclusiones metodológicas. Los pasos 8 y 9 producirán la
evidencia necesaria para afirmar qué métricas se relacionan de verdad con el
juicio de investigadores. El paso 10 solo debe ejecutarse si el uso real supera
la escala para la que fue diseñada la arquitectura actual.
