/**
 * El arranque.
 *
 * `roble.ts` lanza una excepción al importarse si faltan las variables de
 * compilación, y esa excepción llegaría aquí como una pantalla en blanco. Por eso
 * el montaje va dentro de un `try`: una PWA mal compilada tiene que decir qué le
 * falta, no quedarse muda.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { ProveedorDeSesion } from './sesion';
import './estilos.css';

const raiz = document.getElementById('raiz');

if (!raiz) {
  throw new Error('No existe el elemento #raiz en index.html');
}

try {
  createRoot(raiz).render(
    <StrictMode>
      <ProveedorDeSesion>
        <App />
      </ProveedorDeSesion>
    </StrictMode>
  );
} catch (fallo) {
  raiz.innerHTML = '';
  const aviso = document.createElement('p');
  aviso.className = 'aviso error';
  // `textContent` y no `innerHTML`: el mensaje puede venir de un error con texto
  // arbitrario, y esta es justo la clase de descuido que abre un XSS en la única
  // parte de la aplicación que no pasa por React.
  aviso.textContent = fallo instanceof Error ? fallo.message : 'La aplicación no pudo arrancar.';
  raiz.appendChild(aviso);
  throw fallo;
}
