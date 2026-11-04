/**
 * La app de verdad: ROBLE para los datos y `POST /agente` para hablar.
 *
 * **Quién escribe qué**, porque aquí hay una decisión que se aparta de la PWA:
 *
 * - **Reportar una toma va directo a `adherencia`**, con `origen: 'app'`. La PWA obliga a
 *   decírselo al agente, y para un «sí» de un toque eso sería una vuelta del modelo cada
 *   ocho horas, que además puede no llamar a la herramienta. Un botón no es ambiguo, así
 *   que no hay nada que interpretar. Deja el mismo evento que `registrar_adherencia`, y
 *   el profesional y la vigilancia de la Lambda lo leen igual.
 * - **Cómo se siente va por el agente, siempre.** Un 3 de 10 o una frase suelta pueden
 *   ser una señal de alarma, y quien revisa eso y llama a `escalar_urgencia` es él. Una
 *   escritura directa guardaría el número y nadie miraría si había que escalar.
 *
 * Nada de esto crea ni cambia una indicación: el plan sigue siendo del profesional.
 */

import { createRobleClient, RobleApiHttpException } from 'roble-client';
import { almacen } from './almacen';
import { fecha } from './agenda';
import { SesionVencida, type Fuente, type Reporte } from './fuente';
import {
  esVerdad,
  idDe,
  type Adherencia,
  type AgenteDestino,
  type Caso,
  type Cita,
  type Evolucion,
  type FilaConversacion,
  type Identidad,
  type Indicacion,
  type Plan,
  type Recordatorio,
  type RespuestaAgente,
  type Tratamiento,
  type Turno,
} from './tipos';

const CLAVE_SESION = 'caresync.sesion';

const BASE_URL = process.env.EXPO_PUBLIC_ROBLE_BASE_URL;
const CONTRACT_ID = process.env.EXPO_PUBLIC_ROBLE_CONTRACT_ID;
const API_URL = process.env.EXPO_PUBLIC_API_URL?.replace(/\/+$/, '');

const roble = createRobleClient({
  baseUrl: BASE_URL ?? '',
  contractId: CONTRACT_ID ?? '',
  timeoutMs: 20000,
});

async function guardarSesion(): Promise<void> {
  const { accessToken, refreshToken } = roble;
  if (accessToken && refreshToken) {
    await almacen.guardar(CLAVE_SESION, JSON.stringify({ accessToken, refreshToken }));
  } else {
    await almacen.borrar(CLAVE_SESION);
  }
}

// El SDK renueva el token solo tras un 401; sin esto, el nuevo se perdería al cerrar.
roble.onTokenUpdate = () => void guardarSesion();

/**
 * Renueva el token si vence en menos de dos minutos, igual que `renovarSiVence` en la
 * PWA. El SDK sólo lo renueva tras un 401 de ROBLE, y `/agente` no pasa por el SDK: con
 * la app abierta un rato, el backend recibía un token vencido y la persona salía de la
 * sesión, o vencía a mitad de un turno que ya había escrito en ROBLE.
 */
async function renovarSiVence(): Promise<void> {
  const token = roble.accessToken;
  if (!token || !roble.refreshToken) return;
  try {
    const carga = (token.split('.')[1] ?? '').replace(/-/g, '+').replace(/_/g, '/');
    const { exp } = JSON.parse(atob(carga)) as { exp?: unknown };
    if (typeof exp === 'number' && exp - Date.now() / 1000 > 120) return;
    await (roble as unknown as { refreshAccessToken(): Promise<void> }).refreshAccessToken();
    await guardarSesion();
  } catch {
    // Sigue con el token que hay: si ya venció, el 401 lleva a volver a entrar.
  }
}

async function identidad(): Promise<Identidad> {
  const usuario = await roble.currentUser();
  const userId = String(usuario.sub);
  const perfiles = (await leer<{ nombre?: string }>('perfiles', { user_id: userId })) ?? [];
  return {
    userId,
    email: String(usuario.email ?? ''),
    nombre: String(perfiles[0]?.nombre ?? usuario.email ?? ''),
  };
}

