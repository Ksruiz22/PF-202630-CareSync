/**
 * Las notificaciones del teléfono: **locales**, programadas en el propio aparato.
 *
 * No son push. Un push desde la Lambda necesitaría una tabla `dispositivos` y credenciales
 * de envío; las locales funcionan sin nada de eso y sin conexión, a cambio de que la
 * lista se renueva sólo cuando la app se abre. Por eso se programan varios días adelante.
 *
 * Cada sincronización borra y vuelve a programar: así una toma ya respondida o una
 * indicación que el profesional desactivó deja de sonar.
 */

import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import type { Aviso } from './avisos';

/** iOS deja 64 pendientes por app. Con esto sobra para tres días y no se llega al tope. */
const TOPE = 40;

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export async function hayPermiso(): Promise<boolean> {
  const { granted } = await Notifications.getPermissionsAsync();
  return granted;
}

export async function pedirPermiso(): Promise<boolean> {
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('recordatorios', {
      name: 'Recordatorios del plan',
      importance: Notifications.AndroidImportance.HIGH,
    });
  }
  const { granted } = await Notifications.requestPermissionsAsync();
  return granted;
}

export async function programar(avisos: Aviso[]): Promise<void> {
  if (!(await hayPermiso())) return;
  await Notifications.cancelAllScheduledNotificationsAsync();
  await Promise.all(
    avisos.slice(0, TOPE).map((aviso) =>
      Notifications.scheduleNotificationAsync({
        content: { title: aviso.titulo, body: aviso.cuerpo },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.DATE,
          date: aviso.momento,
          channelId: 'recordatorios',
        },
      })
    )
  );
}
