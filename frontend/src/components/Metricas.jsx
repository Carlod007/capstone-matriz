import { useEffect, useState } from "react";

/**
 * Presentación de la capa de medición v2.
 *
 * El panel anterior mostraba entropía, similitud y score de validación, que
 * son las tres métricas retiradas: llegaban siempre en cero y la interfaz
 * parecía averiada sin estarlo.
 *
 * Aquí se aplican dos criterios:
 *
 * 1. Cada métrica se muestra con su nombre y su dirección de lectura. No
 *    todas mejoran al subir, y pintar de verde lo que va mal es peor que no
 *    pintar nada.
 * 2. Se muestra el rango intercuartílico junto a la mediana como descripción
 *    de la muestra. No se compara con un umbral universal: sus escalas son
 *    distintas y todavía no existe calibración suficiente contra N6.
 */

import { api } from "../sesion";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

/* ---------------------------------------------------------------- utilidades */
function fmt(v, decimales = 3) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toFixed(decimales);
}

/**
 * La métrica de cabecera: ¿está respaldado por el artículo?
 *
 * Va sola y a todo lo ancho porque es la pregunta que decide si el resto del
 * panel merece atención. Faltaba entre las destacadas, aunque el explorador ya
 * arranca seleccionándola y hay un botón dedicado a calcularla: la lectura
 * rápida omitía justo lo que el resto del programa trata como principal.
 */
const CABECERA = "N2.1";

/** Métricas destacadas en las tarjetas inferiores, por orden de interés. */
const DESTACADAS = ["N3.1", "N1.2", "N3.2", "N4.2"];

/**
 * Preguntas de lectura para las cuatro métricas que resumen el recorrido.
 *
 * No cambian ni clasifican el dato: traducen la descripción del catálogo a la
 * pregunta que se hace un investigador al leer el panel. Mediana, IQR y n
 * siguen llegando del servidor sin añadir una calificación.
 */
const GUIA_DESTACADAS = {
  "N2.1": {
    pregunta: "¿Las afirmaciones factuales se apoyan en los fragmentos consultados?",
    lectura: "Más alto = más afirmaciones evidenciales autónomas respaldadas; no evalúa por sí sola toda la brecha",
  },
  "N3.1": {
    pregunta: "¿Las brechas cambian entre artículos?",
    lectura: "Más alto = brechas más distintas",
  },
  "N1.2": {
    pregunta: "¿Qué parte de las secciones útiles disponibles llegó al modelo?",
    lectura: "Más alto = cubrió más secciones detectadas en este artículo",
  },
  "N3.2": {
    pregunta: "¿La brecha usa cifras, nombres y métodos concretos?",
    lectura: "Unidad: anclajes por cada 100 palabras",
  },
  "N4.2": {
    pregunta: "¿El resumen conserva el significado del abstract?",
    lectura: "Más alto = mayor cercanía semántica",
  },
};

/** Segundos a "3h 21m 47s", omitiendo las unidades que no aportan. */
function duracion(seg) {
  const s = Math.max(0, Math.floor(seg));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h) return `${h} h ${String(m).padStart(2, "0")} min ${String(r).padStart(2, "0")} s`;
  if (m) return `${m} min ${String(r).padStart(2, "0")} s`;
  return `${r} s`;
}

/**
 * Cuenta atrás anclada al reloj del servidor.
 *
 * El navegador puede ir desfasado respecto a la base de datos, así que en vez
 * de comparar contra la hora local se calcula una sola vez la diferencia entre
 * ambos relojes y se descuenta sobre ella. De lo contrario un ordenador con la
 * hora mal puesta mostraría una cuenta atrás falsa sin que nada lo delatara.
 */
function useCuentaAtras(momentoISO, ahoraServidorISO = null) {
  const [segundos, setSegundos] = useState(null);

  useEffect(() => {
    if (!momentoISO) {
      setSegundos(null);
      return;
    }
    const destino = new Date(momentoISO).getTime();

    // Con instante de referencia del servidor se corrige el desfase entre
    // relojes: hace falta cuando la marca viene sin huso, como las de MySQL.
    // Sin él, la marca ya lleva huso propio y basta el reloj del navegador.
    const desfase = ahoraServidorISO
      ? Date.now() - new Date(ahoraServidorISO).getTime()
      : 0;

    const recalcular = () =>
      setSegundos(Math.max(0, Math.round((destino - (Date.now() - desfase)) / 1000)));

    recalcular();
    const t = setInterval(recalcular, 1000);
    return () => clearInterval(t);
  }, [momentoISO, ahoraServidorISO]);

  return segundos;
}

/* ---------------------------------------------------------------- piezas */
function Etiqueta({ children, tono = "gris" }) {
  const tonos = {
    gris: "bg-hundido text-tinta-media border-borde",
    verde: "bg-bien-claro text-bien border-bien-borde",
    ambar: "bg-aviso-claro text-aviso border-aviso-borde",
    azul: "bg-acento-claro text-acento-fuerte border-acento-borde",
  };
  return (
    <span
      className={`inline-block text-[11px] leading-none px-2 py-[3px] rounded-full border ${
        tonos[tono] || tonos.gris
      }`}
    >
      {children}
    </span>
  );
}

function limitar(valor, minimo, maximo) {
  return Math.min(maximo, Math.max(minimo, valor));
}

/**
 * Sitúa la distribución sin inventar umbrales de calidad.
 *
 * Las métricas acotadas usan su escala teórica completa (0 a 1). Cuando el
 * catálogo solo declara una unidad —por ejemplo, anclajes por 100 palabras—
 * se usa el mínimo y máximo observados y se rotula como tal.
 */
function EscalaMetrica({ metrica, integrada = false }) {
  const { mediana, p25, p75, minimo, maximo, rango, mejor } = metrica;
  const escalaTeorica = rango === "0 a 1" || rango === "0 o 1";
  const inicio = escalaTeorica ? 0 : Number(minimo);
  const fin = escalaTeorica ? 1 : Number(maximo);
  const amplitud = fin - inicio;
  const posicion = (valor) => {
    if (!Number.isFinite(Number(valor)) || !Number.isFinite(amplitud) || amplitud <= 0) {
      return 50;
    }
    return limitar(((Number(valor) - inicio) / amplitud) * 100, 0, 100);
  };
  const posP25 = posicion(p25);
  const posP75 = posicion(p75);
  const posMediana = posicion(mediana);
  const inicioIqr = Math.min(posP25, 98);
  // Sin dispersión no se dibuja franja. El ancho tenía un mínimo de 2 % para
  // que no desapareciera, pero desaparecer es lo correcto: con todas las
  // mediciones iguales —o con una sola— esa banda afirmaba «aquí está el 50 %
  // central» sobre unos datos que no se separan en nada.
  const hayDispersion = Number.isFinite(posP75 - posP25) && posP75 - posP25 > 0.5;
  const anchoIqr = hayDispersion
    ? Math.min(100 - inicioIqr, posP75 - posP25)
    : 0;
  const direccion =
    mejor === "alto"
      ? "En esta métrica, un valor mayor es más favorable."
      : mejor === "bajo"
        ? "En esta métrica, un valor menor es más favorable."
        : "Esta métrica es descriptiva: no hay un valor mejor por sí solo.";

  return (
    <div className={integrada ? "" : "mt-5 border-t border-borde pt-4"}>
      <div className="flex items-start justify-between gap-3 text-[11px]">
        <span className="font-semibold uppercase tracking-[0.12em] text-tinta-suave">
          Escala del resultado
        </span>
        <span className="text-right text-tinta-media">{direccion}</span>
      </div>

      <div className="relative mt-4 py-2" aria-label={`Mediana ${fmt(mediana)} en escala ${rango}`}>
        <div className="h-2 rounded-full bg-hundido ring-1 ring-inset ring-borde">
          {hayDispersion && (
            <div
              className="absolute top-2 h-2 rounded-full bg-acento-claro ring-1 ring-inset ring-acento-borde"
              style={{ left: `${inicioIqr}%`, width: `${anchoIqr}%` }}
              title={`Mitad central: ${fmt(p25)} a ${fmt(p75)}`}
            />
          )}
        </div>
        <div
          className="absolute top-0 -translate-x-1/2"
          style={{ left: `${posMediana}%` }}
          title={`Resultado central: ${fmt(mediana)}`}
        >
          <div className="mx-auto h-6 w-0.5 rounded-full bg-acento-fuerte" />
          <div className="mx-auto -mt-4 h-2.5 w-2.5 rounded-full border-2 border-superficie bg-acento shadow-sm" />
        </div>
      </div>

      <div className="mt-1 flex justify-between gap-4 text-[11px] text-tinta-suave tabular-nums">
        <span>
          {fmt(inicio)} · {escalaTeorica ? "menor valor posible" : "menor observado"}
        </span>
        <span className="text-right">
          {fmt(fin)} · {escalaTeorica ? "mayor valor posible" : "mayor observado"}
        </span>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-tinta-media">
        {hayDispersion ? (
          <>
            La línea marca la mediana ({fmt(mediana)}); la franja azul cubre el
            50 % central, de {fmt(p25)} a {fmt(p75)}.
          </>
        ) : (
          <>
            La línea marca el valor ({fmt(mediana)}). No hay franja porque no
            hay dispersión que mostrar: todas las mediciones coinciden, o solo
            hay una.
          </>
        )}
      </p>
    </div>
  );
}

