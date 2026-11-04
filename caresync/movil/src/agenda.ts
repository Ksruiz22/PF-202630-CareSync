/**
 * De las indicaciones del plan a lo que la persona tiene que hacer hoy.
 *
 * Se calcula aquí, y no se lee de `recordatorios`, porque esa tabla la llena una Lambda
 * que depende de la cuenta de servicio: el 2026-10-30 tenía cero filas. Si la app
 * dependiera de ella, un plan recién escrito se vería vacío. Lo que sí traiga esa tabla
 * se suma como aviso (`Avisos.tsx`), sin ser la fuente de lo que hay que cumplir.
 *
 * Es un módulo sin React ni red, para poder probarlo con `npm run prueba`.
 *
 * **Las horas son una convención de la app, no una pauta clínica.** La indicación se
 * muestra siempre con las palabras del profesional, y lo que aquí se calcula es cuándo
 * preguntar. Ver `HORA_PRIMERA` y `HORA_ULTIMA`.
 */

import { esVerdad, idDe, type Adherencia, type Cita, type Indicacion } from './tipos';

const HORA = 60 * 60 * 1000;
const DIA = 24 * HORA;

/** Bogotá es `-05:00` fijo. El teléfono puede estar en otra zona; el plan no. */
const DESFASE_BOGOTA = -5 * HORA;

/** La misma primera hora que `HORA_MINIMA` en la Lambda de recordatorios. */
const HORA_PRIMERA = 7;
/**
 * La Lambda corta los correos a las 20:00, pero aquí no sirve: «cada 8 horas» desde las
 * 7:00 tiene una tercera toma a las 23:00, y correrla al día siguiente haría parecer que
 * son dos al día. Se pregunta a las 22:00 como máximo, una vez, antes de dormir.
 */
const HORA_ULTIMA = 22;

/** El mismo piso que `INTERVALO_MINIMO` en `caresync_comun/frecuencia.py`. */
const INTERVALO_MINIMO = 4 * HORA;

const NUMEROS: Record<string, number> = { una: 1, dos: 2, tres: 3, cuatro: 4 };

/**
 * Espejo de `caresync_comun/frecuencia.py`. Si cambian las frases que se aceptan,
 * cambian ahí, en `app/src/frecuencia.ts` y aquí: lo que el profesional escriba tiene
 * que significar lo mismo para el correo y para el teléfono.
 */
export function intervaloDe(frecuencia: unknown): number | null {
  const texto = String(frecuencia ?? '').trim().toLowerCase();
  if (!texto) return null;

  const cada = /cada\s+(\d+)\s*(horas?|h|d[ií]as?|semanas?)/.exec(texto);
  if (cada) {
    const cantidad = Number(cada[1]);
    if (cantidad <= 0) return null;
    const unidad = cada[2] ?? '';
    const base = unidad.startsWith('h') ? HORA : unidad.startsWith('d') ? DIA : 7 * DIA;
    return Math.max(cantidad * base, INTERVALO_MINIMO);
  }

  const veces = /(\d+|una|dos|tres|cuatro)\s+ve(?:z|ces)\s+al\s+d[ií]a/.exec(texto);
  if (veces) {
    const crudo = veces[1] ?? '';
    const cuantas = /^\d+$/.test(crudo) ? Number(crudo) : (NUMEROS[crudo] ?? 0);
    if (cuantas <= 0) return null;
    return Math.max(DIA / cuantas, INTERVALO_MINIMO);
  }

  if (texto.includes('cada hora')) return INTERVALO_MINIMO;
  if (texto.includes('diari') || texto.includes('cada día') || texto.includes('cada dia')) return DIA;
  if (texto.includes('semanal') || texto.includes('cada semana')) return 7 * DIA;
  return null;
}

/**
 * Un momento de ROBLE. Sin zona se asume UTC, igual que `reloj.desde_iso`: `new Date`
 * lo tomaría como hora del teléfono y movería cada toma según dónde esté la persona.
 *
 * Es el caso normal: el `read` de ROBLE devuelve `2026-09-11T19:00`, sin zona y sin
 * segundos, y ese valor es UTC (esa cita es la de las 14:00 de Bogotá; comprobado contra
 * la API el 2026-10-30). Por eso una toma cae siempre en un minuto exacto: es lo que
 * permite emparejar un reporte con su toma al releerlo.
 */
