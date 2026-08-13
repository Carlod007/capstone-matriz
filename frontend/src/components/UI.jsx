import { useCallback, useState } from "react";

import { CtxAviso } from "./avisos";

/**
 * Primitivas de interfaz compartidas.
 *
 * Existen para que las pantallas no repitan decisiones visuales. Antes cada
 * una elegía sus propios márgenes, sus colores y su forma de avisar, y el
 * resultado era una sucesión de bloques de texto sin jerarquía: todo pesaba
 * lo mismo, así que nada destacaba.
 *
 * El criterio aquí es que la forma haga el trabajo que hacía el texto. Un
 * estado se comunica con un punto de color y una palabra, no con una frase.
 * Lo que hay que explicar se explica, pero plegado, para que esté disponible
 * sin ocupar la pantalla de quien ya lo sabe.
 */

/* ================================================================ avisos */

/** Sustituye a alert(), que bloquea la página y no permite seguir leyendo.
 *  El hook para consumirlo está en avisos.js, no aquí: ver el motivo allí. */
export function ProveedorAvisos({ children }) {
  const [avisos, setAvisos] = useState([]);

  const avisar = useCallback((mensaje, tono = "info", duracion = 4500) => {
    const id = Math.random().toString(36).slice(2);
    setAvisos((v) => [...v, { id, mensaje, tono }]);
    if (duracion) {
      setTimeout(() => setAvisos((v) => v.filter((a) => a.id !== id)), duracion);
    }
  }, []);

  const tonos = {
    info: "border-acento-borde bg-acento-claro text-acento-fuerte",
    bien: "border-bien-borde bg-bien-claro text-bien",
    aviso: "border-aviso-borde bg-aviso-claro text-aviso",
    mal: "border-mal-borde bg-mal-claro text-mal",
  };

  return (
    <CtxAviso.Provider value={avisar}>
      {children}
      <div className="fixed bottom-5 right-5 z-[60] flex flex-col gap-2 w-80 max-w-[calc(100vw-2.5rem)]">
        {avisos.map((a) => (
          <div
            key={a.id}
            role="status"
            className={`rounded-lg border px-3.5 py-2.5 text-sm leading-snug ${
              tonos[a.tono] || tonos.info
            }`}
            style={{ boxShadow: "var(--sombra-2)", animation: "entrar .18s ease-out" }}
          >
            {a.mensaje}
          </div>
        ))}
      </div>
      <style>{`@keyframes entrar{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}`}</style>
    </CtxAviso.Provider>
  );
}

/* ================================================================ piezas */

