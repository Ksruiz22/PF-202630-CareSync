/**
 * Lo que ve un profesional del CMU o del CAE.
 *
 * Esta es la única pantalla del prototipo donde una persona escribe datos
 * clínicos a mano, y es a propósito: **el plan lo hace el profesional, no el
 * modelo**. El agente de seguimiento acompaña sobre un plan que ya existe; no lo
 * inventa. Si esta pantalla no existiera, el agente no tendría de dónde sacar las
 * indicaciones y la tentación sería dejar que se las imaginara.
 *
 * El profesional ve el resumen del triaje y lo que la persona ha reportado
 * después, pero **no la conversación**: el hilo completo se queda en ROBLE y en la
 * bitácora del caso. Lo que se necesita para atender es el resumen, no la
 * transcripción.
 */

import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Aviso, Cargando, Etiqueta, Nivel, Tarjeta, Vacio } from '../componentes/Piezas';
import { bandaDeEscala, escalaVisible, fechaHora, hace, soloFecha } from '../formato';
import { mensajeDeError, roble } from '../roble';
import { useSesion } from '../sesion';
import {
  esVerdad,
  idDe,
  idDeInsercion,
  type Adherencia,
  type Caso,
  type Cita,
  type Evolucion,
  type Indicacion,
  type Plan,
} from '../tipos';

interface Agenda {
  citas: Cita[];
  casos: Record<string, Caso>;
}

