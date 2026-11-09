/**
 * El sistema visual de la app. El tono de marca es el de `app/src/estilos.css`: es el
 * mismo CareSync en otra pantalla. Lo demás está escrito para el teléfono; el porqué
 * de cada decisión está en `movil/DESIGN.md`.
 *
 * **Una sola familia, Atkinson Hyperlegible**, en regular y negrita. Está diseñada
 * para que no se confundan letras parecidas (I, l, 1; O, 0), que es justo lo que pide
 * leer una dosis o una hora al sol. Con una fuente cargada, `fontWeight` no sirve: el
 * navegador inventa una negrita falsa y Android la ignora. Por eso el peso va siempre
 * en `fontFamily`, con `F.regular` o `F.negrita`, y nunca con `fontWeight`.
 */

import { StyleSheet, useColorScheme } from 'react-native';

export const F = {
  regular: 'AtkinsonHyperlegible_400Regular',
  negrita: 'AtkinsonHyperlegible_700Bold',
} as const;

/** Escala de 1,2 entre pasos: la que impeccable recomienda para pantallas de trabajo. */
export const T = {
  pie: 13,
  fino: 14,
  texto: 16,
  titulo: 19,
  pantalla: 26,
} as const;

/** Ritmo de 4/8: todo margen y separación sale de aquí. */
export const S = { xs: 4, s: 8, m: 12, l: 16, xl: 24, xxl: 32 } as const;

const claro = {
  tinta: '#0f2a2b',
  tintaSuave: '#4a6362',
  // El fondo es un gris verdoso frío, no crema: la app se mira al sol, y un fondo
  // claro y neutro deja que las superficies blancas se separen sin bordes.
  papel: '#eef3f2',
  papelAlto: '#ffffff',
  borde: '#d9e4e1',
  primario: '#0b6e69',
  primarioSuave: '#e0efec',
  sobrePrimario: '#ffffff',
  verde: '#1d6643',
  verdeClaro: '#e0f2e8',
  // Para la marca de «resuelto» sobre el panel de color de marca: `verdeClaro` es casi
  // blanco y ahí no se leía como verde.
  verdeVivo: '#a7e9c3',
  sobreVerdeVivo: '#14532f',
  ambar: '#74500f',
  ambarClaro: '#faefd4',
  coral: '#a8401f',
  coralClaro: '#fbe5db',
  rojo: '#a51f1f',
  rojoClaro: '#fbe8e8',
  sombra: '#0f2a2b',
};

export type Colores = typeof claro;

const oscuro: Colores = {
  tinta: '#e3efec',
  tintaSuave: '#a3bbb6',
  papel: '#0c1817',
  papelAlto: '#142423',
  borde: '#26403d',
  primario: '#5cc8bf',
  primarioSuave: '#17312f',
  sobrePrimario: '#0c1817',
  verde: '#7fd3a6',
  verdeClaro: '#16342a',
  verdeVivo: '#14532f',
  sobreVerdeVivo: '#a7e9c3',
  ambar: '#e3b863',
  ambarClaro: '#2c2415',
  coral: '#f0a083',
  coralClaro: '#3a2119',
  rojo: '#f3a3a3',
  rojoClaro: '#3a1b1b',
  sombra: '#000000',
};

export function useColores(): Colores {
  return useColorScheme() === 'dark' ? oscuro : claro;
}

export function estilosDe(c: Colores) {
  return StyleSheet.create({
    /** La superficie blanca sobre el fondo. Sin borde: la separa el contraste y una sombra corta. */
    tarjeta: {
      backgroundColor: c.papelAlto,
      borderRadius: 16,
      padding: S.l,
      gap: S.m,
      shadowColor: c.sombra,
      shadowOpacity: 0.06,
      shadowRadius: 8,
      shadowOffset: { width: 0, height: 2 },
      elevation: 1,
    },
    tituloTarjeta: { color: c.tinta, fontSize: T.titulo, lineHeight: 24, fontFamily: F.negrita },
    /** El título de una sección que no es una tarjeta: va sobre el fondo, encima de su lista. */
    seccion: { color: c.tinta, fontSize: T.titulo, lineHeight: 24, fontFamily: F.negrita },
    texto: { color: c.tinta, fontSize: T.texto, lineHeight: 23, fontFamily: F.regular },
    fuerte: { color: c.tinta, fontSize: T.texto, lineHeight: 23, fontFamily: F.negrita },
    fino: { color: c.tintaSuave, fontSize: T.fino, lineHeight: 20, fontFamily: F.regular },
    pie: { color: c.tintaSuave, fontSize: T.pie, lineHeight: 18, fontFamily: F.regular },
    boton: {
      backgroundColor: c.primario,
      borderRadius: 12,
      minHeight: 48,
      paddingHorizontal: S.l,
      alignItems: 'center',
      justifyContent: 'center',
    },
    textoBoton: { color: c.sobrePrimario, fontSize: T.texto, fontFamily: F.negrita },
    botonSuave: {
      backgroundColor: c.primarioSuave,
      borderRadius: 12,
      minHeight: 48,
      paddingHorizontal: S.l,
      alignItems: 'center',
      justifyContent: 'center',
    },
    textoBotonSuave: { color: c.primario, fontSize: T.texto, fontFamily: F.negrita },
    campo: {
      backgroundColor: c.papelAlto,
      borderColor: c.borde,
      borderWidth: 1,
      borderRadius: 12,
      minHeight: 48,
      paddingHorizontal: S.m,
      paddingVertical: 10,
      color: c.tinta,
      fontSize: T.texto,
      fontFamily: F.regular,
    },
    separador: { height: StyleSheet.hairlineWidth, backgroundColor: c.borde },
  });
}
