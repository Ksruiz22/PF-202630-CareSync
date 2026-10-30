/**
 * Lo que ve un estudiante.
 *
 * La conversación es lo primero y ocupa el centro: para un paciente, CareSync es
 * el chat. Todo lo demás —la cita, el plan, cómo va— es consecuencia de lo que se
 * habló ahí, y por eso se lee de ROBLE después de cada turno en lugar de
 * mantenerse en el estado de React: el agente escribe en la base, no en el
 * navegador, y la única forma de que la pantalla no mienta es volver a leer.
 *
 * Nada de esto se edita a mano. Un paciente no marca una indicación como cumplida
 * con un botón: se lo dice al agente de seguimiento, que valida y registra. Un
 * formulario habría sido más rápido de construir y habría dejado el sistema sin
 * la trazabilidad que justifica que exista un agente.
 */

import { useCallback, useEffect, useState } from 'react';
import { Conversacion } from '../componentes/Conversacion';
// El filtro del hilo se mudó a `conversaciones.ts` cuando el historial de triajes del
// profesional necesitó el mismo hilo sin filtrar: las dos miradas tienen que cambiar
// juntas si el orquestador cambia cómo marca el autor de una fila.
import { turnosParaLaPersona } from '../conversaciones';
import { Aviso, Cabecera, Cargando, Etiqueta, Nivel, Tarjeta, Vacio } from '../componentes/Piezas';
import {
  IconoAlerta,
  IconoCalendario,
  IconoDocumento,
  IconoEscudo,
  IconoFlechaDerecha,
  IconoMensaje,
  IconoPlan,
  IconoReloj,
  IconoTendencia,
} from '../componentes/Iconos';
import { bandaDeEscala, escalaVisible, fechaHora, hace, soloFecha } from '../formato';
import { mensajeDeError, roble } from '../roble';
import { useSesion } from '../sesion';
import {
  esVerdad,
  idDe,
  type Adherencia,
  type Caso,
  type Cita,
  type Evolucion,
  type FilaConversacion,
  type Indicacion,
  type Plan,
  type Turno,
} from '../tipos';

interface Panorama {
  caso: Caso | null;
  /** El último caso cerrado, sólo cuando no hay ninguno vigente: para decir que se cerró. */
  anterior: Caso | null;
  cita: Cita | null;
  plan: Plan | null;
  indicaciones: Indicacion[];
  evoluciones: Evolucion[];
  adherencias: Adherencia[];
  /** Lo ya conversado en el caso, para que recargar la página no lo borre. */
  previos: Turno[];
}

const VACIO: Panorama = {
  caso: null,
  anterior: null,
  cita: null,
  plan: null,
  indicaciones: [],
  evoluciones: [],
  adherencias: [],
  previos: [],
};

