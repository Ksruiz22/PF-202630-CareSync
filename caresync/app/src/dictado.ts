/**
 * Dictado por voz con Amazon Transcribe en tiempo real.
 *
 * El recorrido: el micrófono del navegador → un `AudioWorklet` que lo pasa a PCM de
 * 16 bits a 16 kHz → mensajes de *event stream* de AWS por un WebSocket → Transcribe,
 * que devuelve el texto mientras la persona habla. La URL del WebSocket la firma el
 * orquestador (`POST /dictado/sesion`), porque la PWA no tiene credenciales de AWS.
 *
 * Por qué no la Web Speech API del navegador, que sería gratis y sin backend: en
 * Chrome manda el audio a Google, y lo que se dicta aquí es un plan de tratamiento.
 * Transcribe está en la misma cuenta que el modelo y en tiempo real no guarda el
 * audio. El motivo largo está en `lambdas/orquestador/dictado.py`.
 *
 * Lo que devuelve Transcribe son trozos: uno **parcial** que se va corrigiendo
 * mientras se habla, y al cerrar cada frase uno **final** que ya no cambia. La vista
 * pinta el parcial aparte y sólo pega al texto los finales, para que el profesional
 * no vea su texto reescribirse solo mientras lo edita.
 */

import { EventStreamCodec } from '@smithy/eventstream-codec';
import { fromUtf8, toUtf8 } from '@smithy/util-utf8';
import { abrirSesionDeDictado } from './consulta';

export type EstadoDelDictado = 'conectando' | 'escuchando' | 'terminando' | 'detenido';

export interface Oyente {
  /** El trozo que todavía puede cambiar. Vacío cuando ya se cerró. */
  alParcial(texto: string): void;
  /** Un trozo cerrado: se añade al texto y no vuelve a cambiar. */
  alFinal(texto: string): void;
  alEstado(estado: EstadoDelDictado): void;
  alError(mensaje: string): void;
}

export interface Dictado {
  /** Deja de escuchar, espera los últimos trozos finales y cierra la conexión. */
  detener(): Promise<void>;
}

const codec = new EventStreamCodec(toUtf8, fromUtf8);

/**
 * El procesador de audio, como texto para cargarlo desde un `Blob`.
 *
 * Va en una cadena y no en un archivo aparte porque un `AudioWorklet` se carga por
 * URL, y así no depende de cómo empaquete Vite un módulo que no se importa.
 *
 * Remuestrea con interpolación lineal desde la tasa del contexto (44,1 o 48 kHz, la
 * que tenga el micrófono) a 16 kHz. Pedirle al `AudioContext` que trabaje directamente
 * a 16 kHz sería más corto, pero Firefox se niega a conectar un micrófono a un
 * contexto con otra tasa. Manda bloques de 100 ms, que es lo que sugiere Transcribe.
 */
const PROCESADOR = `
class Pcm16 extends AudioWorkletProcessor {
  constructor(opciones) {
    super();
    const destino = opciones.processorOptions.tasaDestino;
    this.paso = sampleRate / destino;
    this.posicion = 0;
    this.anterior = 0;
    this.bloque = new Int16Array(Math.round(destino / 10));
    this.lleno = 0;
  }

  process(entradas) {
    const canal = entradas[0] && entradas[0][0];
    if (!canal || canal.length === 0) return true;
    const n = canal.length;
    let posicion = this.posicion;
    while (posicion <= n - 1) {
      const i = Math.floor(posicion);
      const fraccion = posicion - i;
      const a = i < 0 ? this.anterior : canal[i];
      const b = fraccion === 0 ? a : canal[i + 1];
      const valor = Math.max(-1, Math.min(1, a + (b - a) * fraccion));
      this.bloque[this.lleno++] = valor < 0 ? valor * 0x8000 : valor * 0x7fff;
      if (this.lleno === this.bloque.length) {
        this.port.postMessage(this.bloque.buffer.slice(0));
        this.lleno = 0;
      }
      posicion += this.paso;
    }
    this.posicion = posicion - n;
    this.anterior = canal[n - 1];
    return true;
  }
}
registerProcessor('pcm16-caresync', Pcm16);
`;

export function sePuedeDictar(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof AudioWorkletNode !== 'undefined' &&
    typeof WebSocket !== 'undefined'
  );
}

