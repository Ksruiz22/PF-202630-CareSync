/**
 * Dónde viven los dos tokens en el teléfono: el llavero del sistema.
 *
 * Metro elige `almacen.web.ts` al compilar para el navegador. Aquí no hay `localStorage`,
 * y `AsyncStorage` sería texto plano en el disco de un teléfono que se puede perder.
 */

import * as SecureStore from 'expo-secure-store';

export const almacen = {
  leer: (clave: string): Promise<string | null> => SecureStore.getItemAsync(clave),
  guardar: (clave: string, valor: string): Promise<void> => SecureStore.setItemAsync(clave, valor),
  borrar: (clave: string): Promise<void> => SecureStore.deleteItemAsync(clave),
};