export function fecha(valor: unknown): Date | null {
  if (!valor) return null;
  const texto = String(valor);
  const conZona = /(?:Z|[+-]\d{2}:?\d{2})$/.test(texto) ? texto : `${texto.replace(' ', 'T')}Z`;
  const momento = new Date(conZona);
  return Number.isNaN(momento.getTime()) ? null : momento;
}

function entero(valor: unknown): number | null {
  if (valor === null || valor === undefined || valor === '') return null;
  const numero = Number(valor);
  return Number.isFinite(numero) ? numero : null;
}

/** La medianoche de Bogotá del día de `momento`, como instante absoluto. */
export function inicioDelDia(momento: Date): number {
  const local = momento.getTime() + DESFASE_BOGOTA;
  return Math.floor(local / DIA) * DIA - DESFASE_BOGOTA;
}

// ----------------------------------------------------------------- clasificar

/**
 * Cómo se acompaña una indicación, según su `tipo`.
 *
 * - `toma`: se repite, y en cada momento se pregunta si se hizo.
 * - `hito`: pasa una vez (un examen, una remisión, un control).
 * - `serie`: varias citas, y se lleva la cuenta.
 * - `vigilancia`: nunca se recuerda. Si pasa, se le cuenta al agente, que es quien escala.
 * - `reposo`: no se reporta; sólo se dice hasta cuándo.
 * - `abierta`: sin frecuencia entendible. Se puede reportar, pero no se le pregunta a
 *   ninguna hora: inventarle una sería recordar algo que nadie indicó.
 *
 * `tipo` nulo se comporta como `otro`, y así caen todas las filas anteriores al 29/10.
 */
export type Acompanamiento = 'toma' | 'hito' | 'serie' | 'vigilancia' | 'reposo' | 'abierta';

export function acompanamientoDe(indicacion: Indicacion): Acompanamiento {
  switch (indicacion.tipo) {
    case 'vigilancia':
      return 'vigilancia';
    case 'reposo':
      return 'reposo';
    case 'sesiones':
      return 'serie';
    case 'control':
    case 'examen':
    case 'remision':
      return 'hito';
    default:
      return intervaloDe(indicacion.frecuencia) ? 'toma' : 'abierta';
  }
}

/** Con `duracion_dias`, hasta cuándo sigue vigente. Nulo: hasta que se desactive. */
export function venceEn(indicacion: Indicacion): Date | null {
  const dias = entero(indicacion.duracion_dias);
  const creada = fecha(indicacion.creado_en);
  return dias !== null && creada ? new Date(creada.getTime() + dias * DIA) : null;
}

export function sigueVigente(indicacion: Indicacion, ahora: Date): boolean {
  if (!esVerdad(indicacion.activa)) return false;
  const vence = venceEn(indicacion);
  return !vence || ahora < vence;
}

// ---------------------------------------------------------------------- tomas

export interface Toma {
  clave: string;
  indicacion: Indicacion;
  momento: Date;
  /** `pendiente` aún no llega su hora o acaba de pasar; `sin_reporte` ya quedó atrás. */
  estado: 'pendiente' | 'cumplida' | 'no_cumplida' | 'sin_reporte';
  reporte?: Adherencia;
}

