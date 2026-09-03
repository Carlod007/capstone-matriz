# Métricas, nivel por nivel

**Este documento se genera.** No lo edites a mano: sale de
`backend/app/services/metricas/catalogo.py`, que es lo que la aplicación sirve
al panel. Para actualizarlo:

```bash
cd backend && python scripts/generar_doc_metricas.py
```

Un documento escrito al lado del código se desincroniza en cuanto alguien añade
una métrica, y aquí ya ha costado caro tener dos verdades para un mismo hecho.

---

## Cómo leer cualquiera de ellas

**Mediana y recorrido intercuartílico, no promedio.** Con pocos artículos un
caso extremo arrastra la media entera. Una mediana de 0.86 con dispersión nula
y otra con dispersión amplia dicen cosas opuestas.

**La dirección no es la misma en todas.** `↓ menor es mejor` significa que un
valor alto es un problema. Leerlas todas como «más es mejor» invierte el
sentido de varias.

**Sin valor no es cero.** Una métrica que no aplica —ROUGE entre idiomas
distintos, por ejemplo— se declara no aplicable. Un cero afirmaría que el
resultado fue pésimo.

**«Separa los casos» habla del instrumento, no del proyecto.** Dice si esa
métrica distingue unos artículos de otros. Un resultado excelente y parejo en
todos sale como «valores parecidos», y no es una mala noticia.

**No hay umbrales de calidad.** No existen valores calibrados que digan qué es
bueno en este dominio: por eso el panel no pinta zonas verdes ni rojas. Eso es
lo que N6 viene a resolver.

---

## N1 — Recuperación

Qué fragmentos llegaron al modelo. Si aquí falla algo, todo lo demás mide sobre un texto equivocado.

### N1.2 · Cobertura seccional

**Qué mide.** Qué proporción de las secciones sustantivas detectadas e indexadas en ese artículo llegó al modelo.

**Por qué importa.** Un valor bajo significa que el análisis dejó fuera secciones útiles que sí estaban disponibles. Si no se reconoció ninguna sección sustantiva, la métrica no es calculable.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v2 |

### N1.3 · Diversidad del contexto

**Qué mide.** Cuánto se diferencian entre sí los fragmentos entregados al modelo.

**Por qué importa.** Si es baja, el contexto repite la misma idea y desaprovecha la ventana disponible.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

## N2 — Fidelidad

Si lo que dice la brecha se sostiene en el artículo. Es la capa que distingue esta herramienta de pedirle un resumen a un chatbot.

### N2.1 · Respaldo de afirmaciones evidenciales

**Qué mide.** Qué proporción de las afirmaciones evidenciales autónomas de la brecha está respaldada por los fragmentos consultados del artículo.

**Por qué importa.** Evalúa el respaldo de afirmaciones factuales, no la corrección total de la brecha. Una conclusión puede ser discutible aunque sus evidencias estén respaldadas, y una afirmación sin respaldo en la ventana puede aparecer en otra parte del PDF.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N2.2 · Trazabilidad

**Qué mide.** Proporción de afirmaciones evidenciales autónomas que pueden vincularse a un fragmento y una cita comprobables.

**Por qué importa.** Mide si las afirmaciones factuales son auditables. Las inferencias se excluyen porque no siempre requieren una cita propia; si no hay ninguna afirmación elegible, la métrica no es calculable.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v2 |

### N2.4 · Composición evidencial

**Qué mide.** Qué parte de la brecha describe hechos del artículo, frente a la que solo concluye.

**Por qué importa.** Una brecha compuesta unicamente por conclusiones no tiene nada que verificar: es especulación bien redactada, y un valor muy bajo avisa de ello aunque la fidelidad salga alta por apoyarse en una sola afirmación. Pero un valor muy alto tampoco es la meta: una brecha que solo describe lo que el artículo dice no señala ningún vacío. Se describe la proporción y no se premia ninguna: cuál es la buena es justo lo que hace falta anotación humana para saber.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | descriptiva (no hay valor mejor) |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N2.5 · Contradicciones

