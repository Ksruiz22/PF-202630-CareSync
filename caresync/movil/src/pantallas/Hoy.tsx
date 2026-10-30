/**
 * Lo que hay que hacer hoy. Es la pantalla de todos los días, así que lo primero es lo
 * que se responde con un toque.
 */

import { useState } from 'react';
import { Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import {
  acompanamientoDe,
  estadoDeHito,
  fecha,
  fechaHoraDe,
  horaDe,
  sigueVigente,
  tomasDelDia,
  type Toma,
} from '../agenda';
import type { Reporte } from '../fuente';
import { Boton, Etiqueta, Tarjeta } from '../piezas';
import { estilosDe, useColores } from '../tema';
import { idDe, type AgenteDestino, type Tratamiento } from '../tipos';

export interface PropsDeHoy {
  tratamiento: Tratamiento;
  reportar: (reporte: Omit<Reporte, 'tratamiento'>) => Promise<void>;
  conversar: (mensaje: string, agente: AgenteDestino) => void;
  abrirAsistente: () => void;
  ahora: Date;
}

export function Hoy({ tratamiento, reportar, conversar, abrirAsistente, ahora }: PropsDeHoy) {
  const c = useColores();
  const e = estilosDe(c);
  const { plan, indicaciones, adherencias, citas } = tratamiento;

  const tomas = tomasDelDia(indicaciones, adherencias, ahora, ahora);
  const proximaCita = citas
    .filter((cita) => cita.estado === 'confirmada' && (fecha(cita.inicio)?.getTime() ?? 0) > ahora.getTime())
    .sort((a, b) => String(a.inicio ?? '').localeCompare(String(b.inicio ?? '')))[0];

  const porResponder = tomas.filter((toma) => toma.estado === 'pendiente').length;

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
      {proximaCita ? (
        <Tarjeta titulo="Tu próxima cita" extra={<Etiqueta texto={nombreDeCita(proximaCita.tipo)} />}>
          <Text style={[e.texto, { fontWeight: '600' }]}>{fechaHoraDe(proximaCita.inicio)}</Text>
          <Text style={e.fino}>
            {proximaCita.profesional_nombre ?? 'Profesional por asignar'} · {proximaCita.centro ?? ''}
          </Text>
          <Boton
            suave
            texto="Cambiar o cancelar"
            alPulsar={() => conversar('Necesito cambiar o cancelar mi próxima cita.', 'agenda')}
          />
        </Tarjeta>
      ) : null}

      {!plan ? (
        <Tarjeta titulo="Aún no hay plan">
          <Text style={e.texto}>
            Tu tratamiento aparece aquí cuando tu profesional lo escriba, después de la consulta.
          </Text>
          {/* Sólo canalizado: antes el triaje no ha dicho a qué centro va, y pedirle
              una cita al agente de agenda se saltaría esa decisión. */}
          {tratamiento.caso.estado === 'canalizado' && !proximaCita ? (
            <Boton
              texto="Buscar una cita"
              alPulsar={() => conversar('Quiero buscar un espacio para mi cita.', 'agenda')}
            />
          ) : tratamiento.caso.estado === 'abierto' ? (
            <>
              <Text style={e.fino}>Tu orientación con el asistente sigue en curso.</Text>
              <Boton suave texto="Continuar con el asistente" alPulsar={abrirAsistente} />
            </>
          ) : null}
        </Tarjeta>
      ) : (
        <>
          <Tarjeta
            titulo="Para hoy"
            extra={
              tomas.length > 0 ? (
                <Etiqueta
                  tono={porResponder === 0 ? 'verde' : 'neutro'}
                  texto={porResponder === 0 ? 'Al día' : `${porResponder} por responder`}
                />
              ) : undefined
            }
          >
            {tomas.length === 0 ? (
              <Text style={e.fino}>Hoy no hay nada programado en tu plan.</Text>
            ) : (
              tomas.map((toma) => (
                <FilaDeToma key={toma.clave} toma={toma} ahora={ahora} reportar={reportar} />
              ))
            )}
          </Tarjeta>

          <Pendientes {...{ tratamiento, reportar, conversar, abrirAsistente, ahora }} />
          <ComoTeSientes tratamiento={tratamiento} conversar={conversar} />
        </>
      )}
    </ScrollView>
  );
}

