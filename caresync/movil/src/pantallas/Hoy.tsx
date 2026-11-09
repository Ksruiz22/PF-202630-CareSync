/**
 * Lo que hay que hacer hoy. Es la pantalla de todos los días, así que lo primero es lo
 * que se responde con un toque.
 *
 * **El día se lee como un horario de clases**: las horas en una columna, una línea que
 * las une y una marca de «Ahora». Es lo que un estudiante ya lee todos los días, y
 * responde de un vistazo las dos preguntas de esta pantalla: qué me toca y qué sigue.
 * Sólo lleva botones lo que ya se puede responder; lo respondido queda marcado en la
 * línea y lo que falta, en gris, sin botones. Cada toma dice su frecuencia y cuál es
 * del día («Cada 8 horas, la 2 de 3 de hoy»): ver `cuentaDelDia`.
 *
 * Antes cada toma era una fila con hora, texto, frecuencia y dos botones grandes, y con
 * dos indicaciones la lista ocupaba dos pantallas: «¿Cómo te sientes hoy?» quedaba
 * donde nadie llegaba.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useRef, useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
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
import { Aparece, Rebote } from '../movimiento';
import { Boton, Desplazable, Etiqueta, Seccion, Tarjeta } from '../piezas';
import { estilosDe, F, S, T, useColores, type Colores } from '../tema';
import { idDe, type AgenteDestino, type Tratamiento } from '../tipos';

export interface PropsDeHoy {
  tratamiento: Tratamiento;
  reportar: (reporte: Omit<Reporte, 'tratamiento'>) => Promise<void>;
  conversar: (mensaje: string, agente: AgenteDestino) => void;
  abrirAsistente: () => void;
  ahora: Date;
}

/** Una toma se puede responder desde una hora antes de su momento. */
const ANTICIPO = 60 * 60 * 1000;

function sePuedeResponder(toma: Toma, ahora: Date): boolean {
  if (toma.estado === 'sin_reporte') return true;
  return toma.estado === 'pendiente' && toma.momento.getTime() <= ahora.getTime() + ANTICIPO;
}

/**
 * Cuántas tomas esperan respuesta ahora mismo. La usa también el contador de la
 * pestaña: si fueran dos cuentas, la pestaña podría decir 3 y la pantalla 5.
 */
export function porResponder(tratamiento: Tratamiento, ahora: Date): number {
  if (!tratamiento.plan) return 0;
  return tomasDelDia(tratamiento.indicaciones, tratamiento.adherencias, ahora, ahora).filter((toma) =>
    sePuedeResponder(toma, ahora)
  ).length;
}

export function Hoy({
  nombre,
  tratamiento,
  reportar,
  conversar,
  abrirAsistente,
  ahora,
}: PropsDeHoy & { nombre: string }) {
  const c = useColores();
  const e = estilosDe(c);
  const { plan, indicaciones, adherencias, citas } = tratamiento;

  const tomas = tomasDelDia(indicaciones, adherencias, ahora, ahora);
  const proximaCita = citas
    .filter((cita) => cita.estado === 'confirmada' && (fecha(cita.inicio)?.getTime() ?? 0) > ahora.getTime())
    .sort((a, b) => String(a.inicio ?? '').localeCompare(String(b.inicio ?? '')))[0];
  const pendientes = tomas.filter((toma) => sePuedeResponder(toma, ahora)).length;

  return (
    <Desplazable>
      <Resumen nombre={nombre} tratamiento={tratamiento} tomas={tomas} proximaCita={proximaCita} ahora={ahora} />

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
        <View style={{ gap: S.s }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: S.xs }}>
            <Text accessibilityRole="header" style={e.seccion}>
              Tu día
            </Text>
            {tomas.length > 0 ? (
              <Etiqueta
                tono={pendientes === 0 ? 'verde' : 'coral'}
                texto={pendientes === 0 ? 'Al día' : `${pendientes} por responder`}
              />
            ) : null}
          </View>
          <View style={[e.tarjeta, { paddingVertical: S.l }]}>
            {tomas.length === 0 ? (
              <Text style={e.fino}>Hoy no hay nada programado en tu plan.</Text>
            ) : (
              <Horario tomas={tomas} ahora={ahora} reportar={reportar} />
            )}
          </View>
        </View>
      )}

      {proximaCita ? (
        <Tarjeta titulo="Tu próxima cita" extra={<Etiqueta texto={nombreDeCita(proximaCita.tipo)} />}>
          <View style={{ gap: 2 }}>
            <Text style={e.fuerte}>{capitalizar(fechaHoraDe(proximaCita.inicio))}</Text>
            <Text style={e.fino}>
              Con {proximaCita.profesional_nombre ?? 'un profesional por asignar'}
              {proximaCita.centro ? `, en el ${String(proximaCita.centro)}` : ''}
            </Text>
          </View>
          {/* Dice a dónde lleva: el botón abre la conversación con el agente de agenda,
              y sin decirlo el salto a otra pestaña parecía un error. */}
          <Boton
            suave
            compacto
            texto="Cambiar o cancelar con el asistente"
            alPulsar={() => conversar('Necesito cambiar o cancelar mi próxima cita.', 'agenda')}
          />
        </Tarjeta>
      ) : null}

      {plan ? (
        <>
          <ComoTeSientes tratamiento={tratamiento} conversar={conversar} />
          <Pendientes {...{ tratamiento, reportar, conversar, abrirAsistente, ahora }} />
        </>
      ) : null}
    </Desplazable>
  );
}