/** Una tabla que falla no tumba las demás: que no haya plan no deja la pantalla en blanco. */
async function leer<T>(tabla: string, filtros: Record<string, unknown>): Promise<T[]> {
  try {
    return (await roble.read(tabla, filtros)) as T[];
  } catch (error) {
    if (error instanceof RobleApiHttpException && error.statusCode === 401) {
      throw new SesionVencida('Tu sesión venció. Vuelve a entrar.');
    }
    console.warn(`No se pudo leer ${tabla}`, error);
    return [];
  }
}

function descendente<T>(campo: keyof T) {
  return (a: T, b: T) => String(b[campo] ?? '').localeCompare(String(a[campo] ?? ''));
}

/** Igual que `turnosParaLaPersona` en la PWA: sin notas `[sistema]` ni lo del personal. */
function turnosDe(filas: FilaConversacion[]): Turno[] {
  const ordenadas = [...filas].sort((a, b) =>
    String(a.creado_en ?? '').localeCompare(String(b.creado_en ?? ''))
  );
  const turnos: Turno[] = [];
  let ultimoHumano = '';
  for (const fila of ordenadas) {
    const texto = String(fila.contenido ?? '').trim();
    const autor = String(fila.autor ?? 'paciente');
    if (!texto || autor === 'sistema') continue;
    if (autor === 'agente') {
      if (ultimoHumano === 'paciente') turnos.push({ quien: 'agente', texto });
      continue;
    }
    ultimoHumano = autor;
    if (autor === 'paciente') turnos.push({ quien: 'yo', texto });
  }
  return turnos.slice(-30);
}

async function tratamientoDe(caso: Caso): Promise<Tratamiento> {
  const casoId = idDe(caso);
  const [planes, indicaciones, adherencias, evoluciones, citas, recordatorios, hilo] =
    await Promise.all([
      leer<Plan>('planes', { caso_id: casoId }),
      leer<Indicacion>('indicaciones', { caso_id: casoId }),
      leer<Adherencia>('adherencia', { caso_id: casoId }),
      leer<Evolucion>('evolucion', { caso_id: casoId }),
      leer<Cita>('citas', { caso_id: casoId }),
      leer<Recordatorio>('recordatorios', { caso_id: casoId }),
      leer<FilaConversacion>('conversaciones', { caso_id: casoId }),
    ]);
  return {
    caso,
    plan: [...planes].sort(descendente<Plan>('creado_en'))[0] ?? null,
    indicaciones: indicaciones.filter((fila) => esVerdad(fila.activa)),
    adherencias,
    evoluciones: [...evoluciones].sort(descendente<Evolucion>('reportado_en')),
    citas,
    recordatorios,
    turnos: turnosDe(hilo),
  };
}

