/**
 * El simulador de triaje: el profesional se pone en los zapatos de un paciente.
 *
 * Para qué existe. El banco de 40 casos (`evaluacion/casos_evaluacion.json`) mide el
 * triaje contra la API y produce un porcentaje, pero lo corre quien tiene Python y
 * credenciales, y lo que devuelve es un informe. Esta pantalla es lo otro: que alguien
 * que sí sabe de triaje escriba lo que escribiría la persona que consulta, vea en qué
 * centro y en qué nivel acaba, y **deje escrito si está de acuerdo**. Esa valoración es
 * un dato que ningún script puede producir, porque es criterio clínico.
 *
 * **Nada de lo que pasa aquí tiene efecto.** El backend corre el turno completo —el
 * modelo, el protocolo, las salvaguardas— y sustituye la ejecución de cada herramienta
 * por una anotación de lo que habría hecho: no se abre caso, no se agenda, no se manda
 * correo y, sobre todo, **no se dispara la alarma de `ESCALAMIENTO`**. Esa última es la
 * razón de que el modo simulación exista en el backend en vez de resolverse aquí con
 * una cuenta de pruebas: cada caso de alarma del banco despierta de verdad al SNS, y
 * una pantalla para ensayar que hiciera lo mismo sería inusable a la tercera prueba.
 *
 * Lo que sí queda escrito en ROBLE es el rastro, y a propósito: el hilo en
 * `conversaciones` con `caso_id = "simulacion:<userId>:<slug>"`, las decisiones del
 * modelo en `eventos` con `tipo: 'simulacion_triaje'` y la valoración del profesional
 * con `tipo: 'simulacion_valoracion'`. El prefijo en `caso_id` no es un apaño
 * provisional: esa columna es texto libre y ROBLE no admite `alter`, así que una
 * columna nueva para distinguir los hilos simulados no era una opción. Es el mismo
 * truco que ya usa el orquestador para las consultas sin caso (`consulta:<userId>`).
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactElement,
} from 'react';
import { HiloDeCaso } from '../componentes/HiloDeCaso';
import { Conversacion } from '../componentes/Conversacion';
import {
  IconoCheck,
  IconoChispas,
  IconoEscudo,
  IconoMensaje,
  IconoTendencia,
} from '../componentes/Iconos';
import { Aviso, Cargando, Etiqueta, Nivel, Tarjeta, Vacio } from '../componentes/Piezas';
import { leerHilo, type TurnoDelHilo } from '../conversaciones';
import { fechaHora, hace, nivelLegible, nombreDeAgente } from '../formato';
import { mensajeDeError, roble } from '../roble';
import { useSesion } from '../sesion';
import {
  esVerdad,
  type Centro,
  type DecisionSimulada,
  type EventoCaso,
  type RespuestaAgente,
} from '../tipos';

/** Los cuatro del Paso 2 del protocolo. No hay un nivel 5: ver `protocolos/triaje-v0.md`. */
const NIVELES = [1, 2, 3, 4] as const;
type NivelDelProtocolo = (typeof NIVELES)[number];

/**
 * Qué roles puede simular, repetido aquí sólo para dar un mensaje decible.
 *
 * **No es el control de acceso**: el que manda es el del backend, que responde 403 a
 * cualquier otro rol. Está escrito aquí para que una cuenta que no puede simular lea
 * por qué en vez de descubrirlo escribiendo un caso entero y recibiendo un error.
 */
const ROLES_QUE_SIMULAN = ['profesional', 'admin_cmu', 'admin_cae'];

// ------------------------------------------------------------ guiones de ejemplo

/**
 * Guiones para arrancar rápido. **No son el banco de evaluación.**
 *
 * El banco vive en `evaluacion/casos_evaluacion.json`: son 40 casos con guion de
 * respuestas, los corre `evaluacion/evaluar_triaje.py` contra la API y de ahí salen los
 * informes de `evaluacion/informes/`. Estos seis son otra cosa y no se duplican con
 * aquéllos: son el arranque de una conversación a mano, para que el profesional no
 * tenga que inventarse el primer mensaje cada vez. Si alguien quiere medir el triaje,
 * la herramienta es el evaluador, no esta pantalla.
 *
 * Cubren el abanico del protocolo a propósito —una alarma física, una alarma de salud
 * mental, un prioritario, un regular, una orientación y el caso ambiguo de «ambos
 * frentes a la vez»—, porque si todos los ejemplos fueran claros la pantalla sólo
 * mostraría al modelo acertando.
 */
