/**
 * Cliente de ROBLE para el navegador.
 *
 * El SDK de JavaScript **no persiste la sesión**: guarda los tokens en memoria y
 * ofrece `onTokenUpdate` para que la aplicación decida dónde ponerlos. Es una
 * diferencia real con el SDK de Python, que sí tiene un almacén enchufable. Aquí
 * se persiste en `localStorage` y se restaura al arrancar, que es lo que hace que
 * recargar la página no eche a la persona.
 *
 * `localStorage` y no una cookie `HttpOnly` porque no hay un backend propio que
 * ponga la cookie: la PWA habla directamente con ROBLE y con el API Gateway. Es
 * la decisión que el prototipo puede sostener, y su consecuencia está anotada en
 * docs/arquitectura.md: un XSS en la aplicación expondría el token. Lo que sí se
 * evita es guardar cualquier otra cosa: aquí sólo viven los dos tokens.
 */

import { createRobleClient, RobleApiHttpException } from 'roble-client';
import type { RobleApiClient } from 'roble-client';
import { ROLES, type Perfil, type Rol } from './tipos';

const CLAVE_SESION = 'caresync.sesion';

const BASE_URL = import.meta.env.VITE_ROBLE_BASE_URL as string | undefined;
const CONTRACT_ID = import.meta.env.VITE_ROBLE_CONTRACT_ID as string | undefined;

if (!BASE_URL || !CONTRACT_ID) {
  // Falla al cargar y no en el primer clic: una PWA compilada sin estas
  // variables no funciona de ninguna manera, y descubrirlo al intentar entrar
  // parece un problema de credenciales cuando es un problema de compilación.
  throw new Error(
    'Faltan VITE_ROBLE_BASE_URL o VITE_ROBLE_CONTRACT_ID. ' +
      'Compila con scripts/publicar_app.sh, que las toma de las salidas de Terraform.'
  );
}

interface SesionGuardada {
  accessToken: string;
  refreshToken: string;
}

function leerGuardada(): SesionGuardada | null {
  try {
    const crudo = localStorage.getItem(CLAVE_SESION);
    if (!crudo) return null;
    const datos = JSON.parse(crudo) as Partial<SesionGuardada>;
    if (!datos.accessToken || !datos.refreshToken) return null;
    return { accessToken: datos.accessToken, refreshToken: datos.refreshToken };
  } catch {
    // Un JSON corrupto no debe dejar la aplicación inarrancable.
    localStorage.removeItem(CLAVE_SESION);
    return null;
  }
}

function guardar(cliente: RobleApiClient): void {
  const acceso = cliente.accessToken;
  const refresco = cliente.refreshToken;
  if (!acceso || !refresco) {
    localStorage.removeItem(CLAVE_SESION);
    return;
  }
  localStorage.setItem(
    CLAVE_SESION,
    JSON.stringify({ accessToken: acceso, refreshToken: refresco })
  );
}

export const roble: RobleApiClient = createRobleClient({
  baseUrl: BASE_URL,
  contractId: CONTRACT_ID,
  timeoutMs: 20000,
});

// El SDK refresca el access token por su cuenta cuando una petición de datos
// responde 401. Sin este callback, el token renovado se quedaría sólo en memoria
// y la siguiente recarga usaría el viejo, ya vencido.
roble.onTokenUpdate = () => guardar(roble);

const guardada = leerGuardada();
if (guardada) {
  roble.setTokens(guardada);
}

/** ¿Hay algo que intentar restaurar? No garantiza que el token sirva. */
export function haySesionGuardada(): boolean {
  return roble.accessToken !== null;
}

export function tokenActual(): string {
  return roble.accessToken ?? '';
}

// ------------------------------------------------------------------ identidad

export interface Identidad {
  userId: string;
  email: string;
  nombre: string;
  rol: Rol;
  centro: 'CMU' | 'CAE' | null;
  perfilId: string;
}

/**
 * Quién es quien está usando la aplicación.
 *
 * `currentUser()` de ROBLE devuelve `sub` y `email`, nada más: ni nombre ni rol.
 * Los dos salen de la tabla `perfiles`, que es la que este proyecto controla y la
 * misma que consulta la Lambda. Si no hay perfil, el rol es `paciente`: el menos
 * privilegiado, igual que en el backend.
 */