export function Profesional() {
  const { quien, salir } = useSesion();
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
      <header className="cabecera">
        <div>
          <h1>{quien?.nombre}</h1>
          <p>
            Tu agenda en {quien?.centro ?? 'tu centro'}. {proximas.length} cita
            {proximas.length === 1 ? '' : 's'} por atender.
          </p>
        </div>
        <button type="button" className="secundario" onClick={() => void salir()}>
          Salir
        </button>
      </header>

      {error && <Aviso tipo="error">{error}</Aviso>}

      <div className="columnas">
        <section className="lista">
          <Tarjeta titulo="Por atender">
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
  const [contexto, setContexto] = useState<Contexto | null>(null);
  const [resumen, setResumen] = useState('');
  const [lineas, setLineas] = useState('');
  const [frecuencia, setFrecuencia] = useState('cada 24 horas');
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState('');
  const [error, setError] = useState('');

  const cargar = useCallback(async () => {
    setContexto(await contextoDelCaso(casoId));
  }, [casoId]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function guardarPlan(evento: FormEvent) {
    evento.preventDefault();
    const indicaciones = lineas
      .split('\n')
      .map((linea) => linea.trim())
      .filter(Boolean);

    if (!resumen.trim() || indicaciones.length === 0) {
      setError('Hace falta el resumen y al menos una indicación.');
      return;
    }

    setGuardando(true);
    setError('');
    setAviso('');
    try {
      await registrarPlan({
        casoId,
        citaId: idDe(cita),
        autor,
        resumen: resumen.trim(),
        indicaciones,
        frecuencia: frecuencia.trim() || 'cada 24 horas',
      });
      setResumen('');
      setLineas('');
      setAviso('Plan registrado. El agente de seguimiento ya puede acompañar este caso.');
      await cargar();
      alGuardar();
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setGuardando(false);
    }
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
          {contexto.evoluciones.length > 0 && (
            <Tarjeta titulo="Lo que ha reportado">
              <ul className="evolucion">
                {contexto.evoluciones.map((fila) => (
                  <li key={idDe(fila)}>
                    <span className={`escala ${bandaDeEscala(fila.escala)}`}>
                      {escalaVisible(fila.escala)}
                    </span>
                    <span className="texto">{String(fila.nota ?? '')}</span>
                    <span className="fino">{hace(fila.reportado_en)}</span>
                  </li>
                ))}
              </ul>
            </Tarjeta>
          )}

          {contexto.plan && (
            <Tarjeta titulo="Plan vigente">
              <p className="resumen">{String(contexto.plan.resumen ?? '')}</p>
              <p className="fino">
                {String(contexto.plan.profesional_nombre ?? '')} ·{' '}
                {soloFecha(contexto.plan.creado_en)}
              </p>
              <ul className="indicaciones">
                {contexto.indicaciones.map((indicacion) => (
                  <li key={idDe(indicacion)}>
                    <span className="texto">{String(indicacion.texto ?? '')}</span>
                    <span className="fino">
                      {String(indicacion.frecuencia ?? '')} ·{' '}
                      {contarAdherencia(contexto.adherencias, idDe(indicacion))}
                    </span>
                    <button
                      type="button"
                      className="enlace"
                      onClick={() => {
                        void desactivar(idDe(indicacion))
                          .then(cargar)
                          .catch((fallo) => setError(mensajeDeError(fallo)));
                      }}
                    >
                      Desactivar
                    </button>
                  </li>
                ))}
              </ul>
              <p className="fino">
                Al desactivar una indicación se detienen sus recordatorios. Los ya
                enviados quedan en la bitácora.
              </p>
            </Tarjeta>
          )}

          <Tarjeta titulo={contexto.plan ? 'Nuevo plan' : 'Registrar el plan'}>
            <form className="formulario" onSubmit={guardarPlan}>
              <label>
                Resumen de la consulta
                <textarea
                  value={resumen}
                  onChange={(e) => setResumen(e.target.value)}
                  rows={4}
                  maxLength={2000}
                  placeholder="Qué se encontró y qué se decidió."
                  required
                />
              </label>

              <label>
                Indicaciones, una por línea
                <textarea
                  value={lineas}
                  onChange={(e) => setLineas(e.target.value)}
                  rows={5}
                  maxLength={2000}
                  placeholder={'Caminar 20 minutos al día\nEjercicio de respiración antes de dormir'}
                  required
                />
              </label>

              <label>
                Cada cuánto se le pregunta
                <input
                  type="text"
                  value={frecuencia}
                  onChange={(e) => setFrecuencia(e.target.value)}
                  maxLength={60}
                  placeholder="cada 24 horas"
                />
              </label>
              <p className="fino">
                Se acepta «cada 12 horas», «cada 2 días», «semanal». Los recordatorios
                salen entre las 7:00 y las 20:00, hora de Bogotá.
              </p>

              <button type="submit" className="principal" disabled={guardando}>
                {guardando ? 'Guardando…' : 'Guardar plan y cerrar la consulta'}
              </button>

              {aviso && <Aviso>{aviso}</Aviso>}
              {error && <Aviso tipo="error">{error}</Aviso>}
            </form>
          </Tarjeta>
        </>
      )}
    </>
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
  const [planes, indicaciones, evoluciones, adherencias] = await Promise.all([
    leer<Plan>('planes', { caso_id: casoId }),
    leer<Indicacion>('indicaciones', { caso_id: casoId }),
    leer<Evolucion>('evolucion', { caso_id: casoId }),
    leer<Adherencia>('adherencia', { caso_id: casoId }),
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
    evoluciones: [...evoluciones]
      .sort((a, b) => String(b.reportado_en ?? '').localeCompare(String(a.reportado_en ?? '')))
      .slice(0, 8),
    adherencias,
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
  indicaciones: string[];
  frecuencia: string;
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
    datos.indicaciones.map((texto) => ({
      caso_id: datos.casoId,
      plan_id: planId,
      texto,
      frecuencia: datos.frecuencia,
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

async function desactivar(indicacionId: string): Promise<void> {
  await roble.update('indicaciones', indicacionId, { activa: false });
}

function contarAdherencia(filas: Adherencia[], indicacionId: string): string {
  const propias = filas.filter((fila) => String(fila.indicacion_id ?? '') === indicacionId);
  if (propias.length === 0) return 'sin reportes';
  const cumplidas = propias.filter((fila) => esVerdad(fila.cumplida)).length;
  return `${cumplidas}/${propias.length} cumplidas`;
}

function repartir(citas: Cita[]): { proximas: Cita[]; pasadas: Cita[] } {
  const ahora = Date.now();
  const proximas: Cita[] = [];
  const pasadas: Cita[] = [];

  for (const cita of citas) {
    const inicio = new Date(String(cita.inicio ?? '')).getTime();
    const yaFue = Number.isFinite(inicio) && inicio < ahora;
    // Una cita pasada pero sin atender sigue en «por atender»: es justo la que no
    // hay que perder de vista.
    if (yaFue && cita.estado === 'atendida') pasadas.push(cita);
    else proximas.push(cita);
  }

  proximas.sort((a, b) => String(a.inicio ?? '').localeCompare(String(b.inicio ?? '')));
  pasadas.sort((a, b) => String(b.inicio ?? '').localeCompare(String(a.inicio ?? '')));
  return { proximas, pasadas };
}