// ------------------------------------------------------------------- el resumen

type Tono = 'atencion' | 'listo' | 'neutro';
type NombreDeIcono = keyof typeof Ionicons.glyphMap;

interface PuntoDelResumen {
  clave: string;
  tono: Tono;
  icono: NombreDeIcono;
  texto: string;
}

/**
 * Lo que la persona tiene que saber al abrir la app, en tres líneas como máximo.
 *
 * Cada punto tiene su versión «resuelta» en verde con una marca —«No tienes citas
 * próximas»—, porque saber que no falta nada también es información: sin ella, la
 * ausencia de un punto se leería como «la app no cargó esto».
 *
 * Están, en este orden:
 * - **Lo de hoy**: las indicaciones diarias (un medicamento, unas gárgaras) que ya se
 *   pueden marcar. Se cuentan sin nombrarlas —«3 pendientes por hacer hoy»—: el detalle
 *   está justo debajo, en el horario.
 * - **La próxima cita.**
 * - **Lo que se hace una sola vez y tiene fecha límite**: agendar un control, hacerse
 *   un examen, ir a una remisión. Ésas sí se nombran, con su fecha, porque no son
 *   diarias y un número solo no dice qué hay que hacer. Una versión anterior decía «2
 *   pendientes por hacer», y no se entendía que no eran del día.
 *
 * Hubo un cuarto punto, «Cuéntanos cómo te sientes hoy», y se quitó: la escala tiene
 * su propia tarjeta más abajo, y en el resumen competía con lo que sí es urgente.
 */