function FilaDeToma({
  toma,
  ahora,
  reportar,
}: {
  toma: Toma;
  ahora: Date;
  reportar: PropsDeHoy['reportar'];
}) {
  const c = useColores();
  const e = estilosDe(c);
  const [preguntando, setPreguntando] = useState(false);
  const [nota, setNota] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [fallo, setFallo] = useState('');

  async function responder(cumplida: boolean, conNota = '') {
    setOcupado(true);
    setFallo('');
    try {
      await reportar({
        indicacion: toma.indicacion,
        cumplida,
        nota: conNota,
        programadoPara: toma.momento,
      });
    } catch {
      // Se queda en pantalla para reintentar: un «sí» perdido en silencio se leería
      // después como una toma que no se hizo.
      setFallo('No se pudo guardar. Revisa tu conexión y vuelve a intentar.');
      setOcupado(false);
    }
  }

  const yaEsHora = toma.momento.getTime() <= ahora.getTime() + 60 * 60 * 1000;

  return (
    <View style={{ borderTopWidth: 1, borderTopColor: c.borde, paddingTop: 10, gap: 8 }}>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <Text style={{ color: c.primario, fontSize: 14, fontWeight: '700', width: 72 }}>
          {horaDe(toma.momento)}
        </Text>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={e.texto}>{String(toma.indicacion.texto ?? '')}</Text>
          {toma.indicacion.frecuencia ? <Text style={e.fino}>{String(toma.indicacion.frecuencia)}</Text> : null}
        </View>
      </View>

      {toma.estado === 'cumplida' ? (
        <Etiqueta tono="verde" texto="Lo hiciste" />
      ) : toma.estado === 'no_cumplida' ? (
        <Etiqueta tono="ambar" texto="Anotado: no se pudo" />
      ) : preguntando ? (
        <View style={{ gap: 8 }}>
          <Text nativeID={`nota-${toma.clave}`} style={e.fino}>¿Qué se te dificultó? (opcional)</Text>
          <TextInput
            accessibilityLabelledBy={`nota-${toma.clave}`}
            value={nota}
            onChangeText={setNota}
            maxLength={400}
            style={e.campo}
          />
          <Boton texto="Guardar" desactivado={ocupado} alPulsar={() => void responder(false, nota)} />
        </View>
      ) : yaEsHora || toma.estado === 'sin_reporte' ? (
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Boton texto="Sí, lo hice" desactivado={ocupado} alPulsar={() => void responder(true)} />
          </View>
          <View style={{ flex: 1 }}>
            <Boton suave texto="No pude" desactivado={ocupado} alPulsar={() => setPreguntando(true)} />
          </View>
        </View>
      ) : (
        <Text style={e.fino}>Te preguntamos cuando sea la hora.</Text>
      )}
      {fallo ? (
        <Text accessibilityRole="alert" style={{ color: c.rojo, fontSize: 13 }}>
          {fallo}
        </Text>
      ) : null}
    </View>
  );
}

/** Lo que pasa una vez: un control por agendar, un examen, una remisión. */
function Pendientes({ tratamiento, reportar, conversar, ahora }: PropsDeHoy) {
  const c = useColores();
  const e = estilosDe(c);
  const { indicaciones, adherencias, citas } = tratamiento;

  const hitos = indicaciones.filter(
    (indicacion) =>
      acompanamientoDe(indicacion) === 'hito' &&
      sigueVigente(indicacion, ahora) &&
      !estadoDeHito(indicacion, adherencias, citas).hecho
  );
  if (hitos.length === 0) return null;

  return (
    <Tarjeta titulo="Por hacer">
      {hitos.map((indicacion) => {
        const { limite, cita } = estadoDeHito(indicacion, adherencias, citas);
        const texto = String(indicacion.texto ?? '');
        const vencio = limite !== null && limite < ahora;
        return (
          <View key={idDe(indicacion)} style={{ borderTopWidth: 1, borderTopColor: c.borde, paddingTop: 10, gap: 8 }}>
            <Text style={e.texto}>{texto}</Text>
            {cita ? (
              <Text style={e.fino}>Agendado: {fechaHoraDe(cita.inicio)}</Text>
            ) : limite ? (
              <Text style={[e.fino, vencio ? { color: c.coral } : null]}>
                {vencio ? 'El plazo era hasta el' : 'Antes del'} {fechaHoraDe(limite).split(',').slice(0, 2).join(',')}
              </Text>
            ) : null}
            {indicacion.tipo === 'control' && !cita ? (
              <Boton
                texto="Agendar"
                alPulsar={() => conversar(`Quiero agendar esto de mi plan: ${texto}.`, 'agenda')}
              />
            ) : indicacion.tipo !== 'control' ? (
              <Boton
                suave
                texto={indicacion.tipo === 'remision' ? 'Ya fui' : 'Ya lo hice'}
                alPulsar={() => void reportar({ indicacion, cumplida: true })}
              />
            ) : null}
          </View>
        );
      })}
    </Tarjeta>
  );
}

/**
 * La escala de 0 a 10. El número no se escribe aquí: se le cuenta al agente, que es
 * quien revisa las señales de alarma y lo registra. Ver `fuenteRoble.ts`.
 */
function ComoTeSientes({
  tratamiento,
  conversar,
}: {
  tratamiento: Tratamiento;
  conversar: PropsDeHoy['conversar'];
}) {
  const c = useColores();
  const e = estilosDe(c);
  const [elegido, setElegido] = useState<number | null>(null);
  const ultima = tratamiento.evoluciones[0];

  return (
    <Tarjeta titulo="¿Cómo te sientes hoy?">
      <Text style={e.fino}>De 0 (peor que nunca) a 10 (como antes de todo esto).</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        {Array.from({ length: 11 }, (_, numero) => (
          <Pressable
            key={numero}
            accessibilityRole="button"
            accessibilityLabel={`${numero} de 10`}
            accessibilityState={{ selected: elegido === numero }}
            onPress={() => setElegido(numero)}
            style={{
              width: 44,
              height: 44,
              borderRadius: 22,
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: elegido === numero ? c.primario : c.primarioSuave,
            }}
          >
            <Text style={{ color: elegido === numero ? c.sobrePrimario : c.primario, fontWeight: '600' }}>
              {numero}
            </Text>
          </Pressable>
        ))}
      </View>
      <Boton
        texto="Contárselo al asistente"
        desactivado={elegido === null}
        alPulsar={() => {
          conversar(`Hoy me siento en ${elegido} de 10.`, 'seguimiento');
          setElegido(null);
        }}
      />
      {ultima ? (
        <Text style={e.fino}>
          Último reporte: {String(ultima.escala)} de 10, {fechaHoraDe(ultima.reportado_en)}
        </Text>
      ) : null}
    </Tarjeta>
  );
}

function nombreDeCita(tipo: unknown): string {
  if (tipo === 'control') return 'Control';
  if (tipo === 'sesion') return 'Sesión';
  return 'Consulta';
}
