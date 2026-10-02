/**
 * El hilo de un caso en sólo lectura, para quien no participó en él.
 *
 * Es el gemelo de `Conversacion.tsx` sin redactor y sin estado: aquí nadie escribe.
 * Se parecen a propósito —las mismas clases del chat, las mismas burbujas— porque el
 * profesional que abre un caso en el historial de triajes tiene que reconocer de un
 * vistazo que está viendo la conversación que tuvo la persona, no un informe sobre
 * ella. Duplicar el chat con otro aspecto habría hecho dudar de si es lo mismo.
 *
 * Tres decisiones que no son cosméticas:
 *
 * **Las burbujas del paciente van del lado de «la otra persona»**, el mismo de las
 * respuestas del agente en el chat del paciente, y nunca del lado de `yo`. Quien mira
 * esta pantalla no escribió ninguna de estas líneas, y el lado de `yo` significa
 * exactamente eso en las otras cuatro vistas.
 *
 * **Las notas `[sistema]` se muestran y se marcan como internas.** Son las que deja
 * `_dejar_constancia_de_los_fallos` cuando una herramienta no completó su efecto, y
 * sin ellas una respuesta del agente parece un error del modelo cuando en realidad
 * está reaccionando a un fallo de escritura. Pero nunca se le dijeron a la persona, y
 * leerlas como parte de la conversación sería atribuirle al agente algo que no dijo:
 * de ahí el rótulo.
 *
 * **No hay forma de escribir.** Si el profesional quiere dejar algo registrado, lo
 * hace en el plan o hablando con el agente desde su pantalla, que es lo que queda en
 * la bitácora. Un campo de texto aquí habría creado un canal de notas clínicas sin
 * trazabilidad, que es justo lo que el resto del sistema evita.
 */

import type { ReactElement } from 'react';
import { Cargando, Vacio } from './Piezas';
import { fechaHora, nombreDeAgente, rolLegible } from '../formato';
import type { TurnoDelHilo } from '../conversaciones';

export function HiloDeCaso({
  turnos,
  cargando,
}: {
  turnos: TurnoDelHilo[];
  cargando?: boolean;
}): ReactElement {
  if (cargando) {
    return (
      <div className="hilo hilo-lectura">
        <Cargando que="Cargando la conversación" />
      </div>
    );
  }

  if (turnos.length === 0) {
    return (
      <Vacio>
        Este caso no tiene conversación guardada. Pasa con los casos que el personal del
        centro abrió a mano y con los que se crearon antes de que el orquestador
        empezara a guardar el hilo.
      </Vacio>
    );
  }

  // `role="region"` con nombre, y `tabIndex` para que se pueda desplazar con el
  // teclado: `.hilo` tiene alto fijo y desborda, así que sin un contenedor enfocable la
  // transcripción —el contenido largo de la pestaña— queda inalcanzable sin ratón. El
  // papel de región la convierte además en un punto de referencia al que un lector de
  // pantalla salta sin recorrer antes la lista de casos.
  return (
    <div
      className="hilo hilo-lectura"
      aria-label="Conversación completa del caso, en sólo lectura"
      tabIndex={0}
      role="region"
    >
      {turnos.map((turno) => (
        <Burbuja key={turno.id} turno={turno} />
      ))}
    </div>
  );
}

function Burbuja({ turno }: { turno: TurnoDelHilo }): ReactElement {
  return (
    <div className={clase(turno)}>
      <span className="autor">{autorVisible(turno)}</span>
      <p>{turno.texto}</p>
      {turno.cuando ? (
        <time className="fino hilo-hora" dateTime={turno.cuando}>
          {fechaHora(turno.cuando)}
        </time>
      ) : (
        <span className="fino hilo-hora">sin fecha</span>
      )}
    </div>
  );
}

/**
 * Las clases del chat más una propia por tipo de turno.
 *
 * Las del chat hacen el trabajo visible —`burbuja`, y `sistema` para el recuadro
 * ámbar— y las `hilo-*` son el añadido de esta pantalla. Están pensadas para que la
 * pantalla siga siendo legible si todavía no tienen CSS: sin ellas todo queda como
 * una burbuja de «la otra persona», que es lo correcto aunque se distinga peor.
 */
function clase(turno: TurnoDelHilo): string {
  if (turno.quien === 'sistema') return 'burbuja sistema hilo-nota';
  if (turno.quien === 'agente') return 'burbuja agente hilo-agente';
  if (turno.quien === 'personal') return 'burbuja hilo-personal';
  return 'burbuja hilo-paciente';
}

/**
 * Quién habló, dicho para alguien que no estaba en la conversación.
 *
 * El nombre del agente sale de `nombreDeAgente` y no de la clave cruda: «seguimiento»
 * no le dice a nadie que ese turno lo contestó el agente de Seguimiento, y el nombre
 * legible es el mismo que ve el paciente en su chat.
 *
 * Al personal se le nombra por su rol legible y no como «Equipo»: en un hilo donde
 * aparecen el profesional y la administración del centro, saber cuál de los dos
 * escribió es parte de lo que se está revisando.
 */
function autorVisible(turno: TurnoDelHilo): string {
  if (turno.quien === 'paciente') return 'Paciente';
  if (turno.quien === 'agente') {
    return turno.agente ? nombreDeAgente(turno.agente) : 'Asistente';
  }
  if (turno.quien === 'sistema') {
    // El rótulo entero va aquí porque `.autor` ya existe y se ve: una línea más
    // dentro de la burbuja se habría leído como parte de la nota.
    return 'Nota interna · no se le mostró a la persona';
  }
  return turno.autor ? rolLegible(turno.autor) : 'Personal del centro';
}
