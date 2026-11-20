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
 * **Las horas son las mismas que las de los correos.** La regla vive en
 * `caresync_comun/frecuencia.py` (`momentos_del_dia`) y aquí está su espejo: las horas
 * que fijó el profesional (`indicaciones.horas`) o, sin ellas, la ventana de 8:00 a
 * 19:00. La indicación se muestra siempre con las palabras del profesional; lo que aquí
 * se calcula es cuándo preguntar.
 */

import { esVerdad, idDe, type Adherencia, type Cita, type Indicacion, type Turno } from './tipos';

const HORA = 60 * 60 * 1000;
const DIA = 24 * HORA;

/** Bogotá es `-05:00` fijo. El teléfono puede estar en otra zona; el plan no. */
const DESFASE_BOGOTA = -5 * HORA;

/**
 * La ventana de los avisos (propuesta de Kevin, 2026-11-02): nada antes de las 8:00 ni
 * después de las 19:00, para no ser intrusivo. Antes eran las 7:00 y las 22:00 aquí, y
 * las 7:00 y las 20:00 en los correos: el mismo plan preguntaba a horas distintas en el
 * teléfono y en el correo. «Cada 8 horas» son ahora las 8:00 y las 16:00; la toma de la
 * medianoche no suena, salvo que el profesional fije las horas.
 */
const HORA_PRIMERA = 8;
const HORA_ULTIMA = 19;

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
      return intervaloDe(indicacion.frecuencia) || horasFijas(indicacion.horas).length ? 'toma' : 'abierta';
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

/** «6:00, 18:30» es [[6, 0], [18, 30]]: espejo de `horas_fijas` en `frecuencia.py`. */
export function horasFijas(horas: unknown): Array<[number, number]> {
  const vistas = new Map<string, [number, number]>();
  for (const trozo of String(horas ?? '').trim().toLowerCase().split(/[,;y ]+/)) {
    const encontrada = /^(\d{1,2})(?:[:.h](\d{2}))?$/.exec(trozo.trim());
    if (!encontrada) continue;
    const hora = Number(encontrada[1]);
    const minuto = Number(encontrada[2] ?? 0);
    if (hora <= 23 && minuto <= 59) vistas.set(`${hora}:${minuto}`, [hora, minuto]);
  }
  return [...vistas.values()].sort((a, b) => a[0] * 60 + a[1] - (b[0] * 60 + b[1]));
}

/** «3 veces al día» es 3: ésas se reparten en la ventana, no cada 8 horas. */
function vecesAlDia(frecuencia: unknown): number | null {
  const veces = /(\d+|una|dos|tres|cuatro)\s+ve(?:z|ces)\s+al\s+d[ií]a/.exec(
    String(frecuencia ?? '').trim().toLowerCase()
  );
  if (!veces) return null;
  const crudo = veces[1] ?? '';
  const cuantas = /^\d+$/.test(crudo) ? Number(crudo) : (NUMEROS[crudo] ?? 0);
  return cuantas > 0 ? cuantas : null;
}

/**
 * Los momentos en que se pregunta por esta indicación durante el día de `dia`.
 *
 * Espejo de `momentos_del_dia` en `caresync_comun/frecuencia.py`:
 * - con horas del profesional, ésas;
 * - «N veces al día», repartidas entre las 8:00 y las 19:00;
 * - «cada N horas», desde las 8:00 y sin pasar de las 19:00;
 * - cada varios días, a las 8:00 de los días que tocan.
 */
