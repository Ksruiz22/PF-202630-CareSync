/** En el navegador, lo mismo que la PWA: `localStorage`, con su misma consecuencia. */
export const almacen = {
  leer: async (clave: string): Promise<string | null> => localStorage.getItem(clave),
  guardar: async (clave: string, valor: string): Promise<void> => localStorage.setItem(clave, valor),
  borrar: async (clave: string): Promise<void> => localStorage.removeItem(clave),
};
