/**
 * Los tipos de indicación y qué datos lleva cada uno.
 *
 * Es el espejo de `TIPOS` y `CAMPOS_POR_TIPO` en `lambdas/orquestador/plan_propuesta.py`:
 * la propuesta del plan sólo deja pasar los campos de su tipo, y el editor sólo muestra
 * esos. Si se separaran, el profesional guardaría un dato que no vio. `prueba_consulta.py`
 * comprueba que los nombres de los tipos coincidan.
 *
 * Cómo acompaña Seguimiento cada tipo está comentado en `ESQUEMA`
 * (`app/esquema/bootstrap_roble.mjs`): un control se ofrece para agendar, una señal de
 * alarma no se recuerda pero escala si la persona la cuenta, y así.
 */

import type { TipoIndicacion } from './tipos';

export type CampoDeTipo = 'duracion_dias' | 'plazo_dias' | 'sesiones' | 'centro_destino';
export type CentroDestino = 'CMU' | 'CAE' | 'externo';

export const TIPOS: Array<{ valor: TipoIndicacion; etiqueta: string }> = [
  { valor: 'medicamento', etiqueta: 'Medicamento' },
  { valor: 'autocuidado', etiqueta: 'Autocuidado' },
  { valor: 'tarea', etiqueta: 'Tarea' },
  { valor: 'control', etiqueta: 'Control' },
  { valor: 'sesiones', etiqueta: 'Sesiones' },
  { valor: 'examen', etiqueta: 'Examen' },
  { valor: 'remision', etiqueta: 'Remisión' },
  { valor: 'vigilancia', etiqueta: 'Señal de alarma' },
  { valor: 'reposo', etiqueta: 'Reposo' },
  { valor: 'otro', etiqueta: 'Otro' },
];

export const CAMPOS_POR_TIPO: Record<TipoIndicacion, CampoDeTipo[]> = {
  medicamento: ['duracion_dias'],
  autocuidado: ['duracion_dias'],
  tarea: ['duracion_dias'],
  control: ['plazo_dias', 'centro_destino'],
  sesiones: ['sesiones', 'centro_destino'],
  examen: ['plazo_dias'],
  remision: ['plazo_dias', 'centro_destino'],
  vigilancia: [],
  reposo: ['duracion_dias'],
  otro: ['duracion_dias'],
};

export const CENTROS_DESTINO: Array<{ valor: CentroDestino; etiqueta: string }> = [
  { valor: 'CMU', etiqueta: 'CMU' },
  { valor: 'CAE', etiqueta: 'CAE' },
  { valor: 'externo', etiqueta: 'Fuera de la universidad' },
];

/** Lo que el editor pregunta de cada campo, con la unidad dentro de la frase. */
export const ETIQUETA_DEL_CAMPO: Record<CampoDeTipo, string> = {
  duracion_dias: 'Durante (días)',
  plazo_dias: 'En (días)',
  sesiones: 'Sesiones',
  centro_destino: 'Dónde',
};

export function esTipo(valor: unknown): valor is TipoIndicacion {
  return TIPOS.some((t) => t.valor === valor);
}