function puntosDelResumen(
  tratamiento: Tratamiento,
  tomas: Toma[],
  proximaCita: Tratamiento['citas'][number] | undefined,
  ahora: Date
): PuntoDelResumen[] {
  const puntos: PuntoDelResumen[] = [];
  const { plan, indicaciones, adherencias, citas } = tratamiento;

  if (plan) {
    const porHacerAhora = tomas.filter((toma) => sePuedeResponder(toma, ahora));
    const siguiente = tomas
      .filter((toma) => toma.estado === 'pendiente' && !sePuedeResponder(toma, ahora))
      .sort((a, b) => a.momento.getTime() - b.momento.getTime())[0];
    if (porHacerAhora.length > 0) {
      const n = porHacerAhora.length;
      puntos.push({
        clave: 'diario',
        tono: 'atencion',
        icono: 'alert',
        texto: `${n} ${n === 1 ? 'pendiente' : 'pendientes'} por hacer hoy`,
      });
    } else if (tomas.length === 0) {
      puntos.push({ clave: 'diario', tono: 'listo', icono: 'checkmark', texto: 'Hoy no tienes nada diario en tu plan' });
    } else if (siguiente) {
      puntos.push({
        clave: 'diario',
        tono: 'listo',
        icono: 'checkmark',
        texto: `Estás al día. Lo siguiente es a las ${horaSinCorte(siguiente.momento)}`,
      });
    } else {
      puntos.push({ clave: 'diario', tono: 'listo', icono: 'checkmark', texto: 'Respondiste todo lo de hoy' });
    }
  }

  puntos.push(
    proximaCita
      ? { clave: 'cita', tono: 'neutro', icono: 'calendar', texto: `Cita ${cuandoEs(fecha(proximaCita.inicio), ahora)}` }
      : { clave: 'cita', tono: 'listo', icono: 'checkmark', texto: 'No tienes citas próximas' }
  );

  if (plan) {
    const conFecha = indicaciones.filter(
      (indicacion) => acompanamientoDe(indicacion) === 'hito' && sigueVigente(indicacion, ahora)
    );
    // Lo agendado ya no se cuenta: su fecha es la de la cita, que va en el punto anterior.
    const faltan = conFecha
      .map((indicacion) => ({ indicacion, estado: estadoDeHito(indicacion, adherencias, citas) }))
      .filter(({ estado }) => !estado.hecho && !estado.cita)
      .sort(
        (a, b) =>
          (a.estado.limite?.getTime() ?? Number.MAX_SAFE_INTEGER) - (b.estado.limite?.getTime() ?? Number.MAX_SAFE_INTEGER)
      );
    const primero = faltan[0];
    if (primero) {
      const vencido = primero.estado.limite !== null && primero.estado.limite < ahora;
      const plazo = primero.estado.limite
        ? `${vencido ? ', se pasó la fecha: era' : ', hasta'} el ${diaCorto(primero.estado.limite).replace(',', '')}`
        : '';
      const mas = faltan.length > 1 ? `. Y ${faltan.length - 1} más en Mi plan` : '';
      puntos.push({
        clave: 'una-vez',
        tono: vencido ? 'atencion' : 'neutro',
        icono: 'flag',
        texto: `${String(primero.indicacion.texto ?? '')}${plazo}${mas}`,
      });
    } else if (conFecha.length > 0) {
      puntos.push({ clave: 'una-vez', tono: 'listo', icono: 'checkmark', texto: 'Nada pendiente por agendar ni por hacer' });
    }
  } else {
    puntos.push({ clave: 'plan', tono: 'neutro', icono: 'document-text', texto: 'Tu plan aparece aquí después de la consulta' });
  }

  return puntos;
}

/**
 * El saludo y el resumen: lo primero que se ve al abrir la app. Es el único bloque en
 * el color de marca —el resto de la pantalla es blanco sobre gris—, porque es lo que
 * responde «¿cómo voy?» antes de bajar al detalle.
 */
function Resumen({
  nombre,
  tratamiento,
  tomas,
  proximaCita,
  ahora,
}: {
  nombre: string;
  tratamiento: Tratamiento;
  tomas: Toma[];
  proximaCita: Tratamiento['citas'][number] | undefined;
  ahora: Date;
}) {
  const c = useColores();
  const puntos = puntosDelResumen(tratamiento, tomas, proximaCita, ahora);
  const colores: Record<Tono, [string, string]> = {
    atencion: [c.coralClaro, c.coral],
    listo: [c.verdeVivo, c.sobreVerdeVivo],
    neutro: [c.papelAlto, c.primario],
  };

  return (
    <View
      accessibilityRole="summary"
      style={{ backgroundColor: c.primario, borderRadius: 20, padding: S.xl, gap: S.l }}
    >
      <View style={{ gap: 2 }}>
        <Text accessibilityRole="header" style={{ color: c.sobrePrimario, fontSize: 30, lineHeight: 36, fontFamily: F.negrita }}>
          Hola, {nombre}
        </Text>
        <Text style={{ color: c.sobrePrimario, opacity: 0.9, fontSize: T.texto, fontFamily: F.regular }}>
          {capitalizar(
            ahora.toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'America/Bogota' })
          )}
        </Text>
      </View>

      <View style={{ gap: S.m }}>
        {puntos.map((punto) => {
          const [fondo, tinta] = colores[punto.tono];
          return (
            <View key={punto.clave} style={{ flexDirection: 'row', alignItems: 'center', gap: S.m }}>
              <View
                style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: fondo, alignItems: 'center', justifyContent: 'center' }}
              >
                <Ionicons name={punto.icono} size={16} color={tinta} accessibilityElementsHidden importantForAccessibility="no" />
              </View>
              <Text style={{ flex: 1, color: c.sobrePrimario, fontSize: T.texto, lineHeight: 22, fontFamily: punto.tono === 'atencion' ? F.negrita : F.regular }}>
                {punto.texto}
              </Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const DIA = 24 * 60 * 60 * 1000;

function claveDeDia(momento: Date): string {
  return momento.toLocaleDateString('es-CO', { timeZone: 'America/Bogota', year: 'numeric', month: '2-digit', day: '2-digit' });
}

/** La hora con espacios que no se cortan: en el resumen, «7:00 p. m.» partía «p. m.» a la línea siguiente. */
function horaSinCorte(momento: Date): string {
  return horaDe(momento).replace(/\s/g, '\u00a0');
}

function mismoDia(a: Date, b: Date): boolean {
  return claveDeDia(a) === claveDeDia(b);
}

function diaCorto(momento: Date): string {
  return momento.toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'America/Bogota' });
}

