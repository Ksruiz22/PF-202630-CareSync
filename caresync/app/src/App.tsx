/**
 * El reparto por rol.
 *
 * No hay enrutador: no hay URLs que compartir ni navegación hacia atrás que
 * preservar. Lo que decide qué se ve es quién entró, y eso es un `switch`. Añadir
 * `react-router` para cinco pantallas sin rutas anidadas habría sido una
 * dependencia por costumbre.
 *
 * El rol de esta pantalla es sólo de presentación: **decide qué se muestra, no qué
 * se puede hacer**. Quién puede llamar a cada herramienta lo decide la Lambda contra
 * el rol del actor, y qué filas se pueden leer y escribir lo decide ROBLE.
 *
 * Durante un tiempo eso fue menos cierto de lo que parecía. `perfiles` es la fuente
 * del rol en las dos capas —`_resolver_actor` la prefiere sobre lo que declara ROBLE,
 * que es el cambio que hizo falta para que un rol asignado se aplicara de verdad— y
 * el rol `user` de ROBLE tenía `perfiles:update` sobre toda la tabla. Es decir:
 * cualquiera con sesión podía reescribir su propia fila desde la consola del
 * navegador y ascenderse.
 *
 * **Ya no.** `perfiles:update` vive sólo en el rol `plataforma` de ROBLE, que tienen
 * las cuentas administrativas; el rol `user` que hereda toda cuenta registrada no lo
 * tiene. Así que el `switch` de aquí abajo sigue siendo presentación, pero ahora la
 * fila que lo decide sólo la puede cambiar quien administra. El detalle está en
 * docs/runbook-roble.md.
 */

import type { ReactElement } from 'react';
import { AvisoGlobal } from './componentes/AvisoGlobal';
import { Cargando } from './componentes/Piezas';
import { useSesion } from './sesion';
import type { Rol } from './tipos';
import { Acceso } from './vistas/Acceso';
import { Administrativo } from './vistas/Administrativo';
import { Paciente } from './vistas/Paciente';
import { Plataforma } from './vistas/Plataforma';
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

  return (
    <>
      <AvisoGlobal />
      {vistaDeRol(quien.rol)}
    </>
  );
}

/**
 * El `switch` que era el cuerpo de `App`.
 *
 * Se separó al añadir el aviso global: la alternativa era repetir el fragmento con
 * `<AvisoGlobal />` en cada rama. `default` sigue siendo `Paciente` porque es el rol
 * menos privilegiado, así que un rol que no se reconozca degrada hacia abajo y no
 * hacia arriba.
 */
function vistaDeRol(rol: Rol): ReactElement {
  switch (rol) {
    case 'profesional':
      return <Profesional />;
    case 'admin_cmu':
    case 'admin_cae':
      return <Administrativo />;
    case 'admin_plataforma':
      return <Plataforma />;
    default:
      return <Paciente />;
  }
}
