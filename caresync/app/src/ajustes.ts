/**
 * Los ajustes de la plataforma: una tabla `clave`/`valor` y un catálogo cerrado.
 *
 * **La regla de este archivo: un ajuste sólo existe si algo lo lee.** Es fácil
 * llenar una pantalla de configuración con interruptores que no están conectados a
 * nada —se ven bien en una demostración y son mentira—, así que cada definición de
 * `CATALOGO` lleva escrito quién consume el valor, y ese campo se muestra en la
 * pantalla. Si algún día un ajuste se queda sin lector, se borra del catálogo.
 *
 * El valor se guarda **siempre como texto** aunque sea un número. La tabla tiene una
 * sola columna de valor y ROBLE devuelve los tipos como vengan de PostgreSQL; con
 * texto y una conversión explícita al leer no hay dudas sobre qué llega. La
 * validación de rango vive en `problemaDeAjuste` y se aplica antes de escribir.
 *
 * Si la tabla `ajustes` todavía no existe en el contrato, `leerAjustes` devuelve el
 * catálogo con sus valores predeterminados en vez de romper la aplicación: una
 * instalación sin ajustes es una instalación con los ajustes de fábrica. Crearla
 * está en docs/runbook-roble.md.
 */

import { DIAS_POR_DEFECTO } from './agenda_cupos';
import { roble } from './roble';
import { idDe, type Ajuste } from './tipos';

export interface DefinicionDeAjuste {
  clave: string;
  etiqueta: string;
  ayuda: string;
  /** Quién lee este valor en el código. Si nadie lo lee, el ajuste no debe existir. */
  loLee: string;
  tipo: 'numero' | 'texto';
  predeterminado: string;
  minimo?: number;
  maximo?: number;
  /** Longitud máxima para los de tipo texto. */
  largo?: number;
}

export const CATALOGO: readonly DefinicionDeAjuste[] = [
  {
    clave: 'dias_agenda',
    etiqueta: 'Días de agenda que publica cada tanda',
    ayuda:
      'Cuántos días hacia adelante abre el botón «Publicar cupos» del personal ' +
      'administrativo. Más días es más agenda abierta y más filas en ROBLE.',
    loLee: 'Administrativo.tsx → generarCupos()',
    tipo: 'numero',
    predeterminado: String(DIAS_POR_DEFECTO),
    minimo: 1,
    maximo: 60,
  },
  {
    clave: 'aviso_global',
    etiqueta: 'Aviso para todas las pantallas',
    ayuda:
      'Se muestra arriba de todo a cualquiera que entre, con el rol que sea. Vacío ' +
      'para no mostrar nada. Sirve para «el CMU no atiende el viernes», no para ' +
      'instrucciones permanentes.',
    loLee: 'App.tsx → <AvisoGlobal />',
    tipo: 'texto',
    predeterminado: '',
    largo: 240,
  },
];

export type Ajustes = Record<string, string>;

/** El catálogo tal cual, para cuando no hay tabla o no hay filas. */
export function ajustesDeFabrica(): Ajustes {
  const salida: Ajustes = {};
  for (const definicion of CATALOGO) salida[definicion.clave] = definicion.predeterminado;
  return salida;
}

/**
 * Lee la tabla y la mezcla sobre los valores de fábrica.
 *
 * Nunca lanza: un fallo de lectura —la tabla no existe, ROBLE está limitando— deja
 * la plataforma con sus valores predeterminados, que es un estado correcto. Lo que
 * no sería correcto es que una pantalla de agenda no cargue porque falta un ajuste.
 */
export async function leerAjustes(): Promise<Ajustes> {
  const salida = ajustesDeFabrica();
  try {
    const filas = (await roble.read('ajustes', {})) as Ajuste[];
    for (const fila of filas) {
      const clave = String(fila.clave ?? '').trim();
      if (clave && clave in salida) salida[clave] = String(fila.valor ?? '');
    }
  } catch (error) {
    console.warn('No se pudieron leer los ajustes; se usan los predeterminados', error);
  }
  return salida;
}

/**
 * Escribe un ajuste: actualiza su fila si existe y la crea si no.
 *
 * `update` sobre `ajustes` necesita el permiso `ajustes:update`, que en ROBLE vive
 * sólo en el rol `plataforma` — no en el `user` que hereda toda cuenta registrada, que
 * es justo lo que impide que un paciente cambie los ajustes de todos. Sin el permiso
 * la escritura falla con un 500 que se lee como «no me puedo conectar»; está anotado
 * en el runbook.
 */
export async function guardarAjuste(clave: string, valor: string, quien: string): Promise<void> {
  const existentes = (await roble.read('ajustes', { clave })) as Ajuste[];
  const datos = {
    clave,
    valor,
    actualizado_en: new Date().toISOString(),
    actualizado_por: quien,
  };
  const id = idDe(existentes[0]);
  if (id) {
    await roble.update('ajustes', id, datos);
  } else {
    await roble.create('ajustes', datos);
  }
}

export function numeroDeAjuste(ajustes: Ajustes, clave: string): number {
  const definicion = CATALOGO.find((entrada) => entrada.clave === clave);
  const numero = Number(ajustes[clave]);
  if (Number.isFinite(numero) && numero > 0) return numero;
  return Number(definicion?.predeterminado ?? 0);
}

export function textoDeAjuste(ajustes: Ajustes, clave: string): string {
  return String(ajustes[clave] ?? '').trim();
}

/** Lo que está mal con este valor, o `null` si se puede guardar. */
export function problemaDeAjuste(definicion: DefinicionDeAjuste, valor: string): string | null {
  if (definicion.tipo === 'numero') {
    const numero = Number(valor);
    if (!Number.isInteger(numero)) return 'Tiene que ser un número entero.';
    if (definicion.minimo !== undefined && numero < definicion.minimo) {
      return `El mínimo es ${definicion.minimo}.`;
    }
    if (definicion.maximo !== undefined && numero > definicion.maximo) {
      return `El máximo es ${definicion.maximo}.`;
    }
    return null;
  }
  if (definicion.largo !== undefined && valor.length > definicion.largo) {
    return `El máximo son ${definicion.largo} caracteres.`;
  }
  return null;
}