/** «hoy a las 5:11 p. m.», «mañana a las…» o «el martes 10 de noviembre a las…». */
function cuandoEs(momento: Date | null, ahora: Date): string {
  if (!momento) return 'por confirmar';
  const hora = `a las ${horaSinCorte(momento)}`;
  if (mismoDia(momento, ahora)) return `hoy ${hora}`;
  if (mismoDia(momento, new Date(ahora.getTime() + DIA))) return `mañana ${hora}`;
  return `el ${diaCorto(momento).replace(',', '')} ${hora}`;
}

// ------------------------------------------------------------------- el horario

type Paso =
  | { tipo: 'grupo'; hora: string; momento: Date; tomas: Toma[] }
  | { tipo: 'ahora' };

/**
 * Agrupa por la hora tal como se lee y mete la marca de «Ahora» antes del primer grupo
 * que todavía no llega. Si todo ya pasó, la marca va al final; si nada ha pasado, al
 * principio.
 */
function pasosDelDia(tomas: Toma[], ahora: Date): Paso[] {
  const grupos: Extract<Paso, { tipo: 'grupo' }>[] = [];
  for (const toma of [...tomas].sort((a, b) => a.momento.getTime() - b.momento.getTime())) {
    const hora = horaDe(toma.momento);
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && ultimo.hora === hora) ultimo.tomas.push(toma);
    else grupos.push({ tipo: 'grupo', hora, momento: toma.momento, tomas: [toma] });
  }
  const indice = grupos.findIndex((grupo) => grupo.momento.getTime() > ahora.getTime());
  const pasos: Paso[] = [...grupos];
  pasos.splice(indice === -1 ? pasos.length : indice, 0, { tipo: 'ahora' });
  return pasos;
}

/** Ancho de la columna de horas: «10:00 p. m.» entra en una línea. */
const COLUMNA = 84;
const RIEL = 20;

/**
 * Qué toma del día es cada una, por indicación: «la 2 de 3 de hoy».
 *
 * Junto a la frecuencia que escribió el profesional, porque las dos dicen cosas
 * distintas: «cada 8 horas» es la regla; «la 2 de 3» es dónde va la persona en ella.
 * Una versión anterior de esta pantalla quitó la frecuencia confiando en que el
 * horario ya mostraba las repeticiones, pero eso obligaba a contar puntos para saber
 * cuántas veces tocaba, justo en el momento de marcar.
 */
function cuentaDelDia(tomas: Toma[]): Map<string, { n: number; total: number }> {
  const porIndicacion = new Map<string, Toma[]>();
  for (const toma of tomas) {
    const id = idDe(toma.indicacion);
    porIndicacion.set(id, [...(porIndicacion.get(id) ?? []), toma]);
  }
  const cuenta = new Map<string, { n: number; total: number }>();
  for (const grupo of porIndicacion.values()) {
    const ordenadas = [...grupo].sort((a, b) => a.momento.getTime() - b.momento.getTime());
    ordenadas.forEach((toma, indice) => cuenta.set(toma.clave, { n: indice + 1, total: ordenadas.length }));
  }
  return cuenta;
}

