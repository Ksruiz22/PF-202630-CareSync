/**
 * Registrar el plan: dictarlo o escribirlo de corrido, dejar que se ordene, revisar y
 * guardar.
 *
 * Dos pasos, y el segundo no se salta (RF-11: «con confirmación antes de guardar»):
 *
 * 1. **Lo que decidiste.** Un solo campo de texto libre, con dictado por voz. Se le
 *    habla como a un colega: qué se encontró, qué se indica y cada cuánto.
 * 2. **Revisa antes de guardar.** El resumen y las indicaciones ya separadas, cada una
 *    con su frecuencia, todo editable, con las dudas que dejó el modelo arriba y lo
 *    dictado a mano para comparar. Sólo aquí está el botón de guardar.
 *
 * El modelo ordena; no decide. Nada de lo que propone llega a ROBLE sin pasar por el
 * paso 2, y quien guarda es el profesional con su token (`alGuardar`, que es
 * `registrarPlan` en `Profesional.tsx`). Por eso se puede saltar el modelo entero con
 * «Llenarlo por partes»: el paso 2 vacío es el formulario de siempre.
 */

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { proponerPlan } from '../consulta';
import { dictar, sePuedeDictar, type Dictado, type EstadoDelDictado } from '../dictado';
import { EJEMPLOS_DE_FRECUENCIA, programaRecordatorios } from '../frecuencia';
import { mensajeDeError } from '../roble';
import { Aviso, Tarjeta } from './Piezas';
import { IconoChispas, IconoMas, IconoMicrofono, IconoPlan, IconoQuitar } from './Iconos';

export interface PlanAGuardar {
  resumen: string;
  indicaciones: Array<{ texto: string; frecuencia: string }>;
}

interface Fila {
  clave: number;
  texto: string;
  frecuencia: string;
}

interface Revision {
  resumen: string;
  filas: Fila[];
  dudas: string[];
  /** Lo dictado, para comparar con la propuesta. Vacío si se llenó por partes. */
  original: string;
}

const LIMITE_TEXTO = 6000;
let siguienteClave = 1;

function fila(texto = '', frecuencia = ''): Fila {
  return { clave: siguienteClave++, texto, frecuencia };
}

