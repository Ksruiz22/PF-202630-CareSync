/**
 * El historial de triajes: los casos ya triados del centro y, al abrir uno, la
 * conversación completa que lo originó.
 *
 * **Esto contradice a propósito la regla con la que se construyó la vista del
 * profesional**, que era que el profesional ve el resumen del triaje y no la
 * transcripción. La razón de aquella regla sigue siendo buena —para atender hace
 * falta el resumen, y leer el hilo entero de cada caso es una intromisión sin
 * motivo—, pero no cubre el caso que faltaba: **revisar si el triaje estuvo bien
 * hecho**. Un resumen no permite juzgar al agente que lo escribió. Para eso hay que
 * ver qué dijo la persona y qué contestó el agente.
 *
 * Y porque el motivo es revisar y no atender, el acceso no es gratis:
 *
 * - **Cada apertura de un hilo se escribe en `eventos`** como `hilo_consultado`, con
 *   quién lo abrió y cuántos turnos vio. La bitácora del caso es el único sitio donde
 *   esto queda, y es lo que convierte «el profesional puede leerlo todo» en «el
 *   profesional puede leerlo todo y se sabe cuándo lo hizo».
 * - **La pantalla lo dice antes y después de abrirlo.** Un registro que la persona
 *   que lo activa no conoce no es trazabilidad, es vigilancia.
 *
 * Los casos se listan por centro y no por «los míos»: un profesional del CMU revisa
 * triajes del CMU, tenga cita con esa persona o no, que es lo que hace posible mirar
 * el trabajo del agente y no sólo el propio. Los que sí tienen cita con él van
 * marcados, y hay un interruptor para quedarse sólo con esos.
 *
 * Esta vista **no pinta su propia `<Cabecera>` ni su `.panel`**: vive dentro de una
 * pestaña de `Profesional.tsx`, que es quien pone el marco.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { HiloDeCaso } from '../componentes/HiloDeCaso';
import { Aviso, Cargando, Etiqueta, Nivel, Tarjeta, Vacio } from '../componentes/Piezas';
import { IconoBuscar, IconoDocumento, IconoMensaje, IconoReloj } from '../componentes/Iconos';
import { leerHilo, type TurnoDelHilo } from '../conversaciones';
import { estadoLegible, fechaHora, hace, soloFecha } from '../formato';
import { mensajeDeError, roble } from '../roble';
import { useSesion } from '../sesion';
import { idDe, type Caso, type Cita, type EventoCaso } from '../tipos';

/** Cuántas filas se pintan como mucho. Lo filtrado de verdad puede ser más. */
const TOPE_DE_FILAS = 60;

/** Cuántas líneas de bitácora se muestran. Las demás siguen en ROBLE. */
const EVENTOS_VISIBLES = 10;

interface Historial {
  /** Los casos triados, sin ordenar todavía: el orden lo pone el filtro. */
  casos: Caso[];
  /** Ids de los casos que tienen cita con este profesional. */
  mios: Set<string>;
  /** `true` cuando el perfil no tenía centro y la lista salió de las propias citas. */
  porRespaldo: boolean;
}

const VACIO: Historial = { casos: [], mios: new Set(), porRespaldo: false };

