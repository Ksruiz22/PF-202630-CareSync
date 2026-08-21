/**
 * La conversación con los agentes.
 *
 * Es el mismo componente para los cuatro roles: la diferencia de qué agente
 * responde y qué puede hacer la decide el backend. Duplicar el chat por rol
 * habría sido la forma más rápida de que las cuatro copias se separaran.
 *
 * Dos detalles que importan:
 *
 * **Las acciones se muestran.** Cuando el agente agenda una cita o escala una
 * urgencia, la persona ve una línea que lo dice. Un asistente que actúa sin
 * mostrar qué hizo no es auditable, y este sistema toca la atención en salud.
 *
 * **El aviso de que no es personal de salud está siempre visible**, no una vez al
 * empezar.
 */

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ErrorDelAgente, hablar } from '../agente';
import { nombreDeAgente } from '../formato';
import type { RespuestaAgente, Turno } from '../tipos';

const LIMITE = 2000;

interface Props {
  /** Caso sobre el que se conversa. Vacío en un paciente sin caso: lo abre el backend. */
  casoId?: string;
  agente?: 'triaje' | 'agenda' | 'seguimiento';
  saludo: string;
  /** Se llama tras cada turno para que la vista recargue lo que cambió en ROBLE. */
  alResponder?: (respuesta: RespuestaAgente) => void;
  alVencerSesion?: () => void;
}

export function Conversacion({ casoId, agente, saludo, alResponder, alVencerSesion }: Props) {
  const [turnos, setTurnos] = useState<Turno[]>([{ quien: 'agente', texto: saludo }]);
  const [borrador, setBorrador] = useState('');
  const [esperando, setEsperando] = useState(false);
  const [caso, setCaso] = useState(casoId ?? '');
  const fondo = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fondo.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turnos, esperando]);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    const mensaje = borrador.trim();
    if (!mensaje || esperando) return;

    setBorrador('');
    setTurnos((previos) => [...previos, { quien: 'yo', texto: mensaje }]);
    setEsperando(true);

    try {
      const respuesta = await hablar({
        mensaje,
        ...(caso ? { casoId: caso } : {}),
        ...(agente ? { agente } : {}),
      });

      // El caso lo asigna el backend en el primer turno; a partir de ahí se
      // manda para que un refresco del navegador no abra un caso nuevo.
      if (respuesta.caso?.id) setCaso(respuesta.caso.id);

      setTurnos((previos) => [
        ...previos,
        {
          quien: 'agente',
          texto: respuesta.respuesta || 'Sigo aquí, pero no supe qué responder.',
          agentes: respuesta.agentes,
          acciones: respuesta.acciones?.filter((a) => a.ok),
        },
      ]);
      alResponder?.(respuesta);
    } catch (fallo) {
      const esAgente = fallo instanceof ErrorDelAgente;
      if (esAgente && fallo.sesionVencida) {
        alVencerSesion?.();
      }
      setTurnos((previos) => [
        ...previos,
        {
          quien: 'sistema',
          texto: esAgente ? fallo.message : 'No se pudo enviar el mensaje.',
        },
      ]);
    } finally {
      setEsperando(false);
    }
  }

  return (
    <section className="conversacion" aria-label="Conversación con el asistente">
      <div className="hilo">
        {turnos.map((turno, indice) => (
          <Burbuja key={indice} turno={turno} />
        ))}
        {esperando && (
          <p className="burbuja agente pensando" aria-live="polite">
            <span className="punto" />
            <span className="punto" />
            <span className="punto" />
            <span className="lectores">El asistente está escribiendo</span>
          </p>
        )}
        <div ref={fondo} />
      </div>

      <form className="redactor" onSubmit={enviar}>
        <label className="lectores" htmlFor="mensaje">
          Escribe tu mensaje
        </label>
        <textarea
          id="mensaje"
          value={borrador}
          maxLength={LIMITE}
          rows={2}
          placeholder="Cuéntame qué te pasa…"
          onChange={(e) => setBorrador(e.target.value)}
          onKeyDown={(e) => {
            // Enter envía, Shift+Enter hace salto de línea: es lo que la gente
            // espera de un chat, y escribir párrafos aquí no es el caso de uso.
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void enviar(e as unknown as FormEvent);
            }
          }}
          disabled={esperando}
        />
        <button type="submit" disabled={esperando || !borrador.trim()}>
          {esperando ? 'Enviando…' : 'Enviar'}
        </button>
      </form>

      <p className="descargo">
        Esto es un prototipo académico. No reemplaza una consulta con personal de
        salud. Si es una urgencia, llama a la línea de emergencias del campus o al 123.
      </p>
    </section>
  );
}

function Burbuja({ turno }: { turno: Turno }) {
  const autor =
    turno.quien === 'yo'
      ? 'Tú'
      : turno.quien === 'sistema'
        ? 'CareSync'
        : turno.agentes?.length
          ? turno.agentes.map(nombreDeAgente).join(' → ')
          : 'Asistente';

  return (
    <div className={`burbuja ${turno.quien}`}>
      <span className="autor">{autor}</span>
      <p>{turno.texto}</p>
      {turno.acciones && turno.acciones.length > 0 && (
        <ul className="acciones" aria-label="Lo que hizo el asistente">
          {turno.acciones.map((accion, indice) => (
            <li key={indice}>{describir(accion.herramienta)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Qué se le dice a la persona que pasó.
 *
 * Los nombres de las herramientas son del catálogo del backend; mostrarlos crudos
 * («canalizar_caso») no le dice nada a nadie. Lo que no está en esta tabla no se
 * muestra: es mejor no decir nada que enseñar un identificador interno.
 */
function describir(herramienta: string): string {
  const textos: Record<string, string> = {
    canalizar_caso: 'Tu caso quedó canalizado al centro que corresponde',
    escalar_urgencia: 'Se activó la ruta de urgencias y se avisó al equipo',
    consultar_disponibilidad: 'Se revisaron los espacios disponibles',
    agendar_cita: 'Tu cita quedó agendada',
    notificar_profesional: 'El profesional ya tiene tu información',
    registrar_evolucion: 'Se registró cómo te sientes',
    registrar_adherencia: 'Se registró tu reporte del plan',
    consultar_plan: 'Se revisó tu plan',
    consultar_estado_caso: 'Se revisó el estado de tu caso',
  };
  return textos[herramienta] ?? 'Se registró una acción';
}