function GuiaLecturaMetricas() {
  const conceptos = [
    {
      titulo: "Mediana",
      texto: "El resultado central: la mitad de las mediciones queda por debajo y la otra mitad por encima.",
    },
    {
      titulo: "IQR",
      texto: "Cuánto se separa el 50 % central. Un IQR mayor indica más variación, no necesariamente mejor calidad.",
    },
    {
      titulo: "Muestra (n)",
      texto: "Cantidad real de brechas, artículos o análisis que aportaron valores a esa métrica.",
    },
    {
      titulo: "Sin umbral común",
      texto: "Un IQR grande o pequeño no se califica como bueno o malo: cada métrica tiene una escala distinta y aún falta calibrarla con revisión humana.",
    },
  ];

  return (
    <div className="rounded-xl border border-borde bg-hundido/40 px-4 py-3.5">
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        {conceptos.map((concepto) => (
          <div key={concepto.titulo} className="flex gap-2.5">
            <span
              className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border border-acento-borde bg-acento-claro text-[10px] font-semibold text-acento"
              aria-hidden="true"
            >
              i
            </span>
            <p className="text-xs leading-relaxed text-tinta-media">
              <strong className="font-semibold text-tinta">{concepto.titulo}:</strong>{" "}
              {concepto.texto}
            </p>
          </div>
        ))}
      </div>
      <p className="mt-3 border-t border-borde pt-3 text-[11px] leading-relaxed text-tinta-suave">
        La barra ayuda a ubicar el resultado de menor a mayor. No muestra zonas
        «malas» o «buenas» porque todavía no existen umbrales académicos calibrados
        para clasificarlas.
      </p>
    </div>
  );
}

function Tarjeta({ metrica }) {
  if (!metrica) return null;
  const {
    codigo,
    nombre,
    mediana,
    iqr,
    descripcion,
    n,
    nivel,
    ambito,
  } = metrica;
  // La guía nueva de N1.2 solo describe v2. Aplicarla a un valor histórico
  // haría que un número antiguo pareciera calculado con el denominador nuevo.
  const guia = codigo === "N1.2" && metrica.version_formula !== 2
    ? {}
    : GUIA_DESTACADAS[codigo] || {};
  const alcance = {
    run: "Se calcula una vez por análisis completo",
    brecha: "Se calcula en cada brecha",
    articulo: "Se calcula en cada artículo",
    proyecto: "Se calcula para el proyecto completo",
  }[ambito] || ambito;
  const unidadMuestra = {
    run: n === 1 ? "análisis medido" : "análisis medidos",
    brecha: n === 1 ? "brecha medida" : "brechas medidas",
    articulo: n === 1 ? "artículo medido" : "artículos medidos",
    proyecto: n === 1 ? "proyecto medido" : "proyectos medidos",
  }[ambito] || "mediciones";
  const estado = estadoMetrica(metrica);
  const deLote = esDeLote(metrica);
  const sinDatos = n === 0;
  const binaria = esBinaria(metrica) && !sinDatos;
  const recuento = binaria ? recuentoBinario(metrica) : null;

  return (
    <article
      className="rounded-xl border border-borde bg-superficie p-5 shadow-[var(--sombra-1)]"
      title={descripcion}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-tinta-suave">
            Resultado
          </div>
          <h3 className="mt-2 text-base font-semibold leading-tight text-tinta">
            {nombre}
          </h3>
        </div>
        <Etiqueta tono="azul">{nivel?.replace(/^N\d+\s*/, "") || codigo}</Etiqueta>
      </div>

      <div className="mt-5 grid gap-5 sm:grid-cols-[minmax(0,1fr)_13rem]">
        <div className="min-w-0">
          <div className="text-4xl font-semibold tracking-tight text-acento tabular-nums">
            {fmt(mediana)}
          </div>
          <p className="mt-2 text-sm font-medium leading-snug text-tinta">
            {guia.pregunta || descripcion}
          </p>
          <p className="mt-2 text-xs leading-relaxed text-tinta-media">
            {guia.lectura || metrica.interpretacion}
          </p>
        </div>

        {/* A una métrica de lote no se le piden IQR ni tamaño de muestra: da
            un solo número por análisis, así que ese recuadro salía siempre con
            IQR 0.000, n=1 y un aviso ámbar de «muestra limitada». Dedicarle
            media tarjeta a decir que la medición es pobre, en la métrica que
            el propio catálogo llama la más diagnóstica, invitaba a desconfiar
            de un valor que está completo. */}
        <div className="border-t border-borde pt-4 sm:border-l sm:border-t-0 sm:pl-5 sm:pt-0">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-tinta-suave">
            {deLote || binaria ? "Cómo se obtuvo" : "Cómo se midió"}
          </div>

          {deLote ? (
            <p className="mt-3 text-xs leading-relaxed text-tinta-media">
              Un único valor calculado sobre el análisis completo. No tiene
              dispersión que medir: no es una muestra a la que le falten casos,
              sino la medición entera.
            </p>
          ) : binaria ? (
            <p className="mt-3 text-xs leading-relaxed text-tinta-media">
              Cada medición vale 0 o 1, así que lo que cuenta es en cuántas se
              cumplió: {recuento?.aciertos} de {recuento?.total}. La dispersión
              no aporta nada en una métrica de sí o no.
            </p>
          ) : (
            <>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-hundido px-2.5 py-2">
                  <div className="text-[10px] uppercase tracking-wide text-tinta-suave">IQR</div>
                  <div className="mt-0.5 font-semibold tabular-nums text-tinta">{fmt(iqr)}</div>
                </div>
                <div className="rounded-lg bg-hundido px-2.5 py-2">
                  <div className="text-[10px] uppercase tracking-wide text-tinta-suave">Muestra</div>
                  <div className="mt-0.5 font-semibold tabular-nums text-tinta">n={n}</div>
                </div>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-tinta-suave">
                {n} {unidadMuestra}. {alcance}.
              </p>
            </>
          )}

          <div className="mt-3">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-[3px] text-[11px] leading-none ${estado.etiqueta}`}
              title={estado.texto}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${estado.punto}`} aria-hidden="true" />
              {estado.texto}
            </span>
          </div>
        </div>
      </div>

      {!sinDatos && <EscalaMetrica metrica={metrica} />}
    </article>
  );
}

function DatoResumen({ valor, etiqueta, tono = "acento" }) {
  const colores = {
    acento: "text-acento",
    bien: "text-bien",
    neutro: "text-tinta",
  };
  return (
    <div className="min-w-0 px-4 py-3.5">
      <div className={`text-lg font-semibold tabular-nums ${colores[tono] || colores.acento}`}>
        {valor}
      </div>
      <div className="mt-0.5 text-xs leading-snug text-tinta-suave">{etiqueta}</div>
    </div>
  );
}

/**
 * Explica por qué el estado de validación es "pendiente".
 *
 * Va plegado: el texto es necesario la primera vez y estorba a partir de la
 * segunda, y aparecía repetido en el panel y en cada brecha. Un titular basta
 * para saber que hay algo que leer.
 */
export function AvisoValidacion() {
  return (
    <details className="rounded-lg border border-aviso-borde bg-aviso-claro text-aviso text-sm">
      <summary className="cursor-pointer select-none px-3 py-2 font-medium marker:text-current">
        Validación automática pendiente de calibrar
      </summary>
      <div className="px-3 pb-3 space-y-2 leading-relaxed opacity-90">
        {/* El título solo tenía sentido para quien ya conocía la historia. Lo
            primero que hace falta es decir qué significa para quien lee una
            brecha ahora mismo. */}
        <p>
          <b>Qué significa para ti:</b> las brechas aparecen como «pendiente» en
          vez de «aceptada» o «rechazada». Nadie ha dictaminado si son buenas;
          hay que leerlas con criterio propio.
        </p>
        <p>
          <b>Por qué está así:</b> había reglas que puntuaban cada brecha
          automáticamente, pero sus umbrales nunca llegaban a activarse y casi
          todas terminaban marcadas como aceptadas sin haber sido comprobadas.
          Un sello de goma es peor que ningún sello, así que se desactivaron.
        </p>
        <p>
          <b>Qué falta:</b> un conjunto de brechas evaluadas por expertos con el
          que ajustar los umbrales. Hasta entonces el sistema prefiere
          declararse indeciso antes que dar por buena una brecha que no ha
          comprobado.
        </p>
        <p className="text-[13px]">
          Lo que sí está medido es la <b>fidelidad a las fuentes</b>, más abajo:
          eso no dice si la brecha es valiosa, pero sí si lo que afirma está en
          el artículo.
        </p>
      </div>
    </details>
  );
}