export function HistorialDeTriajes(): ReactElement {
  const { quien } = useSesion();
  const [historial, setHistorial] = useState<Historial>(VACIO);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');

  const [busqueda, setBusqueda] = useState('');
  const [nivel, setNivel] = useState('todos');
  const [estado, setEstado] = useState('todos');
  const [soloMios, setSoloMios] = useState(false);
  const [elegido, setElegido] = useState('');

  const userId = quien?.userId ?? '';
  const nombre = quien?.nombre ?? '';
  const centro = quien?.centro ?? null;

  /**
   * Qué hilos se han abierto ya en esta sesión de pantalla.
   *
   * Un `useRef` y no estado porque esto no se pinta y porque cambiarlo no debe
   * provocar un repintado: lo único que hace es evitar la segunda escritura. Sin él,
   * cualquier re-render que remonte el detalle —y `StrictMode` monta los efectos dos
   * veces en desarrollo— escribía dos filas en `eventos` por una sola apertura, y la
   * cuota de ROBLE es de 100 operaciones por minuto y por IP.
   */
  const anotados = useRef<Set<string>>(new Set());

  const cargar = useCallback(async () => {
    if (!userId) return;
    try {
      setHistorial(await historialDe(userId, centro));
      setError('');
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setCargando(false);
    }
  }, [userId, centro]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  /**
   * La anotación de que se abrió un hilo, una sola vez por caso.
   *
   * La comprobación y el apunte en el conjunto van **antes** de la escritura y de
   * forma sincrónica: si se esperara a que ROBLE confirmara, las dos pasadas de
   * `StrictMode` entrarían las dos antes de que la primera terminara. La consecuencia
   * es que una escritura fallida no se reintenta en esta sesión de pantalla, y está
   * bien: perder una línea de bitácora es menos grave que gastar la cuota de ROBLE
   * reintentándola, y el fallo queda en la consola.
   */
  const anotarUnaVez = useCallback(
    (casoId: string, turnos: number) => {
      if (!casoId || !userId || anotados.current.has(casoId)) return;
      anotados.current.add(casoId);
      void anotarConsulta(casoId, turnos, userId, nombre);
    },
    [userId, nombre]
  );

  const estados = useMemo(
    () =>
      [...new Set(historial.casos.map((caso) => String(caso.estado ?? '')).filter(Boolean))].sort(),
    [historial.casos]
  );

  /**
   * El filtro, entero en memoria.
   *
   * `read` de ROBLE sólo compara por igualdad: no hay `like`, ni rangos, ni orden, ni
   * paginación. Buscar, filtrar por nivel y ordenar por actividad se hacen aquí sobre
   * lo que ya se leyó, y es aceptable con el volumen de un centro del campus. El día
   * que no lo sea, esto es una consulta guardada en ROBLE llamada con `executeQuery`,
   * no un `read` con más parámetros.
   */
  const filtrados = useMemo(() => {
    const aguja = busqueda.trim().toLowerCase();
    return historial.casos
      .filter((caso) => {
        if (soloMios && !historial.mios.has(idDe(caso))) return false;
        if (nivel !== 'todos' && String(Number(caso.nivel_urgencia) || 0) !== nivel) return false;
        if (estado !== 'todos' && String(caso.estado ?? '') !== estado) return false;
        if (!aguja) return true;
        return `${String(caso.paciente_nombre ?? '')} ${String(caso.motivo ?? '')}`
          .toLowerCase()
          .includes(aguja);
      })
      .sort(porActividadDescendente);
  }, [historial, busqueda, nivel, estado, soloMios]);

  const visibles = filtrados.slice(0, TOPE_DE_FILAS);
  // El caso abierto se busca en todo lo leído y no en lo filtrado: si se buscara ahí,
  // escribir una letra más en el buscador cerraría de golpe la conversación que se
  // está leyendo, y la lectura del hilo se repetiría al volver. Es la misma razón por
  // la que el tablero administrativo guarda el caso elegido entero y no su fila.
  const abierto = historial.casos.find((caso) => idDe(caso) === elegido) ?? null;

  if (!quien) {
    return <Aviso tipo="error">No hay sesión: vuelve a entrar para ver el historial.</Aviso>;
  }

  return (
    <div className="columnas">
      <section className="lista">
        <Tarjeta
          titulo="Casos triados"
          icono={<IconoDocumento />}
          extra={<span className="contador neutro">{filtrados.length}</span>}
        >
          <p className="fino">
            {centro
              ? `Los casos ya triados del ${centro}, tengas cita con la persona o no.`
              : 'Tu perfil no tiene centro, así que aquí sólo salen los casos con los que tienes cita.'}{' '}
            <strong>Abrir la conversación de un caso queda registrado</strong> en su
            bitácora, con tu nombre y la hora.
          </p>

          <label htmlFor="buscar-triajes">Buscar caso</label>
          <div className="buscador">
            <IconoBuscar width={17} height={17} />
            <input
              id="buscar-triajes"
              type="search"
              value={busqueda}
              onChange={(evento) => setBusqueda(evento.target.value)}
              placeholder="Nombre del paciente o motivo"
            />
          </div>

          <div className="controles">
            <label>
              Urgencia
              <select value={nivel} onChange={(evento) => setNivel(evento.target.value)}>
                <option value="todos">Todos los niveles</option>
                <option value="1">1 · Emergencia</option>
                <option value="2">2 · Prioritario</option>
                <option value="3">3 · Regular</option>
                <option value="4">4 · Orientación</option>
                <option value="0">Sin clasificar</option>
              </select>
            </label>
            <label>
              Estado
              <select value={estado} onChange={(evento) => setEstado(evento.target.value)}>
                <option value="todos">Cualquier estado</option>
                {estados.map((clave) => (
                  <option key={clave} value={clave}>
                    {estadoLegible(clave)}
                  </option>
                ))}
              </select>
            </label>
            {/*
              Un botón con `aria-pressed` y no una casilla de verificación: es el mismo
              patrón que las filas del tablero administrativo —un interruptor que queda
              puesto— y así no hace falta un estilo de casilla que la hoja no tiene.
            */}
            <button
              type="button"
              className={soloMios ? 'principal fino' : 'secundario'}
              aria-pressed={soloMios}
              onClick={() => setSoloMios((antes) => !antes)}
            >
              Sólo mis casos
            </button>
          </div>

          <p className="fino" aria-live="polite">
            {filtrados.length} de {historial.casos.length} caso
            {historial.casos.length === 1 ? '' : 's'} triado
            {historial.casos.length === 1 ? '' : 's'}
            {soloMios ? ', sólo los que tienen cita contigo' : ''}.
          </p>

          {cargando ? (
            <Cargando que="Cargando el historial" />
          ) : historial.casos.length === 0 ? (
            <Vacio>
              Todavía no hay casos triados
              {centro ? ` en el ${centro}` : ' entre los que tienen cita contigo'}. Un caso
              aparece aquí cuando el agente de triaje le pone nivel, resumen o centro.
            </Vacio>
          ) : filtrados.length === 0 ? (
            <Vacio>Ningún caso coincide con lo que buscas.</Vacio>
          ) : (
            <>
              <ul className="casos">
                {visibles.map((caso) => (
                  <FilaDeTriaje
                    key={idDe(caso)}
                    caso={caso}
                    mio={historial.mios.has(idDe(caso))}
                    activa={idDe(caso) === elegido}
                    alAbrir={() => setElegido(idDe(caso))}
                  />
                ))}
              </ul>
              {filtrados.length > visibles.length && (
                <p className="fino">
                  Se muestran los {visibles.length} más recientes de {filtrados.length}.
                  Afina la búsqueda o los filtros para llegar al resto.
                </p>
              )}
            </>
          )}
        </Tarjeta>

        {error && <Aviso tipo="error">{error}</Aviso>}
        {historial.porRespaldo && !cargando && (
          <Aviso>
            Tu perfil no tiene centro asignado, así que esta lista se armó con los casos de
            tus propias citas. Quien administre el contrato de ROBLE puede poner CMU o CAE
            en tu fila de «perfiles» para ver el historial completo del centro.
          </Aviso>
        )}
      </section>

      <section className="detalle">
        {!abierto ? (
          <Tarjeta titulo="Revisión del triaje">
            <Vacio>
              Elige un caso para ver su triaje y la conversación que lo originó.
            </Vacio>
          </Tarjeta>
        ) : (
          <DetalleDelTriaje
            key={idDe(abierto)}
            caso={abierto}
            mio={historial.mios.has(idDe(abierto))}
            alConsultar={anotarUnaVez}
          />
        )}
      </section>
    </div>
  );
}

/**
 * Una fila del historial.
 *
 * `aria-pressed` y no `aria-selected`: igual que en el tablero administrativo, esto no
 * es navegación —la fila no lleva a otra pantalla— sino un interruptor que queda
 * puesto, y es lo que hay que anunciar. `aria-selected` necesitaría además un
 * `role="listbox"` en la lista y el manejo de teclado que ese papel promete.
 */
function FilaDeTriaje({
  caso,
  mio,
  activa,
  alAbrir,
}: {
  caso: Caso;
  mio: boolean;
  activa: boolean;
  alAbrir: () => void;
}): ReactElement {
  return (
    <li>
      <button
        type="button"
        className={`fila ${activa ? 'activa' : ''}`}
        aria-pressed={activa}
        onClick={alAbrir}
      >
        <span className="quien">{String(caso.paciente_nombre ?? 'Paciente')}</span>
        <span className="marcas">
          <Nivel valor={caso.nivel_urgencia} />
          <Etiqueta estado={caso.estado} />
          {/* El texto lo dice y no sólo el color: la marca tiene que sobrevivir a una
              impresión en blanco y negro y a quien no distingue los dos tonos. */}
          {mio && <span className="pildora">Tiene cita contigo</span>}
        </span>
        <span className="fino">{hace(caso.actualizado_en ?? caso.creado_en)}</span>
      </button>
    </li>
  );
}

// ------------------------------------------------------------------- el detalle

/**
 * El caso abierto: su triaje, su conversación y su bitácora.
 *
 * Está separado y con `key` por caso para que cambiar de caso remonte el componente:
 * así el hilo y la bitácora no se quedan nunca con los del caso anterior mientras
 * cargan los nuevos, que es la forma más fácil de mostrarle a alguien la conversación
 * equivocada.
 */
function DetalleDelTriaje({
  caso,
  mio,
  alConsultar,
}: {
  caso: Caso;
  mio: boolean;
  alConsultar: (casoId: string, turnos: number) => void;
}): ReactElement {
  const casoId = idDe(caso);
  // `null` mientras carga, y lista —aunque esté vacía— cuando ya se sabe qué hay.
  const [turnos, setTurnos] = useState<TurnoDelHilo[] | null>(null);
  const [bitacora, setBitacora] = useState<EventoCaso[]>([]);
  const [falloElHilo, setFalloElHilo] = useState(false);

  useEffect(() => {
    let vivo = true;
    void (async () => {
      const [hilo, eventos] = await Promise.all([
        hiloDelCaso(casoId),
        leer<EventoCaso>('eventos', { caso_id: casoId }),
      ]);
      // El registro va **antes** del guardia de montaje: la lectura ya ocurrió y el
      // hilo ya salió de ROBLE, así que la consulta pasó de verdad. Dejarlo detrás del
      // guardia lo perdía siempre en desarrollo, donde `StrictMode` desmonta el primer
      // montaje antes de que la promesa resuelva.
      //
      // Y no se anota si la lectura falló: no hubo conversación que ver, y dejar el
      // caso sin anotar es lo que permite que el siguiente intento sí quede registrado.
      if (!hilo.fallo) alConsultar(casoId, hilo.turnos.length);
      if (!vivo) return;
      setTurnos(hilo.turnos);
      setFalloElHilo(hilo.fallo);
      setBitacora(
        [...eventos]
          .sort((a, b) => String(b.creado_en ?? '').localeCompare(String(a.creado_en ?? '')))
          .slice(0, EVENTOS_VISIBLES)
      );
    })();
    return () => {
      vivo = false;
    };
  }, [casoId, alConsultar]);

  return (
    <>
      <Tarjeta
        titulo={String(caso.paciente_nombre ?? 'Paciente')}
        extra={<Etiqueta estado={caso.estado} />}
      >
        <dl className="datos">
          <dt>Urgencia</dt>
          <dd>
            <Nivel valor={caso.nivel_urgencia} />
          </dd>
          <dt>Centro</dt>
          <dd>{String(caso.centro ?? 'por definir')}</dd>
          <dt>Caso abierto</dt>
          <dd>
            {soloFecha(caso.creado_en)} · {hace(caso.creado_en)}
          </dd>
          <dt>Última actividad</dt>
          <dd>{hace(caso.actualizado_en ?? caso.creado_en)}</dd>
          <dt>Cita contigo</dt>
          <dd>{mio ? 'Sí' : 'No, es un caso del centro'}</dd>
        </dl>

        {/* `|| texto` y no `??`: ROBLE devuelve cadena vacía tan a menudo como `null`
            —depende de si la columna se escribió con un valor vacío o no se escribió—, y
            con `??` la cadena vacía pasaba el filtro y dejaba el hueco sin explicar. */}
        <h3>Resumen del triaje</h3>
        <p className="resumen">
          {String(caso.resumen_triaje ?? '').trim() || 'Sin resumen del triaje registrado.'}
        </p>

        <h3>Motivo</h3>
        <p className="resumen">
          {String(caso.motivo ?? '').trim() || 'Sin motivo registrado.'}
        </p>
      </Tarjeta>

      <Tarjeta titulo="Conversación completa" icono={<IconoMensaje />}>
        <p className="fino">
          Esto es lo que la persona escribió y lo que le contestaron los agentes, tal
          como quedó en ROBLE. <strong>Esta apertura quedó registrada</strong> en la
          bitácora del caso con tu nombre, la hora y cuántos turnos tiene el hilo.
        </p>
        {falloElHilo && (
          <Aviso tipo="error">
            No se pudo leer la conversación de este caso. Lo demás de la pantalla sí es
            fiable. Para reintentar, elige otro caso y vuelve a este.
          </Aviso>
        )}
        <HiloDeCaso turnos={turnos ?? []} cargando={turnos === null} />
      </Tarjeta>

      <Tarjeta titulo="Bitácora del caso" icono={<IconoReloj />}>
        <p className="fino">
          Lo que el sistema hizo con este caso. Es el contexto para juzgar el triaje:
          una canalización y una urgencia escalada en el mismo caso dicen más que
          cualquiera de las dos por separado.
        </p>
        {turnos === null ? (
          <Cargando que="Cargando la bitácora" />
        ) : bitacora.length === 0 ? (
          <Vacio>Este caso no tiene nada anotado en la bitácora.</Vacio>
        ) : (
          <ul className="triajes-bitacora">
            {bitacora.map((evento, indice) => (
              <li key={idDe(evento) || `evento-${indice}`}>
                <span className="cuando">{fechaHora(evento.creado_en)}</span>
                <span className="texto">{tipoLegible(evento.tipo)}</span>
                <span className={`etiqueta triajes-severidad-${claveDeSeveridad(evento.severidad)}`}>
                  {severidadLegible(evento.severidad)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Tarjeta>
    </>
  );
}

// ---------------------------------------------------------------------- datos

/**
 * Los casos triados que este profesional puede revisar.
 *
 * Dos lecturas en el camino normal: sus citas —para saber qué casos son suyos— y los
 * casos de su centro. Las dos van en paralelo porque son independientes y en serie se
 * notan.
 *
 * Sin centro en el perfil hay respaldo, y no una pantalla vacía: se leen los casos de
 * sus propias citas, una lectura por caso, igual que hace `agendaDe`. Es más caro en
 * llamadas y por eso no es el camino principal, pero un perfil sin centro es una
 * configuración incompleta y no un error de quien usa la aplicación: que vea lo suyo.
 */
async function historialDe(userId: string, centro: string | null): Promise<Historial> {
  const [citas, delCentro] = await Promise.all([
    leer<Cita>('citas', { profesional_user_id: userId }),
    centro ? leer<Caso>('casos', { centro }) : Promise.resolve(null),
  ]);

  // Las canceladas no cuentan como «caso mío», igual que en la agenda: una cita
  // cancelada no es una consulta que este profesional vaya a tener.
  const mios = new Set(
    citas
      .filter((cita) => cita.estado !== 'cancelada')
      .map((cita) => String(cita.caso_id ?? ''))
      .filter(Boolean)
  );

  if (delCentro) {
    return { casos: delCentro.filter(esTriado), mios, porRespaldo: false };
  }

  const filas = await Promise.all([...mios].map((id) => leerCaso(id)));
  const casos: Caso[] = [];
  for (const fila of filas) {
    if (fila && esTriado(fila)) casos.push(fila);
  }
  return { casos, mios, porRespaldo: true };
}

/**
 * ¿Pasó ya por el triaje?
 *
 * Tres señales y no una porque las tres las escribe el triaje y ninguna está
 * garantizada: `canalizar_caso` pone centro y nivel, pero una urgencia escalada puede
 * quedar con nivel 1 y sin centro, y un caso canalizado a mano desde la vista
 * administrativa tiene centro y ningún resumen. Pedir las tres dejaría fuera
 * exactamente los casos que más interesa revisar.
 */
function esTriado(caso: Caso): boolean {
  if (Number(caso.nivel_urgencia) > 0) return true;
  if (String(caso.resumen_triaje ?? '').trim()) return true;
  return Boolean(String(caso.centro ?? '').trim());
}

/**
 * El hilo, y si falló leerlo.
 *
 * Se devuelve el fallo en vez de una lista vacía a secas porque las dos cosas se ven
 * igual en pantalla y no son lo mismo: «este caso no tiene conversación» es un dato
 * del caso, y «no pude leerla» es un problema de la pantalla. Decir el primero cuando
 * pasa el segundo es mentirle al profesional sobre lo que hay en la base.
 */
async function hiloDelCaso(casoId: string): Promise<{ turnos: TurnoDelHilo[]; fallo: boolean }> {
  try {
    return { turnos: await leerHilo(casoId), fallo: false };
  } catch (error) {
    console.warn('No se pudo leer la conversación del caso', casoId, error);
    return { turnos: [], fallo: true };
  }
}

/**
 * Que se abrió el hilo de un caso, en la bitácora.
 *
 * No lanza nunca: el profesional ya tiene la conversación delante y tumbarle la
 * pantalla no desharía la consulta. Queda en la consola, que es donde se mira si la
 * bitácora de un caso parece incompleta.
 *
 * Las columnas son **exactamente** las de `eventos` en `bootstrap_roble.mjs`
 * (`caso_id`, `tipo`, `severidad`, `actor_user_id`, `actor_rol`, `detalle`,
 * `creado_en`): ROBLE rechaza la escritura entera con un 400 si se envía una columna
 * que no existe, y no hay forma de hacerle un `alter` a la tabla para arreglarlo
 * después.
 */
async function anotarConsulta(
  casoId: string,
  turnos: number,
  userId: string,
  nombre: string
): Promise<void> {
  try {
    await roble.create('eventos', {
      caso_id: casoId,
      tipo: 'hilo_consultado',
      severidad: 'info',
      actor_user_id: userId,
      actor_rol: 'profesional',
      detalle: { turnos, por: nombre },
      creado_en: new Date().toISOString(),
    });
  } catch (error) {
    console.warn('Se abrió el hilo pero no se pudo anotar en la bitácora', casoId, error);
  }
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

/**
 * Una lectura con `catch` propio.
 *
 * Igual que en `Paciente.tsx` y en `Profesional.tsx`: que falte un permiso en una
 * tabla no puede dejar en blanco las otras. Aquí importa especialmente, porque la
 * bitácora y el hilo son dos tablas distintas y perder una no debería costar la otra.
 */
async function leer<T>(tabla: string, filtros: Record<string, unknown>): Promise<T[]> {
  try {
    return (await roble.read(tabla, filtros)) as T[];
  } catch (error) {
    console.warn(`No se pudo leer ${tabla}`, error);
    return [];
  }
}

function porActividadDescendente(a: Caso, b: Caso): number {
  return String(b.actualizado_en ?? b.creado_en ?? '').localeCompare(
    String(a.actualizado_en ?? a.creado_en ?? '')
  );
}

/**
 * El tipo de evento, dicho en español.
 *
 * Al contrario que `describir` en `Conversacion.tsx`, lo que no está en la tabla **sí**
 * se muestra, con su clave cruda. Allí el público es la persona atendida y un
 * identificador interno no le dice nada; aquí es personal del centro revisando una
 * bitácora, y esconder una línea porque el backend añadió un tipo nuevo sería peor que
 * mostrar `sin_adherencia` tal cual.
 */
function tipoLegible(tipo: unknown): string {
  const textos: Record<string, string> = {
    caso_canalizado: 'Caso canalizado al centro',
    urgencia_escalada: 'Urgencia escalada',
    cita_agendada: 'Cita agendada',
    profesional_notificado: 'Profesional notificado',
    evolucion_desfavorable: 'Evolución desfavorable',
    indicacion_no_cumplida: 'Indicación no cumplida',
    sin_adherencia: 'Sin reportes del plan',
    sin_evolucion: 'Sin reportes de evolución',
    caso_cerrado: 'Caso cerrado',
    hilo_consultado: 'Conversación consultada',
  };
  const clave = String(tipo ?? '');
  return textos[clave] ?? (clave || 'sin tipo');
}

/** Las tres que escribe el backend: `info` por defecto, `alta` y `critica`. */
function severidadLegible(severidad: unknown): string {
  const clave = claveDeSeveridad(severidad);
  if (clave === 'critica') return 'Crítica';
  if (clave === 'alta') return 'Alta';
  return 'Informativa';
}

function claveDeSeveridad(severidad: unknown): string {
  const clave = String(severidad ?? 'info').toLowerCase();
  return clave === 'critica' || clave === 'alta' ? clave : 'info';
}
