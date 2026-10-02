/**
 * El hilo de un caso: una sola puerta para leerlo y dos formas de mirarlo.
 *
 * La tabla `conversaciones` guarda todo lo que se dijo alrededor de un caso: lo que
 * escribió la persona, lo que respondió cada agente, las notas `[sistema]` que deja
 * `_dejar_constancia_de_los_fallos` cuando una herramienta falla, y lo que el
 * personal del centro le preguntó al agente **sobre** ese caso. Quién mira decide
 * qué parte de eso tiene sentido mostrar, así que hay dos normalizaciones y no una:
 *
 * - `turnosParaLaPersona` es la del paciente, y **filtra**. Vivía privada en
 *   `Paciente.tsx` como `turnosDelHilo` y se mudó aquí sin tocarle una línea el día
 *   que apareció el segundo consumidor del hilo; su docstring explica qué se quita y
 *   por qué, y eso no ha cambiado.
 * - `hiloDeFilas` es la del profesional en el historial de triajes, y **no filtra
 *   por autor**: su trabajo es juzgar un triaje a partir de lo que de verdad se
 *   dijo, con las notas de fallo incluidas, porque una nota «no se completó la
 *   canalización» explica una respuesta del agente que de otro modo parece un error
 *   del modelo.
 *
 * Que las dos vivan en el mismo archivo no es casualidad: si cambia cómo el
 * orquestador marca el autor de una fila, las dos tienen que cambiar a la vez. Y
 * tener aquí también la lectura evita que cada vista se invente su propio filtro
 * contra `conversaciones`, que es como se separan dos pantallas que deberían contar
 * lo mismo.
 */

import { roble } from './roble';
import { idDe, type FilaConversacion, type Turno } from './tipos';

export interface TurnoDelHilo {
  id: string;
  /** 'personal' es el profesional o el administrativo que escribió sobre el caso. */
  quien: 'paciente' | 'agente' | 'sistema' | 'personal';
  /** El rol crudo de la fila, tal como lo escribió el orquestador. */
  autor: string;
  /** Clave del agente que respondió; cadena vacía si la fila no la trae. */
  agente: string;
  texto: string;
  /** El `creado_en` tal como vino de ROBLE. */
  cuando: string;
}

/**
 * Las filas tal cual, ordenadas y con cada turno marcado.
 *
 * El orden lo pone esta función porque ROBLE no ordena: `read` sólo compara por
 * igualdad y devuelve las filas como salgan. Ascendente, que es como se lee una
 * conversación.
 *
 * Lo único que no llega a la lista son las filas sin texto. No es un filtro de
 * contenido —el profesional tiene que ver todo lo que se dijo— sino de escrituras que
 * quedaron a medias: una burbuja vacía no informa de nada y se lee como un fallo de
 * la pantalla.
 *
 * Las filas anteriores a que el orquestador guardara el autor real llevan todas
 * `paciente`; ahí no hay nada que recuperar, y por eso `autor` viaja crudo en cada
 * turno: quien pinta puede decir «rol desconocido» en vez de afirmar quién habló.
 */
export function hiloDeFilas(filas: FilaConversacion[]): TurnoDelHilo[] {
  const ordenadas = [...filas].sort((a, b) =>
    String(a.creado_en ?? '').localeCompare(String(b.creado_en ?? ''))
  );

  const turnos: TurnoDelHilo[] = [];
  ordenadas.forEach((fila, indice) => {
    const texto = String(fila.contenido ?? '').trim();
    if (!texto) return;
    const autor = String(fila.autor ?? 'paciente');
    turnos.push({
      // Una fila a la que ROBLE no devolviera `_id` dejaría la clave de React vacía
      // y repetida, y React reutilizaría la burbuja equivocada al cambiar de caso.
      // El índice del orden ya calculado basta: es estable mientras la lista no se
      // vuelva a leer.
      id: idDe(fila) || `sin-id-${indice}`,
      quien: clasificar(autor),
      autor,
      agente: String(fila.agente ?? ''),
      texto,
      cuando: String(fila.creado_en ?? ''),
    });
  });
  return turnos;
}

