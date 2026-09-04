# Protocolo de validación externa de N2.6

## Pregunta que se evalúa

N2.6 intenta detectar un error concreto: **la brecha presenta como pendiente
algo que el propio artículo ya realizó**. No evalúa si la brecha es interesante,
si está bien redactada ni si resulta correcta en términos generales. Para eso
existe la revisión humana N6.

La unidad de evaluación es una brecha asociada a su artículo. La etiqueta
humana es binaria:

- **Sí, ya lo realizó:** el artículo contiene evidencia de que ejecutó o aportó
  aquello que la brecha formula como trabajo pendiente.
- **No, sigue pendiente:** el artículo no realizó aquello que la brecha propone.

Cada respuesta exige una justificación que señale la sección, página o pasaje
en que se apoya. Una impresión general sin evidencia no constituye una
etiqueta auditable.

## Separación de los datos

Los cinco artículos usados para descubrir el error y diseñar N2.6 son datos de
desarrollo. No pueden usarse para afirmar que la métrica generaliza.

La primera evaluación debe hacerse con un proyecto nuevo de cinco artículos
que no hayan intervenido en ajustes del verificador. Para una evaluación más
sólida se ampliará a 20–30 artículos de más de un área. Si después de ver los
resultados se modifica el prompt, el parser o la regla de N2.6, esos casos pasan
a ser datos de desarrollo y la versión nueva necesita otra muestra reservada.

## Flujo dentro del programa

1. Crear un proyecto con artículos no usados previamente para ajustar N2.6.
2. Analizarlo y ejecutar **Verificar fidelidad** en todas sus brechas.
3. En Resultados, abrir **Validación metodológica de N2.6**.
4. Pulsar **Comenzar revisión ciega**. En ese momento el sistema copia y
   congela la predicción, versión de fórmula y procedencia de cada N2.6.
5. Leer cada PDF y responder la pregunta binaria. Las predicciones no son
   enviadas por la API mientras el lote está abierto.
6. Cuando todas las respuestas estén guardadas, cerrar el lote. Las etiquetas
   quedan bloqueadas y recién entonces se revela la comparación.
7. Informar la matriz de confusión, las proporciones y sus intervalos del 95 %.

Comenzar o completar esta revisión no llama a Gemini ni consume cuota. La
cuota se utiliza antes, al analizar y verificar los artículos.

## Qué se registra

El lote conserva la ejecución evaluada, la persona que etiqueta, la versión del
protocolo, la versión de la fórmula y la procedencia técnica común. Cada caso
conserva la predicción congelada, la etiqueta humana y su justificación.

El lote solo puede iniciarse si todas las brechas tienen N2.6 binaria, con la
fórmula vigente, procedencia registrada y una misma versión del verificador.
Esto evita presentar como una sola evaluación una mezcla de resultados
producidos por configuraciones distintas.

## Lectura de la matriz de confusión

Se toma como caso positivo que **el artículo ya lo realizó**:

| | Juicio humano: sí | Juicio humano: no |
|---|---:|---:|
| N2.6: sí | Verdadero positivo: lo detectó | Falso positivo: alertó sin corresponder |
| N2.6: no | Falso negativo: no lo detectó | Verdadero negativo: lo descartó bien |

Se muestran cuatro proporciones:

- **Exactitud:** decisiones totales que coincidieron con el juicio humano.
- **Sensibilidad:** casos realmente ya resueltos que N2.6 detectó.
- **Especificidad:** casos realmente pendientes que N2.6 descartó bien.
- **Precisión:** alertas emitidas por N2.6 que eran correctas.

Cada proporción incluye un intervalo binomial de Wilson del 95 %. Si no existe
el denominador necesario —por ejemplo, ninguna alerta positiva— la medida queda
como **no calculable**, no como cero. Con menos de 20 casos el programa declara
el resultado exploratorio: una coincidencia alta en cinco casos tiene una
incertidumbre amplia y no demuestra generalización.

## Límites que permanecen

- La primera evaluación puede seguir siendo de una sola persona.
- Un solo proyecto o dominio no demuestra transferencia a otras áreas.
- N2.6 depende de la ventana de evidencia recuperada por el sistema; el juicio
  humano debe leer el artículo, no limitarse a esa ventana.
- Este protocolo valida N2.6. No sustituye N6 ni calibra por sí mismo N3, N5 o
  los umbrales de lectura del panel.
