/**
 * Cliente del orquestador de agentes.
 *
 * Una sola función y un solo endpoint: `POST /agente`. La PWA no elige qué
 * agente responde —eso lo decide el orquestador según el rol y el estado del
 * caso— y sólo puede *sugerirlo* con el campo `agente`, que el backend ignora si
 * no le corresponde a ese rol.
 *
 * El token va en la cabecera `Authorization`. El API Gateway no tiene
 * autorizador JWT a propósito: el orquestador necesita el token no sólo para
 * validar quién llama, sino para actuar contra ROBLE en su nombre. El motivo
 * largo está en infra/api.tf.
 *
 * **El modo simulación.** La misma función sirve para el simulador de triaje del
 * profesional (`vistas/SimuladorDeTriaje.tsx`): con `simulacion` el cuerpo lleva
 * `simulacion: true` y un `simulacion_id`, y el backend corre el turno completo
 * —modelo, protocolo, salvaguardas— pero **no ejecuta ninguna herramienta**: no
 * abre caso, no agenda, no manda correos y no dispara la alarma de urgencias. En
 * vez del efecto devuelve en `decisiones` lo que el modelo habría hecho, que es
 * justo lo que el profesional juzga.
 *
 * Quién puede simular **lo decide el backend**, no esta función ni la vista que la
 * llama: hoy admite `profesional`, `admin_cmu` y `admin_cae`, y a cualquier otro
 * rol le responde 403. Es el mismo criterio que el resto del sistema —un permiso se
 * comprueba en código del lado que tiene el efecto, no en la PWA—, así que la
 * comprobación por rol que haga la vista es cortesía para dar un mensaje decible,
 * nunca el control de acceso.
 *
 * El slug lo propone la PWA y el backend lo sanea y lo devuelve en
 * `simulacion_id`: hay que usar el que vuelve, porque es el que forma el `caso_id`
 * del hilo guardado en ROBLE.
 */

import { tokenActual } from './roble';
import type { RespuestaAgente } from './tipos';

const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/+$/, '');

if (!API_URL) {
  throw new Error(
    'Falta VITE_API_URL. Compila con scripts/publicar_app.sh, que la toma de la salida de Terraform.'
  );
}

export class ErrorDelAgente extends Error {
  constructor(
    readonly estado: number,
    mensaje: string
  ) {
    super(mensaje);
    this.name = 'ErrorDelAgente';
  }

  /** Un 401 significa que hay que volver a entrar, no que el mensaje esté mal. */
  get sesionVencida(): boolean {
    return this.estado === 401;
  }
}

export interface PeticionAgente {
  mensaje: string;
  casoId?: string;
  agente?: 'triaje' | 'agenda' | 'seguimiento';
  /**
   * Presente sólo cuando el turno es un ensayo: ver el comentario del módulo.
   *
   * Es un objeto y no un `boolean` + un `string` sueltos para que no exista la
   * combinación imposible de pedir simulación sin identificarla: el backend necesita
   * el slug para saber en qué hilo escribir, y una petición con `simulacion: true` y
   * sin id no tendría dónde guardarse.
   */
  simulacion?: { id: string };
}

export async function hablar({
  mensaje,
  casoId,
  agente,
  simulacion,
}: PeticionAgente): Promise<RespuestaAgente> {
  const token = tokenActual();
  if (!token) throw new ErrorDelAgente(401, 'No hay sesión activa.');

  // Un turno con herramientas puede tardar: el modelo hace varias vueltas y cada
  // una escribe en ROBLE. 45 s es holgado y aun así menor que el tiempo de espera
  // de la Lambda, para que el error que vea la persona sea el nuestro.
  const corte = new AbortController();
  const reloj = setTimeout(() => corte.abort(), 45000);

  let respuesta: Response;
  try {
    respuesta = await fetch(`${API_URL}/agente`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        mensaje,
        ...(casoId ? { caso_id: casoId } : {}),
        ...(agente ? { agente } : {}),
        // Las dos claves van juntas o no va ninguna: el backend lee el modo de
        // `simulacion` y el hilo de `simulacion_id`, y una sin la otra es una
        // petición que no sabría dónde escribir.
        ...(simulacion ? { simulacion: true, simulacion_id: simulacion.id } : {}),
      }),
      signal: corte.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ErrorDelAgente(504, 'El asistente tardó demasiado. Vuelve a intentarlo.');
    }
    throw new ErrorDelAgente(0, 'No hay conexión con CareSync.');
  } finally {
    clearTimeout(reloj);
  }

  const cuerpo = await leerCuerpo(respuesta);

  if (!respuesta.ok) {
    // El backend manda `{"error": "<mensaje público>"}`; nunca el detalle interno.
    const mensajeError =
      (typeof cuerpo === 'object' && cuerpo && 'error' in cuerpo
        ? String((cuerpo as { error: unknown }).error)
        : '') || `El asistente respondió ${respuesta.status}.`;
    throw new ErrorDelAgente(respuesta.status, mensajeError);
  }

  return cuerpo as RespuestaAgente;
}

async function leerCuerpo(respuesta: Response): Promise<unknown> {
  const texto = await respuesta.text();
  if (!texto) return {};
  try {
    return JSON.parse(texto);
  } catch {
    return { error: texto.slice(0, 300) };
  }
}

/** Sonda sin token: sirve para saber si el problema es la sesión o el despliegue. */
export async function salud(): Promise<unknown> {
  const respuesta = await fetch(`${API_URL}/salud`);
  return respuesta.json();
}