/**
 * Quién escribió, en las cuatro categorías que la interfaz sabe pintar.
 *
 * `paciente`, `agente` y `sistema` los escribe el orquestador con esos nombres
 * exactos. Todo lo demás es personal del centro —`profesional`, `admin_cmu`,
 * `admin_cae`— y se agrupa en `personal`: para quien lee el hilo lo que importa es
 * que eso **no** lo dijo la persona atendida. El rol concreto sigue en `autor`.
 *
 * Un rol nuevo en el backend cae aquí en `personal` y no rompe la pantalla. Es la
 * dirección correcta del error: antes de inventar una categoría, tratarlo como lo
 * que seguro no es.
 */
function clasificar(autor: string): TurnoDelHilo['quien'] {
  if (autor === 'paciente') return 'paciente';
  if (autor === 'agente') return 'agente';
  if (autor === 'sistema') return 'sistema';
  return 'personal';
}

/**
 * El hilo de un caso, leído de ROBLE.
 *
 * Una sola lectura: `conversaciones` filtrada por `caso_id`. No hay paginación que
 * pedir —ROBLE no la tiene— así que el hilo llega entero y se recorta, si hay que
 * recortarlo, al pintarlo.
 *
 * No atrapa el fallo a propósito: quien llama es el que sabe si una pantalla sin hilo
 * todavía sirve. En el historial de triajes sí sirve —el resumen y la bitácora siguen
 * ahí—, y por eso ahí se envuelve en un `catch` con `console.warn`.
 */
export async function leerHilo(casoId: string): Promise<TurnoDelHilo[]> {
  const filas = (await roble.read('conversaciones', { caso_id: casoId })) as FilaConversacion[];
  return hiloDeFilas(filas);
}

/** Cuántos turnos anteriores se pintan al volver. El resto sigue en ROBLE. */
const TURNOS_PREVIOS = 30;

/**
 * Lo que la persona ve de su propio hilo al volver a entrar.
 *
 * Antes, recargar la página dejaba el chat con el saludo y nada más, aunque la
 * conversación estuviera entera en ROBLE: la persona tenía que recordar qué le había
 * dicho el agente, y el agente —que sí tiene el historial— le hablaba de cosas que ya
 * no estaban en pantalla.
 *
 * No se pinta todo lo que hay en la tabla, y lo que se quita es a propósito:
 *
 * - Las notas `[sistema]`, que son para el modelo («en el turno anterior no se
 *   completó…») y no se le dicen a la persona.
 * - Lo que el personal del centro o el profesional le escribió al agente sobre este
 *   caso, y lo que el agente les respondió. Es una conversación de trabajo sobre la
 *   persona, no con ella; mostrársela sería leerle las notas de otro.
 *
 * Las filas anteriores a que el orquestador guardara el autor real llevan todas
 * `paciente`, así que ahí no se puede distinguir. Es un caso viejo y acotado.
 */
export function turnosParaLaPersona(filas: FilaConversacion[]): Turno[] {
  const ordenadas = [...filas].sort((a, b) =>
    String(a.creado_en ?? '').localeCompare(String(b.creado_en ?? ''))
  );

  const turnos: Turno[] = [];
  let ultimoHumano = '';
  for (const fila of ordenadas) {
    const texto = String(fila.contenido ?? '').trim();
    const autor = String(fila.autor ?? 'paciente');
    if (!texto || autor === 'sistema') continue;

    if (autor === 'agente') {
      if (ultimoHumano === 'paciente') {
        turnos.push({ quien: 'agente', texto, ...(fila.agente ? { agentes: [fila.agente] } : {}) });
      }
      continue;
    }

    ultimoHumano = autor;
    if (autor === 'paciente') turnos.push({ quien: 'yo', texto });
  }
  return turnos.slice(-TURNOS_PREVIOS);
}
