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
import { Aviso, Cargando, Etiqueta, Nivel, Tarjeta, Vacio } from '../componentes/Piezas';
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
  type Indicacion,
  type Plan,
} from '../tipos';

interface Panorama {
  caso: Caso | null;
  cita: Cita | null;
  plan: Plan | null;
  indicaciones: Indicacion[];
  evoluciones: Evolucion[];
  adherencias: Adherencia[];
}

const VACIO: Panorama = {
  caso: null,
  cita: null,
  plan: null,
  indicaciones: [],
  evoluciones: [],
  adherencias: [],
};

export function Paciente() {
  const { quien, salir } = useSesion();
  const [datos, setDatos] = useState<Panorama>(VACIO);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');

  const userId = quien?.userId ?? '';

  const cargar = useCallback(async () => {
    if (!userId) return;
    try {
      const caso = await casoVigente(userId);
      setDatos(caso ? await alrededorDelCaso(caso) : VACIO);
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

  const casoId = idDe(datos.caso);
  const nivel = Number(datos.caso?.nivel_urgencia ?? 0);

  return (
    <div className="panel paciente">
      <header className="cabecera">
        <div>
          <h1>Hola, {primerNombre(quien?.nombre)}</h1>
          <p>Cuéntale al asistente qué te pasa y él te acompaña desde ahí.</p>
        </div>
        <button type="button" className="secundario" onClick={() => void salir()}>
          Salir
        </button>
      </header>

      {error && <Aviso tipo="error">{error}</Aviso>}
      {nivel === 1 && (
        <Aviso tipo="urgente">
          Tu caso está marcado como emergencia. Si aún no has recibido ayuda, llama
          ya a la línea de emergencias del campus o al 123.
        </Aviso>
      )}

      <div className="columnas">
        <Conversacion
          {...(casoId ? { casoId } : {})}
          saludo={saludoSegun(datos.caso)}
          alResponder={() => void cargar()}
          alVencerSesion={() => void salir()}
        />

        <aside className="lateral">
          {cargando ? (
            <Cargando que="Buscando tu caso" />
          ) : !datos.caso ? (
            <Tarjeta titulo="Todavía no hay caso">
              <Vacio>
                Cuando le escribas al asistente se abre un caso y aquí verás en qué
                va.
              </Vacio>
            </Tarjeta>
          ) : (
            <>
              <Tarjeta titulo="Tu caso" extra={<Etiqueta estado={datos.caso.estado} />}>
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

              <Tarjeta titulo="Tu cita">
                {datos.cita ? (
                  <>
                    <p className="destacado">{fechaHora(datos.cita.inicio)}</p>
                    <p>
                      {String(datos.cita.profesional_nombre ?? 'Profesional por asignar')} ·{' '}
                      {nombreDeCentro(datos.cita.centro)}
                    </p>
                    <Etiqueta estado={datos.cita.estado} />
                  </>
                ) : (
                  <Vacio>
                    Sin cita agendada. Pídele al asistente que te busque un espacio.
                  </Vacio>
                )}
              </Tarjeta>

              {datos.plan && (
                <Tarjeta titulo="Tu plan">
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
                <Tarjeta titulo="Cómo has ido">
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
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

/**
 * El caso sobre el que se conversa.
 *
 * `read` de ROBLE sólo filtra por igualdad y no ordena, así que se traen los casos
 * de la persona y se elige aquí: el más reciente que no esté cerrado. Cuando eso
 * deje de caber en una lectura habrá que crear una consulta guardada en ROBLE y
 * llamarla con `executeQuery`; para el número de casos de un estudiante, no hace
 * falta.
 */
async function casoVigente(userId: string): Promise<Caso | null> {
  const casos = (await roble.read('casos', { paciente_user_id: userId })) as Caso[];
  const abiertos = casos.filter((caso) => caso.estado !== 'cerrado');
  const candidatos = abiertos.length > 0 ? abiertos : casos;
  return [...candidatos].sort(porFechaDescendente)[0] ?? null;
}

async function alrededorDelCaso(caso: Caso): Promise<Panorama> {
  const casoId = idDe(caso);

  // En paralelo porque son cinco lecturas independientes y en serie se notan.
  // `catch` por tabla: que no haya plan todavía no puede dejar la pantalla en
  // blanco, y un permiso faltante en una tabla no debe tumbar las otras cuatro.
  const [citas, planes, indicaciones, evoluciones, adherencias] = await Promise.all([
    leer<Cita>('citas', { caso_id: casoId }),
    leer<Plan>('planes', { caso_id: casoId }),
    leer<Indicacion>('indicaciones', { caso_id: casoId }),
    leer<Evolucion>('evolucion', { caso_id: casoId }),
    leer<Adherencia>('adherencia', { caso_id: casoId }),
  ]);

  const activa = citas.filter((cita) => cita.estado !== 'cancelada');

  return {
    caso,
    cita: [...activa].sort(porInicioAscendente)[0] ?? null,
    plan: [...planes].sort(porFechaDescendente)[0] ?? null,
    indicaciones: indicaciones.filter((fila) => esVerdad(fila.activa)),
    evoluciones: [...evoluciones].sort(porReporteDescendente).slice(0, 5),
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

function porFechaDescendente(a: { creado_en?: unknown }, b: { creado_en?: unknown }): number {
  return String(b.creado_en ?? '').localeCompare(String(a.creado_en ?? ''));
}

function porReporteDescendente(a: { reportado_en?: unknown }, b: { reportado_en?: unknown }): number {
  return String(b.reportado_en ?? '').localeCompare(String(a.reportado_en ?? ''));
}

function porInicioAscendente(a: { inicio?: unknown }, b: { inicio?: unknown }): number {
  return String(a.inicio ?? '').localeCompare(String(b.inicio ?? ''));
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

function primerNombre(nombre: string | undefined): string {
  const limpio = String(nombre ?? '').trim();
  if (!limpio) return 'hola';
  const primero = limpio.split(/\s+/)[0] ?? limpio;
  // Si el «nombre» es en realidad el correo —pasa cuando no hay fila en
  // `perfiles`—, se corta en la arroba para no saludar a «juan.perez@uninorte».
  return (primero.split('@')[0] ?? primero) || 'hola';
}

function nombreDeCentro(centro: unknown): string {
  const clave = String(centro ?? '').toUpperCase();
  if (clave === 'CMU') return 'Centro Médico Universitario';
  if (clave === 'CAE') return 'Centro de Acompañamiento Estudiantil';
  return 'por definir';
}
