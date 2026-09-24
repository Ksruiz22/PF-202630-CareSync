/**
 * Piezas de interfaz que se repiten en las cinco vistas.
 *
 * Están juntas en un archivo porque son pequeñas y no tienen estado: repartirlas
 * en seis archivos de veinte líneas cada uno haría el árbol más difícil de leer,
 * no más fácil.
 */

import type { ReactNode } from 'react';
import { estadoLegible, nivelLegible } from '../formato';
import { IconoAlerta, IconoCheck } from './Iconos';

export function Aviso({
  tipo = 'info',
  children,
}: {
  tipo?: 'info' | 'exito' | 'error' | 'urgente';
  children: ReactNode;
}) {
  return (
    <p className={`aviso ${tipo}`} role={tipo === 'error' ? 'alert' : 'status'}>
      {(tipo === 'urgente' || tipo === 'error') && <IconoAlerta />}
      {tipo === 'exito' && <IconoCheck />}
      <span>{children}</span>
    </p>
  );
}

/**
 * El encabezado de pantalla: antetítulo opcional, título, subtítulo y un extra a la
 * derecha.
 *
 * El botón de salir vivía aquí y se mudó a la barra superior (`Marco.tsx`), que es
 * la misma para todos los roles. Las cuatro vistas por rol siguen usando esta pieza
 * para que un ajuste de estilo aplique a las cuatro a la vez.
 */
export function Cabecera({
  antetitulo,
  titulo,
  subtitulo,
  extra,
}: {
  antetitulo?: string;
  titulo: ReactNode;
  subtitulo?: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <header className="cabecera">
      <div>
        {antetitulo && <p className="antetitulo">{antetitulo}</p>}
        <h1>{titulo}</h1>
        {subtitulo && <p className="subtitulo">{subtitulo}</p>}
      </div>
      {extra}
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
  className,
  children,
}: {
  titulo: string;
  icono?: ReactNode;
  extra?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={className ? `tarjeta ${className}` : 'tarjeta'}>
      <header>
        <h2>
          {icono && <span className="icono-titulo">{icono}</span>}
          {titulo}
        </h2>
        {extra}
      </header>
      {children}
    </section>
  );
}

/** «Ana María Restrepo» → «AM». Ignora títulos con punto como «Dra.» o «Ps.». */
export function iniciales(texto: unknown, cuantas = 2): string {
  const palabras = String(texto ?? '')
    .split(/\s+/)
    .filter((palabra) => palabra && !/\.$/.test(palabra) && /^\p{L}/u.test(palabra));
  const salida = palabras
    .slice(0, cuantas)
    .map((palabra) => palabra[0]?.toUpperCase() ?? '')
    .join('');
  return salida || '?';
}
