import { createContext, useContext } from "react";

/**
 * Contexto de avisos, separado de UI.jsx a proposito.
 *
 * Fast Refresh solo conserva el estado de un modulo si este exporta
 * unicamente componentes. Con el hook viviendo junto a las piezas visuales,
 * cualquier retoque de estilo reiniciaba el estado de toda la pantalla en
 * caliente: el proyecto a medio escribir se perdia al cambiar un margen.
 */

export const CtxAviso = createContext(() => {});

/** Devuelve `avisar(mensaje, tono, duracion)`. Sustituye a alert(). */
export const useAviso = () => useContext(CtxAviso);