**Qué mide.** Proporción de afirmaciones de la brecha a las que algún fragmento del artículo lleva la contraria.

**Por qué importa.** No es la inversa de la fidelidad y pesa más: una afirmación sin respaldo significa que el artículo no habla de eso; una contradicha significa que dice lo opuesto. Se comprueban también las inferenciales, que no se verifican pero sí pueden ser incompatibles con lo que el artículo afirma. La primera detección real fue una generalización: la brecha afirmaba que omitir ciertos factores «resulta en una subestimación de la capacidad», y el artículo advierte que en un régimen concreto ocurre lo contrario.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↓ menor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N2.6 · Brecha ya resuelta

**Qué mide.** Si la brecha pide como pendiente algo que el propio artículo ya hizo.

**Por qué importa.** Es el error que ninguna otra métrica puede ver. Los artículos motivan su aportación explicando qué faltaba antes, así que una brecha que repite esa motivación en futuro sale con todas sus afirmaciones respaldadas: se detectó anotando a mano, y una de las dos brechas afectadas tenía fidelidad 1.000. El fallo no está en ninguna frase suelta sino en el tiempo verbal del conjunto.

| | |
|---|---|
| Escala | 0 o 1 |
| Dirección | ↓ menor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N2.verificada · Verificación realizada

**Qué mide.** Si la comprobación de fidelidad llegó a ejecutarse.

**Por qué importa.** Requiere una llamada adicional al modelo. Cuando no se ejecuta se guarda el motivo: una medición que no se hizo no equivale a una medición con resultado cero.

| | |
|---|---|
| Escala | 0 o 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

## N3 — Especificidad

Si las brechas distinguen un artículo de otro o son intercambiables.

### N3.1 · Discriminabilidad

**Qué mide.** Cuánto se diferencian las brechas de artículos distintos del mismo proyecto.

**Por qué importa.** Es la métrica más diagnóstica: si el modelo emite la misma brecha genérica para todos los artículos, este valor se desploma.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | el análisis completo |
| Versión de fórmula | v1 |

### N3.2 · Densidad de anclajes

**Qué mide.** Cifras, nombres propios, siglas y vocabulario metodológico en la brecha.

**Por qué importa.** Distingue «faltan estudios en contextos diversos» de «no hay validación externa en cohortes latinoamericanas».

| | |
|---|---|
| Escala | por 100 palabras |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N3.3 · Contenido informativo

**Qué mide.** Cuán poco frecuentes son los términos de la brecha dentro del corpus.

**Por qué importa.** Un valor alto indica vocabulario específico; uno bajo, lugares comunes.

| | |
|---|---|
| Escala | IDF medio |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N3.4 · Redundancia

**Qué mide.** Proporción de brechas casi idénticas a otra del proyecto.

**Por qué importa.** Debería ser cero. Valores altos indican que el modelo repite hallazgos.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↓ menor es mejor |
| Se calcula sobre | el análisis completo |
| Versión de fórmula | v2 |

## N4 — Resumen

Calidad del resumen generado frente al abstract.

### N4.1a · ROUGE-1 precisión

**Qué mide.** Qué proporción de las palabras del resumen aparece en el abstract.

**Por qué importa.** Penaliza que el resumen añada contenido ausente en el original. Solo se calcula si ambos están en el mismo idioma.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N4.1b · ROUGE-1 recall

**Qué mide.** Solape de palabras entre el resumen generado y el abstract del artículo.

**Por qué importa.** Solo se calcula si ambos están en el mismo idioma: entre idiomas distintos daría casi cero con independencia de la calidad.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N4.1c · ROUGE-1 F1

**Qué mide.** Equilibrio entre precisión y exhaustividad del solape de palabras.

