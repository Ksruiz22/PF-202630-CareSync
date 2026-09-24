/**
 * Los iconos de la interfaz, dibujados en línea.
 *
 * Cero dependencia externa: una librería de iconos por una veintena de símbolos
 * habría pesado más que todo `estilos.css`. Los trazos siguen la geometría de
 * Lucide (24×24, trazo redondeado), que es la que usó el rediseño. Heredan el color
 * del texto (`currentColor`) y siempre llevan tamaño explícito —nunca un `<svg>` sin
 * `width`/`height`, que el navegador expande a 300×150 por defecto.
 *
 * Un icono nunca es la única señal: en cada sitio donde se usan acompañan texto
 * o un color que ya existía, no lo reemplazan.
 */

import type { ReactNode, SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement>;

function Base({ children, className, ...props }: Props & { children: ReactNode }) {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className ? `icono ${className}` : 'icono'}
      {...props}
    >
      {children}
    </svg>
  );
}

export function IconoSalir(props: Props) {
  return (
    <Base {...props}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5" />
      <path d="M21 12H9" />
    </Base>
  );
}

export function IconoAlerta(props: Props) {
  return (
    <Base {...props}>
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </Base>
  );
}

export function IconoCalendario(props: Props) {
  return (
    <Base {...props}>
      <rect x="3" y="4" width="18" height="17" rx="2" />
      <path d="M16 2v4M8 2v4M3 9h18" />
    </Base>
  );
}

export function IconoLapiz(props: Props) {
  return (
    <Base {...props}>
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      <path d="M15 5l4 4" />
    </Base>
  );
}

export function IconoAjustes(props: Props) {
  return (
    <Base {...props}>
      <circle cx="12" cy="12" r="3" />
      <path
        d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34
           1.7 1.7 0 0 0-1.04 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.96 19.9a1.7 1.7 0 0 0-1.87.34
           l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.04H3a2 2 0 1 1 0-4h.09
           A1.7 1.7 0 0 0 4.6 8.96a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34
           H9a1.7 1.7 0 0 0 1.04-1.56V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.04 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06
           a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.56 1.04H21a2 2 0 1 1 0 4h-.09
           A1.7 1.7 0 0 0 19.4 15Z"
      />
    </Base>
  );
}

/** La marca: un corazón con pulso. */
export function IconoCorazon(props: Props) {
  return (
    <Base {...props}>
      <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
      <path d="M3.22 12H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27" />
    </Base>
  );
}

export function IconoUsuarios(props: Props) {
  return (
    <Base {...props}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </Base>
  );
}

export function IconoEstetoscopio(props: Props) {
  return (
    <Base {...props}>
      <path d="M11 2v2M5 2v2M5 3H4a2 2 0 0 0-2 2v4a6 6 0 0 0 12 0V5a2 2 0 0 0-2-2h-1" />
      <path d="M8 15a6 6 0 0 0 12 0v-3" />
      <circle cx="20" cy="10" r="2" />
    </Base>
  );
}

export function IconoBuscar(props: Props) {
  return (
    <Base {...props}>
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </Base>
  );
}

export function IconoMas(props: Props) {
  return (
    <Base {...props}>
      <path d="M5 12h14" />
      <path d="M12 5v14" />
    </Base>
  );
}

export function IconoReloj(props: Props) {
  return (
    <Base {...props}>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v6l4 2" />
    </Base>
  );
}

export function IconoFlechaAbajo(props: Props) {
  return (
    <Base {...props}>
      <path d="m6 9 6 6 6-6" />
    </Base>
  );
}

export function IconoFlechaDerecha(props: Props) {
  return (
    <Base {...props}>
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </Base>
  );
}

export function IconoCheck(props: Props) {
  return (
    <Base {...props}>
      <path d="M20 6 9 17l-5-5" />
    </Base>
  );
}

export function IconoEnviar(props: Props) {
  return (
    <Base {...props}>
      <path d="m22 2-7 20-4-9-9-4Z" />
      <path d="M22 2 11 13" />
    </Base>
  );
}

export function IconoEscudo(props: Props) {
  return (
    <Base {...props}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
      <path d="m9 12 2 2 4-4" />
    </Base>
  );
}

export function IconoChispas(props: Props) {
  return (
    <Base {...props}>
      <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" />
    </Base>
  );
}

export function IconoDocumento(props: Props) {
  return (
    <Base {...props}>
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5Z" />
      <path d="M14 2v6h6" />
      <path d="M16 13H8M16 17H8" />
    </Base>
  );
}

export function IconoPlan(props: Props) {
  return (
    <Base {...props}>
      <rect x="8" y="2" width="8" height="4" rx="1" />
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <path d="M12 11h4M12 16h4M8 11h.01M8 16h.01" />
    </Base>
  );
}

export function IconoTendencia(props: Props) {
  return (
    <Base {...props}>
      <path d="M22 7 13.5 15.5 8.5 10.5 2 17" />
      <path d="M16 7h6v6" />
    </Base>
  );
}

export function IconoMensaje(props: Props) {
  return (
    <Base {...props}>
      <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />
    </Base>
  );
}

export function IconoCampana(props: Props) {
  return (
    <Base {...props}>
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
      <path d="M4 2C2.8 3.7 2 5.7 2 8M22 8c0-2.3-.8-4.3-2-6" />
    </Base>
  );
}

export function IconoAyuda(props: Props) {
  return (
    <Base {...props}>
      <circle cx="12" cy="12" r="10" />
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
      <path d="M12 17h.01" />
    </Base>
  );
}