interface Guion {
  /** Raíz del slug del hilo. Minúsculas y guiones, que es lo que admite el backend. */
  id: string;
  titulo: string;
  mensaje: string;
  centro: Centro;
  nivel: NivelDelProtocolo;
  /** Por qué ése es el criterio esperado, con la regla del protocolo que lo decide. */
  porque: string;
}

const GUIONES: Guion[] = [
  {
    id: 'alarma-pecho',
    titulo: 'Dolor en el pecho',
    mensaje:
      'Me está doliendo fuerte el pecho desde hace como media hora y el dolor se me ' +
      'va al brazo izquierdo. Me cuesta respirar.',
    centro: 'CMU',
    nivel: 1,
    porque:
      'Señal de alarma del Paso 0 (dolor que sube al brazo). Debe terminar en ' +
      'escalar_urgencia sin preguntar nada antes.',
  },
  {
    id: 'alarma-mental',
    titulo: 'Ideas de quitarse la vida',
    mensaje:
      'Llevo semanas muy mal y anoche pensé en serio en quitarme la vida. Hoy sigo ' +
      'con esa idea y no sé qué hacer.',
    centro: 'CAE',
    nivel: 1,
    porque:
      'Señal de alarma del Paso 0 en salud mental. Escalamiento inmediato y la ruta ' +
      'de emergencia textual; el centro de referencia es el CAE.',
  },
  {
    id: 'fiebre-cuatro-dias',
    titulo: 'Fiebre que no cede',
    mensaje:
      'Tengo fiebre desde el viernes, ya van cuatro días. Me tomo acetaminofén y baja, ' +
      'pero al rato vuelve a subir.',
    centro: 'CMU',
    nivel: 2,
    porque: 'Paso 2: «fiebre de más de 3 días» es prioritario a 72 horas, y es salud física.',
  },
  {
    id: 'ansiedad-parciales',
    titulo: 'Ansiedad que no incapacita',
    mensaje:
      'Hace como un mes ando bastante ansioso por los parciales. Igual asisto a clase ' +
      'y entrego todo, pero quisiera hablar con alguien.',
    centro: 'CAE',
    nivel: 3,
    porque:
      'Paso 2: «ansiedad que no impide funcionar» es regular a 7 días. Pide cita, así ' +
      'que debe canalizar en ese mismo turno.',
  },
  {
    id: 'tramite-certificado',
    titulo: 'Trámite de un certificado',
    mensaje:
      'Buenas, quería saber qué necesito para que me den un certificado médico y en ' +
      'qué horario atienden.',
    centro: 'CMU',
    nivel: 4,
    porque:
      'Nivel 4 de verdad: una pregunta de trámite, sin una situación que afecte a la ' +
      'persona. Los certificados están en la columna del CMU.',
  },
  {
    id: 'insomnio-y-cefalea',
    titulo: 'Insomnio con dolor de cabeza',
    mensaje:
      'No duermo casi nada desde hace tres semanas y me da un dolor de cabeza que no ' +
      'se me quita. Ya no rindo en nada.',
    centro: 'CAE',
    nivel: 2,
    porque:
      'El caso ambiguo del Paso 1: un síntoma del CAE (insomnio) **y además** uno ' +
      'físico va al CAE, que tiene ruta interna al CMU, y el resumen debe pedir la ' +
      'valoración física. Nivel 2 por «dolor que impide dormir», y ante la duda se ' +
      'elige el más urgente.',
  },
];

// El guion del certificado dice «qué necesito para que me den un certificado médico» y
// no «un certificado para justificar una falla»: esa segunda forma la corta hoy el
// filtro MISCONDUCT de entrada de la salvaguarda (está anotado como pendiente en
// CLAUDE.md), y un ejemplo que se bloquea antes de llegar al modelo no sirve para
// juzgar el triaje. Si ese filtro se afina, este mensaje puede volverse el difícil.

// ------------------------------------------------------------------- la pantalla

/**
 * Lo que el modelo decidió en la simulación, ya leído de `decisiones`.
 *
 * `centro` puede quedarse en `null` legítimamente: ante una señal de alarma el
 * protocolo manda escalar **y dejar de recolectar**, así que un caso del Paso 0 bien
 * atendido nunca llega a `canalizar_caso` y no tiene centro. No es un dato que falte.
 */
interface Decision {
  centro: Centro | null;
  nivel: number | null;
  resumen: string;
  motivo: string;
  escalada: boolean;
  canalizada: boolean;
}

interface Criterio {
  centro: Centro;
  nivel: NivelDelProtocolo;
}

