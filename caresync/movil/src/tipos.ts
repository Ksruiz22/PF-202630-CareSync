/**
 * Las filas de ROBLE que usa la app, laxas por la misma razón que las de la PWA:
 * `read` devuelve las columnas tal cual, y un `boolean` o un `int4` pueden llegar como
 * texto. Los nombres son los de `ESQUEMA` en `app/esquema/bootstrap_roble.mjs`.
 */

export interface Fila {
  _id?: string;
  id?: string;
}

export type TipoIndicacion =
  | 'medicamento'
  | 'autocuidado'
  | 'tarea'
  | 'control'
  | 'sesiones'
  | 'examen'
  | 'remision'
  | 'vigilancia'
  | 'reposo'
  | 'otro';

export interface Caso extends Fila {
  paciente_user_id?: string;
  estado?: string;
  centro?: string | null;
  nivel_urgencia?: number | string | null;
  motivo?: string | null;
  resumen_triaje?: string | null;
  creado_en?: string;
  caso_origen_id?: string | null;
}

export interface Plan extends Fila {
  caso_id?: string;
  profesional_nombre?: string | null;
  resumen?: string;
  creado_en?: string;
  cita_id?: string | null;
}

export interface Indicacion extends Fila {
  caso_id?: string;
  plan_id?: string;
  texto?: string;
  frecuencia?: string | null;
  activa?: boolean | string | number;
  creado_en?: string;
  tipo?: TipoIndicacion | null;
  duracion_dias?: number | string | null;
  plazo_dias?: number | string | null;
  sesiones?: number | string | null;
  centro_destino?: string | null;
}

export interface Adherencia extends Fila {
  caso_id?: string;
  indicacion_id?: string;
  cumplida?: boolean | string | number;
  nota?: string | null;
  reportado_en?: string;
  programado_para?: string | null;
  origen?: string | null;
}

export interface Evolucion extends Fila {
  caso_id?: string;
  escala?: number | string;
  nota?: string | null;
  reportado_en?: string;
}

export interface Cita extends Fila {
  caso_id?: string;
  profesional_nombre?: string | null;
  centro?: string;
  inicio?: string;
  fin?: string;
  estado?: string;
  tipo?: string | null;
  indicacion_id?: string | null;
}

export interface Recordatorio extends Fila {
  caso_id?: string;
  indicacion_id?: string;
  cita_id?: string | null;
  programado_para?: string;
  estado?: string;
  texto?: string;
}

export interface FilaConversacion extends Fila {
  autor?: string;
  contenido?: string;
  creado_en?: string;
}

export interface Turno {
  quien: 'yo' | 'agente';
  texto: string;
}

export interface Identidad {
  userId: string;
  email: string;
  nombre: string;
}

/** Todo lo que la app muestra de un caso, leído de una vez. */
export interface Tratamiento {
  caso: Caso;
  plan: Plan | null;
  indicaciones: Indicacion[];
  adherencias: Adherencia[];
  evoluciones: Evolucion[];
  citas: Cita[];
  recordatorios: Recordatorio[];
  turnos: Turno[];
}

export type AgenteDestino = 'seguimiento' | 'agenda';

export interface RespuestaAgente {
  respuesta: string;
  agentes?: string[];
  salvaguardas_intervinieron?: boolean;
}

export function esVerdad(valor: unknown): boolean {
  return valor === true || valor === 1 || valor === 'true' || valor === '1' || valor === 't';
}

export function idDe(fila: Fila | null | undefined): string {
  return String(fila?._id ?? fila?.id ?? '');
}
