/**
 * El plan completo, con las palabras del profesional. Aquí se lee; no se edita nada,
 * porque no existe forma de que nadie más que el profesional cambie una indicación.
 */

import { ScrollView, Text, View } from 'react-native';
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
import { Boton, Etiqueta, Tarjeta } from '../piezas';
import { estilosDe, useColores } from '../tema';
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
      <ScrollView contentContainerStyle={{ padding: 16 }}>
        <Tarjeta titulo="Aún no hay plan">
          <Text style={e.texto}>Tu profesional lo escribe después de la consulta.</Text>
        </Tarjeta>
      </ScrollView>
    );
  }

  const vigentes = indicaciones.filter((indicacion) => sigueVigente(indicacion, ahora));
  const vigilancia = vigentes.filter((indicacion) => acompanamientoDe(indicacion) === 'vigilancia');
  const resto = vigentes.filter((indicacion) => acompanamientoDe(indicacion) !== 'vigilancia');
  const avance = avanceDe(indicaciones, adherencias, ahora);

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
      <Tarjeta titulo="Tu plan">
        <Text style={e.texto}>{String(plan.resumen ?? '')}</Text>
        <Text style={e.fino}>
          {plan.profesional_nombre ?? 'Tu profesional'} · {diaDe(plan.creado_en)}
        </Text>
      </Tarjeta>

      {avance.proporcion !== null ? (
        <Tarjeta titulo="Últimos 7 días">
          <View
            accessibilityRole="progressbar"
            accessibilityValue={{ min: 0, max: avance.esperadas, now: avance.cumplidas }}
            style={{ height: 8, borderRadius: 4, backgroundColor: c.primarioSuave, overflow: 'hidden' }}
          >
            <View
              style={{
                height: 8,
                width: `${Math.round(avance.proporcion * 100)}%`,
                backgroundColor: c.primario,
              }}
            />
          </View>
          <Text style={e.fino}>
            Reportaste {avance.cumplidas} de {avance.esperadas} como hechas
            {avance.sinReporte > 0 ? `; ${avance.sinReporte} quedaron sin respuesta` : ''}.
          </Text>
        </Tarjeta>
      ) : null}

      {vigilancia.length > 0 ? (
        <Tarjeta titulo="Si te pasa esto, no esperes">
          {vigilancia.map((indicacion) => (
            <Text key={idDe(indicacion)} style={e.texto}>
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
        </Tarjeta>
      ) : null}

      <Tarjeta titulo="Lo que te indicaron">
        {resto.length === 0 ? (
          <Text style={e.fino}>Sin indicaciones vigentes.</Text>
        ) : (
          resto.map((indicacion) => (
            <View
              key={idDe(indicacion)}
              style={{ borderTopWidth: 1, borderTopColor: c.borde, paddingTop: 10, gap: 6 }}
            >
              {NOMBRE_DE_TIPO[String(indicacion.tipo)] ? (
                <View style={{ flexDirection: 'row' }}>
                  <Etiqueta texto={NOMBRE_DE_TIPO[String(indicacion.tipo)] ?? ''} />
                </View>
              ) : null}
              <Text style={e.texto}>{String(indicacion.texto ?? '')}</Text>
              <Detalle indicacion={indicacion} tratamiento={tratamiento} conversar={conversar} />
            </View>
          ))
        )}
      </Tarjeta>

      {adherencias.length === 0 && citas.length === 0 ? (
        <Text style={[e.fino, { textAlign: 'center' }]}>
          Lo que reportes aquí lo ve tu profesional antes de la siguiente consulta.
        </Text>
      ) : null}
    </ScrollView>
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

  switch (acompanamientoDe(indicacion)) {
    case 'reposo':
      return <Text style={e.fino}>{vence ? `Hasta el ${diaDe(vence)}` : 'Hasta que te lo indiquen'}</Text>;

    case 'serie': {
      const serie = estadoDeSerie(indicacion, citas);
      return (
        <View style={{ gap: 6 }}>
          <Text style={e.fino}>
            {serie.atendidas} de {serie.total ?? '?'} sesiones
            {indicacion.frecuencia ? ` · ${String(indicacion.frecuencia)}` : ''}
            {indicacion.centro_destino ? ` · ${String(indicacion.centro_destino)}` : ''}
          </Text>
          {serie.proxima ? (
            <Text style={e.fino}>Siguiente: {fechaHoraDe(serie.proxima.inicio)}</Text>
          ) : serie.falta ? (
            <Boton
              suave
              texto="Agendar la siguiente"
              alPulsar={() => conversar(`Quiero agendar la siguiente sesión de: ${texto}.`, 'agenda')}
            />
          ) : (
            <Etiqueta tono="verde" texto="Serie completa" />
          )}
        </View>
      );
    }

    case 'hito': {
      const hito = estadoDeHito(indicacion, adherencias, citas);
      if (hito.hecho) return <Etiqueta tono="verde" texto="Hecho" />;
      return (
        <Text style={[e.fino, { color: c.tintaSuave }]}>
          {hito.cita
            ? `Agendado: ${fechaHoraDe(hito.cita.inicio)}`
            : hito.limite
              ? `Antes del ${diaDe(hito.limite)}`
              : 'Sin fecha límite'}
          {indicacion.centro_destino ? ` · ${String(indicacion.centro_destino)}` : ''}
        </Text>
      );
    }

    default:
      return (
        <Text style={e.fino}>
          {indicacion.frecuencia ? String(indicacion.frecuencia) : 'Sin horario'}
          {vence ? ` · hasta el ${diaDe(vence)}` : ''}
        </Text>
      );
  }
}
