/**
 * Convertir horarios en cupos.
 *
 * `horarios` dice «este profesional atiende los martes de 8:00 a 12:00 en bloques
 * de 30 minutos». `cupos` son las filas concretas que el agente de agenda puede
 * reservar. Alguien tiene que traducir lo primero en lo segundo, y aquí eso lo
 * hace el personal administrativo desde su pantalla, con un botón.
 *
 * **Por qué en la aplicación y no en una Lambda.** Es la decisión de diseño de este
 * archivo. Generar cupos es una tarea administrativa, no clínica: no la pide un
 * agente, la pide una persona que sabe si el centro va a atender la próxima semana.
 * Ponerla en la Lambda de recordatorios habría añadido un proceso automático que
 * escribe agenda sin que nadie lo haya decidido, y en un centro de salud eso se
 * paga con cupos publicados que no existen. El costo de esta decisión es que la
 * lógica sólo corre cuando alguien abre la aplicación; para un prototipo con dos
 * centros, es el costo correcto.
 *
 * **Zona horaria.** Los horarios se guardan como «08:00» sin zona y Bogotá está en
 * UTC-5 todo el año, sin horario de verano. Por eso aquí se compone la marca de
 * tiempo con el desplazamiento fijo `-05:00` y se convierte a UTC antes de
 * escribir. Si Colombia adoptara horario de verano, este archivo es lo primero que
 * habría que cambiar.
 */

import { roble } from './roble';
import {
  esVerdad,
  idDe,
  type Centro,
  type Cupo,
  type Horario,
  type Profesional,
} from './tipos';

/** Bogotá, todo el año. Ver la nota de arriba. */
const DESPLAZAMIENTO = '-05:00';

const MINUTOS_POR_DEFECTO = 30;
const DIAS_POR_DEFECTO = 14;

/** Tope de seguridad: un clic no debe poder escribir miles de filas en ROBLE. */
const MAX_CUPOS_POR_TANDA = 400;

const FECHA_EN_BOGOTA = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Bogota',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

export interface ResultadoGeneracion {
  creados: number;
  yaEstaban: number;
  profesionales: number;
  desde: string;
  hasta: string;
  /** Se llenó el tope y quedaron días sin cubrir. */
  truncado: boolean;
}

/**
 * Publica los cupos libres de los próximos días para un centro.
 *
 * Es idempotente: los cupos que ya existen para el mismo profesional y la misma
 * hora se cuentan y no se vuelven a escribir. Se puede pulsar el botón dos veces
 * seguidas sin duplicar la agenda, que es exactamente lo que va a pasar.
 */
export async function generarCupos(
  centro: Centro,
  dias: number = DIAS_POR_DEFECTO
): Promise<ResultadoGeneracion> {
  const profesionales = (
    (await roble.read('profesionales', { centro })) as Profesional[]
  ).filter((fila) => fila.activo === undefined || esVerdad(fila.activo));

  const desde = fechaEnBogota(0);
  const hasta = fechaEnBogota(Math.max(1, dias) - 1);

  if (profesionales.length === 0) {
    return { creados: 0, yaEstaban: 0, profesionales: 0, desde, hasta, truncado: false };
  }

  const existentes = await inicios(centro);
  const nuevos: Cupo[] = [];
  let yaEstaban = 0;
  let truncado = false;

  for (const profesional of profesionales) {
    const profesionalId = idDe(profesional);
    const horarios = (
      (await roble.read('horarios', { profesional_id: profesionalId })) as Horario[]
    ).filter((fila) => fila.activo === undefined || esVerdad(fila.activo));

    for (let dia = 0; dia < Math.max(1, dias); dia += 1) {
      const fecha = fechaEnBogota(dia);
      const delDia = horarios.filter(
        (horario) => normalizarDia(horario.dia_semana) === diaDeLaSemana(fecha)
      );

      for (const horario of delDia) {
        for (const inicio of tramos(fecha, horario)) {
          const clave = `${profesionalId}|${inicio.inicio}`;
          if (existentes.has(clave)) {
            yaEstaban += 1;
            continue;
          }
          if (nuevos.length >= MAX_CUPOS_POR_TANDA) {
            truncado = true;
            continue;
          }
          existentes.add(clave);
          nuevos.push({
            centro,
            profesional_id: profesionalId,
            inicio: inicio.inicio,
            fin: inicio.fin,
            estado: 'libre',
            modalidad: String(horario.modalidad ?? 'presencial'),
            caso_id: null,
          });
        }
      }
    }
  }

  // En lotes y no de una: `createMany` con cuatrocientas filas es una petición
  // grande para un API gratuito, y si falla no se sabe qué entró. En lotes, lo que
  // entró queda escrito y la próxima pulsada del botón completa el resto —que es
  // seguro, porque esto es idempotente.
  let creados = 0;
  for (const lote of enLotes(nuevos, 50)) {
    const resultado = await roble.createMany('cupos', lote);
    creados += resultado?.inserted?.length ?? lote.length;
  }

  return { creados, yaEstaban, profesionales: profesionales.length, desde, hasta, truncado };
}

