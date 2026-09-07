/**
 * Traducción del estado técnico a palabras útiles para quien investiga.
 *
 * Se mantiene fuera de App para que las mismas fases gobiernen la tarjeta, la
 * navegación y el seguimiento del análisis sin repetir condiciones distintas.
 */

const FASES_CON_RESULTADOS = new Set([
  "generando_estado_arte",
  "resultados_listos",
  "estado_arte_fallido",
  "analisis_listo",
]);

export function destinoProyecto(proyecto) {
  if (proyecto?.estado_proceso === "analizando") return "articulos";
  if (FASES_CON_RESULTADOS.has(proyecto?.estado_proceso)) return "brechas";
  if (proyecto?.n_brechas > 0 || proyecto?.tiene_estado_arte) return "brechas";
  return "articulos";
}

export function presentarProyecto(proyecto) {
  const articulos = proyecto?.n_articulos ?? proyecto?.articulos_count ?? 0;

  switch (proyecto?.estado_proceso) {
    case "analizando":
      return {
        tono: "acento",
        etiqueta: "Analizando artículos",
        valor: "En curso",
        apoyo: "El proceso continúa en segundo plano",
        mensaje: "Puedes salir de esta pantalla; el análisis continuará en el servidor.",
        accion: "Ver avance",
        puedeVerSintesis: false,
      };
    case "generando_estado_arte":
      return {
        tono: "acento",
        etiqueta: "Generando estado del arte",
        valor: "Sintetizando",
        apoyo: "Las brechas ya están disponibles",
        mensaje: "Ya puedes revisar las brechas mientras se redacta la síntesis final.",
        accion: "Ver resultados",
        puedeVerSintesis: false,
      };
    case "resultados_listos":
      return {
        tono: "bien",
        etiqueta: "Estado del arte listo · ver",
        valor: "Resultados listos",
        apoyo: "Brechas y síntesis disponibles",
        mensaje: "Puedes revisar la matriz de brechas y la síntesis generada.",
        accion: "Abrir proyecto",
        puedeVerSintesis: true,
      };
    case "estado_arte_fallido":
      return {
        tono: "aviso",
        etiqueta: "Síntesis no generada",
        valor: "Brechas listas",
        apoyo: "La síntesis necesita reintentarse",
        mensaje: "El análisis terminó y las brechas se conservan; solo falló la síntesis final.",
        accion: "Ver resultados",
        puedeVerSintesis: false,
      };
    case "analisis_listo":
      return {
        tono: "bien",
        etiqueta: "Análisis terminado",
        valor: "Completado",
        apoyo: "Brechas disponibles para revisar",
        mensaje: "Puedes revisar las brechas y las métricas del análisis.",
        accion: "Ver resultados",
        puedeVerSintesis: false,
      };
    default:
      return {
        tono: "neutro",
        etiqueta: "Sin analizar",
        valor: "Pendiente",
        apoyo: articulos
          ? "Ejecuta el análisis cuando estén listos los artículos"
          : "Primero incorpora los artículos",
        mensaje: articulos
          ? "Revisa los documentos incorporados y ejecuta el análisis para obtener las brechas."
          : "Sube tus artículos para comenzar a construir la matriz de brechas.",
        accion: "Abrir proyecto",
        puedeVerSintesis: false,
      };
  }
}

export function presentarAvance(estado, total, quieto = false) {
  const hecho = estado?.n_items_ok ?? 0;
  const cantidad = estado?.n_items_total ?? total;

  if (estado?.fase === "generando_estado_arte") {
    return {
      etapa: "Generando estado del arte",
      hecho: cantidad,
      total: cantidad,
      detalle: "Las brechas ya están listas. Se está redactando la síntesis final.",
      termino: false,
    };
  }
  if (estado?.fase === "resultados_listos" || estado?.fase === "analisis_listo") {
    return { termino: true, exito: true };
  }
  if (estado?.fase === "estado_arte_fallido") {
    return { termino: true, exito: false, soloSintesis: true };
  }
  if (estado?.estado === "fallido" || estado?.fase === "fallido") {
    return { termino: true, exito: false, soloSintesis: false };
  }

  // Compatibilidad durante un despliegue: un backend anterior no devuelve
  // `fase`; en ese breve intervalo conserva el comportamiento previo.
  if (!estado?.fase && estado?.estado === "completado") {
    return { termino: true, exito: true };
  }

  return {
    etapa: "Analizando artículos",
    hecho,
    total: cantidad,
    detalle: quieto
      ? "Este artículo está tardando más de lo habitual; el proceso continúa en segundo plano."
      : "Puedes cerrar esta página; el análisis sigue en el servidor.",
    termino: false,
  };
}

export function presentarBorradoProyecto(proyecto) {
  const articulos = proyecto?.n_articulos ?? proyecto?.articulos_count ?? 0;
  const brechas = proyecto?.n_brechas ?? proyecto?.brechas_count ?? 0;
  const tieneResultados = Boolean(
    brechas > 0 ||
    proyecto?.tiene_estado_arte ||
    ["generando_estado_arte", "resultados_listos", "estado_arte_fallido",
      "analisis_listo"].includes(proyecto?.estado_proceso)
  );

  if (tieneResultados) {
    return {
      nivel: "alto",
      titulo: "Este proyecto ya tiene resultados",
      detalle:
        `Se eliminarán permanentemente ${articulos} ${articulos === 1 ? "archivo PDF" : "archivos PDF"}, ` +
        "sus brechas, resúmenes, métricas, revisiones y estados del arte.",
      aviso:
        "No se puede deshacer. La cuota de API que ya se consumió tampoco se recupera.",
    };
  }
  if (articulos > 0) {
    return {
      nivel: "medio",
      titulo: "Este proyecto contiene documentos",
      detalle:
        `Se eliminarán ${articulos} ${articulos === 1 ? "PDF subido" : "PDF subidos"} ` +
        "junto con el proyecto. Todavía no hay resultados que perder.",
      aviso: "No se puede deshacer, pero podrás volver a subir esos documentos en otro proyecto.",
    };
  }
  return {
    nivel: "bajo",
    titulo: "Este proyecto está vacío",
    detalle: "Solo se eliminarán el tema, el objetivo y la configuración del proyecto.",
    aviso: "No hay PDF ni resultados asociados.",
  };
}
