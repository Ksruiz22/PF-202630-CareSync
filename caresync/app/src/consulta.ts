/**
 * Las dos ayudas de la consulta del profesional, del lado de la PWA.
 *
 * - `proponerPlan`: manda lo que el profesional dictó o escribió y recibe el mismo
 *   contenido ordenado en resumen e indicaciones. **No guarda nada**: lo que vuelve
 *   es una propuesta para que la corrija, y el plan lo escribe después
 *   `registrarPlan` en `vistas/Profesional.tsx`, con su token, sólo si lo confirma.
 * - `abrirSesionDeDictado`: pide la URL firmada para hablarle a Amazon Transcribe.
 *   La usa `dictado.ts`.
 *
 * Quién puede llamarlas lo decide el backend (`_solo_profesional`): a cualquier otro
 * rol le responde 403, aunque esta vista nunca le enseñe el botón.
 */

import { pedirAlApi } from './agente';
import type { CentroDestino } from './tratamiento';
import type { TipoIndicacion } from './tipos';

export interface IndicacionPropuesta {
  texto: string;
  frecuencia: string;
  /** Lo sugiere el modelo y lo confirma el profesional, como la frecuencia. */
  tipo: TipoIndicacion;
  /** Sólo vienen los campos del tipo (`CAMPOS_POR_TIPO`); el resto, nulo. */
  duracion_dias: number | null;
  plazo_dias: number | null;
  sesiones: number | null;
  centro_destino: CentroDestino | null;
  /** Lo que dirá la función de recordatorios de esta frecuencia, según el backend. */
  programa_recordatorios: boolean;
}

export interface PropuestaDePlan {
  resumen: string;
  indicaciones: IndicacionPropuesta[];
  /** Lo que el modelo no pudo resolver con lo dictado: el profesional lo decide. */
  dudas: string[];
}

export interface SesionDeDictado {
  url: string;
  idioma: string;
  tasa_de_muestreo: number;
  vigencia_segundos: number;
}

export function proponerPlan(texto: string): Promise<PropuestaDePlan> {
  // Ordenar un dictado es una sola llamada al modelo sin herramientas: con 25 s sobra,
  // y es menos que el techo de 30 s del HTTP API para que el error sea el nuestro.
  return pedirAlApi<PropuestaDePlan>('/plan/propuesta', { texto }, { esperaMs: 25000 });
}

export function abrirSesionDeDictado(): Promise<SesionDeDictado> {
  return pedirAlApi<SesionDeDictado>('/dictado/sesion', {}, { esperaMs: 10000 });
}
