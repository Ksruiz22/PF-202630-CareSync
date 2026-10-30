/**
 * Qué se le avisa a la persona y cuándo, con la misma lista para la pantalla y el
 * teléfono: si fueran dos cálculos, una notificación podría anunciar algo que la
 * pantalla no muestra.
 */

import {
  fecha,
  fechaHoraDe,
  horaDe,
  sigueVigente,
  tomasDelDia,
} from './agenda';
import { idDe, type Tratamiento } from './tipos';

const HORA = 60 * 60 * 1000;
const DIA = 24 * HORA;

export interface Aviso {
  clave: string;
  momento: Date;
  titulo: string;
  cuerpo: string;
  origen: 'toma' | 'cita' | 'recordatorio';
}

/** Los avisos futuros de los próximos días: las tomas, y la cita 24 y 2 horas antes. */
export function avisosDe(tratamientos: Tratamiento[], ahora: Date, dias = 3): Aviso[] {
  const avisos: Aviso[] = [];

  for (const { indicaciones, adherencias, citas, recordatorios } of tratamientos) {
    const vigentes = indicaciones.filter((indicacion) => sigueVigente(indicacion, ahora));
    for (let adelante = 0; adelante < dias; adelante += 1) {
      const dia = new Date(ahora.getTime() + adelante * DIA);
      for (const toma of tomasDelDia(vigentes, adherencias, dia, ahora)) {
        if (toma.estado !== 'pendiente' || toma.momento <= ahora) continue;
        avisos.push({
          clave: `toma|${toma.clave}`,
          momento: toma.momento,
          titulo: `Son las ${horaDe(toma.momento)}`,
          cuerpo: String(toma.indicacion.texto ?? 'Tienes algo de tu plan pendiente'),
          origen: 'toma',
        });
      }
    }

    for (const cita of citas) {
      const inicio = fecha(cita.inicio);
      if (!inicio || cita.estado !== 'confirmada') continue;
      for (const [horas, cuando] of [
        [24, 'Mañana'],
        [2, 'En dos horas'],
      ] as const) {
        const momento = new Date(inicio.getTime() - horas * HORA);
        if (momento <= ahora) continue;
        avisos.push({
          clave: `cita|${idDe(cita)}|${horas}`,
          momento,
          titulo: `${cuando} tienes cita`,
          cuerpo: `${fechaHoraDe(inicio)} · ${cita.profesional_nombre ?? 'tu profesional'}`,
          origen: 'cita',
        });
      }
    }

    // Lo que dejó la Lambda de reloj, cuando corre. Las tomas ya salen de arriba, así que
    // de esa tabla sólo se suma lo que no sea de una indicación que ya se está calculando.
    const calculadas = new Set(vigentes.map(idDe));
    for (const fila of recordatorios) {
      const momento = fecha(fila.programado_para);
      if (!momento || momento <= ahora || fila.estado !== 'pendiente') continue;
      if (calculadas.has(String(fila.indicacion_id ?? ''))) continue;
      avisos.push({
        clave: `recordatorio|${idDe(fila)}`,
        momento,
        titulo: 'Recordatorio de tu plan',
        cuerpo: String(fila.texto ?? ''),
        origen: 'recordatorio',
      });
    }
  }

  return avisos.sort((a, b) => a.momento.getTime() - b.momento.getTime());
}