**Por qué importa.** Misma condición de idioma que el recall.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N4.1d · ROUGE-2 F1

**Qué mide.** Solape de pares de palabras consecutivas.

**Por qué importa.** Más exigente que ROUGE-1: premia que se conserve la formulación.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N4.1e · ROUGE-L F1

**Qué mide.** Subsecuencia común más larga entre resumen y abstract.

**Por qué importa.** Tolera que el resumen intercale palabras, a diferencia de ROUGE-2.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N4.2 · Similitud semántica

**Qué mide.** Cercanía de significado entre el resumen y el abstract.

**Por qué importa.** Capta la paráfrasis correcta que ROUGE penaliza, y es la única de las dos que sigue siendo válida cuando están en idiomas distintos.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N4.4 · Densidad léxica

**Qué mide.** Proporción de palabras con contenido frente al total.

**Por qué importa.** Es una estadística descriptiva, no una nota: una densidad alta no implica un resumen mejor.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | descriptiva (no hay valor mejor) |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N4.ref · Abstract localizado

**Qué mide.** Si se pudo extraer el abstract real del PDF.

**Por qué importa.** Sin él no se calcula ROUGE, para no producir una cifra sin significado.

| | |
|---|---|
| Escala | 0 o 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | cada artículo |
| Versión de fórmula | v1 |

## N5 — Síntesis

El estado del arte: qué cubre y si inventa citas.

### N5.2 · Reetiquetado automático

**Qué mide.** Con qué frecuencia un contador de palabras clave sobrescribe el tipo que asignó el modelo.

**Por qué importa.** Un valor alto significa que la etiqueta final la decide una heurística y no el modelo. Conviene saberlo antes de dar por buena la tipificación, pero no se declara ninguna dirección: nunca se comprobó si esa heurística acierta más o menos que el modelo, y decir «menos es mejor» —como estaba— daba por supuesto que estorba. Con tipos anotados a mano se podrá saber cuál de los dos acierta.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | descriptiva (no hay valor mejor) |
| Se calcula sobre | cada brecha |
| Versión de fórmula | v1 |

### N5.3 · Cobertura de la síntesis

**Qué mide.** Qué proporción de las brechas del lote está representada en el estado del arte.

**Por qué importa.** Detecta que la síntesis ignore artículos. Con diez brechas de entrada y una redacción que recoge seis, el texto parece completo y no lo está.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↑ mayor es mejor |
| Se calcula sobre | el proyecto completo |
| Versión de fórmula | v1 |

### N5.5 · Citas sin correspondencia

**Qué mide.** Proporción de referencias del estado del arte que no corresponde a ningún artículo del proyecto.

**Por qué importa.** El prompt prohíbe inventar citas y hasta ahora nada verificaba que se cumpliera. Referencias inventadas son el fallo más grave posible en una herramienta de revisión de literatura.

| | |
|---|---|
| Escala | 0 a 1 |
| Dirección | ↓ menor es mejor |
| Se calcula sobre | el proyecto completo |
| Versión de fórmula | v1 |

## N6 — Anclaje humano

No aparece arriba porque **no la calcula el sistema**. La aporta quien se ha
leído los artículos, desde la pantalla «Tu revisión de las brechas».

Cada brecha se marca como **correcta**, **parcial** —acierta el problema y
falla en un matiz, vale medio punto— o **incorrecta**, y las dos últimas exigen
explicación escrita. Sin el motivo, el dato dice que algo falló pero no qué: no
sirve para corregir el sistema ni para sostener la evaluación.

Los veredictos viven en `validacion_humana`, con una fila por (brecha,
persona), de modo que el acuerdo entre jueces se pueda calcular el día que haya
más de un anotador.

**La limitación que hay que declarar:** con un solo anotador no existe acuerdo
entre jueces. Y validar un modelo de lenguaje con otro modelo de lenguaje es
circular: sirve para localizar pasajes, no para juzgar.