/**
 * Los inicios que ya están publicados, como `profesional|inicio`.
 *
 * Se leen todos los cupos del centro porque `read` no sabe comparar rangos de
 * fechas: no hay forma de pedir «los de las próximas dos semanas». Para un centro
 * con dos o tres profesionales cabe de sobra; el día que no quepa, esto pasa a ser
 * una consulta guardada en ROBLE.
 */
async function inicios(centro: Centro): Promise<Set<string>> {
  const cupos = (await roble.read('cupos', { centro })) as Cupo[];
  const claves = new Set<string>();
  for (const cupo of cupos) {
    claves.add(`${String(cupo.profesional_id ?? '')}|${String(cupo.inicio ?? '')}`);
  }
  return claves;
}

interface Tramo {
  inicio: string;
  fin: string;
}

/** Parte un horario del día en tramos, descartando los que ya pasaron. */
function tramos(fecha: string, horario: Horario): Tramo[] {
  const abre = enMinutos(horario.hora_inicio);
  const cierra = enMinutos(horario.hora_fin);
  const paso = Number(horario.minutos_cupo) > 0 ? Number(horario.minutos_cupo) : MINUTOS_POR_DEFECTO;

  if (abre === null || cierra === null || cierra <= abre) return [];

  const ahora = Date.now();
  const salida: Tramo[] = [];

  // El tramo tiene que caber completo antes del cierre: un bloque de 30 minutos que
  // empieza a las 11:50 y termina a las 12:20 no es un cupo, es una hora extra.
  for (let minuto = abre; minuto + paso <= cierra; minuto += paso) {
    const inicio = marcaDeTiempo(fecha, minuto);
    if (new Date(inicio).getTime() <= ahora) continue;
    salida.push({ inicio, fin: marcaDeTiempo(fecha, minuto + paso) });
  }
  return salida;
}

/** «08:30» → 510. Devuelve `null` si no se entiende, para no inventar una hora. */
function enMinutos(hora: unknown): number | null {
  const texto = String(hora ?? '').trim();
  const partes = /^(\d{1,2}):(\d{2})/.exec(texto);
  if (!partes) return null;
  const horas = Number(partes[1]);
  const minutos = Number(partes[2]);
  if (horas > 23 || minutos > 59) return null;
  return horas * 60 + minutos;
}

/** Fecha de Bogotá + minutos del día → instante en UTC, como lo guarda ROBLE. */
function marcaDeTiempo(fecha: string, minutoDelDia: number): string {
  const horas = String(Math.floor(minutoDelDia / 60)).padStart(2, '0');
  const minutos = String(minutoDelDia % 60).padStart(2, '0');
  return new Date(`${fecha}T${horas}:${minutos}:00${DESPLAZAMIENTO}`).toISOString();
}

/**
 * La fecha en Bogotá dentro de `dias` días, como `YYYY-MM-DD`.
 *
 * Se ancla al mediodía UTC —las 7 de la mañana en Bogotá— y se suman días enteros:
 * así sumar un día nunca cae en el mismo día por el desplazamiento de la zona, que
 * es el error clásico de `setDate(getDate() + 1)`.
 */
function fechaEnBogota(dias: number): string {
  const hoy = FECHA_EN_BOGOTA.format(new Date());
  const [anio, mes, dia] = hoy.split('-').map(Number);
  const ancla = Date.UTC(anio ?? 1970, (mes ?? 1) - 1, dia ?? 1, 12);
  return new Date(ancla + dias * 86_400_000).toISOString().slice(0, 10);
}

/** 0 = lunes … 6 = domingo, la convención de la tabla `horarios`. */
function diaDeLaSemana(fecha: string): number {
  const dia = new Date(`${fecha}T12:00:00Z`).getUTCDay();
  return (dia + 6) % 7;
}

function normalizarDia(valor: unknown): number {
  const numero = Number(valor);
  return Number.isInteger(numero) && numero >= 0 && numero <= 6 ? numero : -1;
}

function enLotes<T>(filas: T[], tamano: number): T[][] {
  const lotes: T[][] = [];
  for (let i = 0; i < filas.length; i += tamano) {
    lotes.push(filas.slice(i, i + tamano));
  }
  return lotes;
}