/** Los momentos en que se pregunta por esta indicación durante el día de `dia`. */
export function momentosDelDia(indicacion: Indicacion, dia: Date): Date[] {
  const intervalo = intervaloDe(indicacion.frecuencia);
  const creada = fecha(indicacion.creado_en);
  if (!intervalo || !creada) return [];

  const inicio = inicioDelDia(dia);
  if (inicio + DIA <= inicioDelDia(creada)) return [];
  const primera = inicio + HORA_PRIMERA * HORA;

  // Cada varios días: sólo los días que le tocan, contados desde que se escribió.
  if (intervalo >= DIA) {
    const dias = Math.round((inicio - inicioDelDia(creada)) / DIA);
    const paso = Math.round(intervalo / DIA);
    if (dias <= 0 || dias % paso !== 0) return dias === 0 && primera > creada.getTime() ? [new Date(primera)] : [];
    return [new Date(primera)];
  }

  const ultima = inicio + HORA_ULTIMA * HORA;
  const cuantas = Math.round(DIA / intervalo);
  const momentos = new Set<number>();
  for (let i = 0; i < cuantas; i += 1) {
    momentos.add(Math.min(primera + i * intervalo, ultima));
  }
  // Lo anterior a que existiera la indicación no se le puede reclamar a nadie.
  return [...momentos]
    .filter((instante) => instante > creada.getTime())
    .sort((a, b) => a - b)
    .map((instante) => new Date(instante));
}

/**
 * Las tomas de un día con su estado.
 *
 * Un reporte se empareja por `programado_para`. Los que escribió el agente no lo traen
 * —hablan de la indicación, no de una toma— y cuentan para la toma más cercana de ese
 * día que no tenga reporte, para que la pantalla no vuelva a preguntar algo que la
 * persona ya le contó al asistente.
 */
export function tomasDelDia(
  indicaciones: Indicacion[],
  adherencias: Adherencia[],
  dia: Date,
  ahora: Date
): Toma[] {
  const tomas: Toma[] = [];
  for (const indicacion of indicaciones) {
    if (acompanamientoDe(indicacion) !== 'toma' || !sigueVigente(indicacion, dia)) continue;
    const id = idDe(indicacion);
    const propias = adherencias.filter((fila) => String(fila.indicacion_id ?? '') === id);
    const usados = new Set<Adherencia>();

    const momentos = momentosDelDia(indicacion, dia);
    const delDia = momentos.map((momento) => {
      const reporte = propias.find(
        (fila) => !usados.has(fila) && fecha(fila.programado_para)?.getTime() === momento.getTime()
      );
      if (reporte) usados.add(reporte);
      return { momento, reporte };
    });

    const inicio = inicioDelDia(dia);
    const sueltos = propias.filter((fila) => {
      const cuando = fecha(fila.reportado_en);
      return !fila.programado_para && cuando && cuando.getTime() >= inicio && cuando.getTime() < inicio + DIA;
    });
    for (const suelto of sueltos) {
      const cuando = fecha(suelto.reportado_en)?.getTime() ?? 0;
      const candidata = delDia
        .filter((toma) => !toma.reporte)
        .sort((a, b) => Math.abs(a.momento.getTime() - cuando) - Math.abs(b.momento.getTime() - cuando))[0];
      if (candidata) candidata.reporte = suelto;
    }

    for (const { momento, reporte } of delDia) {
      tomas.push({
        clave: `${id}|${momento.toISOString()}`,
        indicacion,
        momento,
        reporte,
        estado: reporte
          ? esVerdad(reporte.cumplida)
            ? 'cumplida'
            : 'no_cumplida'
          : momento.getTime() + 6 * HORA < ahora.getTime()
            ? 'sin_reporte'
            : 'pendiente',
      });
    }
  }
  return tomas.sort((a, b) => a.momento.getTime() - b.momento.getTime());
}

// ---------------------------------------------------------- hitos y series

export interface EstadoDeHito {
  hecho: boolean;
  /** Fecha límite si la indicación trae `plazo_dias`. */
  limite: Date | null;
  cita: Cita | null;
}

export function citasDe(indicacion: Indicacion, citas: Cita[]): Cita[] {
  const id = idDe(indicacion);
  return citas.filter(
    (cita) => String(cita.indicacion_id ?? '') === id && cita.estado !== 'cancelada'
  );
}

export function estadoDeHito(
  indicacion: Indicacion,
  adherencias: Adherencia[],
  citas: Cita[]
): EstadoDeHito {
  const id = idDe(indicacion);
  const propias = citasDe(indicacion, citas);
  const reportado = adherencias.some(
    (fila) => String(fila.indicacion_id ?? '') === id && esVerdad(fila.cumplida)
  );
  const plazo = entero(indicacion.plazo_dias);
  const creada = fecha(indicacion.creado_en);
  return {
    hecho: reportado || propias.some((cita) => cita.estado === 'atendida'),
    limite: plazo !== null && creada ? new Date(creada.getTime() + plazo * DIA) : null,
    cita: propias.find((cita) => cita.estado === 'confirmada') ?? null,
  };
}

