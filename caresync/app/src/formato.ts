/**
 * Fechas y textos como se le muestran a una persona.
 *
 * Siempre en hora de Bogotá y nunca en la del navegador. Parece lo mismo hasta
 * que alguien abre la aplicación desde un portátil con el reloj en otra zona y
 * ve su cita corrida cinco horas. El backend guarda UTC; aquí se traduce a la
 * única zona en la que vive este sistema.
 */

const ZONA = 'America/Bogota';

const FECHA_HORA = new Intl.DateTimeFormat('es-CO', {
  timeZone: ZONA,
  weekday: 'long',
  day: '2-digit',
  month: 'long',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const SOLO_FECHA = new Intl.DateTimeFormat('es-CO', {
  timeZone: ZONA,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
});

const SOLO_HORA = new Intl.DateTimeFormat('es-CO', {
  timeZone: ZONA,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

function comoFecha(valor: unknown): Date | null {
  if (!valor) return null;
  const fecha = new Date(String(valor));
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}

export function fechaHora(valor: unknown): string {
  const fecha = comoFecha(valor);
  return fecha ? FECHA_HORA.format(fecha) : 'sin fecha';
}

export function soloFecha(valor: unknown): string {
  const fecha = comoFecha(valor);
  return fecha ? SOLO_FECHA.format(fecha) : '—';
}

export function soloHora(valor: unknown): string {
  const fecha = comoFecha(valor);
  return fecha ? SOLO_HORA.format(fecha) : '—';
}

/** «hace 3 días», «hace 2 horas». Para saber de un vistazo qué está frío. */
export function hace(valor: unknown): string {
  const fecha = comoFecha(valor);
  if (!fecha) return '—';

  const minutos = Math.round((Date.now() - fecha.getTime()) / 60000);
  if (minutos < 1) return 'ahora mismo';
  if (minutos < 60) return `hace ${minutos} min`;

  const horas = Math.round(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;

  const dias = Math.round(horas / 24);
  if (dias < 30) return `hace ${dias} ${dias === 1 ? 'día' : 'días'}`;
  return soloFecha(valor);
}

const ESTADOS: Record<string, string> = {
  abierto: 'En triaje',
  canalizado: 'Canalizado',
  agendado: 'Con cita',
  atendido: 'Atendido',
  en_seguimiento: 'En seguimiento',
  urgencia_escalada: 'Urgencia escalada',
  cerrado: 'Cerrado',
};

export function estadoLegible(estado: unknown): string {
  return ESTADOS[String(estado ?? '')] ?? String(estado ?? 'sin estado');
}

const NIVELES: Record<string, string> = {
  '1': 'Emergencia · ahora',
  '2': 'Prioritario · 72 h',
  '3': 'Regular · 7 días',
  '4': 'Orientación · sin cita',
};

export function nivelLegible(nivel: unknown): string {
  const clave = String(nivel ?? '');
  return NIVELES[clave] ?? 'Sin clasificar';
}

/**
 * En qué franja cae un reporte de evolución.
 *
 * La escala es de 0 a 10, la misma que declara `catalogo_herramientas.py`. Los
 * cortes no son decorativos: 3 o menos es lo que el agente de seguimiento trata
 * como preocupante (`ESCALA_PREOCUPANTE`), así que el color y la lógica del backend
 * dicen lo mismo. Si allá cambia el umbral, aquí también.
 */
/** El número de la escala, con el 0 mostrado como 0 y no como «—». */
export function escalaVisible(valor: unknown): string {
  const numero = Number(valor);
  if (!Number.isFinite(numero) || String(valor ?? '') === '') return '—';
  return String(numero);
}

export function bandaDeEscala(valor: unknown): 'mal' | 'medio' | 'bien' | 'sin' {
  const numero = Number(valor);
  if (!Number.isFinite(numero) || String(valor ?? '') === '') return 'sin';
  if (numero <= 3) return 'mal';
  if (numero <= 6) return 'medio';
  return 'bien';
}

export function nombreDeAgente(clave: string): string {
  const nombres: Record<string, string> = {
    triaje: 'Triaje',
    agenda: 'Agenda y Logística',
    seguimiento: 'Seguimiento',
  };
  return nombres[clave] ?? clave;
}
