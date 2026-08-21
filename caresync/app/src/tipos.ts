/**
 * Los tipos del dominio, escritos una vez.
 *
 * Deliberadamente laxos en lo que viene de ROBLE: `read` devuelve las columnas
 * de PostgreSQL tal cual, y un `timestamptz` llega como string mientras un
 * `boolean` puede llegar como `true` o como `"true"` según la ruta. Marcar esos
 * campos como `string | number | boolean` y normalizarlos al leer es más honesto
 * que declarar un tipo estricto que el runtime no cumple.
 */

export const ROLES = ['paciente', 'profesional', 'admin_cmu', 'admin_cae'] as const;
export type Rol = (typeof ROLES)[number];

export type Centro = 'CMU' | 'CAE';

/** Los mismos literales que usa `caresync_comun.roble_acceso`. */
export type EstadoCaso =
  | 'abierto'
  | 'canalizado'
  | 'agendado'
  | 'atendido'
  | 'en_seguimiento'
  | 'urgencia_escalada'
  | 'cerrado';

export interface Fila {
  _id?: string;
  id?: string;
  [columna: string]: unknown;
}

export interface Perfil extends Fila {
  user_id: string;
  nombre?: string;
  rol?: string;
  centro?: string | null;
}

export interface Caso extends Fila {
  paciente_user_id?: string;
  paciente_nombre?: string;
  paciente_email?: string;
  estado?: EstadoCaso;
  centro?: Centro | null;
  nivel_urgencia?: number | string | null;
  motivo?: string;
  resumen_triaje?: string | null;
  creado_en?: string;
  actualizado_en?: string;
}

export interface Cita extends Fila {
  caso_id?: string;
  cupo_id?: string;
  profesional_id?: string;
  profesional_user_id?: string;
  profesional_nombre?: string;
  paciente_user_id?: string;
  centro?: Centro;
  inicio?: string;
  fin?: string;
  estado?: string;
}

export interface Cupo extends Fila {
  centro?: Centro;
  profesional_id?: string;
  inicio?: string;
  fin?: string;
  estado?: 'libre' | 'reservado' | 'confirmado';
  modalidad?: string;
  caso_id?: string | null;
}

export interface Profesional extends Fila {
  user_id?: string;
  nombre?: string;
  email?: string;
  centro?: Centro;
  especialidad?: string;
  activo?: boolean | string;
}

export interface Horario extends Fila {
  profesional_id?: string;
  /** 0 = lunes … 6 = domingo, igual que `Date.getDay()` corrido. */
  dia_semana?: number | string;
  /** «08:00», hora de Bogotá. La zona no se guarda porque el sistema vive en una sola. */
  hora_inicio?: string;
  hora_fin?: string;
  minutos_cupo?: number | string;
  modalidad?: string;
  activo?: boolean | string;
}

export interface Indicacion extends Fila {
  caso_id?: string;
  plan_id?: string;
  texto?: string;
  frecuencia?: string;
  activa?: boolean | string;
  creado_en?: string;
}

export interface Plan extends Fila {
  caso_id?: string;
  profesional_user_id?: string;
  profesional_nombre?: string;
  resumen?: string;
  creado_en?: string;
}

export interface Evolucion extends Fila {
  caso_id?: string;
  escala?: number | string;
  nota?: string;
  reportado_en?: string;
}

export interface Adherencia extends Fila {
  caso_id?: string;
  indicacion_id?: string;
  cumplida?: boolean | string;
  nota?: string;
  reportado_en?: string;
}

export interface EventoCaso extends Fila {
  caso_id?: string;
  tipo?: string;
  severidad?: string;
  detalle?: unknown;
  creado_en?: string;
}

/** Lo que devuelve `POST /agente`. Debe coincidir con `_conversar` del orquestador. */
export interface RespuestaAgente {
  respuesta: string;
  caso: {
    id: string;
    estado?: EstadoCaso;
    centro?: Centro | null;
    nivel_urgencia?: number | null;
  };
  agentes: string[];
  acciones: Array<{ herramienta: string; ok: boolean; resultado?: unknown }>;
  salvaguardas_intervinieron: boolean;
}

export interface Turno {
  quien: 'yo' | 'agente' | 'sistema';
  texto: string;
  agentes?: string[];
  acciones?: RespuestaAgente['acciones'];
}

/** `true` para `true`, `"true"`, `1` y `"1"`. ROBLE devuelve las cuatro formas. */
export function esVerdad(valor: unknown): boolean {
  return valor === true || valor === 1 || valor === 'true' || valor === '1' || valor === 't';
}

export function idDe(fila: Fila | null | undefined): string {
  return String(fila?._id ?? fila?.id ?? '');
}

/**
 * El id de lo que se acabó de insertar.
 *
 * `create` de ROBLE no promete una forma: según la versión devuelve la fila, o un
 * `{ inserted: [fila] }` como el de `createMany`. Se aceptan las dos y se devuelve
 * cadena vacía si no viene ninguna, para que quien llama decida qué hacer en lugar
 * de seguir con un `undefined` disfrazado de id.
 */
export function idDeInsercion(resultado: unknown): string {
  if (!resultado || typeof resultado !== 'object') return '';
  const directo = idDe(resultado as Fila);
  if (directo) return directo;
  const insertadas = (resultado as { inserted?: unknown }).inserted;
  if (Array.isArray(insertadas) && insertadas.length > 0) {
    return idDe(insertadas[0] as Fila);
  }
  return '';
}