export async function identidad(): Promise<Identidad> {
  const usuario = await roble.currentUser();
  const userId = String(usuario.sub);

  let perfil: Perfil | undefined;
  try {
    const filas = (await roble.read('perfiles', { user_id: userId })) as Perfil[];
    perfil = filas[0];
  } catch (error) {
    // Sin permiso de lectura sobre `perfiles` la aplicación sigue, como paciente.
    console.warn('No se pudo leer el perfil', error);
  }

  const rol = normalizarRol(perfil?.rol);
  return {
    userId,
    email: String(usuario.email ?? ''),
    nombre: String(perfil?.nombre ?? usuario.email ?? 'sin nombre'),
    rol,
    centro: centroDeRol(rol) ?? normalizarCentro(perfil?.centro),
    perfilId: String(perfil?._id ?? perfil?.id ?? ''),
  };
}

function normalizarRol(valor: unknown): Rol {
  const texto = String(valor ?? '')
    .trim()
    .toLowerCase()
    .replace(/[-\s]/g, '_');
  return (ROLES as readonly string[]).includes(texto) ? (texto as Rol) : 'paciente';
}

function normalizarCentro(valor: unknown): 'CMU' | 'CAE' | null {
  const texto = String(valor ?? '')
    .trim()
    .toUpperCase();
  return texto === 'CMU' || texto === 'CAE' ? texto : null;
}

/** Un rol administrativo tiene centro por definición; la tabla no lo contradice. */
function centroDeRol(rol: Rol): 'CMU' | 'CAE' | null {
  if (rol === 'admin_cmu') return 'CMU';
  if (rol === 'admin_cae') return 'CAE';
  return null;
}

// ---------------------------------------------------------------------- sesión

export async function entrar(email: string, password: string): Promise<Identidad> {
  await roble.login({ email: email.trim().toLowerCase(), password });
  guardar(roble);
  return identidad();
}

export async function salir(): Promise<void> {
  try {
    await roble.logout();
  } catch {
    // Que el servidor no confirme el cierre no puede impedir cerrar aquí.
  } finally {
    roble.clearTokens();
    localStorage.removeItem(CLAVE_SESION);
  }
}

export function olvidarSesion(): void {
  roble.clearTokens();
  localStorage.removeItem(CLAVE_SESION);
}

// ---------------------------------------------------------------------- errores

export function esSesionInvalida(error: unknown): boolean {
  return error instanceof RobleApiHttpException && (error.statusCode === 401 || error.statusCode === 403);
}

/**
 * Los límites de ROBLE que se pueden alcanzar usando la aplicación con normalidad.
 *
 * Medidos contra la API el 2026-08-27 leyendo las cabeceras `X-Ratelimit-*`, porque
 * el 429 llega como `ThrottlerException: Too Many Requests` y así no se distingue
 * cuál de los tres cubos se agotó ni cuánto hay que esperar:
 *
 * | ruta | límite | ventana |
 * |---|---|---|
 * | `/auth/<contrato>/signup` | 5 | 1 hora |
 * | `/auth/<contrato>/login` | 10 | 15 minutos |
 * | todo lo demás (leer, escribir, refrescar el token) | 100 | 1 minuto |
 *
 * Son por IP, no por cuenta: en una red compartida se agotan entre varios.
 */
const LIMITE_DE_INTENTOS =
  'ROBLE está limitando los intentos desde esta red. Espera unos minutos y vuelve a ' +
  'intentar: permite 10 inicios de sesión cada 15 minutos y 5 cuentas nuevas por hora.';

/** Mensaje decible para la persona a partir de un fallo del SDK. */
export function mensajeDeError(error: unknown): string {
  if (error instanceof RobleApiHttpException) {
    if (error.statusCode === 429) return LIMITE_DE_INTENTOS;
    if (error.statusCode === 401) return 'Tu sesión venció. Vuelve a entrar.';
    if (error.statusCode === 403) return 'Tu cuenta no tiene permiso para esto.';
    if (error.statusCode === 404) return 'Eso no existe o ya no está disponible.';
    if (error.statusCode >= 500) return 'ROBLE está con problemas. Intenta en un momento.';
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return 'Algo falló y no sabemos qué.';
}
