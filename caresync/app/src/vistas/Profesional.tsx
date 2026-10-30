/**
 * Lo que ve un profesional del CMU o del CAE.
 *
 * **Hasta ahora el profesional no veía la conversación**, y era deliberado: en la
 * consulta se atiende con el resumen del triaje, no con la transcripción. Eso sigue
 * siendo cierto en la pestaña de agenda, que no la muestra. Lo que cambió es que hay
 * dos trabajos más que sí la necesitan, y cada uno tiene su pestaña:
 *
 * - **Historial de triajes**: revisar cómo quedó clasificado un caso exige leer de
 *   dónde salió esa clasificación. El resumen lo escribió el agente, y juzgar el
 *   resumen con el resumen no es revisar nada. Por eso abrir un hilo **queda
 *   registrado en la bitácora del caso** (`eventos`, tipo `hilo_consultado`): el
 *   acceso existe, y quién lo usó se puede auditar. Esa fila es el precio de la
 *   pestaña, no un adorno.
 * - **Simulador de triaje**: ponerse en los zapatos de quien consulta para evaluar al
 *   modelo, sin abrir un caso, sin agendar, sin correos y sin disparar la alarma de
 *   urgencias. Lo real de esa conversación es sólo el modelo.
 *
 * Lo que no cambió: **el plan lo hace el profesional, no el modelo**. Ésta es la
 * única pantalla del prototipo donde una persona escribe datos clínicos, y es a
 * propósito. El agente de seguimiento acompaña sobre un plan que ya existe; no lo
 * inventa. Si esta pantalla no existiera, el agente no tendría de dónde sacar las
 * indicaciones y la tentación sería dejar que se las imaginara.
 *
 * El plan se puede dictar y dejar que el asistente lo ordene (`EditorDelPlan`), pero
 * eso no cambia quién lo escribe: la propuesta vuelve a esta pantalla, el profesional
 * la corrige y sólo lo que confirma se guarda, con su token, en `registrarPlan`.
 *
 * De cada paciente se ve además su progreso a lo largo del seguimiento (`Progreso`):
 * las alertas de la bitácora, la evolución en el tiempo y la adherencia a cada
 * indicación.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Aviso, Cabecera, Cargando, Etiqueta, Nivel, Tarjeta, Vacio } from '../componentes/Piezas';
import { IconoCalendario, IconoChispas, IconoDocumento } from '../componentes/Iconos';
import { EditorDelPlan, type PlanAGuardar } from '../componentes/EditorDelPlan';
import {
  AdherenciaPorIndicacion,
  Alertas,
  CurvaDeEvolucion,
  esAlerta,
} from '../componentes/Progreso';
import { HistorialDeTriajes } from './HistorialDeTriajes';
import { SimuladorDeTriaje } from './SimuladorDeTriaje';
import { fechaHora, hace, soloFecha } from '../formato';
import { mensajeDeError, roble } from '../roble';
import { useSesion } from '../sesion';
import {
  esVerdad,
  idDe,
  idDeInsercion,
  type Adherencia,
  type Caso,
  type Cita,
  type EventoCaso,
  type Evolucion,
  type Indicacion,
  type Plan,
} from '../tipos';

interface Agenda {
  citas: Cita[];
  casos: Record<string, Caso>;
}

type Pestana = 'agenda' | 'triajes' | 'simulador';

export function Profesional() {
  const { quien } = useSesion();
  const [pestana, setPestana] = useState<Pestana>('agenda');
  const [agenda, setAgenda] = useState<Agenda>({ citas: [], casos: {} });
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');
  const [abierta, setAbierta] = useState('');

  const userId = quien?.userId ?? '';

  const cargar = useCallback(async () => {
    if (!userId) return;
    try {
      setAgenda(await agendaDe(userId));
      setError('');
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setCargando(false);
    }
  }, [userId]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const { proximas, pasadas } = useMemo(() => repartir(agenda.citas), [agenda.citas]);
  const seleccionada = agenda.citas.find((cita) => idDe(cita) === abierta) ?? null;
  const casoAbierto = seleccionada ? agenda.casos[String(seleccionada.caso_id ?? '')] : undefined;

  return (
    <div className="panel profesional">
      <Cabecera
        antetitulo="Panel del profesional"
        titulo={quien?.nombre}
        subtitulo={subtituloDe(pestana, {
          centro: quien?.centro ?? 'tu centro',
          porAtender: proximas.length,
        })}
      />

      {/*
        Tres pestañas y no tres pantallas: lo que el profesional hace aquí es un solo
        trabajo visto de tres maneras —atender, revisar cómo se clasificó y probar al
        modelo—, y repartirlo por rol en `App.tsx` habría significado inventar un rol
        que no existe. La agenda sigue cargándose aunque se mire otra pestaña: la
        cuenta de «por atender» está en la cabecera, que es común a las tres, y
        volverla a leer en cada cambio de pestaña gasta cuota de ROBLE sin añadir nada.
      */}
      <div className="pestanas" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={pestana === 'agenda'}
          onClick={() => setPestana('agenda')}
        >
          <IconoCalendario width={17} height={17} /> Agenda
          {!cargando && proximas.length > 0 && <span className="cuenta">{proximas.length}</span>}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={pestana === 'triajes'}
          onClick={() => setPestana('triajes')}
        >
          <IconoDocumento width={17} height={17} /> Historial de triajes
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={pestana === 'simulador'}
          onClick={() => setPestana('simulador')}
        >
          <IconoChispas width={17} height={17} /> Simulador
        </button>
      </div>

      {pestana === 'triajes' && <HistorialDeTriajes />}
      {pestana === 'simulador' && <SimuladorDeTriaje />}

      {/*
        La agenda se esconde con `hidden` en vez de desmontarse: el plan a medio
        escribir en el formulario de la consulta se perdería al mirar un triaje y
        volver, y eso es justo lo que un profesional hace mientras atiende. Que
        `hidden` gane a `display: flex` lo garantiza la regla `[hidden]` del reset en
        `estilos.css`; sin ella la clase del contenedor lo anula y la pestaña se
        pintaría dos veces.
      */}
      <div className="pila" hidden={pestana !== 'agenda'}>
        {error && <Aviso tipo="error">{error}</Aviso>}

        <div className="columnas">
          <section className="lista">
            <Tarjeta titulo="Por atender" icono={<IconoCalendario />}>
              {cargando ? (
                <Cargando que="Cargando tu agenda" />
              ) : proximas.length === 0 ? (
                <Vacio>No tienes citas pendientes.</Vacio>
              ) : (
                <ul className="citas">
                  {proximas.map((cita) => (
                    <FilaDeCita
                      key={idDe(cita)}
                      cita={cita}
                      caso={agenda.casos[String(cita.caso_id ?? '')]}
                      activa={idDe(cita) === abierta}
                      alAbrir={() => setAbierta(idDe(cita))}
                    />
                  ))}
                </ul>
              )}
            </Tarjeta>

            {pasadas.length > 0 && (
              <Tarjeta titulo="Ya pasaron">
                <ul className="citas">
                  {pasadas.map((cita) => (
                    <FilaDeCita
                      key={idDe(cita)}
                      cita={cita}
                      caso={agenda.casos[String(cita.caso_id ?? '')]}
                      activa={idDe(cita) === abierta}
                      alAbrir={() => setAbierta(idDe(cita))}
                    />
                  ))}
                </ul>
              </Tarjeta>
            )}
          </section>

          <section className="detalle">
            {!seleccionada || !casoAbierto ? (
              <Tarjeta titulo="Consulta">
                <Vacio>Elige una cita para ver el caso y registrar el plan.</Vacio>
              </Tarjeta>
            ) : (
              <Consulta
                key={idDe(seleccionada)}
                cita={seleccionada}
                caso={casoAbierto}
                autor={{ userId, nombre: quien?.nombre ?? '' }}
                alGuardar={() => void cargar()}
              />
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

/**
 * Qué dice la cabecera en cada pestaña.
 *
 * La cuenta de citas por atender sólo tiene sentido en la agenda: dejarla fija
 * mientras se revisa un triaje de hace un mes hacía leer la pantalla como si esa
 * conversación fuera una de las citas pendientes.
 */
function subtituloDe(
  pestana: Pestana,
  datos: { centro: string; porAtender: number }
): ReactNode {
  if (pestana === 'triajes') {
    return `Los casos ya triados de ${datos.centro}, con la conversación de la que salió cada clasificación.`;
  }
  if (pestana === 'simulador') {
    return 'Conversa con el agente de triaje como si fueras quien consulta, para ver cómo clasifica.';
  }
  return (
    <>
      Tu agenda en {datos.centro}. {datos.porAtender} cita
      {datos.porAtender === 1 ? '' : 's'} por atender.
    </>
  );
}

function FilaDeCita({
  cita,
  caso,
  activa,
  alAbrir,
}: {
  cita: Cita;
  caso: Caso | undefined;
  activa: boolean;
  alAbrir: () => void;
}) {
  return (
    <li>
      <button type="button" className={`fila ${activa ? 'activa' : ''}`} onClick={alAbrir}>
        <span className="cuando">{fechaHora(cita.inicio)}</span>
        <span className="quien">{String(caso?.paciente_nombre ?? 'Paciente')}</span>
        <span className="marcas">
          <Nivel valor={caso?.nivel_urgencia} />
          <Etiqueta estado={cita.estado} />
        </span>
      </button>
    </li>
  );
}

// ------------------------------------------------------------------- la consulta

interface Contexto {
  plan: Plan | null;
  indicaciones: Indicacion[];
  evoluciones: Evolucion[];
  adherencias: Adherencia[];
  eventos: EventoCaso[];
}

function Consulta({
  cita,
  caso,
  autor,
  alGuardar,
}: {
  cita: Cita;
  caso: Caso;
  autor: { userId: string; nombre: string };
  alGuardar: () => void;
}) {
  const casoId = idDe(caso);
  const cerrado = caso.estado === 'cerrado';
  const [contexto, setContexto] = useState<Contexto | null>(null);
  const [error, setError] = useState('');

  const cargar = useCallback(async () => {
    setContexto(await contextoDelCaso(casoId));
  }, [casoId]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  // Los errores de guardar los muestra el editor, junto al botón que los causó.
  async function guardarPlan(plan: PlanAGuardar) {
    await registrarPlan({ casoId, citaId: idDe(cita), autor, ...plan });
    await cargar();
    alGuardar();
  }

  return (
    <>
      <Tarjeta
        titulo={String(caso.paciente_nombre ?? 'Paciente')}
        extra={<Etiqueta estado={caso.estado} />}
      >
        <dl className="datos">
          <dt>Cita</dt>
          <dd>{fechaHora(cita.inicio)}</dd>
          <dt>Urgencia</dt>
          <dd>
            <Nivel valor={caso.nivel_urgencia} />
          </dd>
          <dt>Caso abierto</dt>
          <dd>{hace(caso.creado_en)}</dd>
        </dl>
        <h3>Resumen del triaje</h3>
        <p className="resumen">
          {String(caso.resumen_triaje ?? caso.motivo ?? 'Sin resumen registrado.')}
        </p>
        <p className="fino">
          Lo escribió el agente de triaje a partir de la conversación. La
          conversación completa no se muestra aquí.
        </p>
      </Tarjeta>

      {contexto === null ? (
        <Cargando que="Cargando el historial" />
      ) : (
        <>
          {error && <Aviso tipo="error">{error}</Aviso>}

          {/*
            El progreso sólo aparece cuando hay de qué: en la primera consulta no hay
            plan ni reportes, y dos tarjetas vacías encima del formulario esconden lo
            único que hay que hacer ahí, que es escribir el plan.
          */}
          {(contexto.plan || contexto.evoluciones.length > 0 || contexto.eventos.some(esAlerta)) && (
            <>
              <Alertas eventos={contexto.eventos} />
              <CurvaDeEvolucion filas={contexto.evoluciones} />
            </>
          )}

          {contexto.plan && (
            <Tarjeta titulo="Plan vigente">
              <p className="resumen">{String(contexto.plan.resumen ?? '')}</p>
              <p className="fino">
                {String(contexto.plan.profesional_nombre ?? '')} ·{' '}
                {soloFecha(contexto.plan.creado_en)}
              </p>
              <AdherenciaPorIndicacion
                indicaciones={contexto.indicaciones}
                adherencias={contexto.adherencias}
                alDesactivar={(indicacionId) => {
                  void desactivar(indicacionId)
                    .then(cargar)
                    .catch((fallo) => setError(mensajeDeError(fallo)));
                }}
              />
              <p className="fino">
                Al desactivar una indicación se detienen sus recordatorios. Los ya
                enviados quedan en la bitácora.
              </p>
            </Tarjeta>
          )}

          {!cerrado && cita.estado === 'confirmada' && yaEmpezo(cita) && !contexto.plan && (
            <Inasistencia cita={cita} caso={caso} autor={autor} alMarcar={alGuardar} />
          )}

          {cerrado ? (
            <Tarjeta titulo="Caso cerrado">
              <p>
                Este caso ya no está en seguimiento: no salen recordatorios y, si la
                persona vuelve a escribir, el asistente le abre un caso nuevo desde el
                triaje.
              </p>
            </Tarjeta>
          ) : (
            <EditorDelPlan hayPlan={!!contexto.plan} alGuardar={guardarPlan} />
          )}

          {!cerrado && (
            <CierreDelCaso casoId={casoId} autor={autor} alCerrar={alGuardar} />
          )}
        </>
      )}
    </>
  );
}

/**
 * La persona no llegó a la cita.
 *
 * Antes no había cómo decirlo: la cita se quedaba `confirmada` para siempre y el caso
 * en `agendado`, y si la persona volvía a escribir el agente de agenda no le podía dar
 * otra. Marcarla deja el dato —cuántas citas se pierden es una de las cosas que el
 * centro querrá saber— y devuelve el caso a agenda, que le ofrece otra cita la próxima
 * vez que escriba.
 *
 * Sólo aparece cuando la hora de la cita ya llegó y no hay plan: después de escribir
 * el plan, la persona evidentemente sí vino.
 */
function Inasistencia({
  cita,
  caso,
  autor,
  alMarcar,
}: {
  cita: Cita;
  caso: Caso;
  autor: { userId: string; nombre: string };
  alMarcar: () => void;
}) {
  const [confirmando, setConfirmando] = useState(false);
  const [marcando, setMarcando] = useState(false);
  const [error, setError] = useState('');

  async function marcar() {
    setMarcando(true);
    setError('');
    try {
      await marcarInasistencia(cita, caso, autor);
      alMarcar();
    } catch (fallo) {
      setError(mensajeDeError(fallo));
      setMarcando(false);
    }
  }

  return (
    <Tarjeta titulo="¿No llegó a la cita?">
      <p className="fino">
        Márcalo si la persona no vino. El caso vuelve a agenda y el asistente le ofrece
        otra cita cuando vuelva a escribir.
      </p>
      {confirmando ? (
        <div className="botonera">
          <button type="button" className="principal" disabled={marcando} onClick={() => void marcar()}>
            {marcando ? 'Marcando…' : 'Sí, no asistió'}
          </button>
          <button
            type="button"
            className="enlace"
            disabled={marcando}
            onClick={() => setConfirmando(false)}
          >
            Cancelar
          </button>
        </div>
      ) : (
        <button type="button" className="secundario" onClick={() => setConfirmando(true)}>
          Marcar que no asistió
        </button>
      )}
      {error && <Aviso tipo="error">{error}</Aviso>}
    </Tarjeta>
  );
}

/**
 * Cerrar el caso: la última escritura del ciclo de vida, y la única que faltaba.
 *
 * Hasta ahora ninguna ruta del sistema escribía `cerrado`, así que todo caso se
 * quedaba en seguimiento para siempre: seguían saliendo recordatorios y, si la
 * persona volvía a escribir meses después por otra cosa, el agente de seguimiento le
 * preguntaba por un plan viejo en vez de hacerle el triaje.
 *
 * Lo cierra el profesional y no el agente por lo mismo que el plan lo escribe él: dar
 * a alguien de alta es una decisión clínica. Por eso pide confirmación —no hay botón
 * para deshacerlo— y deja rastro en la bitácora con quién lo cerró.
 */
function CierreDelCaso({
  casoId,
  autor,
  alCerrar,
}: {
  casoId: string;
  autor: { userId: string; nombre: string };
  alCerrar: () => void;
}) {
  const [confirmando, setConfirmando] = useState(false);
  const [cerrando, setCerrando] = useState(false);
  const [error, setError] = useState('');

  async function cerrar() {
    setCerrando(true);
    setError('');
    try {
      await cerrarCaso(casoId, autor);
      alCerrar();
    } catch (fallo) {
      setError(mensajeDeError(fallo));
      setCerrando(false);
    }
  }

  return (
    <Tarjeta titulo="Cerrar el caso">
      <p className="fino">
        Ciérralo cuando la persona ya no necesite acompañamiento. Dejan de salir los
        recordatorios y, si vuelve a escribir, empieza un caso nuevo desde el triaje.
      </p>
      {confirmando ? (
        <div className="botonera">
          <button type="button" className="principal" disabled={cerrando} onClick={() => void cerrar()}>
            {cerrando ? 'Cerrando…' : 'Sí, cerrar el caso'}
          </button>
          <button
            type="button"
            className="enlace"
            disabled={cerrando}
            onClick={() => setConfirmando(false)}
          >
            Cancelar
          </button>
        </div>
      ) : (
        <button type="button" className="secundario" onClick={() => setConfirmando(true)}>
          Cerrar el caso
        </button>
      )}
      {error && <Aviso tipo="error">{error}</Aviso>}
    </Tarjeta>
  );
}

// ------------------------------------------------------------------- datos

/**
 * La agenda del profesional.
 *
 * Las citas se leen por `profesional_user_id` y no por el id de la fila en
 * `profesionales`: así la pantalla funciona sin una segunda lectura para averiguar
 * el propio id, y el filtro coincide con el sujeto autenticado.
 */
async function agendaDe(userId: string): Promise<Agenda> {
  const citas = (await roble.read('citas', { profesional_user_id: userId })) as Cita[];
  const vigentes = citas.filter((cita) => cita.estado !== 'cancelada');

  // Una lectura por caso. `read` sólo filtra por igualdad, así que no hay forma de
  // pedir «los casos de estos veinte ids» en una sola llamada. Con la agenda de un
  // profesional son pocas; si un día son muchas, esto se convierte en una consulta
  // guardada en ROBLE y se llama con `executeQuery`.
  const ids = [...new Set(vigentes.map((cita) => String(cita.caso_id ?? '')).filter(Boolean))];
  const filas = await Promise.all(ids.map((id) => leerCaso(id)));

  const casos: Record<string, Caso> = {};
  for (const caso of filas) {
    if (caso) casos[idDe(caso)] = caso;
  }
  return { citas: vigentes, casos };
}

async function leerCaso(casoId: string): Promise<Caso | null> {
  try {
    const filas = (await roble.read('casos', { _id: casoId })) as Caso[];
    return filas[0] ?? null;
  } catch (error) {
    console.warn('No se pudo leer el caso', casoId, error);
    return null;
  }
}

async function contextoDelCaso(casoId: string): Promise<Contexto> {
  const [planes, indicaciones, evoluciones, adherencias, eventos] = await Promise.all([
    leer<Plan>('planes', { caso_id: casoId }),
    leer<Indicacion>('indicaciones', { caso_id: casoId }),
    leer<Evolucion>('evolucion', { caso_id: casoId }),
    leer<Adherencia>('adherencia', { caso_id: casoId }),
    // La bitácora entera del caso; las alertas se eligen en la vista. `read` sólo
    // filtra por igualdad, así que pedir «los de estos cinco tipos» serían cinco
    // lecturas en vez de una.
    leer<EventoCaso>('eventos', { caso_id: casoId }),
  ]);

  const plan =
    [...planes].sort((a, b) =>
      String(b.creado_en ?? '').localeCompare(String(a.creado_en ?? ''))
    )[0] ?? null;

  return {
    plan,
    indicaciones: indicaciones.filter(
      (fila) => esVerdad(fila.activa) && (!plan || String(fila.plan_id ?? '') === idDe(plan))
    ),
    // Todas y no las últimas ocho: la gráfica muestra el seguimiento entero.
    evoluciones,
    adherencias,
    eventos,
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

/**
 * Guardar el plan.
 *
 * El orden importa: primero el plan, luego las indicaciones que lo referencian, y
 * al final el caso pasa a `en_seguimiento`. Si algo falla en medio, lo que queda
 * escrito es coherente —un plan sin indicaciones se ve vacío pero no rompe nada—,
 * mientras que mover el caso primero dejaría al agente de seguimiento acompañando
 * un plan que no existe. ROBLE no tiene transacciones, así que el orden es la
 * única garantía disponible.
 */
async function registrarPlan(datos: {
  casoId: string;
  citaId: string;
  autor: { userId: string; nombre: string };
  resumen: string;
  // Cada indicación con su frecuencia: «acetaminofén cada 8 horas» y «caminar a
  // diario» no se recuerdan igual. Antes había una sola para todo el plan.
  indicaciones: Array<{ texto: string; frecuencia: string }>;
}): Promise<void> {
  const ahora = new Date().toISOString();

  const plan = await roble.create('planes', {
    caso_id: datos.casoId,
    profesional_user_id: datos.autor.userId,
    profesional_nombre: datos.autor.nombre,
    resumen: datos.resumen,
    creado_en: ahora,
  });

  const planId = idDeInsercion(plan);
  if (!planId) {
    // Sin id no se puede colgar la indicación del plan, y una indicación huérfana
    // no la recogería `consultar_plan`. Mejor decirlo que escribir a medias.
    throw new Error('ROBLE no devolvió el identificador del plan. No se guardaron las indicaciones.');
  }

  await roble.createMany(
    'indicaciones',
    datos.indicaciones.map(({ texto, frecuencia }) => ({
      caso_id: datos.casoId,
      plan_id: planId,
      texto,
      frecuencia,
      activa: true,
      creado_en: ahora,
    }))
  );

  if (datos.citaId) {
    try {
      await roble.update('citas', datos.citaId, { estado: 'atendida' });
    } catch (error) {
      console.warn('No se pudo marcar la cita como atendida', error);
    }
  }

  // Este cambio de estado es lo que hace que el próximo mensaje del paciente lo
  // atienda el agente de seguimiento y no el de triaje: `agente_por_defecto` en el
  // orquestador enruta por el estado del caso.
  await roble.update('casos', datos.casoId, {
    estado: 'en_seguimiento',
    actualizado_en: ahora,
  });
}

/**
 * El caso pasa a `cerrado` y la bitácora dice quién lo cerró.
 *
 * Primero el caso y después el evento: si el evento fallara, el caso ya está cerrado,
 * que es lo que importa; al revés quedaría escrito un cierre que no ocurrió. Las
 * columnas son las de `eventos` en `bootstrap_roble.mjs` —ROBLE rechaza la escritura
 * entera si se envía una que no existe—.
 */
async function cerrarCaso(
  casoId: string,
  autor: { userId: string; nombre: string }
): Promise<void> {
  const ahora = new Date().toISOString();
  await roble.update('casos', casoId, { estado: 'cerrado', actualizado_en: ahora });
  try {
    await roble.create('eventos', {
      caso_id: casoId,
      tipo: 'caso_cerrado',
      severidad: 'info',
      actor_user_id: autor.userId,
      actor_rol: 'profesional',
      detalle: { cerrado_por: autor.nombre },
      creado_en: ahora,
    });
  } catch (error) {
    console.warn('El caso quedó cerrado pero no se pudo anotar en la bitácora', error);
  }
}

/**
 * La cita pasa a `no_asistio` y el caso, si esperaba esa cita, vuelve a `canalizado`.
 *
 * Primero la cita: si el caso no llegara a cambiar, el agente igual puede dar otra cita,
 * porque una cita pasada ya no bloquea. Al revés, un caso en `canalizado` con una cita
 * todavía `confirmada` se vería en el tablero del centro como si nada hubiera pasado.
 */
async function marcarInasistencia(
  cita: Cita,
  caso: Caso,
  autor: { userId: string; nombre: string }
): Promise<void> {
  const ahora = new Date().toISOString();
  const casoId = idDe(caso);
  await roble.update('citas', idDe(cita), { estado: 'no_asistio' });
  if (caso.estado === 'agendado') {
    await roble.update('casos', casoId, { estado: 'canalizado', actualizado_en: ahora });
  }
  try {
    await roble.create('eventos', {
      caso_id: casoId,
      tipo: 'cita_no_asistio',
      severidad: 'info',
      actor_user_id: autor.userId,
      actor_rol: 'profesional',
      detalle: { cita_id: idDe(cita), inicio: cita.inicio ?? null, marcado_por: autor.nombre },
      creado_en: ahora,
    });
  } catch (error) {
    console.warn('La inasistencia quedó marcada pero no se pudo anotar en la bitácora', error);
  }
}

function yaEmpezo(cita: Cita): boolean {
  const inicio = new Date(String(cita.inicio ?? '')).getTime();
  return Number.isFinite(inicio) && inicio <= Date.now();
}

async function desactivar(indicacionId: string): Promise<void> {
  await roble.update('indicaciones', indicacionId, { activa: false });
}

function repartir(citas: Cita[]): { proximas: Cita[]; pasadas: Cita[] } {
  const ahora = Date.now();
  const proximas: Cita[] = [];
  const pasadas: Cita[] = [];

  for (const cita of citas) {
    const inicio = new Date(String(cita.inicio ?? '')).getTime();
    const yaFue = Number.isFinite(inicio) && inicio < ahora;
    // Una cita pasada pero sin atender sigue en «por atender»: es justo la que no
    // hay que perder de vista. Una marcada como inasistencia ya se resolvió.
    if (yaFue && (cita.estado === 'atendida' || cita.estado === 'no_asistio')) pasadas.push(cita);
    else proximas.push(cita);
  }

  proximas.sort((a, b) => String(a.inicio ?? '').localeCompare(String(b.inicio ?? '')));
  pasadas.sort((a, b) => String(b.inicio ?? '').localeCompare(String(a.inicio ?? '')));
  return { proximas, pasadas };
}
