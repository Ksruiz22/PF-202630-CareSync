/**
 * El aviso que pone quien administra la plataforma, arriba de cualquier pantalla.
 *
 * Se monta una vez por sesión y hace **una** lectura de `ajustes`. Sin sondeo: un
 * aviso que aparece un minuto después de publicarse es suficiente para «el CMU no
 * atiende el viernes», y consultar cada treinta segundos gastaría el cubo de 100
 * peticiones por minuto de ROBLE en algo que casi siempre está vacío.
 *
 * Va después de la sesión y no en la pantalla de acceso a propósito: leer `ajustes`
 * necesita un token, así que antes de entrar no hay nada que mostrar.
 */

import { useEffect, useState } from 'react';
import { leerAjustes, textoDeAjuste } from '../ajustes';

export function AvisoGlobal() {
  const [texto, setTexto] = useState('');

  useEffect(() => {
    let vivo = true;
    void leerAjustes().then((ajustes) => {
      if (vivo) setTexto(textoDeAjuste(ajustes, 'aviso_global'));
    });
    return () => {
      vivo = false;
    };
  }, []);

  if (!texto) return null;

  return (
    <p className="aviso-global" role="status">
      {texto}
    </p>
  );
}
