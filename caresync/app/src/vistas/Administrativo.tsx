/**
 * Lo que ve el personal administrativo de un centro.
 *
 * Tres cosas, en este orden de importancia:
 *
 * 1. **Las urgencias escaladas primero.** Si hay un caso de nivel 1, es lo primero
 *    de la pantalla y no se puede ignorar. El resto del tablero puede esperar.
 * 2. **El estado del centro**: casos por atender, citas del día, cupos libres.
 * 3. **La agenda**: el botón que publica cupos a partir de los horarios, y el chat
 *    con el agente de agenda para mover cosas hablando.
 *
 * El centro no se elige aquí: sale del rol (`admin_cmu` → CMU). Un desplegable para
 * cambiarlo habría sido una puerta para ver los casos del otro centro.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { generarCupos, type ResultadoGeneracion } from '../agenda_cupos';
import { Conversacion } from '../componentes/Conversacion';
import { Aviso, Cargando, Etiqueta, Nivel, Tarjeta, Vacio } from '../componentes/Piezas';
import { fechaHora, hace, soloHora } from '../formato';
import { mensajeDeError, roble } from '../roble';
import { useSesion } from '../sesion';
import { idDe, type Caso, type Centro, type Cita, type Cupo } from '../tipos';

interface Tablero {
  casos: Caso[];
  citas: Cita[];
  cupos: Cupo[];
}

const VACIO: Tablero = { casos: [], citas: [], cupos: [] };

/**
 * El centro se resuelve antes de montar el tablero.
 *
 * Separar el guardia del panel no es ceremonia: hace que `PanelDeCentro` reciba un
 * `Centro` y no un `Centro | null`, y así ninguna de sus veinte líneas de lecturas y
 * escrituras tiene que volver a preguntarse si hay centro.
 */
export function Administrativo() {
  const { quien, salir } = useSesion();
  const centro = (quien?.centro ?? null) as Centro | null;

  if (!centro) {
    return (
      <div className="panel administrativo">
        <header className="cabecera">
          <h1>Sin centro asignado</h1>
          <button type="button" className="secundario" onClick={() => void salir()}>
            Salir
          </button>
        </header>
        <Aviso tipo="error">
          Tu cuenta tiene un rol administrativo pero no un centro. Quien administre el
          contrato de ROBLE tiene que poner CMU o CAE en tu fila de «perfiles».
        </Aviso>
      </div>
    );
  }

  return <PanelDeCentro centro={centro} />;
}