export function Paciente() {
  const { quien, salir } = useSesion();
  const [datos, setDatos] = useState<Panorama>(VACIO);
  const [abiertos, setAbiertos] = useState<Caso[]>([]);
  // Cambia sólo cuando la persona elige otro caso, y entonces el chat se vuelve a
  // montar con el hilo de ese caso. Cuando es el agente el que abre un caso nuevo para
  // un problema distinto, el chat ya sigue en él por su cuenta —toma el `caso` de la
  // respuesta— y reiniciarlo le borraría a la persona lo que acaba de leer.
  const [montaje, setMontaje] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');

  const userId = quien?.userId ?? '';

  const cargar = useCallback(
    async (preferido?: string, remontarChat = false) => {
      if (!userId) return;
      try {
        const { abiertos: vivos, anterior } = await casosDe(userId);
        const caso = vivos.find((fila) => idDe(fila) === preferido) ?? vivos[0] ?? null;
        const panorama = caso ? await alrededorDelCaso(caso) : { ...VACIO, anterior };
        // Juntos y después de leer: si el chat se remontara antes de tener el caso
        // nuevo, se montaría con el hilo del anterior y ya no cambiaría.
        setAbiertos(vivos);
        setDatos(panorama);
        if (remontarChat) setMontaje((n) => n + 1);
        setError('');
      } catch (fallo) {
        setError(mensajeDeError(fallo));
      } finally {
        setCargando(false);
      }
    },
    [userId]
  );

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const casoId = idDe(datos.caso);
  const nivel = Number(datos.caso?.nivel_urgencia ?? 0);
  const nombre = primerNombre(quien?.nombre);

  return (
    <>
      <div className="aviso-bienestar" role="note">
        <IconoAlerta width={18} height={18} />
        <span>
          <strong>Tu bienestar es lo primero.</strong> Si estás en peligro inmediato,
          llama a la línea de emergencias del campus o al 123.
        </span>
      </div>

      <div className="panel paciente">
        <Cabecera
          antetitulo="Acompañamiento CareSync"
          titulo={nombre ? `Hola, ${nombre}` : 'Hola'}
          subtitulo="Cuéntale al asistente qué te pasa y él te acompaña desde ahí."
        />

        {error && <Aviso tipo="error">{error}</Aviso>}
        {abiertos.length > 1 && (
          <SelectorDeCasos
            casos={abiertos}
            elegido={casoId}
            alElegir={(id) => {
              if (id !== casoId) void cargar(id, true);
            }}
          />
        )}
        {nivel === 1 && (
          <Aviso tipo="urgente">
            Tu caso está marcado como emergencia. Si aún no has recibido ayuda, llama
            ya a la línea de emergencias del campus o al 123.
          </Aviso>
        )}

        <div className="columnas">
          {/* El chat espera a que cargue el caso: el saludo y el caso sobre el que se
              conversa se fijan al montarlo, y montarlo antes hacía que todo paciente
              viera el saludo de «sin caso» aunque estuviera en seguimiento. */}
          {cargando ? (
            <section className="conversacion">
              <Cargando que="Preparando la conversación" />
            </section>
          ) : (
            <Conversacion
              key={montaje}
              {...(casoId ? { casoId } : {})}
              saludo={saludoSegun(datos.caso)}
              previos={datos.previos}
              // El caso de la respuesta, no el que había: si la persona contó un
              // problema distinto, el agente lo siguió en un caso nuevo y el panel
              // tiene que mostrar ese.
              alResponder={(respuesta) => void cargar(respuesta.caso?.id ?? casoId)}
              alVencerSesion={() => void salir()}
            />
          )}

          <aside className="lateral">
            {cargando ? (
              <Cargando que="Buscando tu caso" />
            ) : !datos.caso ? (
              <>
                <Tarjeta titulo="Tu caso" icono={<IconoDocumento />}>
                  <div className="caso-vacio">
                    <span className="icono-vacio">
                      <IconoMensaje width={21} height={21} />
                    </span>
                    {datos.anterior ? (
                      <>
                        <strong>Tu caso anterior quedó cerrado</strong>
                        <p>
                          Tu profesional lo dio por terminado. Si necesitas algo
                          nuevo, cuéntaselo al asistente y se abre otro caso.
                        </p>
                      </>
                    ) : (
                      <>
                        <strong>Todavía no hay caso</strong>
                        <p>
                          Cuando le escribas al asistente se abre un caso y aquí verás
                          en qué va.
                        </p>
                      </>
                    )}
                    <button
                      type="button"
                      className="boton-texto"
                      onClick={() => document.getElementById('mensaje')?.focus()}
                    >
                      Comenzar conversación <IconoFlechaDerecha />
                    </button>
                  </div>
                </Tarjeta>
                <TarjetaDePrivacidad />
              </>
            ) : (
              <>
                <Tarjeta
                  titulo="Tu caso"
                  icono={<IconoDocumento />}
                  extra={<Etiqueta estado={datos.caso.estado} />}
                >
                  <dl className="datos">
                    <dt>Urgencia</dt>
                    <dd>
                      <Nivel valor={datos.caso.nivel_urgencia} />
                    </dd>
                    <dt>Centro</dt>
                    <dd>{nombreDeCentro(datos.caso.centro)}</dd>
                    <dt>Abierto</dt>
                    <dd>{hace(datos.caso.creado_en)}</dd>
                  </dl>
                  {datos.caso.resumen_triaje && (
                    <p className="resumen">{String(datos.caso.resumen_triaje)}</p>
                  )}
                </Tarjeta>

                <Tarjeta titulo="Tu cita" icono={<IconoCalendario />}>
                  {datos.cita ? (
                    <>
                      <p className="destacado">{fechaHora(datos.cita.inicio)}</p>
                      <p>
                        {String(datos.cita.profesional_nombre ?? 'Profesional por asignar')} ·{' '}
                        {nombreDeCentro(datos.cita.centro)}
                      </p>
                      <Etiqueta estado={datos.cita.estado} />
                      {datos.cita.estado === 'confirmada' && !yaPaso(datos.cita) && (
                        <p className="fino">
                          Si no puedes ir, escríbelo en la conversación: ahí mismo la
                          cancelas o la cambias de hora.
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="fila-vacia">
                      <IconoReloj width={18} height={18} />
                      <span>Sin cita agendada. Pídele al asistente que te busque un espacio.</span>
                    </p>
                  )}
                </Tarjeta>

                {datos.plan && (
                  <Tarjeta titulo="Tu plan" icono={<IconoPlan />}>
                    <p className="resumen">{String(datos.plan.resumen ?? '')}</p>
                    <p className="fino">
                      {String(datos.plan.profesional_nombre ?? 'Tu profesional')} ·{' '}
                      {soloFecha(datos.plan.creado_en)}
                    </p>
                    {datos.indicaciones.length === 0 ? (
                      <Vacio>Sin indicaciones activas.</Vacio>
                    ) : (
                      <ul className="indicaciones">
                        {datos.indicaciones.map((indicacion) => (
                          <li key={idDe(indicacion)}>
                            <span className="texto">{String(indicacion.texto ?? '')}</span>
                            <span className="fino">
                              {String(indicacion.frecuencia ?? 'sin frecuencia')} ·{' '}
                              {resumenDeAdherencia(datos.adherencias, idDe(indicacion))}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </Tarjeta>
                )}

                {datos.evoluciones.length > 0 && (
                  <Tarjeta titulo="Cómo has ido" icono={<IconoTendencia />}>
                    <ul className="evolucion">
                      {datos.evoluciones.map((fila) => (
                        <li key={idDe(fila)}>
                          <span className={`escala ${bandaDeEscala(fila.escala)}`}>
                            {escalaVisible(fila.escala)}
                          </span>
                          <span className="texto">{String(fila.nota ?? '')}</span>
                          <span className="fino">{hace(fila.reportado_en)}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="fino">
                      De 0 (peor que nunca) a 10 (como antes de todo esto). Lo registra
                      el asistente con lo que tú le cuentas.
                    </p>
                  </Tarjeta>
                )}

                <TarjetaDePrivacidad />
              </>
            )}
          </aside>
        </div>
      </div>
    </>
  );
}

function TarjetaDePrivacidad() {
  return (
    <section className="tarjeta privacidad">
      <IconoEscudo width={18} height={18} />
      <div>
        <strong>Tus datos, bajo cuidado</strong>
        <p>
          Lo que cuentas se usa para orientarte y conectarte con el centro que
          corresponde.
        </p>
      </div>
    </section>
  );
}

/**
 * Los casos abiertos de la persona, el más reciente primero, y el último cerrado si no
 * hay ninguno abierto.
 *
 * `read` de ROBLE sólo filtra por igualdad y no ordena, así que se traen los casos
 * de la persona y se ordenan aquí. Cuando eso deje de caber en una lectura habrá que
 * crear una consulta guardada en ROBLE y llamarla con `executeQuery`; para el número
 * de casos de un estudiante, no hace falta.
 *
 * Puede haber más de un caso abierto desde el 29/10: un problema distinto del que se
 * está atendiendo se tría en un caso aparte, y el anterior sigue su curso. La vista
 * muestra uno a la vez y deja elegir el otro.
 *
 * Un caso cerrado nunca es el vigente. Antes, a falta de uno abierto, se devolvía el
 * último aunque estuviera cerrado, y su id viajaba al chat: el siguiente mensaje
 * seguía escribiendo en un caso que el profesional ya había cerrado, en lugar de
 * abrir uno nuevo con su triaje.
 */
async function casosDe(userId: string): Promise<{ abiertos: Caso[]; anterior: Caso | null }> {
  const casos = (await roble.read('casos', { paciente_user_id: userId })) as Caso[];
  const abiertos = casos.filter((caso) => caso.estado !== 'cerrado').sort(porFechaDescendente);
  const cerrados = casos.filter((caso) => caso.estado === 'cerrado');
  return {
    abiertos,
    anterior: abiertos.length ? null : ([...cerrados].sort(porFechaDescendente)[0] ?? null),
  };
}

/** Un botón por caso abierto. Sólo aparece cuando hay más de uno. */
function SelectorDeCasos({
  casos,
  elegido,
  alElegir,
}: {
  casos: Caso[];
  elegido: string;
  alElegir: (casoId: string) => void;
}) {
  return (
    <nav className="selector-casos" aria-label="Tus casos abiertos">
      <span className="fino">Tienes {casos.length} casos abiertos:</span>
      {casos.map((caso) => {
        const id = idDe(caso);
        const activo = id === elegido;
        return (
          <button
            key={id}
            type="button"
            className={`ficha-caso ${activo ? 'activa' : ''}`}
            aria-pressed={activo}
            onClick={() => alElegir(id)}
          >
            <span className="texto">{motivoCorto(caso)}</span>
            <Etiqueta estado={caso.estado} />
          </button>
        );
      })}
    </nav>
  );
}

function motivoCorto(caso: Caso): string {
  const motivo = String(caso.motivo ?? '').trim();
  if (!motivo) return 'Caso sin motivo';
  return motivo.length > 40 ? `${motivo.slice(0, 40).trimEnd()}…` : motivo;
}

async function alrededorDelCaso(caso: Caso): Promise<Panorama> {
  const casoId = idDe(caso);

  // En paralelo porque son seis lecturas independientes y en serie se notan.
  // `catch` por tabla: que no haya plan todavía no puede dejar la pantalla en
  // blanco, y un permiso faltante en una tabla no debe tumbar las otras cinco.
  const [citas, planes, indicaciones, evoluciones, adherencias, hilo] = await Promise.all([
    leer<Cita>('citas', { caso_id: casoId }),
    leer<Plan>('planes', { caso_id: casoId }),
    leer<Indicacion>('indicaciones', { caso_id: casoId }),
    leer<Evolucion>('evolucion', { caso_id: casoId }),
    leer<Adherencia>('adherencia', { caso_id: casoId }),
    leer<FilaConversacion>('conversaciones', { caso_id: casoId }),
  ]);

  return {
    caso,
    anterior: null,
    cita: citaParaMostrar(citas),
    plan: [...planes].sort(porFechaDescendente)[0] ?? null,
    indicaciones: indicaciones.filter((fila) => esVerdad(fila.activa)),
    evoluciones: [...evoluciones].sort(porReporteDescendente).slice(0, 5),
    adherencias,
    previos: turnosParaLaPersona(hilo),
  };
}

async function leer<T>(tabla: string, filtros: Record<string, unknown>): Promise<T[]> {
  try {
    return (await roble.read(tabla, filtros)) as T[];
  } catch (error) {
    console.warn(`No se pudo leer ${tabla}`, error);
    return [];
  }
}

function porFechaDescendente(a: { creado_en?: unknown }, b: { creado_en?: unknown }): number {
  return String(b.creado_en ?? '').localeCompare(String(a.creado_en ?? ''));
}

function porReporteDescendente(a: { reportado_en?: unknown }, b: { reportado_en?: unknown }): number {
  return String(b.reportado_en ?? '').localeCompare(String(a.reportado_en ?? ''));
}

function porInicioAscendente(a: { inicio?: unknown }, b: { inicio?: unknown }): number {
  return String(a.inicio ?? '').localeCompare(String(b.inicio ?? ''));
}

function yaPaso(cita: Cita): boolean {
  const inicio = new Date(String(cita.inicio ?? '')).getTime();
  return Number.isFinite(inicio) && inicio < Date.now();
}

/**
 * La cita que se le muestra a la persona: la próxima confirmada, y si no hay, la última.
 *
 * Antes era la primera no cancelada por fecha, que con una cita pasada a la que no
 * llegó y otra nueva pedida después mostraba la vieja.
 */
function citaParaMostrar(citas: Cita[]): Cita | null {
  const vigentes = citas.filter((cita) => cita.estado !== 'cancelada').sort(porInicioAscendente);
  const proxima = vigentes.find((cita) => cita.estado === 'confirmada' && !yaPaso(cita));
  return proxima ?? vigentes[vigentes.length - 1] ?? null;
}

function resumenDeAdherencia(filas: Adherencia[], indicacionId: string): string {
  const propias = filas.filter((fila) => String(fila.indicacion_id ?? '') === indicacionId);
  if (propias.length === 0) return 'sin reportes';
  const cumplidas = propias.filter((fila) => esVerdad(fila.cumplida)).length;
  return `${cumplidas} de ${propias.length} cumplidas`;
}

function saludoSegun(caso: Caso | null): string {
  if (!caso) {
    return (
      'Hola. Soy el asistente de CareSync. Cuéntame qué te pasa y desde cuándo, ' +
      'con tus palabras. No soy personal de salud: te oriento y te conecto con quien sí lo es.'
    );
  }
  if (caso.estado === 'en_seguimiento') {
    return '¿Cómo has estado desde la consulta? Cuéntame cómo vas con lo que te indicaron.';
  }
  if (caso.estado === 'canalizado') {
    return 'Tu caso ya está canalizado. Si quieres, buscamos un espacio para tu cita.';
  }
  if (caso.estado === 'agendado') {
    return 'Tu cita ya está agendada. Si algo cambió o tienes dudas, dime.';
  }
  return 'Sigo aquí. Cuéntame en qué vamos.';
}

/** El primer nombre, o cadena vacía si no hay: el título dice entonces sólo «Hola». */
function primerNombre(nombre: string | undefined): string {
  const limpio = String(nombre ?? '').trim();
  if (!limpio) return '';
  const primero = limpio.split(/\s+/)[0] ?? limpio;
  // Si el «nombre» es en realidad el correo —pasa cuando no hay fila en
  // `perfiles`—, se corta en la arroba para no saludar a «juan.perez@uninorte».
  return primero.split('@')[0] ?? primero;
}

function nombreDeCentro(centro: unknown): string {
  const clave = String(centro ?? '').toUpperCase();
  if (clave === 'CMU') return 'Centro Médico Universitario';
  if (clave === 'CAE') return 'Centro de Acompañamiento Estudiantil';
  return 'por definir';
}
