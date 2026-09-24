/**
 * El marco de toda pantalla con sesión: la barra de arriba y el pie.
 *
 * Es igual para los cinco roles. La barra no tiene navegación entre vistas a
 * propósito: qué pantalla se ve lo decide el rol (ver `App.tsx`), así que un menú
 * con enlaces a las demás sería una promesa que la aplicación no cumple.
 */

import { rolLegible } from '../formato';
import { useSesion } from '../sesion';
import { IconoCorazon, IconoEscudo, IconoSalir } from './Iconos';
import { iniciales } from './Piezas';

export function Marca() {
  return (
    <span className="marca-app">
      <span className="marca-sello">
        <IconoCorazon width={20} height={20} />
      </span>
      <span>
        Care<span className="marca-acento">Sync</span>
      </span>
    </span>
  );
}

export function Barra() {
  const { quien, salir } = useSesion();
  const rol = rolLegible(quien?.rol) + (quien?.centro ? ` · ${quien.centro}` : '');

  return (
    <header className="barra">
      <div className="barra-interior">
        <Marca />
        <div className="usuario-barra">
          <span className="avatar" aria-hidden="true">
            {iniciales(quien?.nombre || quien?.email)}
          </span>
          <span className="usuario-texto">
            <strong>{quien?.nombre || quien?.email}</strong>
            <span>{rol}</span>
          </span>
          <button
            type="button"
            className="boton-icono"
            onClick={() => void salir()}
            title="Salir"
          >
            <IconoSalir width={17} height={17} />
            <span className="salir-texto">Salir</span>
          </button>
        </div>
      </div>
    </header>
  );
}

export function Pie() {
  return (
    <footer className="pie">
      <div className="pie-interior">
        <div>
          <Marca />
          <p>Orientación que te acompaña.</p>
        </div>
        <div className="pie-enlaces">
          <span>
            <IconoEscudo width={15} height={15} /> Prototipo académico
          </span>
          <span>Universidad del Norte · {new Date().getFullYear()}</span>
        </div>
      </div>
    </footer>
  );
}