export async function dictar(oyente: Oyente): Promise<Dictado> {
  if (!sePuedeDictar()) {
    throw new Error('Este navegador no permite dictar. Prueba con Chrome, Edge, Firefox o Safari recientes.');
  }

  oyente.alEstado('conectando');

  // El micrófono primero: si la persona niega el permiso, no tiene sentido pedir la
  // firma ni abrir la conexión.
  let microfono: MediaStream;
  try {
    microfono = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
  } catch {
    oyente.alEstado('detenido');
    throw new Error('Sin permiso para usar el micrófono. Actívalo en el candado de la barra de direcciones.');
  }

  const apagarMicrofono = () => microfono.getTracks().forEach((pista) => pista.stop());

  let url: string;
  let tasa: number;
  try {
    const sesion = await abrirSesionDeDictado();
    url = sesion.url;
    tasa = sesion.tasa_de_muestreo;
  } catch (error) {
    apagarMicrofono();
    oyente.alEstado('detenido');
    throw error;
  }

  const contexto = new AudioContext();
  const direccion = URL.createObjectURL(new Blob([PROCESADOR], { type: 'application/javascript' }));
  try {
    await contexto.audioWorklet.addModule(direccion);
  } finally {
    URL.revokeObjectURL(direccion);
  }

  const fuente = contexto.createMediaStreamSource(microfono);
  const procesador = new AudioWorkletNode(contexto, 'pcm16-caresync', {
    processorOptions: { tasaDestino: tasa },
  });
  // Un nodo que no llega al destino puede quedarse sin procesar en algunos
  // navegadores. Se conecta a una ganancia en cero: llega, pero no suena.
  const silencio = contexto.createGain();
  silencio.gain.value = 0;
  fuente.connect(procesador);
  procesador.connect(silencio);
  silencio.connect(contexto.destination);

  const socket = new WebSocket(url);
  socket.binaryType = 'arraybuffer';
  // Lo que se dice mientras el WebSocket termina de abrir no se pierde.
  const enEspera: ArrayBuffer[] = [];
  let hablo = false;
  let cerrado = false;

  procesador.port.onmessage = (mensaje: MessageEvent<ArrayBuffer>) => {
    if (socket.readyState === WebSocket.OPEN) socket.send(eventoDeAudio(mensaje.data));
    else if (socket.readyState === WebSocket.CONNECTING) enEspera.push(mensaje.data);
  };

  const soltarAudio = () => {
    apagarMicrofono();
    procesador.port.onmessage = null;
    fuente.disconnect();
    procesador.disconnect();
    void contexto.close().catch(() => undefined);
  };

  socket.onopen = () => {
    for (const audio of enEspera.splice(0)) socket.send(eventoDeAudio(audio));
    oyente.alEstado('escuchando');
  };

  socket.onmessage = (mensaje: MessageEvent<ArrayBuffer>) => {
    const leido = codec.decode(new Uint8Array(mensaje.data));
    const tipo = leido.headers[':message-type']?.value;
    const cuerpo = leerJson(leido.body);

    if (tipo === 'event' && leido.headers[':event-type']?.value === 'TranscriptEvent') {
      hablo = true;
      for (const resultado of resultadosDe(cuerpo)) {
        if (resultado.parcial) oyente.alParcial(resultado.texto);
        else {
          oyente.alParcial('');
          if (resultado.texto) oyente.alFinal(resultado.texto);
        }
      }
      return;
    }

    if (tipo === 'exception') {
      const clase = String(leido.headers[':exception-type']?.value ?? '');
      console.warn('Transcribe cortó el dictado', clase, cuerpo);
      oyente.alError(mensajeDeExcepcion(clase));
    }
  };

  socket.onerror = () => {
    // Un 403 al abrir —firma vencida o permiso que falta— llega aquí sin detalle:
    // el navegador no deja leer la respuesta del intento de conexión.
    if (!hablo) oyente.alError('No se pudo conectar con el servicio de dictado.');
  };

  socket.onclose = () => {
    cerrado = true;
    soltarAudio();
    oyente.alParcial('');
    oyente.alEstado('detenido');
  };

  return {
    async detener() {
      if (cerrado) return;
      oyente.alEstado('terminando');
      soltarAudio();
      // Un evento de audio vacío es la forma de decirle a Transcribe que se acabó:
      // responde con los últimos trozos finales y cierra él la conexión. Si no lo
      // hace en unos segundos, se cierra desde aquí y se queda lo que ya llegó.
      if (socket.readyState === WebSocket.OPEN) socket.send(eventoDeAudio(new ArrayBuffer(0)));
      await new Promise<void>((listo) => {
        if (socket.readyState === WebSocket.CLOSED) return listo();
        const reloj = setTimeout(() => {
          socket.close();
          listo();
        }, 4000);
        socket.addEventListener(
          'close',
          () => {
            clearTimeout(reloj);
            listo();
          },
          { once: true }
        );
      });
    },
  };
}

function eventoDeAudio(audio: ArrayBuffer): Uint8Array {
  return codec.encode({
    headers: {
      ':message-type': { type: 'string', value: 'event' },
      ':event-type': { type: 'string', value: 'AudioEvent' },
      ':content-type': { type: 'string', value: 'application/octet-stream' },
    },
    body: new Uint8Array(audio),
  });
}

function leerJson(cuerpo: Uint8Array): unknown {
  try {
    return JSON.parse(toUtf8(cuerpo));
  } catch {
    return null;
  }
}

interface Resultado {
  texto: string;
  parcial: boolean;
}

/** `{ Transcript: { Results: [{ IsPartial, Alternatives: [{ Transcript }] }] } }` */
function resultadosDe(cuerpo: unknown): Resultado[] {
  const resultados = (cuerpo as { Transcript?: { Results?: unknown[] } } | null)?.Transcript?.Results;
  if (!Array.isArray(resultados)) return [];
  return resultados.map((crudo) => {
    const resultado = crudo as { IsPartial?: boolean; Alternatives?: Array<{ Transcript?: string }> };
    return {
      texto: String(resultado.Alternatives?.[0]?.Transcript ?? '').trim(),
      parcial: resultado.IsPartial === true,
    };
  });
}

function mensajeDeExcepcion(clase: string): string {
  if (clase === 'LimitExceededException') {
    return 'Hay demasiados dictados abiertos a la vez. Espera un momento y vuelve a intentarlo.';
  }
  if (clase === 'BadRequestException') {
    return 'El servicio de dictado no entendió el audio. Vuelve a intentarlo.';
  }
  return 'El dictado se detuvo por un problema del servicio. Lo que ya estaba escrito se conserva.';
}
