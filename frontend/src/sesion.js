/**
 * Sesión del usuario.
 *
 * Un único sitio por el que pasan todas las llamadas a la API, para que
 * ninguna se olvide de mandar el token. Antes cada componente llamaba a
 * `fetch` por su cuenta; con la sesión repartida así, basta una llamada
 * suelta para que una pantalla devuelva 401 sin que nadie entienda por qué.
 *
 * El token vive en `localStorage` y no en memoria: recargar la página no
 * debe cerrar la sesión. Es un compromiso conocido —una vulnerabilidad de
 * scripting en la página podría leerlo—; la alternativa, una cookie
 * `HttpOnly`, exige que el navegador la envíe sola y con ella llega el
 * riesgo de peticiones cruzadas, que pide su propia defensa. Para una
 * instancia de una sola persona, con el registro cerrado, no compensa.
 */

const CLAVE = "matriz.sesion";

let alExpirarCb = null;

/** Se llama cuando el servidor rechaza el token: caducó o dejó de valer. */
export function alExpirar(cb) {
  alExpirarCb = cb;
}

export function leerSesion() {
  try {
    const crudo = localStorage.getItem(CLAVE);
    return crudo ? JSON.parse(crudo) : null;
  } catch {
    // localStorage puede estar bloqueado (modo privado de algunos
    // navegadores) o guardar algo que no es JSON. Sin sesión, no roto.
    return null;
  }
}

export function guardarSesion(datos) {
  try {
    localStorage.setItem(CLAVE, JSON.stringify(datos));
  } catch {
    // Si no se puede guardar, la sesión dura lo que dure la pestaña.
  }
}

export function cerrarSesion() {
  try {
    localStorage.removeItem(CLAVE);
  } catch {
    // Nada que hacer: si no se pudo leer, tampoco había nada que borrar.
  }
}

export function token() {
  return leerSesion()?.token || null;
}

/**
 * `fetch` con la cabecera de sesión puesta.
 *
 * Un 401 no se devuelve al componente que llamó: significa que la sesión ya
 * no vale, y lo que toca es cerrarla y volver a la pantalla de entrada. Si
 * cada pantalla tuviera que interpretarlo, unas lo harían y otras mostrarían
 * un error incomprensible.
 */
export async function api(url, opciones = {}) {
  const t = token();
  const cabeceras = { ...(opciones.headers || {}) };
  if (t) cabeceras.Authorization = `Bearer ${t}`;

  const r = await fetch(url, { ...opciones, headers: cabeceras });

  if (r.status === 401) {
    cerrarSesion();
    if (alExpirarCb) alExpirarCb();
    const err = new Error("Sesión caducada");
    err.sesionCaducada = true;
    throw err;
  }
  return r;
}