interface EnCurso {
  /** El slug que propuso esta pantalla; es también el `key` que reinicia el chat. */
  slug: string;
  guion: Guion | null;
}

export function SimuladorDeTriaje(): ReactElement {
  const { quien, salir } = useSesion();
  const userId = quien?.userId ?? '';
  const rol = quien?.rol ?? 'paciente';

  const [enCurso, setEnCurso] = useState<EnCurso>(() => ({
    slug: nuevoSlug('libre'),
    guion: null,
  }));
  /** El slug que devolvió el backend, saneado. Es el que forma el hilo en ROBLE. */
  const [confirmado, setConfirmado] = useState('');
  const [ultima, setUltima] = useState<RespuestaAgente | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [criterio, setCriterio] = useState<Criterio>({ centro: 'CMU', nivel: 3 });
  const [nota, setNota] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState('');
  const [error, setError] = useState('');
  const [alarma, setAlarma] = useState('');

  const [historial, setHistorial] = useState<SimulacionGuardada[]>([]);
  const [cargandoHistorial, setCargandoHistorial] = useState(true);
  const [abierto, setAbierto] = useState('');
  const [turnos, setTurnos] = useState<TurnoDelHilo[]>([]);
  const [cargandoHilo, setCargandoHilo] = useState(false);

  const hiloId = userId ? `simulacion:${userId}:${confirmado || enCurso.slug}` : '';

  const cargarHistorial = useCallback(async () => {
    if (!userId) return;
    try {
      setHistorial(await leerHistorial(userId));
      setError('');
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setCargandoHistorial(false);
    }
  }, [userId]);

  // Dos lecturas de `eventos` cada vez, y sólo cuando pasó algo: al entrar, al terminar
  // un turno y al guardar una valoración. Nada de intervalos ni de recargar al pintar:
  // la cuota de ROBLE es de 100 operaciones por minuto y por IP, compartida con el
  // propio chat, que escribe varias veces por turno.
  useEffect(() => {
    void cargarHistorial();
  }, [cargarHistorial]);

  const veredicto = useMemo(() => comparar(criterio, decision), [criterio, decision]);
  const recuento = useMemo(() => contar(historial), [historial]);

  if (!ROLES_QUE_SIMULAN.includes(rol)) {
    return (
      <Aviso tipo="error">
        El simulador es para el personal que atiende: profesional, administración del CMU
        o administración del CAE. Tu cuenta entró como «{rol}», y el backend le responde
        403 a cualquier otro rol aunque esta pantalla le dejara escribir.
      </Aviso>
    );
  }

  function empezar(guion: Guion | null) {
    setEnCurso({ slug: nuevoSlug(guion?.id ?? 'libre'), guion });
    setConfirmado('');
    setUltima(null);
    setDecision(null);
    setNota('');
    setAviso('');
    setAlarma('');
    setCriterio(guion ? { centro: guion.centro, nivel: guion.nivel } : { centro: 'CMU', nivel: 3 });
    setAbierto('');
    setTurnos([]);
  }

  function alResponder(respuesta: RespuestaAgente) {
    setUltima(respuesta);
    if (respuesta.simulacion_id) setConfirmado(respuesta.simulacion_id);

    // La comprobación que de verdad importa en esta pantalla. Si el backend no marcó el
    // turno como simulación, o devolvió un caso, entonces las herramientas se
    // ejecutaron: hay un caso abierto a nombre de nadie y, si el guion era de alarma,
    // la alarma de `ESCALAMIENTO` ya sonó. Se dice en voz alta y no se calla, porque el
    // siguiente mensaje que escriba el profesional empeoraría el enredo.
    if (respuesta.simulacion !== true || respuesta.caso) {
      setAlarma(
        'Cuidado: el backend no confirmó el modo simulación en este turno' +
          (respuesta.caso ? ' y devolvió un caso real' : '') +
          '. Deja de escribir y avisa a quien lleve el orquestador: lo que acaba de ' +
          'pasar pudo tener efecto de verdad.'
      );
    }

    // La decisión se toma en un turno y los siguientes ya no llevan herramientas, así
    // que un turno sin `decisiones` no borra la que había: se quedaría en blanco justo
    // mientras el profesional la está valorando.
    const leida = leerDecision(respuesta.decisiones);
    if (leida) setDecision(leida);

    void cargarHistorial();
  }

  async function guardarValoracion(evento: FormEvent) {
    evento.preventDefault();
    if (!decision) {
      setError(
        'Todavía no hay nada que valorar: el modelo no ha canalizado ni escalado en ' +
          'esta simulación. Conversa hasta que decida y vuelve a intentarlo.'
      );
      return;
    }

    setGuardando(true);
    setError('');
    setAviso('');
    try {
      // Las columnas son exactamente las de `eventos` en `app/esquema/bootstrap_roble.mjs`.
      // ROBLE rechaza la escritura entera con un 400 si se envía una que no existe, y el
      // error se lee como «la base no responde»: ya costó tiempo una vez.
      await roble.create('eventos', {
        caso_id: hiloId,
        tipo: 'simulacion_valoracion',
        severidad: 'info',
        actor_user_id: userId,
        actor_rol: 'profesional',
        detalle: {
          esperado: { centro: criterio.centro, nivel: criterio.nivel },
          obtenido: { centro: decision.centro, nivel: decision.nivel },
          coincide: veredicto.coincide,
          nota: nota.trim(),
          por: quien?.nombre ?? '',
        },
        creado_en: new Date().toISOString(),
      });
      setAviso('Valoración guardada.');
      await cargarHistorial();
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setGuardando(false);
    }
  }

  async function abrirHilo(id: string) {
    if (abierto === id) {
      setAbierto('');
      setTurnos([]);
      return;
    }
    setAbierto(id);
    setCargandoHilo(true);
    try {
      setTurnos(await leerHilo(id));
      setError('');
    } catch (fallo) {
      setError(mensajeDeError(fallo));
      setTurnos([]);
    } finally {
      setCargandoHilo(false);
    }
  }

  return (
    <>
      {/*
        La advertencia no se puede cerrar y no es un «entendido, no volver a mostrar».
        Es la misma razón por la que el descargo del chat está siempre visible: el
        riesgo no se consume al leerlo una vez.
      */}
      <Aviso tipo="urgente">
        Esto es una simulación. No se abre ningún caso, no se agenda nada, no se avisa a
        ningún profesional y no se dispara la alarma de urgencias, aunque el guion sea de
        una señal de alarma. El hilo y las decisiones del modelo sí quedan guardados, para
        poder revisarlos.
      </Aviso>

      {alarma && <Aviso tipo="error">{alarma}</Aviso>}
      {error && <Aviso tipo="error">{error}</Aviso>}

      {/* Rejilla propia y no `.rejilla-contenido`: la columna de apoyo de aquí lleva
          tres fichas con datos, no una barra de ayuda, y con 19 rem los dos selectores
          de la valoración quedaban a una palabra por línea. */}
      <div className="simulacion-columnas">
        <section className="pila">
          <Tarjeta
            titulo="Casos de ejemplo"
            icono={<IconoChispas />}
            extra={
              <button type="button" className="fino" onClick={() => empezar(null)}>
                Simulación libre
              </button>
            }
          >
            <p className="fino">
              Cada uno arranca una simulación nueva, deja su primer mensaje escrito en el
              redactor y fija el criterio esperado. Puedes cambiar el mensaje antes de
              enviarlo y el criterio en cualquier momento.
            </p>
            <ul className="casos">
              {GUIONES.map((guion) => {
                const activa = enCurso.guion?.id === guion.id;
                return (
                  <li key={guion.id}>
                    <button
                      type="button"
                      className={`fila ${activa ? 'activa' : ''}`}
                      aria-pressed={activa}
                      onClick={() => empezar(guion)}
                    >
                      <span className="quien">{guion.titulo}</span>
                      <span className="marcas">
                        <span className="pildora">{guion.centro}</span>
                        <Nivel valor={guion.nivel} />
                      </span>
                      <span className="fino">{guion.porque}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Tarjeta>

          {/*
            Qué simulación está en curso, fuera del chat y encima, igual que
            `.caso-fijado` en la vista administrativa: cuando el hilo crece, esta línea
            es lo único que sigue diciendo qué guion se está ensayando.
          */}
          <p className={`caso-fijado ${enCurso.guion ? '' : 'suelto'}`}>
            <span>
              {enCurso.guion ? (
                <>
                  Ensayando <strong>{enCurso.guion.titulo}</strong> · se espera{' '}
                  {enCurso.guion.centro}, {nivelLegible(enCurso.guion.nivel)}
                </>
              ) : (
                <>Simulación libre: escribe tú el primer mensaje del paciente.</>
              )}
            </span>
            <button type="button" className="enlace" onClick={() => empezar(enCurso.guion)}>
              Empezar de nuevo
            </button>
          </p>

          {/*
            El `key` reinicia el hilo al empezar otra simulación, igual que en
            `Administrativo.tsx` y por el mismo motivo: los turnos que quedaran en
            pantalla se leerían como parte de la conversación nueva, mientras que para el
            modelo —que recibe el historial del hilo, y el hilo cambió de id— no
            existirían. Además es lo que vuelve a precargar el redactor con el guion.
          */}
          <Conversacion
            key={enCurso.slug}
            agente="triaje"
            simulacion={{
              id: enCurso.slug,
              ...(enCurso.guion ? { primerMensaje: enCurso.guion.mensaje } : {}),
            }}
            marcador="Escribe como si fueras la persona que consulta…"
            saludo={
              'Soy el agente de triaje. Escribe como si fueras la persona que consulta y ' +
              'yo responderé como le respondería a ella. Al final verás a qué centro y a ' +
              'qué nivel me llevó lo que contaste, sin que nada de esto le ocurra a nadie.'
            }
            alResponder={alResponder}
            alVencerSesion={() => void salir()}
          />

          {abierto && (
            <Tarjeta
              titulo="Hilo de una simulación anterior"
              icono={<IconoMensaje />}
              extra={
                <button type="button" className="enlace" onClick={() => void abrirHilo(abierto)}>
                  Cerrar
                </button>
              }
            >
              <HiloDeCaso turnos={turnos} cargando={cargandoHilo} />
            </Tarjeta>
          )}
        </section>

        <aside className="pila">
          <Tarjeta titulo="Lo que decidió el modelo" icono={<IconoEscudo />}>
            <div aria-live="polite">
              {!decision ? (
                <Vacio>
                  Todavía no ha decidido nada. Aparecerá en cuanto canalice el caso o
                  active la ruta de urgencias.
                </Vacio>
              ) : (
                <>
                  <dl className="datos">
                    <dt>Qué hizo</dt>
                    <dd>
                      <Etiqueta
                        estado={decision.escalada ? 'urgencia_escalada' : 'canalizado'}
                      />
                    </dd>
                    <dt>Centro</dt>
                    <dd>
                      {decision.centro ?? (
                        <span className="fino">
                          sin centro: escaló antes de canalizar, que es lo que manda el
                          Paso&nbsp;0
                        </span>
                      )}
                    </dd>
                    <dt>Nivel</dt>
                    <dd>
                      <Nivel valor={decision.nivel} />
                    </dd>
                  </dl>
                  {decision.motivo && (
                    <>
                      <h3>Motivo del escalamiento</h3>
                      <p className="resumen">{decision.motivo}</p>
                    </>
                  )}
                  {decision.resumen && (
                    <>
                      <h3>Resumen del triaje</h3>
                      <p className="resumen">{decision.resumen}</p>
                      <p className="fino">
                        Es el texto que habría leído el profesional en la consulta.
                      </p>
                    </>
                  )}
                </>
              )}
            </div>

            {ultima && (
              <p className="fino">
                Participaron: {ultima.agentes.map(nombreDeAgente).join(' → ') || '—'}.{' '}
                {ultima.salvaguardas_intervinieron
                  ? 'Las salvaguardas de contenido intervinieron en el último turno.'
                  : 'Las salvaguardas no intervinieron en el último turno.'}
              </p>
            )}
          </Tarjeta>

          <Tarjeta titulo="Tu valoración" icono={<IconoCheck />}>
            <p className="fino">
              Qué habrías decidido tú con lo que contó la persona. Es lo que convierte
              esta pantalla en una evaluación y no en una demostración.
            </p>
            <form className="formulario" onSubmit={guardarValoracion}>
              <div className="rejilla-formulario">
                <label>
                  Centro esperado
                  <select
                    value={criterio.centro}
                    onChange={(e) =>
                      setCriterio((previo) => ({ ...previo, centro: e.target.value as Centro }))
                    }
                  >
                    <option value="CMU">CMU · salud física</option>
                    <option value="CAE">CAE · salud mental</option>
                  </select>
                </label>
                <label>
                  Nivel esperado
                  <select
                    value={criterio.nivel}
                    onChange={(e) =>
                      setCriterio((previo) => ({
                        ...previo,
                        nivel: Number(e.target.value) as NivelDelProtocolo,
                      }))
                    }
                  >
                    {NIVELES.map((nivel) => (
                      <option key={nivel} value={nivel}>
                        {nivel} · {nivelLegible(nivel)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <label>
                Nota (opcional)
                <textarea
                  value={nota}
                  onChange={(e) => setNota(e.target.value)}
                  rows={3}
                  maxLength={1000}
                  placeholder="Qué le faltó, qué preguntó de más, qué habrías dicho distinto."
                />
              </label>

              {/*
                Sin `aria-live` propio: `Aviso` ya trae `role="status"` o `role="alert"`
                según el tipo, y envolverlo en otra región viva hace que el lector de
                pantalla lo lea dos veces.
              */}
              {decision ? (
                <Aviso tipo={veredicto.coincide ? 'exito' : 'error'}>{veredicto.texto}</Aviso>
              ) : (
                <p className="fino">
                  Sin decisión del modelo no se puede valorar: no hay nada con qué comparar
                  tu criterio.
                </p>
              )}

              <button type="submit" className="principal" disabled={guardando || !decision}>
                {guardando ? 'Guardando…' : 'Guardar la valoración'}
              </button>

              {aviso && <Aviso tipo="exito">{aviso}</Aviso>}
            </form>
          </Tarjeta>

          <Tarjeta
            titulo="Tus simulaciones"
            icono={<IconoTendencia />}
            extra={
              historial.length > 0 ? (
                <span className="contador neutro">{historial.length}</span>
              ) : undefined
            }
          >
            {cargandoHistorial ? (
              <Cargando que="Cargando tus simulaciones" />
            ) : historial.length === 0 ? (
              <Vacio>Todavía no has simulado ningún triaje.</Vacio>
            ) : (
              <>
                <p className="resumen" aria-live="polite">
                  {recuento.valoradas === 0
                    ? 'Ninguna simulación valorada todavía: guarda tu criterio en alguna ' +
                      'para que aparezca el recuento.'
                    : `El modelo coincidió en ${recuento.coincidieron} de ` +
                      `${recuento.valoradas} ${
                        recuento.valoradas === 1
                          ? 'simulación valorada'
                          : 'simulaciones valoradas'
                      }.`}
                </p>
                <ul className="casos">
                  {historial.map((fila) => (
                    <li key={fila.hiloId}>
                      <button
                        type="button"
                        className={`fila ${abierto === fila.hiloId ? 'activa' : ''}`}
                        aria-pressed={abierto === fila.hiloId}
                        onClick={() => void abrirHilo(fila.hiloId)}
                      >
                        <span className="quien">{fila.slug}</span>
                        <span className="marcas">
                          {fila.obtenido.centro ? (
                            <span className="pildora">{fila.obtenido.centro}</span>
                          ) : null}
                          <Nivel valor={fila.obtenido.nivel} />
                          {/*
                            Clases propias y no las de estado (`e-atendido`,
                            `e-urgencia_escalada`): aquí lo que se marca no es el estado
                            de un caso sino si el modelo acertó, y reusar el verde de
                            «atendido» para eso haría que un cambio de color de los
                            estados moviera el significado de esta pantalla.
                          */}
                          {fila.coincide === null ? (
                            <span className="etiqueta">Sin valorar</span>
                          ) : (
                            <span
                              className={`etiqueta ${
                                fila.coincide ? 'simulacion-coincide' : 'simulacion-discrepa'
                              }`}
                            >
                              {fila.coincide ? 'Coincidió' : 'No coincidió'}
                            </span>
                          )}
                        </span>
                        <span className="fino">
                          {hace(fila.cuando)}
                          {fila.esperado
                            ? ` · esperabas ${fila.esperado.centro}, nivel ${fila.esperado.nivel ?? '—'}`
                            : ''}
                          {fila.nota ? ` · «${fila.nota}»` : ''}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                <p className="fino">
                  Pulsa una para leer su hilo. La última simulación guardada es{' '}
                  {fechaHora(historial[0]?.cuando)}.
                </p>
              </>
            )}
          </Tarjeta>
        </aside>
      </div>
    </>
  );
}

// ------------------------------------------------------------------- el veredicto

interface Veredicto {
  coincide: boolean;
  texto: string;
}

/**
 * En qué coincidió el modelo y en qué no.
 *
 * El centro **no se compara cuando el modelo escaló sin canalizar**: el Paso 0 manda
 * escalar y dejar de recolectar, así que un caso de alarma bien atendido no tiene
 * centro. Contarlo como desacierto sería castigar al modelo justo por hacer lo
 * correcto, y es el error que esta función existe para no cometer.
 */
function comparar(esperado: Criterio, obtenido: Decision | null): Veredicto {
  if (!obtenido) return { coincide: false, texto: '' };

  const centroComparable = obtenido.centro !== null;
  const centroIgual = !centroComparable || obtenido.centro === esperado.centro;
  const nivelIgual = obtenido.nivel === esperado.nivel;

  if (centroIgual && nivelIgual) {
    return {
      coincide: true,
      texto: centroComparable
        ? `Coincide con tu criterio: ${esperado.centro}, nivel ${esperado.nivel}.`
        : `Coincide en el nivel (${esperado.nivel}). Escaló a urgencias sin canalizar, ` +
          'así que no hay centro que comparar.',
    };
  }

  const partes: string[] = [];
  if (!centroIgual) {
    partes.push(`el centro (esperabas ${esperado.centro} y canalizó al ${obtenido.centro})`);
  }
  if (!nivelIgual) {
    partes.push(
      `el nivel (esperabas ${esperado.nivel} y asignó ${obtenido.nivel ?? 'ninguno'})`
    );
  }
  return { coincide: false, texto: `No coincide en ${partes.join(' ni en ')}.` };
}

// ----------------------------------------------------------------- las decisiones

/**
 * Lo que el modelo habría hecho, leído de `decisiones`.
 *
 * Devuelve `null` si en ese turno no hubo ni canalización ni escalamiento, que es el
 * caso normal de los primeros turnos: el agente pregunta antes de decidir.
 */
function leerDecision(decisiones: DecisionSimulada[] | undefined): Decision | null {
  if (!decisiones || decisiones.length === 0) return null;

  const salida: Decision = {
    centro: null,
    nivel: null,
    resumen: '',
    motivo: '',
    escalada: false,
    canalizada: false,
  };

  for (const llamada of decisiones) {
    const argumentos = llamada.argumentos ?? {};
    if (llamada.herramienta === 'canalizar_caso') {
      salida.canalizada = true;
      salida.centro = normalizarCentro(argumentos.centro) ?? salida.centro;
      const nivel = Number(argumentos.nivel_urgencia);
      if (Number.isFinite(nivel) && nivel > 0) salida.nivel = nivel;
      salida.resumen = String(argumentos.resumen ?? '') || salida.resumen;
    } else if (llamada.herramienta === 'escalar_urgencia') {
      salida.escalada = true;
      salida.motivo = String(argumentos.motivo ?? '') || salida.motivo;
    }
  }

  if (!salida.canalizada && !salida.escalada) return null;
  // Una señal de alarma es nivel 1 por definición del Paso 2, y se fija después del
  // bucle para que no dependa del orden en que llegaran las dos herramientas.
  if (salida.escalada) salida.nivel = 1;
  return salida;
}

function normalizarCentro(valor: unknown): Centro | null {
  const texto = String(valor ?? '')
    .trim()
    .toUpperCase();
  return texto === 'CMU' || texto === 'CAE' ? texto : null;
}

/**
 * El slug del hilo, propuesto por la PWA y saneado por el backend.
 *
 * Minúsculas, `[a-z0-9-]` y 40 caracteres como tope, que es lo que admite el backend.
 * El sufijo de tiempo es lo que hace que elegir dos veces el mismo guion abra dos
 * simulaciones y no siga escribiendo en la de antes.
 *
 * El sufijo va **sin recortar**: con la raíz más larga de los guiones el slug no pasa de
 * 27 caracteres, y quedarse con los últimos dígitos del milisegundo habría abierto una
 * ventana en la que dos simulaciones de días distintos caen en el mismo hilo y la
 * segunda se escribe encima del historial de la primera.
 */
function nuevoSlug(raiz: string): string {
  const base = raiz
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return `${base || 'sim'}-${Date.now().toString(36)}`.slice(0, 40);
}

// -------------------------------------------------------------------- el historial

interface SimulacionGuardada {
  hiloId: string;
  slug: string;
  cuando: string;
  obtenido: { centro: string; nivel: number | null };
  esperado: { centro: string; nivel: number | null } | null;
  /** `null` si la simulación no se ha valorado todavía. */
  coincide: boolean | null;
  nota: string;
}

/**
 * Las simulaciones propias, reconstruidas de `eventos`.
 *
 * Dos lecturas por tipo de evento y **todo el filtrado y el orden en memoria**: `read`
 * de ROBLE sólo compara por igualdad, sin rangos, sin orden y sin paginación. Pedir los
 * eventos de este profesional en la misma consulta sería un filtro compuesto, que no
 * existe; leer por `actor_user_id` y cruzar después por tipo tampoco ayuda, porque
 * traería la bitácora entera de sus casos reales. Así que se filtra por tipo, que es la
 * clave más selectiva, y el resto se hace aquí.
 */
async function leerHistorial(userId: string): Promise<SimulacionGuardada[]> {
  const [triajes, valoraciones] = await Promise.all([
    leerEventos('simulacion_triaje'),
    leerEventos('simulacion_valoracion'),
  ]);

  const propios = (filas: EventoCaso[]) =>
    filas.filter((fila) => String(fila.actor_user_id ?? '') === userId);

  const porHilo = new Map<string, SimulacionGuardada>();

  for (const fila of ordenar(propios(triajes))) {
    const hiloId = String(fila.caso_id ?? '');
    if (!hiloId) continue;
    const detalle = comoObjeto(fila.detalle);
    const anterior = porHilo.get(hiloId);
    const escalada = String(detalle.herramienta ?? '') === 'escalar_urgencia';
    const nivel = escalada ? 1 : numeroOrNulo(detalle.nivel_urgencia);
    const centro = String(detalle.centro ?? '');

    porHilo.set(hiloId, {
      hiloId,
      slug: hiloId.split(':').slice(2).join(':') || hiloId,
      // Las filas llegan del más nuevo al más viejo, así que lo ya acumulado (`anterior`)
      // es siempre lo más reciente y manda. El evento viejo sólo rellena huecos: un
      // escalamiento no trae centro, y el `canalizar_caso` anterior del mismo hilo es
      // justo de dónde sacarlo sin que su nivel 2 pise el nivel 1 de la alarma.
      cuando: anterior?.cuando || String(fila.creado_en ?? ''),
      obtenido: {
        centro: anterior?.obtenido.centro || centro || '',
        nivel: anterior?.obtenido.nivel ?? nivel ?? null,
      },
      esperado: anterior?.esperado ?? null,
      coincide: anterior?.coincide ?? null,
      nota: anterior?.nota ?? '',
    });
  }

  // La valoración más reciente de cada hilo es la que vale: el profesional puede
  // corregir su criterio, y no hay forma de actualizar un evento ya escrito.
  const yaValorados = new Set<string>();
  for (const fila of ordenar(propios(valoraciones))) {
    const hiloId = String(fila.caso_id ?? '');
    const base = porHilo.get(hiloId);
    if (!hiloId || !base || yaValorados.has(hiloId)) continue;
    yaValorados.add(hiloId);

    const detalle = comoObjeto(fila.detalle);
    const esperado = comoObjeto(detalle.esperado);
    porHilo.set(hiloId, {
      ...base,
      esperado: {
        centro: String(esperado.centro ?? ''),
        nivel: numeroOrNulo(esperado.nivel),
      },
      coincide: esVerdad(detalle.coincide),
      nota: String(detalle.nota ?? ''),
    });
  }

  return [...porHilo.values()].sort((a, b) => b.cuando.localeCompare(a.cuando));
}

async function leerEventos(tipo: string): Promise<EventoCaso[]> {
  try {
    return (await roble.read('eventos', { tipo })) as EventoCaso[];
  } catch (error) {
    console.warn(`No se pudieron leer los eventos de tipo ${tipo}`, error);
    return [];
  }
}

/** Del más nuevo al más viejo, para que el primero de cada hilo sea el que manda. */
function ordenar(filas: EventoCaso[]): EventoCaso[] {
  return [...filas].sort((a, b) =>
    String(b.creado_en ?? '').localeCompare(String(a.creado_en ?? ''))
  );
}

function contar(historial: SimulacionGuardada[]): { valoradas: number; coincidieron: number } {
  const valoradas = historial.filter((fila) => fila.coincide !== null);
  return {
    valoradas: valoradas.length,
    coincidieron: valoradas.filter((fila) => fila.coincide === true).length,
  };
}

/**
 * Un `detalle` de `eventos`, que es una columna JSON.
 *
 * Según por dónde haya pasado la fila, ROBLE devuelve el objeto o su texto: lo escribe
 * la PWA con `create` y lo escribe el orquestador con la API de datos, y las dos rutas
 * no coinciden siempre. Se aceptan las dos formas y cualquier otra cosa se trata como
 * vacía, que es mejor que reventar la lista entera por una fila mal escrita.
 */
function comoObjeto(valor: unknown): Record<string, unknown> {
  if (typeof valor === 'string') {
    try {
      const datos: unknown = JSON.parse(valor);
      return datos && typeof datos === 'object' ? (datos as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }
  return valor && typeof valor === 'object' ? (valor as Record<string, unknown>) : {};
}

function numeroOrNulo(valor: unknown): number | null {
  const numero = Number(valor);
  return Number.isFinite(numero) && numero > 0 ? numero : null;
}
