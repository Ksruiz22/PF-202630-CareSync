/** Los mismos colores que `app/src/estilos.css`: es el mismo CareSync en otra pantalla. */

import { StyleSheet, useColorScheme } from 'react-native';

const claro = {
  tinta: '#12302f',
  tintaSuave: '#52706f',
  papel: '#f1f8f5',
  papelAlto: '#ffffff',
  borde: '#d4e6e1',
  primario: '#0f7470',
  primarioSuave: '#e6f2ef',
  sobrePrimario: '#ffffff',
  verde: '#1f6b45',
  verdeClaro: '#e2f4ea',
  ambar: '#7a5410',
  ambarClaro: '#fbf0d6',
  coral: '#a4492c',
  coralClaro: '#fbe6dc',
  rojo: '#a51f1f',
  rojoClaro: '#fbe8e8',
};

export type Colores = typeof claro;

const oscuro: Colores = {
  tinta: '#e3efec',
  tintaSuave: '#9bb5b0',
  papel: '#0d1a19',
  papelAlto: '#142524',
  borde: '#24403d',
  primario: '#5cc8bf',
  primarioSuave: '#183230',
  sobrePrimario: '#0d1a19',
  verde: '#7fd3a6',
  verdeClaro: '#17352a',
  ambar: '#e3b863',
  ambarClaro: '#2c2415',
  coral: '#ec9c7e',
  coralClaro: '#35201a',
  rojo: '#f09a9a',
  rojoClaro: '#361a1a',
};

export function useColores(): Colores {
  return useColorScheme() === 'dark' ? oscuro : claro;
}

export function estilosDe(c: Colores) {
  return StyleSheet.create({
    tarjeta: {
      backgroundColor: c.papelAlto,
      borderColor: c.borde,
      borderWidth: 1,
      borderRadius: 16,
      padding: 16,
      gap: 10,
    },
    tituloTarjeta: { color: c.tinta, fontSize: 17, fontWeight: '700' },
    texto: { color: c.tinta, fontSize: 15, lineHeight: 21 },
    fino: { color: c.tintaSuave, fontSize: 13, lineHeight: 18 },
    boton: {
      backgroundColor: c.primario,
      borderRadius: 12,
      minHeight: 44,
      paddingHorizontal: 16,
      alignItems: 'center',
      justifyContent: 'center',
    },
    textoBoton: { color: c.sobrePrimario, fontSize: 15, fontWeight: '600' },
    botonSuave: {
      backgroundColor: c.primarioSuave,
      borderRadius: 12,
      minHeight: 44,
      paddingHorizontal: 16,
      alignItems: 'center',
      justifyContent: 'center',
    },
    textoBotonSuave: { color: c.primario, fontSize: 15, fontWeight: '600' },
    campo: {
      backgroundColor: c.papelAlto,
      borderColor: c.borde,
      borderWidth: 1,
      borderRadius: 12,
      minHeight: 44,
      paddingHorizontal: 12,
      paddingVertical: 10,
      color: c.tinta,
      fontSize: 15,
    },
  });
}