function detalleDeToma(toma: Toma, cuenta: Map<string, { n: number; total: number }>): string {
  const lugar = cuenta.get(toma.clave);
  const deHoy = !lugar ? '' : lugar.total === 1 ? 'la única de hoy' : `la ${lugar.n} de ${lugar.total} de hoy`;
  const frecuencia = toma.indicacion.frecuencia ? String(toma.indicacion.frecuencia) : '';
  return capitalizar([frecuencia, deHoy].filter(Boolean).join(', '));
}

function Horario({ tomas, ahora, reportar }: { tomas: Toma[]; ahora: Date; reportar: PropsDeHoy['reportar'] }) {
  const c = useColores();
  const pasos = pasosDelDia(tomas, ahora);
  const cuenta = cuentaDelDia(tomas);

  return (
    <View>
      {pasos.map((paso, indice) => {
        const ultimo = indice === pasos.length - 1;
        if (paso.tipo === 'ahora') {
          return (
            <View key="ahora" style={{ flexDirection: 'row', alignItems: 'center', minHeight: 44, marginBottom: ultimo ? 0 : S.s }}>
              <View style={{ width: COLUMNA }}>
                <Text style={{ color: c.primario, fontSize: T.fino, fontFamily: F.negrita }}>Ahora</Text>
                <Text style={{ color: c.primario, fontSize: T.pie, fontFamily: F.regular }}>{horaDe(ahora)}</Text>
              </View>
              <View style={{ width: RIEL, alignItems: 'center', alignSelf: 'stretch', justifyContent: 'center' }}>
                <Riel c={c} arriba={indice > 0} abajo={!ultimo} />
                <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: c.primario }} />
              </View>
              <View style={{ flex: 1, height: 2, backgroundColor: c.primario, borderRadius: 1, marginLeft: S.xs }} />
            </View>
          );
        }

        const toca = paso.tomas.some((toma) => sePuedeResponder(toma, ahora));
        const hecho = paso.tomas.every((toma) => toma.estado === 'cumplida' || toma.estado === 'no_cumplida');
        return (
          <View key={paso.hora} style={{ flexDirection: 'row' }}>
            <Text
              numberOfLines={1}
              style={{
                width: COLUMNA,
                paddingTop: 1,
                color: toca ? c.tinta : c.tintaSuave,
                fontSize: T.fino,
                fontFamily: toca ? F.negrita : F.regular,
              }}
            >
              {paso.hora}
            </Text>
            <View style={{ width: RIEL, alignItems: 'center' }}>
              <Riel c={c} arriba={indice > 0} abajo={!ultimo} />
              <Punto c={c} toca={toca} hecho={hecho} />
            </View>
            <View style={{ flex: 1, gap: S.m, paddingLeft: S.s, paddingBottom: ultimo ? 0 : S.l }}>
              {paso.tomas.map((toma) => (
                <TomaDelHorario
                  key={toma.clave}
                  toma={toma}
                  detalle={detalleDeToma(toma, cuenta)}
                  ahora={ahora}
                  reportar={reportar}
                />
              ))}
            </View>
          </View>
        );
      })}
    </View>
  );
}

/** La línea que une las horas. Se dibuja por tramos para no salir por arriba del primero ni por debajo del último. */
function Riel({ c, arriba, abajo }: { c: Colores; arriba: boolean; abajo: boolean }) {
  return (
    <>
      {arriba ? <View style={{ position: 'absolute', top: 0, height: 10, width: 2, backgroundColor: c.borde }} /> : null}
      {abajo ? <View style={{ position: 'absolute', top: 10, bottom: 0, width: 2, backgroundColor: c.borde }} /> : null}
    </>
  );
}

