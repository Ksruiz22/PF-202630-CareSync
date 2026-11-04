/**
 * Pruebas de la agenda: `npm run prueba`. No tocan la red ni ROBLE.
 */

import assert from 'node:assert/strict';
import {
  acompanamientoDe,
  agenteParaMensaje,
  avanceDe,
  estadoDeHito,
  estadoDeSerie,
  fecha,
  horaDe,
  intervaloDe,
  momentosDelDia,
  sigueVigente,
  tomasDelDia,
} from './agenda';
import type { Adherencia, Indicacion } from './tipos';

const H = 60 * 60 * 1000;
const D = 24 * H;

let pasaron = 0;
function prueba(nombre: string, cuerpo: () => void): void {
  cuerpo();
  pasaron += 1;
  console.log(`  ok - ${nombre}`);
}

// 30 de octubre, 10:00 en Bogotá.
const AHORA = new Date('2026-10-30T15:00:00Z');
const AYER_7PM = '2026-10-30T00:00:00Z';

function indicacion(campos: Partial<Indicacion>): Indicacion {
  return { _id: 'i1', caso_id: 'c1', texto: 'Algo', activa: true, creado_en: AYER_7PM, ...campos };
}

const horas = (momentos: Date[]) => momentos.map(horaDe);

prueba('entiende las mismas frases que caresync_comun/frecuencia.py', () => {
  for (const [texto, esperado] of [
    ['cada 24 horas', D],
    ['Cada 8 horas', 8 * H],
    ['cada 48 h', 2 * D],
    ['cada 2 días', 2 * D],
    ['cada 3 dias', 3 * D],
    ['cada 2 semanas', 14 * D],
    ['semanal', 7 * D],
    ['diario, en la mañana', D],
    ['dos veces al día', 12 * H],
    ['3 veces al dia', 8 * H],
    ['cada hora', 4 * H],
    ['cada 2 horas', 4 * H],
    ['acude al control del viernes', null],
    ['cada 0 días', null],
    ['', null],
    [null, null],
  ] as const) {
    assert.equal(intervaloDe(texto), esperado, String(texto));
  }
});

prueba('un momento sin zona se lee como UTC, no como hora del teléfono', () => {
  // Como lo devuelve el `read` de ROBLE: sin zona ni segundos.
  assert.equal(fecha('2026-09-11T19:00')?.toISOString(), '2026-09-11T19:00:00.000Z');
  assert.equal(horaDe(fecha('2026-09-11T19:00') as Date), horaDe(new Date('2026-09-11T19:00:00Z')));
  assert.equal(fecha('2026-10-30 12:00:00')?.toISOString(), '2026-10-30T12:00:00.000Z');
  assert.equal(fecha('2026-10-30T12:00:00.000Z')?.toISOString(), '2026-10-30T12:00:00.000Z');
  assert.equal(fecha('no es una fecha'), null);
  assert.equal(fecha(null), null);
});

prueba('cada 8 horas son tres tomas, y la de la noche se pregunta a las 22:00', () => {
  const momentos = momentosDelDia(indicacion({ frecuencia: 'cada 8 horas' }), AHORA);
  assert.equal(momentos.length, 3);
  assert.deepEqual(
    momentos.map((m) => m.toISOString()),
    ['2026-10-30T12:00:00.000Z', '2026-10-30T20:00:00.000Z', '2026-10-31T03:00:00.000Z']
  );
});

prueba('no se pregunta por lo anterior a que existiera la indicación', () => {
  const creada = indicacion({ frecuencia: 'cada 8 horas', creado_en: '2026-10-30T14:00:00Z' });
  assert.equal(momentosDelDia(creada, AHORA).length, 2);
});

prueba('cada dos días sólo pregunta los días que le tocan', () => {
  const cada2 = indicacion({ frecuencia: 'cada 2 días', creado_en: '2026-10-29T14:00:00Z' });
  assert.equal(momentosDelDia(cada2, AHORA).length, 0);
  assert.equal(momentosDelDia(cada2, new Date(AHORA.getTime() + D)).length, 1);
});

prueba('cada tipo se acompaña distinto, y nulo es otro', () => {
  assert.equal(acompanamientoDe(indicacion({ tipo: 'medicamento', frecuencia: 'cada 8 horas' })), 'toma');
  assert.equal(acompanamientoDe(indicacion({ tipo: 'vigilancia', frecuencia: 'cada 8 horas' })), 'vigilancia');
  assert.equal(acompanamientoDe(indicacion({ tipo: 'control' })), 'hito');
  assert.equal(acompanamientoDe(indicacion({ tipo: 'sesiones', frecuencia: 'semanal' })), 'serie');
  assert.equal(acompanamientoDe(indicacion({ tipo: 'reposo' })), 'reposo');
  assert.equal(acompanamientoDe(indicacion({ tipo: null, frecuencia: 'diaria' })), 'toma');
  assert.equal(acompanamientoDe(indicacion({ tipo: null, frecuencia: 'cuando pueda' })), 'abierta');
});

