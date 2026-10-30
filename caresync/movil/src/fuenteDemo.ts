/**
 * Datos de ejemplo en memoria, sin cuenta y sin tocar ROBLE ni el agente.
 *
 * Existe para poder ver la app entera sin credenciales y para probar cada tipo de
 * indicación, que en la base real todavía no hay quien escriba: la vista del profesional
 * aún no guarda `tipo`. Sólo aparece con `EXPO_PUBLIC_DEMO=1`, y la pantalla lo dice.
 * Las personas y las respuestas del asistente son inventadas.
 */

import type { Fuente } from './fuente';
import { idDe, type Adherencia, type Identidad, type Tratamiento } from './tipos';

const DIA = 24 * 60 * 60 * 1000;
const haceDias = (dias: number) => new Date(Date.now() - dias * DIA).toISOString();
const enDias = (dias: number) => new Date(Date.now() + dias * DIA).toISOString();

const PERSONA: Identidad = {
  userId: 'demo',
  email: 'demostracion@caresync.invalid',
  nombre: 'Persona de demostración',
};

function ejemplo(): Tratamiento {
  const base = { caso_id: 'caso-demo', plan_id: 'plan-demo', activa: true };
  return {
    caso: {
      _id: 'caso-demo',
      estado: 'en_seguimiento',
      centro: 'CMU',
      nivel_urgencia: 3,
      motivo: 'Dolor de garganta con fiebre',
      creado_en: haceDias(3),
    },
    plan: {
      _id: 'plan-demo',
      caso_id: 'caso-demo',
      profesional_nombre: 'Profesional de ejemplo',
      resumen: 'Plan de ejemplo para recorrer la app. No es una recomendación médica.',
      creado_en: haceDias(2),
    },
    indicaciones: [
      {
        ...base,
        _id: 'i-medicamento',
        tipo: 'medicamento',
        texto: 'Tomar el medicamento indicado',
        frecuencia: 'cada 8 horas',
        duracion_dias: 5,
        creado_en: haceDias(2),
      },
      {
        ...base,
        _id: 'i-autocuidado',
        tipo: 'autocuidado',
        texto: 'Hacer gárgaras con agua tibia',
        frecuencia: '2 veces al día',
        duracion_dias: 5,
        creado_en: haceDias(2),
      },
      {
        ...base,
        _id: 'i-control',
        tipo: 'control',
        texto: 'Control con tu profesional',
        plazo_dias: 14,
        centro_destino: 'CMU',
        creado_en: haceDias(2),
      },
      {
        ...base,
        _id: 'i-examen',
        tipo: 'examen',
        texto: 'Hacerte el examen antes del control',
        plazo_dias: 7,
        creado_en: haceDias(2),
      },
      {
        ...base,
        _id: 'i-sesiones',
        tipo: 'sesiones',
        texto: 'Sesiones de acompañamiento',
        sesiones: 4,
        frecuencia: 'semanal',
        centro_destino: 'CAE',
        creado_en: haceDias(2),
      },
      {
        ...base,
        _id: 'i-reposo',
        tipo: 'reposo',
        texto: 'Reposo relativo',
        duracion_dias: 3,
        creado_en: haceDias(2),
      },
      {
        ...base,
        _id: 'i-vigilancia',
        tipo: 'vigilancia',
        texto: 'Si la fiebre pasa de 39 °C o te cuesta respirar, ve a urgencias',
        creado_en: haceDias(2),
      },
    ],
    adherencias: [],
    evoluciones: [
      { _id: 'e1', caso_id: 'caso-demo', escala: 5, nota: 'Con molestia al tragar', reportado_en: haceDias(1) },
    ],
    citas: [
      {
        _id: 'cita-sesion',
        caso_id: 'caso-demo',
        indicacion_id: 'i-sesiones',
        tipo: 'sesion',
        estado: 'confirmada',
        centro: 'CAE',
        profesional_nombre: 'Profesional de ejemplo',
        inicio: enDias(1),
      },
    ],
    recordatorios: [],
    turnos: [],
  };
}

let datos: Tratamiento | null = null;
let contador = 0;

function respuestaDe(mensaje: string): string {
  if (/me está pasando|urgenc|respirar/i.test(mensaje)) {
    return '[Demostración] Aquí el agente real revisa las señales de alarma y, si aplica, te da la ruta de emergencia.';
  }
  if (/agendar/i.test(mensaje)) {
    return '[Demostración] Aquí el agente de agenda te buscaría espacios dentro del plazo.';
  }
  return '[Demostración] Aquí el agente de seguimiento registraría lo que le cuentas.';
}

export const fuenteDemo: Fuente = {
  esDemo: true,
  restaurar: async () => null,
  entrar: async () => {
    datos = ejemplo();
    return PERSONA;
  },
  salir: async () => {
    datos = null;
  },
  tratamientos: async () => (datos ? [datos] : []),
  reportar: async (_quien, { indicacion, cumplida, nota, programadoPara }) => {
    contador += 1;
    const fila: Adherencia = {
      _id: `a${contador}`,
      caso_id: 'caso-demo',
      indicacion_id: idDe(indicacion),
      cumplida,
      nota: nota ?? '',
      reportado_en: new Date().toISOString(),
      programado_para: programadoPara?.toISOString() ?? null,
      origen: 'app',
    };
    datos?.adherencias.push(fila);
  },
  hablar: async (mensaje) => {
    await new Promise((resolver) => setTimeout(resolver, 400));
    const respuesta = respuestaDe(mensaje);
    datos?.turnos.push({ quien: 'yo', texto: mensaje }, { quien: 'agente', texto: respuesta });
    return { respuesta };
  },
};
