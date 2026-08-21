/**
 * El reparto por rol.
 *
 * No hay enrutador: no hay URLs que compartir ni navegación hacia atrás que
 * preservar. Lo que decide qué se ve es quién entró, y eso es un `switch`. Añadir
 * `react-router` para cuatro pantallas sin rutas anidadas habría sido una
 * dependencia por costumbre.
 *
 * El rol de esta pantalla es sólo de presentación: **decide qué se muestra, no qué
 * se puede hacer**. Los permisos de verdad los aplica la Lambda de herramientas
 * contra el rol del token, y los de datos los aplica ROBLE. Si alguien manipulara
 * su fila de `perfiles` para verse el tablero del CMU, no conseguiría con eso ni
 * una lectura ni una llamada a una herramienta que no le corresponda.
 */

import { Cargando } from './componentes/Piezas';
import { useSesion } from './sesion';
import { Acceso } from './vistas/Acceso';
import { Administrativo } from './vistas/Administrativo';
import { Paciente } from './vistas/Paciente';
import { Profesional } from './vistas/Profesional';

export function App() {
  const { quien, cargando } = useSesion();

  if (!quien) {
    // Mientras se restaura una sesión guardada no se muestra el formulario: ver la
    // pantalla de acceso y que desaparezca sola un segundo después se lee como un
    // error de la aplicación.
    return cargando ? (
      <main className="arranque">
        <img src="/icono.svg" alt="" width={48} height={48} />
        <Cargando que="Recuperando tu sesión" />
      </main>
    ) : (
      <Acceso />
    );
  }

  switch (quien.rol) {
    case 'profesional':
      return <Profesional />;
    case 'admin_cmu':
    case 'admin_cae':
      return <Administrativo />;
    default:
      return <Paciente />;
  }
}