prueba('pasada su duración deja de contar, y sin duración sigue', () => {
  const tres = indicacion({ duracion_dias: '3', creado_en: '2026-10-26T12:00:00Z' });
  assert.equal(sigueVigente(tres, AHORA), false);
  assert.equal(sigueVigente(indicacion({}), AHORA), true);
  assert.equal(sigueVigente(indicacion({ activa: false }), AHORA), false);
});

prueba('un reporte se empareja con su toma y no con la de al lado', () => {
  const base = indicacion({ tipo: 'medicamento', frecuencia: 'cada 8 horas' });
  const reporte: Adherencia = {
    indicacion_id: 'i1',
    cumplida: true,
    programado_para: '2026-10-30T12:00:00.000Z',
    reportado_en: '2026-10-30T12:30:00Z',
    origen: 'app',
  };
  const tomas = tomasDelDia([base], [reporte], AHORA, AHORA);
  assert.deepEqual(
    tomas.map((t) => t.estado),
    ['cumplida', 'pendiente', 'pendiente']
  );
});

prueba('un reporte releído de ROBLE, sin zona ni segundos, sigue emparejando', () => {
  const base = indicacion({ tipo: 'medicamento', frecuencia: 'cada 8 horas', creado_en: '2026-10-30T00:00' });
  const releido: Adherencia = {
    indicacion_id: 'i1',
    cumplida: true,
    programado_para: '2026-10-30T20:00',
    reportado_en: '2026-10-30T20:03',
    origen: 'app',
  };
  const tomas = tomasDelDia([base], [releido], AHORA, AHORA);
  assert.deepEqual(
    tomas.map((t) => t.estado),
    ['pendiente', 'cumplida', 'pendiente']
  );
});

prueba('lo que se le contó al agente no se vuelve a preguntar', () => {
  const base = indicacion({ tipo: 'medicamento', frecuencia: 'dos veces al día' });
  const delAgente: Adherencia = {
    indicacion_id: 'i1',
    cumplida: 'false',
    reportado_en: '2026-10-30T13:00:00Z',
  };
  const tomas = tomasDelDia([base], [delAgente], AHORA, AHORA);
  assert.equal(tomas[0]?.estado, 'no_cumplida');
  assert.equal(tomas[1]?.estado, 'pendiente');
});

prueba('una toma muy atrás sin respuesta queda sin reporte, no como incumplida', () => {
  const base = indicacion({ tipo: 'medicamento', frecuencia: 'cada 8 horas' });
  const tarde = new Date('2026-10-30T23:00:00Z');
  const tomas = tomasDelDia([base], [], tarde, tarde);
  assert.equal(tomas[0]?.estado, 'sin_reporte');
});

prueba('el avance no cuenta en contra lo que aún está pendiente', () => {
  const base = indicacion({ tipo: 'medicamento', frecuencia: 'cada 8 horas', creado_en: '2026-10-30T11:00:00Z' });
  const avance = avanceDe([base], [], AHORA);
  assert.equal(avance.esperadas, 0);
  assert.equal(avance.proporcion, null);
});

prueba('un control sin cita se ofrece, con cita se muestra, y atendido queda hecho', () => {
  const control = indicacion({ tipo: 'control', plazo_dias: 14 });
  const vacio = estadoDeHito(control, [], []);
  assert.equal(vacio.hecho, false);
  assert.equal(vacio.limite?.toISOString(), '2026-11-13T00:00:00.000Z');
  const conCita = estadoDeHito(control, [], [{ indicacion_id: 'i1', estado: 'confirmada' }]);
  assert.equal(conCita.cita?.estado, 'confirmada');
  assert.equal(estadoDeHito(control, [], [{ indicacion_id: 'i1', estado: 'atendida' }]).hecho, true);
  assert.equal(estadoDeHito(control, [], [{ indicacion_id: 'i1', estado: 'cancelada' }]).cita, null);
});

prueba('una serie lleva la cuenta y sabe cuándo terminó', () => {
  const serie = indicacion({ tipo: 'sesiones', sesiones: 2 });
  const citas = [
    { indicacion_id: 'i1', estado: 'atendida' },
    { indicacion_id: 'i1', estado: 'confirmada', inicio: '2026-11-05T15:00:00Z' },
  ];
  const estado = estadoDeSerie(serie, citas);
  assert.equal(estado.atendidas, 1);
  assert.equal(estado.falta, true);
  assert.equal(estado.proxima?.inicio, '2026-11-05T15:00:00Z');
  assert.equal(
    estadoDeSerie(serie, [
      { indicacion_id: 'i1', estado: 'atendida' },
      { indicacion_id: 'i1', estado: 'atendida' },
    ]).falta,
    false
  );
});

prueba('sin plan decide el orquestador: un triaje a medias no se salta', () => {
  assert.equal(agenteParaMensaje({ plan: null, caso: { estado: 'abierto' } }), undefined);
  assert.equal(agenteParaMensaje({ plan: null, caso: { estado: 'canalizado' } }), undefined);
  assert.equal(agenteParaMensaje({ plan: {}, caso: { estado: 'agendado' } }), 'seguimiento');
  assert.equal(agenteParaMensaje({ plan: {}, caso: { estado: 'urgencia_escalada' } }), undefined);
});

console.log(`\n${pasaron} pruebas pasan.`);