export function momentosDelDia(indicacion: Indicacion, dia: Date): Date[] {
  const intervalo = intervaloDe(indicacion.frecuencia);
  const fijas = horasFijas(indicacion.horas);
  const creada = fecha(indicacion.creado_en);
  if ((!intervalo && !fijas.length) || !creada) return [];

  const inicio = inicioDelDia(dia);
  if (inicio < inicioDelDia(creada)) return [];

  let minutos: number[];
  if (intervalo && intervalo >= DIA) {
    // Cada varios días: sólo los días que le tocan, contados desde que se escribió.
    const dias = Math.round((inicio - inicioDelDia(creada)) / DIA);
    if (dias % Math.max(1, Math.round(intervalo / DIA)) !== 0) return [];
    minutos = fijas.length ? fijas.map(([h, m]) => h * 60 + m) : [HORA_PRIMERA * 60];
  } else if (fijas.length) {
    minutos = fijas.map(([h, m]) => h * 60 + m);
  } else if (vecesAlDia(indicacion.frecuencia)) {
    const cuantas = vecesAlDia(indicacion.frecuencia) ?? 1;
    const ventana = (HORA_ULTIMA - HORA_PRIMERA) * 60;
    minutos =
      cuantas === 1
        ? [HORA_PRIMERA * 60]
        : Array.from({ length: cuantas }, (_, k) => HORA_PRIMERA * 60 + Math.round((k * ventana) / (cuantas - 1)));
  } else {
    const paso = Math.round((intervalo ?? DIA) / (60 * 1000));
    minutos = [];
    for (let m = HORA_PRIMERA * 60; m <= HORA_ULTIMA * 60; m += paso) minutos.push(m);
  }

  // Lo anterior a que existiera la indicación no se le puede reclamar a nadie.
  return [...new Set(minutos)]
    .map((m) => inicio + m * 60 * 1000)
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

// ------------------------------------------------------------ la conversación

/**
 * Cuándo se escribió una fila de `conversaciones`, en milisegundos.
 *
 * `creado_en` no sirve para ordenar: el `read` de ROBLE lo devuelve cortado al minuto, y
 * además en el orden que quiere. Un intercambio rápido cae entero en el mismo minuto, y
 * el 2026-11-19 la app mostró «a las 8:30» antes de la pregunta que respondía. Desde
 * entonces el orquestador escribe también `creado_ms`, que es un entero y ROBLE no
 * recorta. Las filas anteriores sólo tienen `creado_en`, con su minuto.
 */
export function momentoDeFila(fila: { creado_ms?: unknown; creado_en?: unknown }): number {
  const ms = Number(fila.creado_ms);
  if (fila.creado_ms !== null && fila.creado_ms !== undefined && Number.isFinite(ms) && ms > 0) return ms;
  return fecha(fila.creado_en)?.getTime() ?? 0;
}

// --------------------------------------------------------------- a qué agente

/**
 * Cuánto dura una conversación con el agente de agenda. Pasado esto, lo que la persona
 * escriba ya no es la respuesta a «¿te sirve a las 8:00 o a las 8:30?».
 */
const VENTANA_DE_AGENDA = 30 * 60 * 1000;

/**
 * A quién va un mensaje escrito a mano. `undefined` deja que decida el orquestador.
 *
 * El orquestador **obedece** el campo `agente` si el rol puede usar ese agente, y un
 * paciente puede usar los tres. Sugerir seguimiento siempre mandaba un caso con el triaje
 * a medias a un agente que no canaliza, y se saltaba el triaje. Por eso sólo se sugiere
 * con plan, que es lo único que `agente_por_defecto` no sabe: un caso `agendado` puede
 * tener plan de una consulta anterior. Con la urgencia escalada tampoco se toca.
 *
 * **Y si la última respuesta reciente fue de agenda, no se sugiere nada.** El 2026-11-19,
 * en medio de elegir hora, la persona respondió «a las 8:30» y la app lo mandó a
 * seguimiento: falló `agendar_cita` y el agente terminó hablando de las gárgaras. La
 * primera corrección mandaba `agenda` a ciegas, y eso llevó a agenda —que no registra la
 * evolución— el «me siento como un 7 de 10» escrito justo después de cancelar. Quién
 * sigue lo decide ahora el orquestador (`agente_que_sigue`): mira si agenda dejó algo
 * abierto, y para eso lee las notas `[sistema]` del hilo, que esta app no conserva.
 */
export function agenteParaMensaje(
  tratamiento: { plan: unknown; caso: { estado?: string }; turnos?: Turno[] },
  ahora: Date = new Date()
): 'seguimiento' | undefined {
  if (tratamiento.caso.estado === 'urgencia_escalada') return undefined;
  const ultima = [...(tratamiento.turnos ?? [])].reverse().find((turno) => turno.quien === 'agente');
  if (
    ultima?.agente === 'agenda' &&
    ultima.cuando &&
    ahora.getTime() - ultima.cuando < VENTANA_DE_AGENDA
  ) {
    return undefined;
  }
  return tratamiento.plan ? 'seguimiento' : undefined;
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