export const fuenteRoble: Fuente = {
  esDemo: false,

  async restaurar() {
    const crudo = await almacen.leer(CLAVE_SESION);
    if (!crudo) return null;
    try {
      roble.setTokens(JSON.parse(crudo) as { accessToken: string; refreshToken: string });
      return await identidad();
    } catch {
      roble.clearTokens();
      await almacen.borrar(CLAVE_SESION);
      return null;
    }
  },

  async entrar(email, password) {
    await roble.login({ email: email.trim().toLowerCase(), password });
    await guardarSesion();
    return identidad();
  },

  async salir() {
    try {
      await roble.logout();
    } catch {
      // Que el servidor no confirme el cierre no puede impedir cerrar aquí.
    } finally {
      roble.clearTokens();
      await almacen.borrar(CLAVE_SESION);
    }
  },

  async tratamientos(quien) {
    const casos = await leer<Caso>('casos', { paciente_user_id: quien.userId });
    const vigentes = casos
      .filter((caso) => caso.estado !== 'cerrado')
      .sort(descendente<Caso>('creado_en'));
    return Promise.all(vigentes.map(tratamientoDe));
  },

  async reportar(quien, { tratamiento, indicacion, cumplida, nota, programadoPara }) {
    const casoId = idDe(tratamiento.caso);
    const indicacionId = idDe(indicacion);

    await roble.create('adherencia', {
      caso_id: casoId,
      indicacion_id: indicacionId,
      cumplida,
      nota: (nota ?? '').slice(0, 400),
      reportado_en: new Date().toISOString(),
      programado_para: programadoPara?.toISOString() ?? null,
      origen: 'app',
    });

    // Lo mismo que `registrar_adherencia`: es lo que el profesional lee en la bitácora.
    // Si falla, el reporte ya quedó y lo que se pierde es la línea, no el dato.
    if (!cumplida) {
      try {
        await roble.create('eventos', {
          caso_id: casoId,
          tipo: 'indicacion_no_cumplida',
          severidad: 'info',
          actor_user_id: quien.userId,
          actor_rol: 'paciente',
          detalle: { indicacion_id: indicacionId, motivo: (nota ?? '').slice(0, 400) },
          creado_en: new Date().toISOString(),
        });
      } catch (error) {
        console.warn('No se pudo anotar el evento', error);
      }
    }

    // Lo ya respondido no tiene que salir por correo. `_materializar` sólo mira
    // `pendiente`, así que esto no le estorba para programar el siguiente.
    const ahora = Date.now();
    const yaLlegaron = tratamiento.recordatorios.filter(
      (fila) =>
        String(fila.indicacion_id ?? '') === indicacionId &&
        fila.estado === 'pendiente' &&
        (fecha(fila.programado_para)?.getTime() ?? Infinity) <= ahora + 2 * 60 * 60 * 1000
    );
    await Promise.allSettled(
      yaLlegaron.map((fila) => roble.update('recordatorios', idDe(fila), { estado: 'respondido' }))
    );
  },

  async hablar(mensaje, casoId, agente) {
    await renovarSiVence();
    const token = roble.accessToken;
    if (!token) throw new SesionVencida('Tu sesión venció. Vuelve a entrar.');

    const corte = new AbortController();
    const reloj = setTimeout(() => corte.abort(), 45000);
    let respuesta: Response;
    try {
      respuesta = await fetch(`${API_URL}/agente`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ mensaje, caso_id: casoId, agente }),
        signal: corte.signal,
      });
    } catch (error) {
      throw new Error(
        error instanceof Error && error.name === 'AbortError'
          ? 'El asistente tardó demasiado. Vuelve a intentarlo.'
          : 'No hay conexión con CareSync.'
      );
    } finally {
      clearTimeout(reloj);
    }

    const texto = await respuesta.text();
    let cuerpo: { error?: unknown } & Partial<RespuestaAgente> = {};
    try {
      cuerpo = texto ? JSON.parse(texto) : {};
    } catch {
      cuerpo = { error: texto.slice(0, 300) };
    }
    if (respuesta.status === 401) throw new SesionVencida('Tu sesión venció. Vuelve a entrar.');
    if (!respuesta.ok) {
      throw new Error(String(cuerpo.error ?? `El asistente respondió ${respuesta.status}.`));
    }
    return { ...cuerpo, respuesta: String(cuerpo.respuesta ?? '') };
  },
};

export function mensajeDeError(error: unknown): string {
  if (error instanceof RobleApiHttpException) {
    if (error.statusCode === 429) {
      return 'ROBLE está limitando los intentos desde esta red. Espera unos minutos.';
    }
    if (error.statusCode === 401) return 'Correo o contraseña incorrectos.';
    if (error.statusCode >= 500) return 'ROBLE está con problemas. Intenta en un momento.';
    return error.message;
  }
  return error instanceof Error ? error.message : 'Algo falló y no sabemos qué.';
}
