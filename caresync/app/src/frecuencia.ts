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

export function programaRecordatorios(frecuencia: string): boolean {
  const texto = frecuencia.trim().toLowerCase();
  if (!texto) return false;

  const cada = CADA_N.exec(texto);
  if (cada) return Number(cada[1]) > 0;

  const veces = VECES_AL_DIA.exec(texto);
  if (veces) return veces[1] !== '0';

  return PALABRAS.some((palabra) => texto.includes(palabra));
}

/** Ejemplos que la regla entiende, para la ayuda bajo el campo. */
export const EJEMPLOS_DE_FRECUENCIA = ['cada 8 horas', '2 veces al día', 'diario', 'cada 3 días', 'semanal'];