/**
 * Consumo de API frente al límite diario del nivel gratuito.
 *
 * Incluye el desglose porque decir "cuesta 6" sin explicar de dónde sale ese
 * 6 obliga a adivinar si depende del número de artículos, de su tamaño o de
 * los PDF indexados.
 */
export function IndicadorConsumo({ proyectoId, compacto = false }) {
  const [d, setD] = useState(null);
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    let vivo = true;
    // Sin proyecto se consulta la cuota de la clave a secas, que es lo que
    // interesa desde la lista: el margen es el mismo para todos los proyectos.
    const url = proyectoId
      ? `${API_BASE}/proyectos/${proyectoId}/consumo`
      : `${API_BASE}/consumo`;
    api(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((x) => vivo && setD(x))
      .catch(() => {
        // Incluye la sesión caducada, que `api` ya gestionó cerrándola: aquí
        // no hay nada que mostrar, el indicador simplemente no aparece.
      });
    return () => {
      vivo = false;
    };
  }, [proyectoId]);

  // Los hooks van antes de cualquier retorno: su orden debe ser estable
  // entre renderizados.
  const ahoraServidor = d?.ahora_servidor ?? null;
  const segProxima = useCuentaAtras(d?.renovaciones?.[0]?.momento, ahoraServidor);
  const segEjecucion = useCuentaAtras(
    d?.disponible_para_ejecucion_en?.momento,
    ahoraServidor
  );
  // El reinicio del proveedor llega como instante absoluto en UTC, así que
  // no necesita corrección de desfase.
  const segReinicio = useCuentaAtras(d?.reinicio_proveedor?.momento_utc);

  if (!d) return null;
  const usadas = d.generaciones_estimadas;
  const tope = d.limite_diario_nivel_gratuito;
  const restantes = d.restantes_estimadas;
  const pct = Math.min(100, Math.round((usadas / Math.max(1, tope)) * 100));
  // Sin proyecto no hay coste de ejecucion con el que comparar, asi que el
  // aviso se basa en el margen restante.
  const alcanza = proyectoId ? d.alcanza_para_otra_ejecucion : restantes > 0;

  if (compacto) {
    return (
      <div
        className="inline-flex items-center gap-2.5 rounded-full border border-borde bg-superficie pl-3 pr-3.5 py-1.5"
        title={
          segProxima != null
            ? `Se recupera 1 generación en ${duracion(segProxima)}`
            : undefined
        }
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            alcanza ? "bg-acento" : "bg-mal"
          }`}
        />
        <span className="text-xs text-tinta-media">
          API · <span className="tabular-nums">{usadas}</span> de{" "}
          <span className="tabular-nums">{tope}</span> hoy
        </span>
        <span className="w-16 h-1 rounded-full bg-hundido overflow-hidden">
          <span
            className={`block h-full ${alcanza ? "bg-acento" : "bg-mal"}`}
            style={{ width: `${pct}%` }}
          />
        </span>
        {!alcanza && segReinicio != null && (
          <span className="text-xs text-mal tabular-nums">
            {duracion(segReinicio)}
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      className={`rounded-lg border p-3 text-sm ${
        alcanza
          ? "border-borde bg-superficie text-tinta-media"
          : "border-mal-borde bg-mal-claro text-mal"
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium">Consumo de API (24 h)</span>
        <span className="tabular-nums">
          {usadas} / {tope}
        </span>
      </div>

      <div className="mt-2 h-1.5 w-full rounded-full bg-hundido overflow-hidden">
        <div
          className={`h-full ${alcanza ? "bg-acento" : "bg-mal"}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="text-[11px] mt-2 leading-relaxed">
        {proyectoId ? (
          <>
            Analizar este proyecto cuesta{" "}
            <b>{d.coste_de_una_ejecucion} generaciones</b>.{" "}
            {alcanza
              ? `Quedan ${restantes}: alcanza para otra ejecución.`
              : `Quedan ${restantes}, faltan ${d.generaciones_que_faltan}.`}
          </>
        ) : (
          <>Quedan {restantes} generaciones disponibles hoy.</>
        )}
      </div>

      {/* Dos referencias distintas, y conviene no confundirlas: el proveedor
          reinicia su cuota de golpe a medianoche de su huso; nuestra ventana
          móvil libera una generación cada vez que una llamada cumple 24 h. */}
      {(segReinicio != null || segProxima != null || segEjecucion != null) && (
        <div className="mt-2.5 rounded-lg border border-borde bg-hundido/60 px-2.5 py-2 text-[11px] leading-relaxed space-y-1.5">
          {segReinicio != null && (
            <div>
              <span className="text-tinta-suave">
                La cuota vuelve a {d.limite_diario_nivel_gratuito} en{" "}
              </span>
              <span className="font-medium tabular-nums">
                {duracion(segReinicio)}
              </span>
              {/* Se muestra la hora local equivalente: "medianoche UTC-8" se
                  lee como "medianoche" a secas, y con tres horas de diferencia
                  eso lleva a esperar el reinicio cuando no toca. */}
              <div className="text-tinta-suave">
                Es medianoche en {d.reinicio_proveedor?.huso}, el huso del panel
                de AI Studio; aquí serán las{" "}
                {new Date(d.reinicio_proveedor?.momento_utc).toLocaleTimeString(
                  undefined,
                  { hour: "2-digit", minute: "2-digit" }
                )}
                .
              </div>
            </div>
          )}

          {(segProxima != null || segEjecucion != null) && (
            <div className="border-t border-borde pt-1.5">
              {!alcanza && segEjecucion != null ? (
                <>
                  <span className="text-tinta-suave">
                    Nuestra estimación alcanzaría para analizar en{" "}
                  </span>
                  <span className="font-medium tabular-nums">
                    {duracion(segEjecucion)}
                  </span>
                </>
              ) : (
                segProxima != null && (
                  <>
                    <span className="text-tinta-suave">
                      Nuestra estimación recupera 1 en{" "}
                    </span>
                    <span className="font-medium tabular-nums">
                      {duracion(segProxima)}
                    </span>
                  </>
                )
              )}
              <div className="text-tinta-suave">
                Ventana móvil de 24 h de esta aplicación. Manda el reinicio del
                proveedor.
              </div>
            </div>
          )}
        </div>
      )}

      <button
        onClick={() => setAbierto((v) => !v)}
        className="mt-2 text-[11px] text-acento hover:underline"
      >
        {abierto ? "Ocultar" : "¿Qué cuenta como generación?"}
      </button>

      {abierto && (
        <div className="mt-2 space-y-2 text-[11px] leading-relaxed">
          <div>
            Una <b>generación</b> es una llamada al modelo de lenguaje. El nivel
            gratuito permite {tope} al día. Los cálculos que no llaman al modelo
            no cuentan.
          </div>

          {/* La cuota es de la clave, no del proyecto: conviene decirlo donde
              se muestra el número, para que nadie suponga que cada proyecto
              tiene su propio margen. */}
          {d.exactitud?.ambito && (
            <div className="text-tinta-suave">{d.exactitud.ambito}</div>
          )}

          {d.desglose && (
            <div className="border-t pt-2">
              <div className="font-medium mb-1">Sí cuentan</div>
              {d.desglose.map((x, i) => (
                <div key={i} className="mb-1.5">
                  <div className="flex justify-between gap-2">
                    <span>{x.concepto}</span>
                    <span className="tabular-nums font-medium">×{x.cantidad}</span>
                  </div>
                  <div className="text-tinta-suave">{x.detalle}</div>
                </div>
              ))}
              <div className="flex justify-between gap-2 border-t pt-1 mt-1 font-medium">
                <span>Total por ejecución</span>
                <span className="tabular-nums">{d.coste_de_una_ejecucion}</span>
              </div>
            </div>
          )}

          <div className="border-t pt-2">
            <div className="font-medium mb-1">No cuentan</div>
            {(d.no_cuentan || []).map((x, i) => (
              <div key={i} className="mb-1.5">
                <div>{x.concepto}</div>
                <div className="text-tinta-suave">{x.detalle}</div>
              </div>
            ))}
          </div>

          {/* Se dice de dónde sale el número y qué no alcanza a ver. Un
              contador presentado como exacto sin serlo lleva a decisiones
              equivocadas. */}
          {d.exactitud && (
            <div className="border-t pt-2 space-y-1 text-tinta-suave">
              <div>
                <span className="font-medium">Qué cuenta este indicador: </span>
                {d.exactitud.cuenta}
              </div>
              {d.generaciones_fallidas > 0 && (
                <div>
                  De las {usadas} registradas, {d.generaciones_fallidas}{" "}
                  fallaron. Consumen cuota igual.
                </div>
              )}
              <div>
                <span className="font-medium">No cuenta: </span>
                {(d.exactitud.no_cuenta || []).join(" ")}
              </div>
              <div>{d.exactitud.ventana}</div>
              <div>
                Cifra oficial en{" "}
                <a
                  href="https://ai.dev/rate-limit"
                  target="_blank"
                  rel="noreferrer"
                  className="text-acento hover:underline"
                >
                  ai.dev/rate-limit
                </a>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- panel */
export function PanelMetricas({ proyectoId }) {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    let vivo = true;
    api(`${API_BASE}/proyectos/${proyectoId}/metricas`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((x) => vivo && setDatos(x))
      // Una sesión caducada no es un error de este panel: `api` ya la cerró y
      // la aplicación entera vuelve a la pantalla de entrada.
      .catch((e) => vivo && !e?.sesionCaducada && setError(e));
    return () => {
      vivo = false;
    };
  }, [proyectoId]);

  if (error) {
    return (
      <div className="text-sm text-tinta-media border border-borde rounded-lg p-3 bg-superficie">
        No se pudieron cargar las métricas.
      </div>
    );
  }
  if (!datos) {
    return (
      <div className="text-sm text-tinta-suave border border-borde rounded-lg p-3 bg-superficie">
        Cargando métricas…
      </div>
    );
  }
  if (!datos.run) {
    return (
      <div className="text-sm text-tinta-media border border-borde rounded-lg p-3 bg-superficie">
        {datos.aviso || "El proyecto todavía no se ha analizado."}
      </div>
    );
  }

  const porCodigo = Object.fromEntries(datos.metricas.map((m) => [m.codigo, m]));
  return (
    <div className="space-y-5">
      <div className="grid overflow-hidden rounded-xl border border-borde bg-superficie shadow-[var(--sombra-1)] sm:grid-cols-2 lg:grid-cols-4 sm:[&>*:nth-child(even)]:border-l lg:[&>*+*]:border-l">
        <DatoResumen
          valor={datos.conteos.articulos}
          etiqueta="artículos analizados"
        />
        <DatoResumen valor={datos.conteos.brechas} etiqueta="brechas vigentes" />
        <DatoResumen
          valor={datos.estado_arte ? `v${datos.estado_arte.version}` : "Pendiente"}
          etiqueta="estado del arte"
          tono={datos.estado_arte ? "bien" : "neutro"}
        />
        <DatoResumen
          valor={(datos.run.tokens_in + datos.run.tokens_out).toLocaleString("es")}
          etiqueta="tokens utilizados"
          tono="neutro"
        />
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-tinta">
            Lectura rápida del proyecto
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-tinta-media">
            Estos indicadores describen el análisis; no forman una nota global.
          </p>
        </div>
        <Etiqueta tono="azul">Mediana, P25, P75 e IQR</Etiqueta>
      </div>

      <GuiaLecturaMetricas />

      {/* La fidelidad va sola y a todo lo ancho: es la pregunta que decide si
          el resto del panel merece atención. */}
      {porCodigo[CABECERA]?.n > 0 ? (
        <Tarjeta metrica={porCodigo[CABECERA]} />
      ) : (
        <div className="rounded-xl border border-borde bg-superficie p-5 shadow-[var(--sombra-1)]">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-tinta-suave">
            Resultado
          </div>
          <h3 className="mt-2 text-base font-semibold text-tinta">
            Respaldo de afirmaciones evidenciales
          </h3>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-tinta-media">
            ¿Las afirmaciones factuales de las brechas se apoyan en los
            fragmentos consultados? Todavía no se ha comprobado. Se calcula con
            el botón «Verificar fidelidad», que descompone cada brecha y busca
            el fragmento que sostiene cada afirmación evidencial.
          </p>
          <p className="mt-2 text-xs text-tinta-suave">
            Esta medición no decide si la brecha completa es correcta o valiosa:
            las conclusiones también requieren revisión humana.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {DESTACADAS.map((c) => (
          <Tarjeta key={c} metrica={porCodigo[c]} />
        ))}
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-acento-borde bg-acento-claro px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-sm font-medium text-acento-fuerte">
          <span
            className="grid h-6 w-6 place-items-center rounded-full border border-acento-borde text-xs text-acento"
            aria-hidden="true"
          >
            i
          </span>
          <span>
            {datos.metricas.length} métricas · IQR descriptivo, sin calificación
          </span>
        </div>
        <button
          onClick={() => setAbierto((v) => !v)}
          className="shrink-0 rounded-lg border border-acento-borde bg-superficie px-3 py-2 text-sm font-medium text-acento-fuerte transition-colors hover:border-acento"
        >
          {abierto ? "Ocultar" : "Ver"} las {datos.metricas.length} métricas técnicas
        </button>
      </div>

      {!datos.validacion_calibrada && <AvisoValidacion />}

      {abierto && <TablaDistribuciones metricas={datos.metricas} />}
    </div>
  );
}

const GRUPOS_METRICAS = [
  ["N1", "Recuperación"],
  ["N2", "Fidelidad"],
  ["N3", "Especificidad"],
  ["N4", "Resumen"],
  ["N5", "Síntesis y tipificación"],
];

function grupoDeMetrica(codigo = "") {
  return GRUPOS_METRICAS.find(([prefijo]) => codigo.startsWith(prefijo))?.[0] || "OTRO";
}

/**
 * Una métrica de lote no es una distribución.
 *
 * `N3.1 Discriminabilidad` y `N3.4 Redundancia` son de ámbito `run`: se
 * calculan una vez sobre todas las brechas del análisis y devuelven un solo
 * número. No es una muestra de la que falten casos, es la medición completa.
 *
 * Tratarlas con la regla general dejaba a la métrica más diagnóstica del
 * sistema marcada siempre en ámbar como «muestra limitada», con IQR 0.000,
 * como si algo hubiera salido mal. El aviso decía la verdad estadística —un
 * valor no tiene rango intercuartílico— y mentía sobre lo que importa: el
 * número es válido y está completo.
 */
function esDeLote(metrica) {
  return metrica?.ambito === "run" || metrica?.ambito === "proyecto";
}

/**
 * Métricas de sí o no, donde la mediana y el IQR no dicen nada.
 *
 * `N2.verificada` y `N4.ref` valen 0 o 1: se hizo la verificación o no, se
 * encontró el abstract o no. Con las cinco a 1 —el mejor resultado posible—
 * salían como «mediana 1.000, IQR 0.000, poca variación» en ámbar, es decir,
 * con aspecto de problema. Lo que un lector quiere de ellas es un recuento:
 * cuántas de cuántas.
 */
function esBinaria(metrica) {
  return metrica?.rango === "0 o 1";
}

/** "4 de 5" a partir de la media de una métrica binaria. */
function recuentoBinario(metrica) {
  if (!metrica || !metrica.n) return null;
  const aciertos = Math.round((metrica.media ?? metrica.mediana ?? 0) * metrica.n);
  return { aciertos, total: metrica.n };
}

function estadoMetrica(metrica) {
  if (!metrica || metrica.n === 0) {
    return {
      clave: "sin-datos",
      texto: "Sin datos",
      punto: "bg-tinta-suave",
      etiqueta: "bg-hundido text-tinta-media border-borde",
    };
  }
  if (esBinaria(metrica)) {
    const r = recuentoBinario(metrica);
    return {
      clave: "recuento",
      texto: r ? `${r.aciertos} de ${r.total}` : "Recuento",
      punto: "bg-acento",
      etiqueta: "bg-acento-claro text-acento-fuerte border-acento-borde",
    };
  }
  if (esDeLote(metrica)) {
    return {
      clave: "valor-unico",
      texto: "Valor único del análisis",
      punto: "bg-acento",
      etiqueta: "bg-acento-claro text-acento-fuerte border-acento-borde",
    };
  }
  // Una distribución se presenta como descripción, no como veredicto. El
  // antiguo corte IQR=0.05 etiquetaba igual métricas con escalas distintas y
  // no estaba calibrado contra N6.
  return {
    clave: "distribucion",
    texto: "Distribución descriptiva",
    punto: "bg-tinta-suave",
    etiqueta: "bg-hundido text-tinta-media border-borde",
  };
}

function textoAmbito(ambito) {
  return {
    run: "análisis completo",
    brecha: "cada brecha",
    articulo: "cada artículo",
    proyecto: "proyecto completo",
  }[ambito] || ambito || "—";
}

/**
 * La dirección de lectura, en corto, para la lista de métricas.
 *
 * No todas mejoran al subir. `N5.2 Reetiquetado automático` y `N3.4
 * Redundancia` van al revés, y estando la dirección solo dentro del detalle
 * una mediana alta en ellas pasaba por buena de un vistazo. En un proyecto
 * real, N5.2 salía en 1.000 —el peor valor— resumida como «valores parecidos»,
 * que no dice nada de eso.
 *
 * Se muestra la dirección junto al valor, sin calificarlo: el lector tiene los
 * dos datos y saca la conclusión. Poner aquí un juicio exigiría umbrales
 * académicos calibrados, que es justamente lo que este panel no tiene.
 */
const DIRECCION_CORTA = {
  alto: { signo: "↑", texto: "mayor es mejor" },
  bajo: { signo: "↓", texto: "menor es mejor" },
  // Sin flecha: no apunta a ningún lado porque no hay lado mejor.
  neutro: { signo: "", texto: "descriptiva" },
};

/** Lo que se resume de una métrica en la lista: dirección y valor. */
function resumenLista(metrica) {
  const direccion = DIRECCION_CORTA[metrica?.mejor] || null;
  let valor = "sin datos";
  if (metrica?.n > 0) {
    if (esBinaria(metrica)) {
      const r = recuentoBinario(metrica);
      valor = r ? `${r.aciertos} de ${r.total}` : fmt(metrica.mediana);
    } else {
      valor = fmt(metrica.mediana);
    }
  }
  return { direccion, valor };
}

function textoDireccion(mejor) {
  return {
    alto: "un valor mayor es más favorable",
    bajo: "un valor menor es más favorable",
    neutro: "es descriptiva; no existe un valor mejor por sí solo",
  }[mejor] || "sin dirección definida";
}

function DatoTecnico({ etiqueta, valor }) {
  return (
    <div className="rounded-lg border border-borde bg-superficie px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tinta-suave">
        {etiqueta}
      </div>
      <div className="mt-1 text-sm font-medium text-tinta tabular-nums">{valor}</div>
    </div>
  );
}

function DetalleMetrica({ metrica }) {
  const [tecnicoAbierto, setTecnicoAbierto] = useState(false);

  if (!metrica) {
    return (
      <div className="grid min-h-96 place-items-center p-8 text-sm text-tinta-suave">
        Selecciona una métrica para consultar su explicación.
      </div>
    );
  }

  const estado = estadoMetrica(metrica);
  const sinDatos = metrica.n === 0;
  const deLote = esDeLote(metrica);
  const binaria = esBinaria(metrica) && !sinDatos;
  const recuento = binaria ? recuentoBinario(metrica) : null;
  const unidad = {
    run: "análisis",
    brecha: metrica.n === 1 ? "brecha" : "brechas",
    articulo: metrica.n === 1 ? "artículo" : "artículos",
    proyecto: metrica.n === 1 ? "proyecto" : "proyectos",
  }[metrica.ambito] || "mediciones";

  return (
    <section className="min-w-0 p-5 sm:p-7">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-2xl font-semibold tracking-tight text-tinta">
            {metrica.nombre}
          </h3>
          <p className="mt-1 text-sm text-tinta-suave">
            {metrica.codigo} · {metrica.nivel}
          </p>
        </div>
        <span
          className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${estado.etiqueta}`}
        >
          <span className={`h-2 w-2 rounded-full ${estado.punto}`} aria-hidden="true" />
          {estado.texto}
          {/* El IQR de un valor único —o de una métrica de sí o no— es cero
              por definición, no por falta de variación: anunciarlo al lado del
              estado invitaba a leerlo mal. */}
          {!sinDatos && !deLote && !binaria && ` · IQR ${fmt(metrica.iqr)}`}
        </span>
      </div>

      <div className="mt-7">
        <h4 className="text-sm font-semibold text-tinta">Qué mide</h4>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-tinta-media">
          {metrica.descripcion}
        </p>
      </div>

      {sinDatos ? (
        <div className="mt-6 rounded-xl border border-borde bg-hundido px-5 py-6">
          <div className="text-xl font-semibold text-tinta">Sin mediciones aplicables</div>
          {/* El porqué estaba guardado junto a cada medición descartada y la
              pantalla no lo usaba: decía «no produjo valores», que es cierto y
              no explica nada. En las ROUGE, por ejemplo, la razón es que el
              resumen y el abstract están en idiomas distintos. */}
          {metrica.motivo_sin_datos ? (
            <>
              <p className="mt-2 text-sm leading-relaxed text-tinta-media">
                {metrica.motivo_sin_datos}
              </p>
              {metrica.n_intentos > 0 && (
                <p className="mt-2 text-xs text-tinta-suave">
                  Se intentó medir {metrica.n_intentos}{" "}
                  {metrica.n_intentos === 1 ? "vez" : "veces"} y ninguna resultó
                  aplicable. La ausencia de datos no equivale a un cero.
                </p>
              )}
            </>
          ) : (
            <p className="mt-2 text-sm leading-relaxed text-tinta-media">
              Esta métrica no produjo valores en el análisis actual. La ausencia
              de datos no equivale a un resultado de cero.
            </p>
          )}
        </div>
      ) : binaria ? (
        /* Una métrica de sí o no se lee contando, no promediando: «5 de 5» es
           el dato, y «mediana 1.000 con IQR 0.000» era la misma verdad dicha
           de forma que parecía un problema. */
        <div className="mt-6 rounded-xl border border-borde bg-superficie px-5 py-6">
          <div className="text-xs font-medium text-tinta-suave">Recuento</div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-5xl font-semibold tracking-tight text-acento tabular-nums">
              {recuento?.aciertos}
            </span>
            <span className="text-lg text-tinta-media">
              de {recuento?.total} {unidad}
            </span>
          </div>
          <p className="mt-3 text-sm leading-relaxed text-tinta-media">
            Esta métrica solo puede valer 0 o 1 en cada medición, así que se
            cuenta en cuántas se cumplió. La mediana y el rango intercuartílico
            no aportan nada aquí.
          </p>
        </div>
      ) : (
        <>
          <div className="mt-6 grid gap-5 rounded-xl border border-borde bg-superficie p-5 md:grid-cols-[12rem_minmax(0,1fr)] md:items-center">
            <div className="border-b border-borde pb-4 md:border-b-0 md:border-r md:pb-0 md:pr-5">
              <div className="text-xs font-medium text-tinta-suave">Mediana actual</div>
              <div className="mt-2 text-5xl font-semibold tracking-tight text-acento tabular-nums">
                {fmt(metrica.mediana)}
              </div>
            </div>
            <EscalaMetrica metrica={metrica} integrada />
          </div>

          {/* IQR y n van en tinta normal, no en ámbar y verde.
              El color decía cosas que el propio panel desmiente: pintaba de
              ámbar —advertencia— un IQR alto, que es justo lo que aquí se
              considera bueno y lo que activa «variación útil» en verde; y
              pintaba de verde el tamaño de muestra incluso cuando valía 1 y la
              insignia de arriba avisaba en ámbar de que era escaso. Dos
              números fijos no pueden codificar un veredicto que depende del
              dato. El color queda para la insignia, que sí lo evalúa. */}
          {deLote ? (
            <div className="mt-4 rounded-xl border border-borde bg-superficie px-4 py-4">
              <div className="text-sm text-tinta-suave">Cómo se obtuvo</div>
              <p className="mt-1.5 text-sm leading-relaxed text-tinta-media">
                Se calcula una sola vez sobre {textoAmbito(metrica.ambito)}, así
                que da un único número. No tiene dispersión que medir: no es una
                muestra a la que le falten casos, sino la medición completa.
              </p>
            </div>
          ) : (
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-borde bg-superficie px-4 py-4 text-center">
                <div className="text-sm text-tinta-suave">IQR</div>
                <div className="mt-1 text-2xl font-semibold text-tinta tabular-nums">
                  {fmt(metrica.iqr)}
                </div>
                <p className="mt-1 text-[11px] text-tinta-suave">
                  amplitud del 50 % central
                </p>
              </div>
              <div className="rounded-xl border border-borde bg-superficie px-4 py-4 text-center">
                <div className="text-sm text-tinta-suave">Muestra</div>
                <div className="mt-1 text-2xl font-semibold text-tinta tabular-nums">
                  {metrica.n} {unidad}
                </div>
                <p className="mt-1 text-[11px] text-tinta-suave">
                  mediciones incluidas en el resumen
                </p>
              </div>
            </div>
          )}
        </>
      )}

      <div className="mt-5 space-y-3">
        <div className="rounded-xl border border-acento-borde bg-acento-claro px-4 py-3.5">
          <h4 className="text-sm font-semibold text-acento-fuerte">Cómo leerlo</h4>
          <p className="mt-1 text-sm leading-relaxed text-tinta-media">
            {sinDatos
              ? "No debe interpretarse como cero ni compararse con las demás métricas."
              : `${textoDireccion(metrica.mejor)}. Este resultado describe un aspecto del análisis; no es una nota global del proyecto.`}
          </p>
        </div>

        <div className="rounded-xl border border-borde bg-superficie px-4 py-3.5">
          <h4 className="text-sm font-semibold text-tinta">Por qué importa</h4>
          <p className="mt-1 text-sm leading-relaxed text-tinta-media">
            {metrica.interpretacion}
          </p>
        </div>

        <p className="rounded-lg bg-hundido px-3 py-2.5 text-xs leading-relaxed text-tinta-suave">
          La variación describe diferencias entre mediciones; no decide si la
          investigación es buena o mala.
        </p>
      </div>

      <div className="mt-5 border-t border-borde pt-4">
        <button
          type="button"
          onClick={() => setTecnicoAbierto((valor) => !valor)}
          className="text-sm font-medium text-acento hover:underline"
          aria-expanded={tecnicoAbierto}
        >
          {tecnicoAbierto ? "Ocultar" : "Ver"} detalle técnico
        </button>

        {tecnicoAbierto && (
          <div className="mt-4 rounded-xl border border-borde bg-hundido p-4">
            <p className="text-xs leading-relaxed text-tinta-media">
              Datos estadísticos entregados por el sistema; no se añade ninguna
              fórmula ni clasificación nueva.
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <DatoTecnico etiqueta="Código" valor={metrica.codigo} />
              <DatoTecnico
                etiqueta="Versión de fórmula"
                valor={
                  metrica.version_formula === null || metrica.version_formula === undefined
                    ? "legado / desconocida"
                    : `v${metrica.version_formula}`
                }
              />
              <DatoTecnico etiqueta="Ámbito" valor={textoAmbito(metrica.ambito)} />
              <DatoTecnico etiqueta="Dirección" valor={textoDireccion(metrica.mejor)} />
              <DatoTecnico etiqueta="Escala declarada" valor={metrica.rango || "—"} />
              {!sinDatos && (
                <>
                  <DatoTecnico etiqueta="Mínimo" valor={fmt(metrica.minimo)} />
                  <DatoTecnico etiqueta="P25" valor={fmt(metrica.p25)} />
                  <DatoTecnico etiqueta="Mediana" valor={fmt(metrica.mediana)} />
                  <DatoTecnico etiqueta="Media" valor={fmt(metrica.media)} />
                  <DatoTecnico etiqueta="P75" valor={fmt(metrica.p75)} />
                  <DatoTecnico etiqueta="Máximo" valor={fmt(metrica.maximo)} />
                  <DatoTecnico etiqueta="IQR" valor={fmt(metrica.iqr)} />
                  <DatoTecnico etiqueta="Muestra" valor={`n=${metrica.n}`} />
                </>
              )}
            </div>
            {!sinDatos && !deLote && !binaria && (
              <p className="mt-3 text-xs leading-relaxed text-tinta-suave">
                El IQR se informa como amplitud del 50 % central. No se compara
                con un umbral universal ni se usa para calificar esta métrica.
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

export function TablaDistribuciones({ metricas }) {
  const inicial = metricas.find((m) => m.codigo === "N2.1") || metricas[0] || null;
  const [seleccion, setSeleccion] = useState(inicial?.codigo || null);
  const [busqueda, setBusqueda] = useState("");
  const [filtro, setFiltro] = useState("todas");
  const [gruposAbiertos, setGruposAbiertos] = useState(
    () => new Set([grupoDeMetrica(inicial?.codigo)]),
  );

  const normalizada = busqueda.trim().toLocaleLowerCase("es");
  const visibles = metricas.filter((metrica) => {
    const coincideTexto =
      !normalizada ||
      `${metrica.nombre} ${metrica.codigo} ${metrica.descripcion}`
        .toLocaleLowerCase("es")
        .includes(normalizada);
    const coincideFiltro = filtro === "todas" || estadoMetrica(metrica).clave === filtro;
    return coincideTexto && coincideFiltro;
  });
  const seleccionada = metricas.find((m) => m.codigo === seleccion) || inicial;

  function alternarGrupo(clave) {
    setGruposAbiertos((actuales) => {
      const siguientes = new Set(actuales);
      if (siguientes.has(clave)) siguientes.delete(clave);
      else siguientes.add(clave);
      return siguientes;
    });
  }

  function elegirMetrica(metrica) {
    setSeleccion(metrica.codigo);
    setGruposAbiertos((actuales) => new Set([...actuales, grupoDeMetrica(metrica.codigo)]));
  }

  return (
    <div className="overflow-hidden rounded-xl border border-borde bg-superficie shadow-[var(--sombra-1)]">
      <div className="flex flex-col gap-3 border-b border-borde px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-tinta">
            Explorar las {metricas.length} métricas
          </h2>
          <p className="mt-1 text-xs text-tinta-suave">
            Selecciona una para entender qué mide y cómo se interpreta.
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="relative min-w-0 sm:w-64">
            <span className="sr-only">Buscar una métrica</span>
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-tinta-suave" aria-hidden="true">
              ⌕
            </span>
            <input
              value={busqueda}
              onChange={(evento) => setBusqueda(evento.target.value)}
              placeholder="Buscar una métrica…"
              className="w-full rounded-lg border border-borde bg-superficie py-2 pl-9 pr-3 text-sm text-tinta outline-none transition-colors placeholder:text-tinta-suave focus:border-acento"
            />
          </label>
          <label>
            <span className="sr-only">Filtrar métricas</span>
            <select
              value={filtro}
              onChange={(evento) => setFiltro(evento.target.value)}
              className="h-full min-h-9 rounded-lg border border-borde bg-superficie px-3 py-2 text-sm text-tinta outline-none focus:border-acento"
            >
              <option value="todas">Todas</option>
              <option value="distribucion">Distribución descriptiva</option>
              <option value="valor-unico">Valor único del análisis</option>
              <option value="recuento">Recuento (sí o no)</option>
              <option value="sin-datos">Sin datos</option>
            </select>
          </label>
        </div>
      </div>

      <div className="grid lg:grid-cols-[19rem_minmax(0,1fr)]">
        <nav className="border-b border-borde bg-hundido/30 lg:border-b-0 lg:border-r" aria-label="Métricas por dimensión">
          {GRUPOS_METRICAS.map(([clave, nombre]) => {
            const delGrupo = visibles.filter((m) => grupoDeMetrica(m.codigo) === clave);
            const totalGrupo = metricas.filter((m) => grupoDeMetrica(m.codigo) === clave).length;
            if (totalGrupo === 0 || delGrupo.length === 0) return null;
            const abierto = gruposAbiertos.has(clave) || Boolean(normalizada) || filtro !== "todas";
            return (
              <div key={clave} className="border-b border-borde last:border-b-0">
                <button
                  type="button"
                  onClick={() => alternarGrupo(clave)}
                  className="flex w-full items-center gap-2 px-4 py-3 text-left hover:bg-superficie"
                  aria-expanded={abierto}
                >
                  <span className="text-xs font-semibold uppercase tracking-[0.1em] text-tinta-media">
                    {clave} {nombre}
                  </span>
                  <span className="ml-auto rounded-full border border-borde bg-superficie px-2 py-0.5 text-xs text-tinta-suave">
                    {totalGrupo}
                  </span>
                  <span className="text-xs text-tinta-suave" aria-hidden="true">
                    {abierto ? "⌃" : "⌄"}
                  </span>
                </button>

                {abierto && (
                  <div className="pb-2">
                    {delGrupo.map((metrica) => {
                      const estado = estadoMetrica(metrica);
                      const activa = seleccionada?.codigo === metrica.codigo;
                      const { direccion, valor } = resumenLista(metrica);
                      return (
                        <button
                          key={metrica.codigo}
                          type="button"
                          onClick={() => elegirMetrica(metrica)}
                          className={`flex w-full items-start gap-3 border-l-2 px-4 py-2.5 text-left text-sm transition-colors ${
                            activa
                              ? "border-acento bg-acento-claro font-medium text-acento-fuerte"
                              : "border-transparent text-tinta hover:bg-superficie"
                          }`}
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block truncate">{metrica.nombre}</span>
                            {/* Dirección y valor juntos: una mediana alta en
                                una métrica invertida no debe pasar por buena
                                solo porque el número sea grande. */}
                            <span className="mt-0.5 flex items-center gap-1.5 text-[11px] font-normal text-tinta-suave">
                              {direccion && (
                                <span title={textoDireccion(metrica.mejor)}>
                                  {direccion.signo
                                    ? `${direccion.signo} ${direccion.texto}`
                                    : direccion.texto}
                                </span>
                              )}
                              <span aria-hidden="true">·</span>
                              <span className="tabular-nums">{valor}</span>
                            </span>
                          </span>
                          <span
                            className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${estado.punto}`}
                            title={estado.texto}
                            aria-label={estado.texto}
                          />
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}

          {visibles.length === 0 && (
            <p className="px-4 py-8 text-center text-sm text-tinta-suave">
              No hay métricas que coincidan con la búsqueda.
            </p>
          )}
        </nav>

        <DetalleMetrica key={seleccionada?.codigo} metrica={seleccionada} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ fidelidad */

/**
 * La cita del artículo que desmiente una afirmación.
 *
 * Va pegada a la afirmación y no en una lista aparte: sin ver las dos frases
 * juntas no hay forma de juzgar si la contradicción es real, y quien revisa
 * necesita poder discrepar del verificador.
 */
function CitaContraria({ afirmacion }) {
  if (!afirmacion?.contradice) return null;
  return (
    <p className="mt-1.5 rounded-md border border-mal-borde bg-mal-claro px-2 py-1.5 text-[11px] leading-snug text-mal">
      <span className="font-semibold">El artículo dice lo contrario</span>
      {afirmacion.fragmento_contrario && (
        <> · fragmento {afirmacion.fragmento_contrario}</>
      )}
      {afirmacion.cita_contraria && (
        <span className="mt-0.5 block font-normal text-tinta-media">
          «{afirmacion.cita_contraria}»
        </span>
      )}
    </p>
  );
}

/**
 * Desglose de la verificación de fidelidad (nivel N2).
 *
 * Muestra la brecha descompuesta en afirmaciones y, de cada una, si se
 * sostiene en el artículo. Es la diferencia entre decir «esta brecha es
 * fiable» y poder señalar qué frase sale de qué párrafo.
 *
 * Las afirmaciones se separan en dos grupos porque no se comprueban igual:
 * las evidenciales describen lo que el artículo hace y deben rastrearse hasta
 * un fragmento; las inferenciales concluyen lo que falta, y no pueden
 * verificarse contra el propio artículo porque afirman justo lo que no
 * contiene.
 */
export function Fidelidad({ verificacion }) {
  if (!verificacion) return null;

  const {
    disponible,
    motivo,
    afirmaciones = [],
    fidelidad,
    trazabilidad,
    equilibrio_evidencial: equilibrio,
    n_sin_respaldo: sinRespaldo,
    n_dependientes: dependientes = 0,
    n_contradicciones: contradicciones = 0,
    detalle_trazabilidad: detalleTrazabilidad,
  } = verificacion;

  const evidenciales = afirmaciones.filter((a) => a.tipo === "evidencial");
  const inferenciales = afirmaciones.filter((a) => a.tipo === "inferencial");
  const trazabilidadV2 = detalleTrazabilidad?.formula === 2;
  const explicacionTrazabilidad = trazabilidadV2
    ? detalleTrazabilidad.n_elegibles > 0
      ? `${detalleTrazabilidad.n_con_fragmento_y_cita} de ${detalleTrazabilidad.n_elegibles} afirmaciones evidenciales autónomas tienen fragmento y cita. Las inferencias no reducen esta métrica porque no siempre requieren una cita propia.`
      : "No aplicable: esta brecha no contiene afirmaciones evidenciales autónomas que deban vincularse a una cita."
    : "Fórmula anterior: calculaba qué parte de todas las afirmaciones tenía una cita, incluidas inferencias que podían no necesitarla. No debe compararse directamente con la fórmula v2.";

  return (
    <details
      className="border border-borde rounded-lg"
      open={sinRespaldo > 0 || contradicciones > 0}
    >
      <summary className="cursor-pointer select-none px-3 py-2 bg-hundido rounded-t-lg">
        <span className="font-medium">Fidelidad a las fuentes</span>
        {disponible ? (
          <span className="text-tinta-suave">
            {" "}· {Math.round((fidelidad ?? 0) * 100)}% de las afirmaciones
            evidenciales autónomas está respaldada
            {sinRespaldo > 0 && (
              <span className="text-mal">
                {" "}· {sinRespaldo} sin respaldo en los fragmentos
              </span>
            )}
            {/* La contradicción va delante en importancia y por eso se nombra
                aunque la fidelidad sea perfecta: son cosas distintas y esta es
                la grave. */}
            {contradicciones > 0 && (
              <span className="font-medium text-mal">
                {" "}· {contradicciones}{" "}
                {contradicciones === 1
                  ? "contradice al artículo"
                  : "contradicen al artículo"}
              </span>
            )}
          </span>
        ) : (
          <span className="text-tinta-suave"> · sin verificar</span>
        )}
      </summary>

      <div className="p-3 space-y-3">
        {!disponible && (
          <p className="text-tinta-suave leading-relaxed">
            {motivo ||
              "La verificación no llegó a ejecutarse, así que no hay medición."}
          </p>
        )}

        {/* El alcance de la medición, dicho antes de los números.
            Sin esta frase, un 60 % se lee como «el 40 % es inventado», y no es
            eso: la comprobación se hace contra un extracto del artículo, no
            contra el artículo completo. Una afirmación puede ser cierta y
            estar en otra página. */}
        {disponible && (
          <div className="space-y-2 text-tinta-suave leading-relaxed">
            <p>
              Se comprueba contra los fragmentos que el modelo leyó y sus
              párrafos contiguos, no contra el artículo completo. «Sin respaldo»
              significa que ese extracto no la sostiene, no que sea falsa:
              conviene mirar el artículo antes de descartarla.
            </p>
            <p>
              El respaldo mide afirmaciones factuales autónomas. No decide por
              sí solo si la conclusión de la brecha es correcta, relevante o
              novedosa; esa parte necesita revisión humana.
            </p>
          </div>
        )}

        {/* Lo primero después del alcance, porque es lo más grave que puede
            decir esta pantalla. «Sin respaldo» significa que los fragmentos no
            hablan de eso; contradicción significa que dicen lo contrario, y
            eso no se arregla mirando el artículo: ya se miró. */}
        {disponible && contradicciones > 0 && (
          <div className="rounded-lg border border-mal-borde bg-mal-claro px-3 py-2.5">
            <p className="font-medium text-mal">
              {contradicciones}{" "}
              {contradicciones === 1
                ? "afirmación contradice"
                : "afirmaciones contradicen"}{" "}
              al artículo
            </p>
            <p className="mt-1 leading-relaxed text-tinta-media">
              Algún fragmento sostiene lo opuesto. Es distinto de no estar
              respaldada y bastante peor: aquí el artículo sí habla del tema, y
              dice otra cosa. Están marcadas abajo con su cita en contra.
            </p>
          </div>
        )}

        {/* Si esto aparece, el fallo es del verificador y no del modelo que
            redactó la brecha: conviene que se vea y no que se disimule. */}
        {disponible && dependientes > 0 && (
          <p className="text-aviso leading-relaxed">
            {dependientes}{" "}
            {dependientes === 1 ? "afirmación quedó" : "afirmaciones quedaron"}{" "}
            fuera del cálculo por perder el sujeto al descomponerse (empezaban
            por «Esto», «Ello»…). Sin antecedente no hay fragmento que pueda
            respaldarlas, así que contarlas habría hundido la fidelidad por un
            defecto de redacción.
          </p>
        )}

        {/* Cada indicador con lo que mide debajo. Antes eran tres números con
            una etiqueta de una palabra, y "Base factual" o "Trazabilidad" no
            dicen nada por sí solos: había que conocer la especificación para
            interpretarlos. */}
        {disponible && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {[
              [
                "Respaldo evidencial",
                fidelidad,
                "De las afirmaciones factuales autónomas, cuántas sostienen los fragmentos consultados. Un 1.00 no evalúa las conclusiones ni el artículo completo.",
              ],
              [
                "Trazabilidad",
                trazabilidad,
                explicacionTrazabilidad,
              ],
              [
                "Base factual",
                equilibrio,
                "Cuánto de la brecha son hechos del artículo y cuánto interpretación del modelo. Muy bajo significa que casi todo es opinión, aunque la fidelidad salga alta.",
              ],
            ].map(([k, v, explica]) => (
              <div
                key={k}
                className="border border-borde rounded-lg px-2.5 py-2"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[11px] font-medium text-tinta-media">
                    {k}
                  </span>
                  <span className="font-medium tabular-nums">{fmt(v, 2)}</span>
                </div>
                <p className="text-[11px] leading-snug text-tinta-suave mt-1">
                  {explica}
                </p>
              </div>
            ))}
          </div>
        )}

        {evidenciales.length > 0 && (
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-tinta-suave mb-1">
              Comprobables contra el artículo
            </div>
            <p className="text-[11px] text-tinta-suave mb-1.5 leading-snug">
              Afirmaciones que dicen algo que el artículo hace, mide o reporta,
              así que se puede buscar en el texto. Las que solo interpretan
              —«falta estudiar X»— no se pueden comprobar y van más abajo.
            </p>
            <div className="space-y-1.5">
              {evidenciales.map((a, i) => (
                <div
                  key={i}
                  className={`rounded-lg border px-2.5 py-2 ${
                    a.respaldada
                      ? "border-borde bg-hundido/50"
                      : "border-mal-borde bg-mal-claro"
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <span
                      className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                        a.respaldada ? "bg-bien" : "bg-mal"
                      }`}
                    />
                    <div className="min-w-0">
                      <p className="leading-snug">{a.texto}</p>
                      {a.respaldada ? (
                        <p className="text-[11px] text-tinta-suave mt-1">
                          Fragmento {a.fragmento}
                          {a.cita && <>: «{a.cita}»</>}
                        </p>
                      ) : (
                        <p className="text-[11px] text-mal mt-1">
                          Sin respaldo en los fragmentos consultados.
                          {a.motivo && <> {a.motivo}</>}
                        </p>
                      )}
                      <CitaContraria afirmacion={a} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {inferenciales.length > 0 && (
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-tinta-suave mb-1.5">
              Conclusiones
            </div>
            <div className="space-y-1.5">
              {/* Una conclusión no se verifica, pero sí puede contradecir. Es
                  el caso que se coló con datos reales: la brecha hablaba de
                  «posibles diseños inseguros» sobre un artículo que califica el
                  estándar de conservador, y como era una conclusión quedaba
                  fuera de todo cálculo. */}
              {inferenciales.map((a, i) => (
                <div
                  key={i}
                  className={`rounded-lg border px-2.5 py-2 ${
                    a.contradice
                      ? "border-mal-borde bg-mal-claro"
                      : "border-borde bg-hundido/50"
                  }`}
                >
                  <p className="leading-snug">{a.texto}</p>
                  <CitaContraria afirmacion={a} />
                </div>
              ))}
            </div>
            <p className="text-[11px] text-tinta-suave mt-1.5 leading-relaxed">
              Afirman lo que el artículo no cubre, así que no pueden
              comprobarse contra él: su validez se decide con criterio experto.
              Sí se comprueba, en cambio, que no lo contradigan.
            </p>
          </div>
        )}
      </div>
    </details>
  );
}

/* ---------------------------------------------------------------- brecha */
export function DetalleBrecha({ brecha }) {
  if (!brecha) return null;
  const metricas = brecha.metricas || [];
  const respaldo = brecha.respaldo || [];

  return (
    <div className="space-y-4 text-sm">
      <div>
        <div className="text-tinta-suave">Tipo de brecha</div>
        <div className="font-medium">{brecha.tipo_brecha}</div>
      </div>

      <div>
        <div className="text-tinta-suave">Brecha</div>
        <p className="whitespace-pre-wrap leading-relaxed">{brecha.brecha}</p>
      </div>

      <div>
        <div className="text-tinta-suave">Oportunidad de innovación</div>
        <p className="whitespace-pre-wrap leading-relaxed">{brecha.oportunidad}</p>
      </div>

      {!brecha.validacion_calibrada && <AvisoValidacion />}

      {/* Fidelidad antes que el respaldo bruto: interesa más saber qué
          afirmaciones se sostienen que qué fragmentos se consultaron. */}
      <Fidelidad verificacion={brecha.verificacion} />

      {/* Trazabilidad: es lo que permite comprobar de dónde sale la brecha. */}
      <details className="border border-borde rounded-lg" open>
        <summary className="cursor-pointer select-none px-3 py-2 bg-hundido rounded-t-lg">
          En qué se apoyó el análisis ({respaldo.length} fragmentos del artículo)
        </summary>
        <div className="p-3 space-y-2">
          {/* Sin esta explicación, "relevancia 0.412" no significa nada: nadie
              sabe si 0.4 es mucho o poco, ni por qué el modelo leyó solo un
              trozo del artículo en lugar de todo. */}
          <p className="text-[11px] text-tinta-suave leading-snug">
            El artículo no se le da entero al modelo: se parte en fragmentos y se
            le pasan los más pertinentes al tema del proyecto. Estos son los que
            leyó para escribir esta brecha, y los únicos contra los que se
            comprueba su fidelidad.
          </p>

          {brecha.secciones_consultadas?.length > 0 && (
            <div>
              <div className="text-[11px] text-tinta-suave mb-1">
                Secciones de las que salieron. Que aparezcan método, resultados
                o discusión es buena señal: significa que no se quedó en el
                resumen y la introducción.
              </div>
              <div className="flex flex-wrap gap-1">
                {brecha.secciones_consultadas.map((s) => (
                  <Etiqueta key={s} tono="azul">
                    {s}
                  </Etiqueta>
                ))}
              </div>
            </div>
          )}

          {respaldo.length === 0 && (
            <div className="text-tinta-suave">
              No se registró el respaldo de este análisis.
            </div>
          )}

          {respaldo.length > 0 && (
            <div className="text-[11px] text-tinta-suave">
              La <b>relevancia</b> es cuánto se parece el fragmento a lo que se
              buscaba, de 0 a 1. Sirve para comparar entre sí los de un mismo
              análisis, no como nota de calidad.
            </div>
          )}

          {respaldo.map((h, i) => (
            <div key={i} className="border border-borde rounded-lg p-2 bg-hundido">
              <div className="flex items-center justify-between text-[11px] text-tinta-suave">
                <span>
                  Fragmento {i + 1} · sección: {h.seccion || "sin identificar"}
                </span>
                <span>relevancia {fmt(h.score, 3)}</span>
              </div>
            </div>
          ))}
        </div>
      </details>

      <details className="border border-borde rounded-lg">
        <summary className="cursor-pointer select-none px-3 py-2 bg-hundido rounded-t-lg">
          Métricas de esta brecha ({metricas.length})
        </summary>
        <div className="p-3 grid grid-cols-1 md:grid-cols-2 gap-2">
          {metricas.map((m) => {
            // Una métrica sin valor no es un cero: es una que no aplica a este
            // caso. ROUGE cuenta palabras compartidas, así que entre un resumen
            // en español y un abstract en inglés daría casi cero por
            // construcción, por bueno que fuera el resumen. Mostrar ese cero
            // era el fallo original de este proyecto.
            const noAplica =
              m.valor === null || m.valor === undefined ||
              m.detalle?.aplicable === false;
            const motivo = m.detalle?.motivo;

            return (
              <div
                key={m.codigo}
                className={`border rounded-lg p-2 ${
                  noAplica ? "border-borde bg-hundido/40" : "border-borde"
                }`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-tinta">{m.nombre}</span>
                  <span
                    className={
                      noAplica
                        ? "text-[11px] text-tinta-suave shrink-0"
                        : "font-medium tabular-nums"
                    }
                  >
                    {noAplica ? "no aplicable" : fmt(m.valor)}
                  </span>
                </div>

                {/* La descripción, visible. Estaba solo en el atributo `title`,
                    que no existe cuando se mira desde el celular. */}
                {m.descripcion && (
                  <p className="text-[11px] leading-snug text-tinta-media mt-1">
                    {m.descripcion}
                  </p>
                )}

                {noAplica && motivo && (
                  <p className="text-[11px] leading-snug text-aviso mt-1">
                    {motivo}
                  </p>
                )}

                {!noAplica && m.interpretacion && (
                  <p className="text-[11px] leading-snug text-tinta-suave mt-1">
                    {m.interpretacion}
                  </p>
                )}

                <div className="text-[11px] text-tinta-suave mt-1.5">
                  {m.codigo}
                  {!noAplica && (
                    <>
                      {" · "}
                      {m.mejor === "alto"
                        ? "mejor cuanto más alto"
                        : m.mejor === "bajo"
                        ? "mejor cuanto más bajo"
                        : "sin dirección buena o mala"}
                      {m.rango && ` · va de ${m.rango}`}
                    </>
                  )}
                </div>
              </div>
            );
          })}
          {metricas.length === 0 && (
            <div className="text-tinta-suave">Sin métricas registradas.</div>
          )}
        </div>
      </details>
    </div>
  );
}
