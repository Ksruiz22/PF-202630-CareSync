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
}

export async function hablar({ mensaje, casoId, agente }: PeticionAgente): Promise<RespuestaAgente> {
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
