/**
 * En el navegador sólo hay avisos mientras la pestaña esté abierta. Sirve para probar
 * desde el computador; en el teléfono manda `notificaciones.ts`.
 */

import type { Aviso } from './avisos';

/** `setTimeout` no aguanta más de ~24 días, y el navegador tampoco pasa de esta sesión. */
const HORIZONTE = 24 * 60 * 60 * 1000;

let relojes: ReturnType<typeof setTimeout>[] = [];

const disponible = () => typeof Notification !== 'undefined';

export async function hayPermiso(): Promise<boolean> {
  return disponible() && Notification.permission === 'granted';
}

export async function pedirPermiso(): Promise<boolean> {
  if (!disponible()) return false;
  return (await Notification.requestPermission()) === 'granted';
}

export async function programar(avisos: Aviso[]): Promise<void> {
  relojes.forEach(clearTimeout);
  relojes = [];
  if (!(await hayPermiso())) return;
  const ahora = Date.now();
  for (const aviso of avisos) {
    const espera = aviso.momento.getTime() - ahora;
    if (espera <= 0 || espera > HORIZONTE) continue;
    relojes.push(
      setTimeout(() => new Notification(aviso.titulo, { body: aviso.cuerpo }), espera)
    );
  }
}
