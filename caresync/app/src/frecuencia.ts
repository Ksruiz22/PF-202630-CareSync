/**
 * ¿Esta frecuencia va a generar recordatorios?
 *
 * Es un espejo de `lambdas/comun/caresync_comun/frecuencia.py`, que es la regla con la
 * que la función de recordatorios decide si programa una indicación. Está repetida
 * porque son dos lenguajes, como la lista de roles: si allá cambian las frases que se
 * aceptan, aquí también, en el mismo commit.
 *
 * Sirve para avisar mientras el profesional corrige la propuesta: una frecuencia que
 * la regla no entiende no da error al guardar, simplemente no produce ningún
 * recordatorio, y nadie se entera hasta que el paciente deja de recibirlos.
 */

const CADA_N = /cada\s+(\d+)\s*(horas?|h|d[ií]as?|semanas?)/;
const VECES_AL_DIA = /(\d+|una|dos|tres|cuatro)\s+ve(?:z|ces)\s+al\s+d[ií]a/;
const PALABRAS = ['cada hora', 'diari', 'cada día', 'cada dia', 'semanal', 'cada semana'];

export function programaRecordatorios(frecuencia: string, horas = ''): boolean {
  if (horasFijas(horas).length) return true;
  const texto = frecuencia.trim().toLowerCase();
  if (!texto) return false;

  const cada = CADA_N.exec(texto);
  if (cada) return Number(cada[1]) > 0;

  const veces = VECES_AL_DIA.exec(texto);
  if (veces) return veces[1] !== '0';

  return PALABRAS.some((palabra) => texto.includes(palabra));
}

/**
 * La ventana de los avisos, en hora de Bogotá: la misma de `HORA_PRIMERA` y
 * `HORA_ULTIMA` en `frecuencia.py`. Las horas que fije el profesional mandan sobre ella.
 */
export const HORA_PRIMERA = 8;
export const HORA_ULTIMA = 19;

const HORA = /^(\d{1,2})(?:[:.h](\d{2}))?$/;

/** «6:00, 18:30» es [[6, 0], [18, 30]], ordenadas y sin repetir; espejo de `horas_fijas`. */
export function horasFijas(horas: string | null | undefined): Array<[number, number]> {
  const vistas = new Map<string, [number, number]>();
  for (const trozo of String(horas ?? '').trim().toLowerCase().split(/[,;y ]+/)) {
    const encontrada = HORA.exec(trozo.trim());
    if (!encontrada) continue;
    const hora = Number(encontrada[1]);
    const minuto = Number(encontrada[2] ?? 0);
    if (hora <= 23 && minuto <= 59) vistas.set(`${hora}:${minuto}`, [hora, minuto]);
  }
  return [...vistas.values()].sort((a, b) => a[0] * 60 + a[1] - (b[0] * 60 + b[1]));
}

/** Como se guarda `indicaciones.horas`: «06:00,18:30», o vacío. */
export function horasEnTexto(horas: string | null | undefined): string {
  const dos = (n: number) => String(n).padStart(2, '0');
  return horasFijas(horas)
    .map(([hora, minuto]) => `${dos(hora)}:${dos(minuto)}`)
    .join(',');
}

/** Ejemplos que la regla entiende, para la ayuda bajo el campo. */
export const EJEMPLOS_DE_FRECUENCIA = ['cada 8 horas', '2 veces al día', 'diario', 'cada 3 días', 'semanal'];