function Punto({ c, toca, hecho }: { c: Colores; toca: boolean; hecho: boolean }) {
  // Sólo rebota si se completó con la pantalla abierta: al abrir la app con tomas ya
  // respondidas, que todas rebotaran a la vez sería una coreografía de carga.
  const yaEstabaHecho = useRef(hecho).current;
  if (hecho) {
    const marca = (
      <View style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: c.verde, alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name="checkmark" size={11} color={c.papelAlto} accessibilityElementsHidden importantForAccessibility="no" />
      </View>
    );
    return <View style={{ marginTop: 2 }}>{yaEstabaHecho ? marca : <Rebote>{marca}</Rebote>}</View>;
  }
  return (
    <View
      style={{
        marginTop: 4,
        width: 12,
        height: 12,
        borderRadius: 6,
        backgroundColor: toca ? c.coral : c.papelAlto,
        borderWidth: 2,
        borderColor: toca ? c.coral : c.borde,
      }}
    />
  );
}

/** Una toma dentro de su hora: el texto, y según su estado, botones, una marca o nada. */
function TomaDelHorario({
  toma,
  detalle,
  ahora,
  reportar,
}: {
  toma: Toma;
  detalle: string;
  ahora: Date;
  reportar: PropsDeHoy['reportar'];
}) {
  const c = useColores();
  const e = estilosDe(c);
  const texto = String(toma.indicacion.texto ?? '');
  const respondida = toma.estado === 'cumplida' || toma.estado === 'no_cumplida';
  const yaEstabaRespondida = useRef(respondida).current;

  if (respondida) {
    const etiqueta =
      toma.estado === 'cumplida' ? <Etiqueta tono="verde" texto="Lo hiciste" /> : <Etiqueta tono="ambar" texto="No se pudo" />;
    return (
      <View style={{ gap: S.xs, alignItems: 'flex-start' }}>
        <View style={{ gap: 2 }}>
          <Text style={[e.texto, { color: c.tintaSuave }]}>{texto}</Text>
          {detalle ? <Text style={e.pie}>{detalle}</Text> : null}
        </View>
        {yaEstabaRespondida ? etiqueta : <Aparece clave={toma.estado} desde={0.9}>{etiqueta}</Aparece>}
      </View>
    );
  }
  if (!sePuedeResponder(toma, ahora)) {
    return (
      <View style={{ gap: 2 }}>
        <Text style={[e.texto, { color: c.tintaSuave }]}>{texto}</Text>
        {detalle ? <Text style={e.pie}>{detalle}</Text> : null}
      </View>
    );
  }
  return <Responder toma={toma} texto={texto} detalle={detalle} reportar={reportar} />;
}

function Responder({
  toma,
  texto,
  detalle,
  reportar,
}: {
  toma: Toma;
  texto: string;
  detalle: string;
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
      await reportar({ indicacion: toma.indicacion, cumplida, nota: conNota, programadoPara: toma.momento });
    } catch {
      // Se queda en pantalla para reintentar: un «sí» perdido en silencio se leería
      // después como una toma que no se hizo.
      setFallo('No se pudo guardar. Revisa tu conexión y vuelve a intentar.');
      setOcupado(false);
    }
  }

  return (
    <View style={{ gap: S.s }}>
      <View style={{ gap: 2 }}>
        <Text style={e.fuerte}>{texto}</Text>
        {detalle ? <Text style={e.fino}>{detalle}</Text> : null}
      </View>

      {preguntando ? (
        <View style={{ gap: S.s }}>
          <Text nativeID={`nota-${toma.clave}`} style={e.fino}>
            ¿Qué se te dificultó? (opcional)
          </Text>
          <TextInput
            accessibilityLabelledBy={`nota-${toma.clave}`}
            value={nota}
            onChangeText={setNota}
            maxLength={400}
            style={e.campo}
          />
          {/* Con «Cancelar»: antes, quien pulsaba «No pude» por error ya no podía
              volver al «Sí, lo hice». */}
          <View style={{ flexDirection: 'row', gap: S.s }}>
            <View style={{ flex: 1 }}>
              <Boton
                suave
                compacto
                texto="Cancelar"
                desactivado={ocupado}
                alPulsar={() => {
                  setPreguntando(false);
                  setNota('');
                }}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Boton compacto texto="Guardar" desactivado={ocupado} alPulsar={() => void responder(false, nota)} />
            </View>
          </View>
        </View>
      ) : (
        <View style={{ flexDirection: 'row', gap: S.s }}>
          <View style={{ flex: 1 }}>
            <Boton compacto texto="Lo hice" desactivado={ocupado} alPulsar={() => void responder(true)} />
          </View>
          <View style={{ flex: 1 }}>
            <Boton suave compacto texto="No pude" desactivado={ocupado} alPulsar={() => setPreguntando(true)} />
          </View>
        </View>
      )}
      {fallo ? (
        <Text accessibilityRole="alert" style={{ color: c.rojo, fontSize: T.pie, fontFamily: F.regular }}>
          {fallo}
        </Text>
      ) : null}
    </View>
  );
}

