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
 *
 * **Y si hay más de uno, también `paciente`.** El rol `user` de ROBLE ya no puede
 * actualizar `perfiles`, pero conserva `all:create` —lo necesita para que registrarse
 * escriba su propia fila—, así que una cuenta podría insertar una **segunda** fila con
 * su mismo `user_id` y un rol inventado. ROBLE no tiene forma de poner una restricción
 * `UNIQUE` sobre una tabla que ya existe (la Consola SQL sólo admite `ADD COLUMN`), así
 * que el desempate se hace aquí y se hace **fallando cerrado**: dos filas para un
 * `user_id` es una anomalía, y ante una anomalía el rol es el menos privilegiado. Elegir
 * «la primera» o «la más antigua» no serviría: el atacante escribe él el `creado_en`.
 * `_resolver_actor` en `roble_acceso.py` hace lo mismo, y por el mismo motivo.
 */
export async function identidad(): Promise<Identidad> {
  const usuario = await roble.currentUser();
  const userId = String(usuario.sub);

  let perfil: Perfil | undefined;
  try {
    const filas = (await roble.read('perfiles', { user_id: userId })) as Perfil[];
    if (filas.length > 1) {
      console.warn(
        `Hay ${filas.length} filas de perfiles para el mismo user_id; se entra como paciente`
      );
    } else {
      perfil = filas[0];
    }
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

// ------------------------------------------------- inicio de sesion con Google

/**
 * Entrar con Google, escrito a mano con `fetch`.
 *
 * El SDK `roble-client` **no tiene nada de inicio de sesión social** (comprobado en
 * la versión 3.0: ni un método, ni un tipo), así que las dos llamadas se hacen
 * directas contra las mismas rutas del contrato que usa el SDK para todo lo demás.
 * No están documentadas; se descubrieron probando contra la API el 2026-09-21:
 *
 * | paso | petición |
 * |---|---|
 * | arrancar | `POST /auth/<contrato>/auth/google/start` con `{ redirect }` → `{ url, state }` |
 * | volver | ROBLE redirige al destino con `?code=…` o `?error=…&error_description=…` |
 * | canjear | `POST /auth/<contrato>/auth/token` con `{ code }` → los dos tokens |
 *
 * Cuatro detalles que no se adivinan:
 *
 * - **`redirect` es el *nombre* de un destino registrado en la consola**, no una URL.
 *   Mandar una URL no funciona, y es lo correcto: si el servidor aceptara cualquier
 *   dirección, sería un redirector abierto con el código de sesión en la mano.
 * - **El `code` sirve una sola vez**; el segundo canje responde 400 «Código inválido
 *   o expirado». De ahí que se lea al importar el módulo y se memorice la promesa:
 *   `StrictMode` monta los efectos dos veces en desarrollo.
 * - **Google devuelve a ROBLE**, no a la PWA: la URI registrada en la consola de
 *   Google es `https://roble-api.test-openlab.uninorte.edu.co/google/callback` —sin
 *   `/auth`, al contrario que la de GitHub en la misma pantalla—, y el intercambio
 *   con el secreto ocurre del lado de ROBLE. La PWA nunca ve el `client_secret`.
 * - **Google afirma si el correo está verificado**, así que ROBLE vincula la entrada
 *   a la cuenta que ya tenga ese correo en vez de crear una segunda. Entrar y
 *   registrarse son el mismo acto: no hay «cuenta de Google» aparte.
 */

interface Regreso {
  code: string | null;
  /** Mensaje ya decible, si Google o ROBLE rechazaron la entrada. */
  fallo: string | null;
}

/**
 * El regreso se lee **al importar el módulo** y se borra de la barra de direcciones
 * en el mismo acto.
 *
 * Borrarlo no es cosmética: el `code` queda si no en el historial y en cualquier
 * `Referer`, y recargar la página reintentaría un código ya gastado y mostraría un
 * error que no existe.
 */
const regreso: Regreso = leerRegreso();

function leerRegreso(): Regreso {
  const parametros = new URLSearchParams(location.search);
  const code = parametros.get('code');
  const error = parametros.get('error');
  const descripcion = parametros.get('error_description');
  if (!code && !error) return { code: null, fallo: null };

  for (const clave of ['code', 'state', 'error', 'error_description']) {
    parametros.delete(clave);
  }
  const consulta = parametros.toString();
  history.replaceState(null, '', location.pathname + (consulta ? `?${consulta}` : '') + location.hash);

  return {
    code,
    fallo: error ? descripcion || `Google no autorizó la entrada (${error}).` : null,
  };
}

/** ¿Esta carga de la página es la vuelta de Google? */
export function hayRegresoDeGoogle(): boolean {
  return regreso.code !== null || regreso.fallo !== null;
}

/**
 * Manda la pestaña a Google. No devuelve nada porque, cuando funciona, ya no hay
 * aplicación aquí: la siguiente carga es el regreso.
 */
export async function iniciarConGoogle(): Promise<void> {
  const datos = await pedir<{ url?: string }>('auth/google/start', {
    redirect: destinoDeRetorno(),
  });
  if (!datos.url) throw new Error('ROBLE no dijo a dónde mandar a la persona para entrar con Google.');
  location.assign(datos.url);
}

let canje: Promise<Identidad> | null = null;

/** Canjea el código del regreso por una sesión. Una sola vez, aunque se llame dos. */
export function completarGoogle(): Promise<Identidad> {
  canje ??= canjear();
  return canje;
}

async function canjear(): Promise<Identidad> {
  if (regreso.fallo) throw new Error(regreso.fallo);
  if (!regreso.code) throw new Error('Esta página no es un regreso de Google.');

  const datos = await pedir<{ accessToken?: string; refreshToken?: string }>('auth/token', {
    code: regreso.code,
  });
  if (!datos.accessToken || !datos.refreshToken) {
    throw new Error('ROBLE aceptó el código pero no devolvió la sesión.');
  }
  roble.setTokens({ accessToken: datos.accessToken, refreshToken: datos.refreshToken });
  guardar(roble);

  const quien = await identidad();
  return quien.perfilId ? quien : crearPerfilDeGoogle(quien);
}

/**
 * La fila de `perfiles` que una cuenta de Google no trae.
 *
 * Al registrarse con correo y contraseña la escribe `Acceso.tsx`; una cuenta que
 * llega por Google nunca pasa por ese formulario, así que sin esto entraría sin
 * nombre —se mostraría el correo— y el personal administrativo no la vería en
 * ninguna lista. El rol es `paciente`, el mismo que da el registro: un rol
 * administrativo lo asigna quien administra el contrato, nunca el proveedor.
 *
 * El nombre sale de `GET /auth/<contrato>/me`, que es lo único que lo devuelve:
 * `currentUser()` habla con `/verify-token` y ese sólo trae `sub` y `email`.
 */
async function crearPerfilDeGoogle(quien: Identidad): Promise<Identidad> {
  try {
    await roble.create('perfiles', {
      user_id: quien.userId,
      nombre: (await nombreEnRoble()) || quien.email,
      email: quien.email,
      rol: 'paciente',
      centro: null,
      creado_en: new Date().toISOString(),
    });
  } catch (fallo) {
    // Sin fila se entra igual y las dos capas tratan la cuenta como paciente, que es
    // el rol que le tocaba. Lo que falta es el nombre, y se arregla con `--perfil`.
    console.warn('No se pudo crear el perfil de la cuenta de Google', fallo);
    return quien;
  }
  // Se relee para que salgan el `perfilId` —lo necesita editar el perfil— y el nombre.
  return identidad();
}

async function nombreEnRoble(): Promise<string> {
  try {
    const respuesta = await fetch(`${BASE_URL}/auth/${CONTRACT_ID}/me`, {
      headers: { Authorization: `Bearer ${tokenActual()}` },
    });
    if (!respuesta.ok) return '';
    const datos = (await respuesta.json()) as { name?: unknown };
    return String(datos.name ?? '').trim();
  } catch {
    // El nombre es un adorno; su ausencia no puede impedir entrar.
    return '';
  }
}

/**
 * Cuál de los destinos registrados en la consola pedir.
 *
 * Son dos, y los nombres son los que están dados de alta en el proyecto
 * `caresync_cab021ce03`: `default` apunta a la PWA publicada en Amplify y `local` a
 * `http://localhost:5173/`, para poder probar con `npm run dev`. Se elige por el
 * host y no por una variable de compilación porque el servidor de desarrollo no pasa
 * por `publicar_app.sh`, que es quien inyecta las variables.
 */
function destinoDeRetorno(): string {
  return location.hostname === 'localhost' ? 'local' : 'default';
}

async function pedir<T>(ruta: string, cuerpo: unknown): Promise<T> {
  const respuesta = await fetch(`${BASE_URL}/auth/${CONTRACT_ID}/${ruta}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cuerpo),
  });

  const texto = await respuesta.text();
  let datos: unknown = null;
  try {
    datos = texto ? JSON.parse(texto) : null;
  } catch {
    // Un cuerpo que no es JSON sólo importa para el mensaje de error.
  }

  if (!respuesta.ok) {
    throw new Error(mensajeDeCuerpo(datos) || `ROBLE respondió ${respuesta.status} al entrar con Google.`);
  }
  return datos as T;
}

/** ROBLE responde `{ message }`, y a veces una lista de mensajes. */
function mensajeDeCuerpo(datos: unknown): string {
  if (!datos || typeof datos !== 'object') return '';
  const mensaje = (datos as { message?: unknown }).message;
  if (Array.isArray(mensaje)) return mensaje.map(String).join('. ');
  return mensaje ? String(mensaje) : '';
}

// ---------------------------------------------------------------------- errores

export function esSesionInvalida(error: unknown): boolean {
  return error instanceof RobleApiHttpException && (error.statusCode === 401 || error.statusCode === 403);
}

/**
 * Un 5xx de ROBLE, que en este contrato casi siempre es **un permiso de tabla que
 * falta**.
 *
 * ROBLE no responde 403 cuando el rol no puede actualizar una tabla: responde 500, y
 * eso se lee igual que «el servidor está caído». Está documentado en
 * docs/runbook-roble.md; quien llama puede usar esto para sugerir el permiso concreto
 * en lugar de dejar a la persona mirando un error genérico.
 */
export function esFalloDeServidor(error: unknown): boolean {
  return error instanceof RobleApiHttpException && error.statusCode >= 500;
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
