/**
 * Lo que las pantallas le piden al mundo.
 *
 * Es una interfaz para que el modo de demostración no se cuele en las pantallas con
 * `if (demo)`: `fuenteRoble` y `fuenteDemo` son intercambiables y la pantalla no sabe
 * cuál tiene.
 */

import type {
  AgenteDestino,
  Identidad,
  Indicacion,
  RespuestaAgente,
  Tratamiento,
} from './tipos';

export interface Reporte {
  tratamiento: Tratamiento;
  indicacion: Indicacion;
  cumplida: boolean;
  nota?: string;
  /** La toma a la que responde. Sin ella es un hito o una indicación sin horario. */
  programadoPara?: Date;
}

export interface Fuente {
  esDemo: boolean;
  restaurar(): Promise<Identidad | null>;
  entrar(email: string, password: string): Promise<Identidad>;
  salir(): Promise<void>;
  /** Los casos vigentes de la persona, del más reciente al más antiguo. */
  tratamientos(quien: Identidad): Promise<Tratamiento[]>;
  reportar(quien: Identidad, reporte: Reporte): Promise<void>;
  /** Sin `agente` lo decide el orquestador según el estado del caso. */
  hablar(mensaje: string, casoId: string, agente?: AgenteDestino): Promise<RespuestaAgente>;
}

/** Un 401: la sesión ya no sirve y hay que volver a entrar. */
export class SesionVencida extends Error {}
