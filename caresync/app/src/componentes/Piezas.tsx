/**
 * Piezas de interfaz que se repiten en las cinco vistas.
 *
 * Están juntas en un archivo porque son pequeñas y no tienen estado: repartirlas
 * en seis archivos de veinte líneas cada uno haría el árbol más difícil de leer,
 * no más fácil.
 */

import type { ReactNode } from 'react';
import { estadoLegible, nivelLegible } from '../formato';
import { IconoAlerta, IconoSalir } from './Iconos';

export function Aviso({
  tipo = 'info',
  children,
}: {
  tipo?: 'info' | 'error' | 'urgente';
  children: ReactNode;
}) {
  return (
    <p className={`aviso ${tipo}`} role={tipo === 'error' ? 'alert' : 'status'}>
      {tipo === 'urgente' && <IconoAlerta />}
      {children}
    </p>
  );
}

/**
 * La cabecera de pantalla: título, subtítulo opcional y el botón de salir.
 *
 * Las cuatro vistas por rol repetían este mismo bloque de forma idéntica. Vivir
 * en un solo sitio es lo que hace que un ajuste de estilo aplique a las cuatro a
 * la vez, en vez de arriesgarse a que una quede desalineada de las otras tres.
 */
export function Cabecera({
  titulo,
  subtitulo,
  onSalir,
}: {
  titulo: ReactNode;
  subtitulo?: ReactNode;
  onSalir: () => void;
}) {
  return (
    <header className="cabecera">
      <div>
        <h1>{titulo}</h1>
        {subtitulo && <p>{subtitulo}</p>}
      </div>
      <button type="button" className="secundario" onClick={onSalir}>
        <IconoSalir /> Salir
      </button>
    </header>
  );
}

export function Cargando({ que = 'Cargando' }: { que?: string }) {
  return (
    <p className="cargando" aria-live="polite">
      {que}…
    </p>
  );
}

export function Vacio({ children }: { children: ReactNode }) {
  return <p className="vacio">{children}</p>;
}

export function Etiqueta({ estado }: { estado: unknown }) {
  const clave = String(estado ?? 'sin_estado');
  return <span className={`etiqueta e-${clave}`}>{estadoLegible(clave)}</span>;
}

/**
 * El nivel de urgencia, con color.
 *
 * El 1 se ve distinto de los demás a propósito: en un tablero con veinte casos,
 * el que necesita atención ahora tiene que encontrarse sin leer.
 */
export function Nivel({ valor }: { valor: unknown }) {
  const numero = Number(valor);
  if (!numero) return <span className="nivel n-0">Sin clasificar</span>;
  return (
    <span className={`nivel n-${numero}`}>
      {numero === 1 && <IconoAlerta />}
      {nivelLegible(numero)}
    </span>
  );
}

export function Tarjeta({
  titulo,
  icono,
  extra,
  children,
}: {
  titulo: string;
  icono?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="tarjeta">
      <header>
        <h2>
          {icono}
          {titulo}
        </h2>
        {extra}
      </header>
      {children}
    </section>
  );
}