export interface EstadoDeSerie {
  total: number | null;
  atendidas: number;
  /** La siguiente sesión ya agendada, si hay. */
  proxima: Cita | null;
  falta: boolean;
}

export function estadoDeSerie(indicacion: Indicacion, citas: Cita[]): EstadoDeSerie {
  const propias = citasDe(indicacion, citas);
  const total = entero(indicacion.sesiones);
  const atendidas = propias.filter((cita) => cita.estado === 'atendida').length;
  const proxima =
    propias
      .filter((cita) => cita.estado === 'confirmada')
      .sort((a, b) => String(a.inicio ?? '').localeCompare(String(b.inicio ?? '')))[0] ?? null;
  return { total, atendidas, proxima, falta: total === null || atendidas < total };
}

// --------------------------------------------------------------------- avance

export interface Avance {
  esperadas: number;
  cumplidas: number;
  sinReporte: number;
  /** De 0 a 1, o `null` si todavía no había nada que cumplir. */
  proporcion: number | null;
}

/**
 * Cómo va, con lo que ya venció. Lo pendiente de hoy no cuenta en contra.
 *
 * Es un dato para la persona, no un juicio: la pantalla no dice «vas bien» ni «vas
 * mal», igual que el agente no interpreta la evolución en voz alta.
 */
export function avanceDe(
  indicaciones: Indicacion[],
  adherencias: Adherencia[],
  ahora: Date,
  dias = 7
): Avance {
  let esperadas = 0;
  let cumplidas = 0;
  let sinReporte = 0;
  for (let atras = 0; atras < dias; atras += 1) {
    const dia = new Date(ahora.getTime() - atras * DIA);
    for (const toma of tomasDelDia(indicaciones, adherencias, dia, ahora)) {
      if (toma.estado === 'pendiente') continue;
      esperadas += 1;
      if (toma.estado === 'cumplida') cumplidas += 1;
      if (toma.estado === 'sin_reporte') sinReporte += 1;
    }
  }
  return {
    esperadas,
    cumplidas,
    sinReporte,
    proporcion: esperadas > 0 ? cumplidas / esperadas : null,
  };
}

// --------------------------------------------------------------- a qué agente

/**
 * A quién va un mensaje escrito a mano. `undefined` deja que decida el orquestador.
 *
 * El orquestador **obedece** el campo `agente` si el rol puede usar ese agente, y un
 * paciente puede usar los tres. Sugerir seguimiento siempre mandaba un caso con el triaje
 * a medias a un agente que no canaliza, y se saltaba el triaje. Por eso sólo se sugiere
 * con plan, que es lo único que `agente_por_defecto` no sabe: un caso `agendado` puede
 * tener plan de una consulta anterior. Con la urgencia escalada tampoco se toca.
 */
export function agenteParaMensaje(
  tratamiento: { plan: unknown; caso: { estado?: string } }
): 'seguimiento' | undefined {
  return tratamiento.plan && tratamiento.caso.estado !== 'urgencia_escalada'
    ? 'seguimiento'
    : undefined;
}

// ---------------------------------------------------------------------- texto

export function horaDe(momento: Date): string {
  return momento.toLocaleTimeString('es-CO', {
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/Bogota',
  });
}

export function fechaHoraDe(valor: unknown): string {
  const momento = valor instanceof Date ? valor : fecha(valor);
  if (!momento) return 'sin fecha';
  return momento.toLocaleString('es-CO', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/Bogota',
  });
}

export function diaDe(valor: unknown): string {
  const momento = valor instanceof Date ? valor : fecha(valor);
  if (!momento) return 'sin fecha';
  return momento.toLocaleDateString('es-CO', {
    day: 'numeric',
    month: 'long',
    timeZone: 'America/Bogota',
  });
}
