/**
 * Piezas de interfaz que se repiten en las cinco vistas.
 *
 * Están juntas en un archivo porque son pequeñas y no tienen estado: repartirlas
 * en seis archivos de veinte líneas cada uno haría el árbol más difícil de leer,
 * no más fácil.
 */

import type { ReactNode } from 'react';
import { estadoLegible, nivelLegible } from '../formato';

export function Aviso({
  tipo = 'info',
  children,
}: {
  tipo?: 'info' | 'error' | 'urgente';
  children: ReactNode;
}) {
  return (
    <p className={`aviso ${tipo}`} role={tipo === 'error' ? 'alert' : 'status'}>
      {children}
    </p>
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
  return <span className={`nivel n-${numero}`}>{nivelLegible(numero)}</span>;
}

export function Tarjeta({
  titulo,
  extra,
  children,
}: {
  titulo: string;
  extra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="tarjeta">
      <header>
        <h2>{titulo}</h2>
        {extra}
      </header>
      {children}
    </section>
  );
}
