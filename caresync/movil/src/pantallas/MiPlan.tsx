/**
 * El plan completo, con las palabras del profesional. Aquí se lee; no se edita nada,
 * porque no existe forma de que nadie más que el profesional cambie una indicación.
 *
 * El orden es el de la urgencia: primero lo que no puede esperar —las señales de
 * alarma, el único bloque de color fuerte de la pantalla—, después qué indicó el
 * profesional y al final cómo va la persona. Antes las cinco tarjetas tenían el mismo
 * peso, y «Si te pasa esto, no esperes» quedaba tercera, entre el resumen y la lista.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { Text, View } from 'react-native';
import {
  acompanamientoDe,
  avanceDe,
  diaDe,
  estadoDeHito,
  estadoDeSerie,
  fechaHoraDe,
  sigueVigente,
  venceEn,
} from '../agenda';
import { Boton, Desplazable, Etiqueta, Seccion, Tarjeta } from '../piezas';
import { estilosDe, F, S, T, useColores } from '../tema';
import { idDe, type AgenteDestino, type Indicacion, type Tratamiento } from '../tipos';

const NOMBRE_DE_TIPO: Record<string, string> = {
  medicamento: 'Medicamento',
  autocuidado: 'Autocuidado',
  tarea: 'Tarea',
  control: 'Control',
  sesiones: 'Sesiones',
  examen: 'Examen',
  remision: 'Remisión',
  reposo: 'Reposo',
};

export function MiPlan({
  tratamiento,
  conversar,
  ahora,
}: {
  tratamiento: Tratamiento;
  conversar: (mensaje: string, agente: AgenteDestino) => void;
  ahora: Date;
}) {
  const c = useColores();
  const e = estilosDe(c);
  const { plan, indicaciones, adherencias, citas } = tratamiento;

  if (!plan) {
    return (
      <Desplazable>
        <Tarjeta titulo="Aún no hay plan">
          <Text style={e.texto}>Tu profesional lo escribe después de la consulta y aparece aquí.</Text>
        </Tarjeta>
      </Desplazable>
    );
  }

  const vigentes = indicaciones.filter((indicacion) => sigueVigente(indicacion, ahora));
  const vigilancia = vigentes.filter((indicacion) => acompanamientoDe(indicacion) === 'vigilancia');
  const resto = vigentes.filter((indicacion) => acompanamientoDe(indicacion) !== 'vigilancia');
  const avance = avanceDe(indicaciones, adherencias, ahora);

  return (
    <Desplazable>
      <View style={{ gap: S.xs, paddingHorizontal: S.xs }}>
        <Text style={e.texto}>{String(plan.resumen ?? '')}</Text>
        <Text style={e.fino}>
          Lo escribió {plan.profesional_nombre ?? 'tu profesional'} el {diaDe(plan.creado_en)}.
        </Text>
      </View>

      {vigilancia.length > 0 ? (
        <View
          accessibilityRole="summary"
          style={{ backgroundColor: c.coralClaro, borderRadius: 16, padding: S.l, gap: S.m }}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: S.s }}>
            <Ionicons name="warning" size={20} color={c.coral} accessibilityElementsHidden importantForAccessibility="no" />
            <Text accessibilityRole="header" style={{ color: c.coral, fontSize: T.titulo, fontFamily: F.negrita }}>
              Si te pasa esto, no esperes
            </Text>
          </View>
          {vigilancia.map((indicacion) => (
            <Text key={idDe(indicacion)} style={[e.texto, { color: c.tinta }]}>
              {String(indicacion.texto ?? '')}
            </Text>
          ))}
          <Boton
            texto="Me está pasando"
            alPulsar={() =>
              conversar(
                `Me está pasando esto que me indicaron vigilar: ${vigilancia
                  .map((indicacion) => String(indicacion.texto ?? ''))
                  .join('; ')}`,
                'seguimiento'
              )
            }
          />
        </View>
      ) : null}

      {resto.length === 0 ? (
        <Tarjeta titulo="Lo que te indicaron">
          <Text style={e.fino}>No hay indicaciones vigentes.</Text>
        </Tarjeta>
      ) : (
        <Seccion titulo="Lo que te indicaron">
          {resto.map((indicacion) => (
            <View key={idDe(indicacion)} style={{ gap: S.xs }}>
              <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: S.s }}>
                <Text style={[e.fuerte, { flex: 1 }]}>{String(indicacion.texto ?? '')}</Text>
                {NOMBRE_DE_TIPO[String(indicacion.tipo)] ? (
                  <Etiqueta texto={NOMBRE_DE_TIPO[String(indicacion.tipo)] ?? ''} />
                ) : null}
              </View>
              <Detalle indicacion={indicacion} tratamiento={tratamiento} conversar={conversar} />
            </View>
          ))}
        </Seccion>
      )}

      {avance.proporcion !== null ? (
        <Tarjeta titulo="Tus últimos 7 días">
          <View
            accessibilityRole="progressbar"
            accessibilityValue={{ min: 0, max: avance.esperadas, now: avance.cumplidas }}
            style={{ height: 10, borderRadius: 5, backgroundColor: c.primarioSuave, overflow: 'hidden' }}
          >
            <View
              style={{
                height: 10,
                width: `${Math.round(avance.proporcion * 100)}%`,
                backgroundColor: c.primario,
              }}
            />
          </View>
          <Text style={e.fino}>
            Marcaste {avance.cumplidas} de {avance.esperadas} como hechas
            {avance.sinReporte > 0 ? ` y ${avance.sinReporte} quedaron sin respuesta` : ''}. Tu profesional
            lo ve antes de la siguiente consulta.
          </Text>
        </Tarjeta>
      ) : null}
    </Desplazable>
  );
}

function Detalle({
  indicacion,
  tratamiento,
  conversar,
}: {
  indicacion: Indicacion;
  tratamiento: Tratamiento;
  conversar: (mensaje: string, agente: AgenteDestino) => void;
}) {
  const c = useColores();
  const e = estilosDe(c);
  const { adherencias, citas } = tratamiento;
  const vence = venceEn(indicacion);
  const texto = String(indicacion.texto ?? '');
  const centro = indicacion.centro_destino ? `, en el ${String(indicacion.centro_destino)}` : '';

  switch (acompanamientoDe(indicacion)) {
    case 'reposo':
      return <Text style={e.fino}>{vence ? `Hasta el ${diaDe(vence)}` : 'Hasta que te lo indiquen'}</Text>;

    case 'serie': {
      const serie = estadoDeSerie(indicacion, citas);
      return (
        <View style={{ gap: S.s, alignItems: 'flex-start' }}>
          <Text style={e.fino}>
            Llevas {serie.atendidas} de {serie.total ?? '?'} sesiones
            {indicacion.frecuencia ? `, ${String(indicacion.frecuencia)}` : ''}
            {centro}
          </Text>
          {serie.proxima ? (
            <Text style={e.fino}>La siguiente: {fechaHoraDe(serie.proxima.inicio)}</Text>
          ) : serie.falta ? (
            <View style={{ alignSelf: 'stretch' }}>
              <Boton
                suave
                compacto
                texto="Agendar la siguiente con el asistente"
                alPulsar={() => conversar(`Quiero agendar la siguiente sesión de: ${texto}.`, 'agenda')}
              />
            </View>
          ) : (
            <Etiqueta tono="verde" texto="Serie completa" />
          )}
        </View>
      );
    }

    case 'hito': {
      const hito = estadoDeHito(indicacion, adherencias, citas);
      if (hito.hecho) {
        return (
          <View style={{ alignItems: 'flex-start' }}>
            <Etiqueta tono="verde" texto="Hecho" />
          </View>
        );
      }
      return (
        <Text style={e.fino}>
          {hito.cita
            ? `Agendado: ${fechaHoraDe(hito.cita.inicio)}`
            : hito.limite
              ? `Antes del ${diaDe(hito.limite)}`
              : 'Sin fecha límite'}
          {centro}
        </Text>
      );
    }

    default:
      return (
        <Text style={e.fino}>
          {indicacion.frecuencia ? capitalizar(String(indicacion.frecuencia)) : 'Sin horario'}
          {vence ? `, hasta el ${diaDe(vence)}` : ''}
        </Text>
      );
  }
}

function capitalizar(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}