/** Estado en una palabra y un punto de color, en vez de una frase. */
export function Estado({ tono = "neutro", children }) {
  const c = {
    neutro: "text-tinta-suave bg-tinta-suave",
    bien: "text-bien bg-bien",
    aviso: "text-aviso bg-aviso",
    mal: "text-mal bg-mal",
    acento: "text-acento bg-acento",
  }[tono];
  const [texto, punto] = c.split(" ");
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${texto}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${punto}`} />
      {children}
    </span>
  );
}

export function Panel({ children, className = "", ...props }) {
  return (
    <div
      className={`rounded-xl border border-borde bg-superficie ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

/** Encabezado de sección: da jerarquía sin recurrir a más párrafos. */
export function Seccion({ titulo, apoyo, acciones, children }) {
  return (
    <section className="mb-8">
      {(titulo || acciones) && (
        <div className="flex items-end justify-between gap-4 mb-3">
          <div>
            {titulo && (
              <h2 className="text-sm font-semibold text-tinta tracking-wide uppercase">
                {titulo}
              </h2>
            )}
            {apoyo && (
              <p className="text-xs text-tinta-suave mt-1 leading-relaxed max-w-xl">
                {apoyo}
              </p>
            )}
          </div>
          {acciones && (
            <div className="flex items-center gap-2 shrink-0">{acciones}</div>
          )}
        </div>
      )}
      {children}
    </section>
  );
}

/** Explicación disponible sin ocupar sitio a quien ya la conoce. */
export function Nota({ titulo, children, tono = "aviso" }) {
  const c = {
    aviso: "border-aviso-borde bg-aviso-claro text-aviso",
    info: "border-acento-borde bg-acento-claro text-acento-fuerte",
  }[tono];
  return (
    <details className={`rounded-lg border ${c} text-sm`}>
      <summary className="cursor-pointer select-none px-3 py-2 font-medium marker:text-current">
        {titulo}
      </summary>
      <div className="px-3 pb-3 pt-0 leading-relaxed opacity-90">{children}</div>
    </details>
  );
}

export function Vacio({ titulo, children, accion }) {
  return (
    <div className="rounded-xl border border-dashed border-borde-fuerte bg-hundido/50 px-6 py-12 text-center">
      <p className="text-sm font-medium text-tinta">{titulo}</p>
      {children && (
        <p className="text-xs text-tinta-suave mt-1.5 max-w-sm mx-auto leading-relaxed">
          {children}
        </p>
      )}
      {accion && <div className="mt-5">{accion}</div>}
    </div>
  );
}

export function Progreso({ hecho, total, etiqueta }) {
  const pct = total > 0 ? Math.round((hecho / total) * 100) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-xs text-tinta-media">{etiqueta}</span>
        <span className="text-xs text-tinta-suave tabular-nums">
          {hecho} / {total}
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-hundido overflow-hidden">
        <div
          className="h-full bg-acento transition-[width] duration-300 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/* ================================================================ tablas */

export function Tabla({ children, className = "" }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-borde bg-superficie">
      <table className={`min-w-full text-sm ${className}`}>{children}</table>
    </div>
  );
}

export function Th({ children, className = "", ancho }) {
  return (
    <th
      className={`px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider
                  text-tinta-suave bg-hundido border-b border-borde ${className}`}
      style={ancho ? { width: ancho } : undefined}
    >
      {children}
    </th>
  );
}

export function Td({ children, className = "" }) {
  return <td className={`px-4 py-3 align-top ${className}`}>{children}</td>;
}

export function Fila({ children, className = "" }) {
  return (
    <tr
      className={`border-b border-borde last:border-0 hover:bg-hundido/40 transition-colors ${className}`}
    >
      {children}
    </tr>
  );
}

/** Texto largo en una celda: se recorta y se ofrece completo al pasar el ratón. */
export function Recorte({ children, lineas = 2 }) {
  return (
    <span
      title={typeof children === "string" ? children : undefined}
      className="block overflow-hidden"
      style={{
        display: "-webkit-box",
        WebkitLineClamp: lineas,
        WebkitBoxOrient: "vertical",
      }}
    >
      {children}
    </span>
  );
}

/* ================================================================ archivos */

/**
 * Zona de arrastrar y soltar con selección múltiple.
 *
 * Antes se creaba un input suelto por cada archivo, de modo que subir cinco
 * artículos eran cinco ciclos manuales de diálogo del sistema.
 */
export function ZonaArchivos({ onArchivos, disabled, texto, apoyo }) {
  const [encima, setEncima] = useState(false);

  const tomar = (lista) => {
    const pdfs = [...lista].filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length) onArchivos(pdfs);
    return pdfs.length;
  };

  const abrir = () => {
    if (disabled) return;
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/pdf";
    input.multiple = true;
    input.onchange = (e) => tomar(e.target.files || []);
    input.click();
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setEncima(true);
      }}
      onDragLeave={() => setEncima(false)}
      onDrop={(e) => {
        e.preventDefault();
        setEncima(false);
        if (!disabled) tomar(e.dataTransfer.files || []);
      }}
      onClick={abrir}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && abrir()}
      aria-disabled={disabled}
      className={`rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors
        ${disabled ? "opacity-50 cursor-not-allowed border-borde" : "cursor-pointer"}
        ${
          encima
            ? "border-acento bg-acento-claro"
            : "border-borde-fuerte bg-hundido/40 hover:border-acento hover:bg-acento-claro/40"
        }`}
    >
      <svg
        viewBox="0 0 24 24"
        className="w-7 h-7 mx-auto mb-3 text-tinta-suave"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 16V4m0 0L8 8m4-4 4 4" />
        <path d="M20 16v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2" />
      </svg>
      <p className="text-sm font-medium text-tinta">{texto}</p>
      {apoyo && <p className="text-xs text-tinta-suave mt-1">{apoyo}</p>}
    </div>
  );
}