export function EditorDelPlan({
  hayPlan,
  alGuardar,
}: {
  hayPlan: boolean;
  alGuardar: (plan: PlanAGuardar) => Promise<void>;
}) {
  const [texto, setTexto] = useState('');
  const [revision, setRevision] = useState<Revision | null>(null);
  const [ordenando, setOrdenando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState('');

  async function ordenar() {
    setOrdenando(true);
    setError('');
    setAviso('');
    try {
      const propuesta = await proponerPlan(texto.trim());
      setRevision({
        resumen: propuesta.resumen,
        filas: propuesta.indicaciones.length
          ? propuesta.indicaciones.map((i) => fila(i.texto, i.frecuencia))
          : [fila()],
        dudas: propuesta.dudas,
        original: texto.trim(),
      });
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setOrdenando(false);
    }
  }

  function porPartes() {
    setError('');
    setAviso('');
    setRevision({ resumen: texto.trim(), filas: [fila()], dudas: [], original: '' });
  }

  async function guardar(evento: FormEvent) {
    evento.preventDefault();
    if (!revision) return;
    const indicaciones = revision.filas
      .map((f) => ({ texto: f.texto.trim(), frecuencia: f.frecuencia.trim() }))
      .filter((f) => f.texto);

    if (!revision.resumen.trim() || indicaciones.length === 0) {
      setError('Hace falta el resumen y al menos una indicación.');
      return;
    }

    setGuardando(true);
    setError('');
    try {
      await alGuardar({ resumen: revision.resumen.trim(), indicaciones });
      setRevision(null);
      setTexto('');
      setAviso('Plan registrado. El agente de seguimiento ya puede acompañar este caso.');
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setGuardando(false);
    }
  }

  const titulo = hayPlan ? 'Nuevo plan' : 'Registrar el plan';

  if (!revision) {
    return (
      <Tarjeta titulo={titulo} icono={<IconoPlan />}>
        <div className="formulario">
          <label htmlFor="plan-libre">Lo que decidiste en la consulta</label>
          <textarea
            id="plan-libre"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={7}
            maxLength={LIMITE_TEXTO}
            placeholder={
              'Como se lo contarías a un colega: qué encontraste, qué le indicas y cada cuánto.\n' +
              'Por ejemplo: «Faringitis viral, sin signos de alarma. Acetaminofén de 500 cada 8 horas por tres días, ' +
              'gárgaras con agua tibia tres veces al día y control en dos semanas.»'
            }
          />
          <Dictador alTexto={(trozo) => setTexto((actual) => juntar(actual, trozo).slice(0, LIMITE_TEXTO))} />

          <p className="fino">
            El asistente separa el resumen y las indicaciones, cada una con su frecuencia. No
            añade nada que no hayas dicho, y tú lo revisas antes de guardar.
          </p>

          <div className="botonera">
            <button
              type="button"
              className="principal"
              disabled={ordenando || !texto.trim()}
              onClick={() => void ordenar()}
            >
              <IconoChispas width={17} height={17} />
              {ordenando ? 'Ordenando…' : 'Ordenar en un plan'}
            </button>
            <button type="button" className="enlace" disabled={ordenando} onClick={porPartes}>
              Llenarlo por partes
            </button>
          </div>

          {aviso && <Aviso tipo="exito">{aviso}</Aviso>}
          {error && <Aviso tipo="error">{error}</Aviso>}
        </div>
      </Tarjeta>
    );
  }

  const actualizarFila = (clave: number, cambios: Partial<Fila>) =>
    setRevision({
      ...revision,
      filas: revision.filas.map((f) => (f.clave === clave ? { ...f, ...cambios } : f)),
    });

  return (
    <Tarjeta titulo={`${titulo}: revisa antes de guardar`} icono={<IconoPlan />}>
      <form className="formulario revision-plan" onSubmit={guardar}>
        {revision.dudas.length > 0 && (
          <div className="dudas" role="status">
            <p>
              <strong>Antes de guardar, revisa esto:</strong>
            </p>
            <ul>
              {revision.dudas.map((duda) => (
                <li key={duda}>{duda}</li>
              ))}
            </ul>
          </div>
        )}

        <label>
          Resumen de la consulta
          <textarea
            value={revision.resumen}
            onChange={(e) => setRevision({ ...revision, resumen: e.target.value })}
            rows={4}
            maxLength={2000}
            placeholder="Qué se encontró y qué se decidió."
            required
          />
        </label>

        <fieldset className="indicaciones-editables">
          <legend>Indicaciones</legend>
          <ol>
            {revision.filas.map((f, posicion) => (
              <li key={f.clave}>
                <label>
                  <span className="lectores">Indicación {posicion + 1}</span>
                  <input
                    type="text"
                    value={f.texto}
                    onChange={(e) => actualizarFila(f.clave, { texto: e.target.value })}
                    maxLength={500}
                    placeholder="Qué hacer, con dosis y duración"
                  />
                </label>
                <label>
                  <span className="lectores">Frecuencia de la indicación {posicion + 1}</span>
                  <input
                    type="text"
                    value={f.frecuencia}
                    onChange={(e) => actualizarFila(f.clave, { frecuencia: e.target.value })}
                    maxLength={60}
                    placeholder="cada 8 horas"
                  />
                </label>
                <button
                  type="button"
                  className="icono-solo"
                  aria-label={`Quitar la indicación ${posicion + 1}`}
                  title="Quitar"
                  onClick={() =>
                    setRevision({ ...revision, filas: revision.filas.filter((x) => x.clave !== f.clave) })
                  }
                >
                  <IconoQuitar width={16} height={16} />
                </button>
                <AyudaDeFrecuencia frecuencia={f.frecuencia} />
              </li>
            ))}
          </ol>
          <button
            type="button"
            className="enlace"
            onClick={() => setRevision({ ...revision, filas: [...revision.filas, fila()] })}
          >
            <IconoMas width={15} height={15} /> Añadir indicación
          </button>
          <p className="fino">
            Los recordatorios salen entre las 7:00 y las 20:00, hora de Bogotá. Frecuencias que se
            entienden: {EJEMPLOS_DE_FRECUENCIA.map((e) => `«${e}»`).join(', ')}.
          </p>
        </fieldset>

        {revision.original && (
          <details className="original">
            <summary>Lo que dictaste</summary>
            <p>{revision.original}</p>
          </details>
        )}

        <div className="botonera">
          <button type="submit" className="principal" disabled={guardando}>
            {guardando ? 'Guardando…' : 'Guardar plan y cerrar la consulta'}
          </button>
          <button
            type="button"
            className="enlace"
            disabled={guardando}
            onClick={() => {
              if (revision.original) setTexto(revision.original);
              setRevision(null);
            }}
          >
            Volver al texto
          </button>
        </div>

        {error && <Aviso tipo="error">{error}</Aviso>}
      </form>
    </Tarjeta>
  );
}

/** Qué va a pasar con los recordatorios de esta indicación, dicho antes de guardar. */
function AyudaDeFrecuencia({ frecuencia }: { frecuencia: string }) {
  if (!frecuencia.trim()) {
    return <p className="fino ayuda-frecuencia">Sin frecuencia: se hace una vez y no se recuerda.</p>;
  }
  if (programaRecordatorios(frecuencia)) return null;
  return (
    <p className="ayuda-frecuencia problema">
      Esta frecuencia no la entiende el sistema y no va a generar recordatorios. Escríbela como
      «cada 8 horas», «2 veces al día» o «diario».
    </p>
  );
}

/**
 * El botón de dictar, con lo que se va oyendo debajo.
 *
 * Sólo entrega al formulario los trozos finales (`alTexto`); el parcial, que todavía
 * cambia, se pinta aparte en gris. Si se desmonta a medio dictado —el profesional
 * cambia de cita—, cierra el micrófono: un micrófono abierto en segundo plano es lo
 * último que debería dejar una pantalla clínica.
 */
function Dictador({ alTexto }: { alTexto: (trozo: string) => void }) {
  const [estado, setEstado] = useState<EstadoDelDictado>('detenido');
  const [parcial, setParcial] = useState('');
  const [error, setError] = useState('');
  const dictado = useRef<Dictado | null>(null);
  const alTextoActual = useRef(alTexto);
  alTextoActual.current = alTexto;

  useEffect(
    () => () => {
      void dictado.current?.detener();
    },
    []
  );

  if (!sePuedeDictar()) {
    return (
      <p className="fino">
        Este navegador no permite dictar aquí. Con Chrome, Edge, Firefox o Safari recientes, y la
        página en https, aparece el botón de dictado.
      </p>
    );
  }

  async function empezar() {
    setError('');
    try {
      dictado.current = await dictar({
        alParcial: setParcial,
        alFinal: (trozo) => alTextoActual.current(trozo),
        alEstado: (nuevo) => {
          setEstado(nuevo);
          if (nuevo === 'detenido') dictado.current = null;
        },
        alError: setError,
      });
    } catch (fallo) {
      setEstado('detenido');
      setError(fallo instanceof Error ? fallo.message : mensajeDeError(fallo));
    }
  }

  const activo = estado === 'escuchando' || estado === 'conectando';

  return (
    <div className="dictado">
      <button
        type="button"
        className={activo ? 'secundario grabando' : 'secundario'}
        aria-pressed={activo}
        disabled={estado === 'terminando'}
        onClick={() => (activo ? void dictado.current?.detener() : void empezar())}
      >
        <IconoMicrofono width={17} height={17} />
        {estado === 'conectando'
          ? 'Conectando…'
          : estado === 'escuchando'
            ? 'Detener el dictado'
            : estado === 'terminando'
              ? 'Terminando…'
              : 'Dictar'}
      </button>
      <span className="estado-dictado" aria-live="polite">
        {estado === 'escuchando' && (parcial ? <em>{parcial}</em> : 'Escuchando…')}
      </span>
      {error && <Aviso tipo="error">{error}</Aviso>}
    </div>
  );
}

function juntar(actual: string, trozo: string): string {
  if (!actual) return trozo;
  return /\s$/.test(actual) ? actual + trozo : `${actual} ${trozo}`;
}