function PanelDeCentro({ centro }: { centro: Centro }) {
  const { quien, salir } = useSesion();

  const [tablero, setTablero] = useState<Tablero>(VACIO);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');
  const [generando, setGenerando] = useState(false);
  const [resultado, setResultado] = useState<ResultadoGeneracion | null>(null);

  const cargar = useCallback(async () => {
    try {
      setTablero(await leerTablero(centro));
      setError('');
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setCargando(false);
    }
  }, [centro]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const vista = useMemo(() => organizar(tablero), [tablero]);

  async function publicarCupos() {
    setGenerando(true);
    setError('');
    setResultado(null);
    try {
      const salida = await generarCupos(centro);
      setResultado(salida);
      await cargar();
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setGenerando(false);
    }
  }

  return (
    <div className="panel administrativo">
      <header className="cabecera">
        <div>
          <h1>{centro}</h1>
          <p>
            {quien?.nombre} · {vista.porAtender.length} caso
            {vista.porAtender.length === 1 ? '' : 's'} por atender ·{' '}
            {vista.libres.length} cupo{vista.libres.length === 1 ? '' : 's'} libre
            {vista.libres.length === 1 ? '' : 's'}
          </p>
        </div>
        <button type="button" className="secundario" onClick={() => void salir()}>
          Salir
        </button>
      </header>

      {error && <Aviso tipo="error">{error}</Aviso>}

      {vista.urgencias.length > 0 && (
        <Tarjeta titulo="Urgencias escaladas" extra={<span className="contador">{vista.urgencias.length}</span>}>
          <Aviso tipo="urgente">
            Estos casos activaron la ruta de urgencias. Verifica que cada uno tenga
            contacto humano.
          </Aviso>
          <ul className="casos">
            {vista.urgencias.map((caso) => (
              <FilaDeCaso key={idDe(caso)} caso={caso} />
            ))}
          </ul>
        </Tarjeta>
      )}

      <div className="columnas">
        <section className="lista">
          <Tarjeta titulo="Citas de hoy">
            {cargando ? (
              <Cargando que="Cargando el tablero" />
            ) : vista.hoy.length === 0 ? (
              <Vacio>No hay citas para hoy.</Vacio>
            ) : (
              <ul className="citas">
                {vista.hoy.map((cita) => (
                  <li key={idDe(cita)}>
                    <span className="cuando">{soloHora(cita.inicio)}</span>
                    <span className="quien">{String(cita.profesional_nombre ?? 'Profesional')}</span>
                    <Etiqueta estado={cita.estado} />
                  </li>
                ))}
              </ul>
            )}
          </Tarjeta>

          <Tarjeta titulo="Por atender">
            {cargando ? (
              <Cargando />
            ) : vista.porAtender.length === 0 ? (
              <Vacio>Todo lo canalizado ya tiene cita.</Vacio>
            ) : (
              <ul className="casos">
                {vista.porAtender.map((caso) => (
                  <FilaDeCaso key={idDe(caso)} caso={caso} />
                ))}
              </ul>
            )}
          </Tarjeta>

          <Tarjeta
            titulo="Agenda"
            extra={
              <button type="button" className="principal fino" disabled={generando} onClick={() => void publicarCupos()}>
                {generando ? 'Publicando…' : 'Publicar cupos (14 días)'}
              </button>
            }
          >
            <p className="fino">
              Toma los horarios de los profesionales activos del centro y crea los
              cupos libres que faltan. Pulsarlo dos veces no duplica nada.
            </p>

            {resultado && (
              <Aviso>
                {resultado.profesionales === 0
                  ? 'Este centro no tiene profesionales activos con horarios registrados.'
                  : `${resultado.creados} cupos nuevos, ${resultado.yaEstaban} ya estaban, ` +
                    `del ${resultado.desde} al ${resultado.hasta}.` +
                    (resultado.truncado ? ' Se alcanzó el tope de la tanda: vuelve a pulsar para el resto.' : '')}
              </Aviso>
            )}

            {vista.proximosLibres.length > 0 && (
              <>
                <h3>Próximos cupos libres</h3>
                <ul className="cupos">
                  {vista.proximosLibres.map((cupo) => (
                    <li key={idDe(cupo)}>
                      <span className="cuando">{fechaHora(cupo.inicio)}</span>
                      <span className="fino">{String(cupo.modalidad ?? 'presencial')}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </Tarjeta>
        </section>

        <aside className="lateral">
          <Conversacion
            agente="agenda"
            saludo={
              'Soy el agente de agenda del ' +
              centro +
              '. Puedo consultar disponibilidad, agendar y avisar a los profesionales. ' +
              'Dime sobre qué caso trabajamos.'
            }
            alResponder={() => void cargar()}
            alVencerSesion={() => void salir()}
          />
        </aside>
      </div>
    </div>
  );
}

function FilaDeCaso({ caso }: { caso: Caso }) {
  return (
    <li>
      <span className="quien">{String(caso.paciente_nombre ?? 'Paciente')}</span>
      <span className="marcas">
        <Nivel valor={caso.nivel_urgencia} />
        <Etiqueta estado={caso.estado} />
      </span>
      <span className="fino">{hace(caso.actualizado_en ?? caso.creado_en)}</span>
    </li>
  );
}

// ------------------------------------------------------------------------ datos

async function leerTablero(centro: Centro): Promise<Tablero> {
  const [casos, citas, cupos] = await Promise.all([
    leer<Caso>('casos', { centro }),
    leer<Cita>('citas', { centro }),
    leer<Cupo>('cupos', { centro }),
  ]);
  return { casos, citas, cupos };
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
 * El reparto del tablero.
 *
 * Todo se calcula en el navegador porque ROBLE devuelve las filas sin ordenar y sin
 * rangos de fecha. Es aceptable con el volumen de un centro del campus; el día que
 * no lo sea, cada una de estas listas es una consulta guardada en ROBLE.
 */
function organizar(tablero: Tablero) {
  const ahora = Date.now();
  const finDelDia = ahora + 24 * 3600 * 1000;

  const conCita = new Set(
    tablero.citas
      .filter((cita) => cita.estado !== 'cancelada')
      .map((cita) => String(cita.caso_id ?? ''))
  );

  const urgencias = tablero.casos
    .filter((caso) => Number(caso.nivel_urgencia) === 1 || caso.estado === 'urgencia_escalada')
    .filter((caso) => caso.estado !== 'cerrado')
    .sort((a, b) => String(b.actualizado_en ?? '').localeCompare(String(a.actualizado_en ?? '')));

  const idsUrgentes = new Set(urgencias.map((caso) => idDe(caso)));

  const porAtender = tablero.casos
    .filter((caso) => caso.estado === 'canalizado' && !conCita.has(idDe(caso)))
    .filter((caso) => !idsUrgentes.has(idDe(caso)))
    .sort(porPrioridad);

  const hoy = tablero.citas
    .filter((cita) => cita.estado !== 'cancelada')
    .filter((cita) => {
      const inicio = new Date(String(cita.inicio ?? '')).getTime();
      return Number.isFinite(inicio) && inicio >= ahora - 3600 * 1000 && inicio <= finDelDia;
    })
    .sort((a, b) => String(a.inicio ?? '').localeCompare(String(b.inicio ?? '')));

  const libres = tablero.cupos.filter((cupo) => {
    if (cupo.estado !== 'libre') return false;
    const inicio = new Date(String(cupo.inicio ?? '')).getTime();
    return Number.isFinite(inicio) && inicio > ahora;
  });

  const proximosLibres = [...libres]
    .sort((a, b) => String(a.inicio ?? '').localeCompare(String(b.inicio ?? '')))
    .slice(0, 6);

  return { urgencias, porAtender, hoy, libres, proximosLibres };
}

/** Primero el nivel más urgente; a igual nivel, el que lleva más tiempo esperando. */
function porPrioridad(a: Caso, b: Caso): number {
  const nivelA = Number(a.nivel_urgencia) || 9;
  const nivelB = Number(b.nivel_urgencia) || 9;
  if (nivelA !== nivelB) return nivelA - nivelB;
  return String(a.creado_en ?? '').localeCompare(String(b.creado_en ?? ''));
}