// --------------------------------------------------------------- el resto del día

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
    <Seccion titulo="Por hacer">
      {hitos.map((indicacion) => {
        const { limite, cita } = estadoDeHito(indicacion, adherencias, citas);
        const texto = String(indicacion.texto ?? '');
        const vencio = limite !== null && limite < ahora;
        return (
          <View key={idDe(indicacion)} style={{ gap: S.s }}>
            <View style={{ gap: 2 }}>
              <Text style={e.fuerte}>{texto}</Text>
              {cita ? (
                <Text style={e.fino}>Agendado: {fechaHoraDe(cita.inicio)}</Text>
              ) : limite ? (
                <Text style={[e.fino, vencio ? { color: c.coral } : null]}>
                  {vencio ? 'El plazo era hasta el' : 'Antes del'} {fechaHoraDe(limite).split(',').slice(0, 2).join(',')}
                </Text>
              ) : null}
            </View>
            {indicacion.tipo === 'control' && !cita ? (
              <Boton
                compacto
                texto="Agendar con el asistente"
                alPulsar={() => conversar(`Quiero agendar esto de mi plan: ${texto}.`, 'agenda')}
              />
            ) : indicacion.tipo !== 'control' ? (
              <Boton
                suave
                compacto
                texto={indicacion.tipo === 'remision' ? 'Ya fui' : 'Ya lo hice'}
                alPulsar={() => void reportar({ indicacion, cumplida: true })}
              />
            ) : null}
          </View>
        );
      })}
    </Seccion>
  );
}

/**
 * La escala de 0 a 10. El número no se escribe aquí: se le cuenta al agente, que es
 * quien revisa las señales de alarma y lo registra. Ver `fuenteRoble.ts`.
 *
 * En una sola fila, con los extremos rotulados debajo. Con círculos de 44 px no cabían
 * los once y la escala partía en 0–5 y 6–10, que se leía como dos grupos distintos.
 * Cada celda conserva 44 de alto; el ancho lo reparte la fila.
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
      <View accessibilityRole="radiogroup" style={{ gap: S.xs }}>
        <View style={{ flexDirection: 'row', gap: 3 }}>
          {Array.from({ length: 11 }, (_, numero) => {
            const activo = elegido === numero;
            return (
              <Pressable
                key={numero}
                accessibilityRole="radio"
                accessibilityLabel={`${numero} de 10`}
                accessibilityState={{ checked: activo }}
                onPress={() => setElegido(numero)}
                style={({ pressed }) => ({
                  flex: 1,
                  height: 44,
                  borderRadius: 10,
                  alignItems: 'center',
                  justifyContent: 'center',
                  backgroundColor: activo ? c.primario : c.primarioSuave,
                  opacity: pressed ? 0.8 : 1,
                })}
              >
                <Text style={{ color: activo ? c.sobrePrimario : c.primario, fontSize: T.texto, fontFamily: F.negrita }}>
                  {numero}
                </Text>
              </Pressable>
            );
          })}
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text style={e.pie}>Peor que nunca</Text>
          <Text style={e.pie}>Como antes de todo esto</Text>
        </View>
      </View>
      <Boton
        texto={elegido === null ? 'Elige un número' : `Contarle al asistente: ${elegido} de 10`}
        desactivado={elegido === null}
        alPulsar={() => {
          conversar(`Hoy me siento en ${elegido} de 10.`, 'seguimiento');
          setElegido(null);
        }}
      />
      {ultima ? (
        <Text style={e.pie}>
          La última vez dijiste {String(ultima.escala)} de 10, el {fechaHoraDe(ultima.reportado_en)}
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

function capitalizar(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}
