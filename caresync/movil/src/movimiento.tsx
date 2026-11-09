/**
 * El movimiento de la app: poco, rápido y siempre para explicar un cambio.
 *
 * Es una app de uso diario, así que el movimiento sirve a la respuesta y a la
 * continuidad, nunca a la decoración: nada de entradas escalonadas al abrir una
 * pantalla, que obligan a esperar algo que ya está ahí. Hay dos movimientos:
 *
 * - **Cambio de pestaña**: un *fade-through* corto (el patrón de Material para la
 *   barra de navegación inferior): la pestaña nueva aparece con opacidad y una escala
 *   mínima. Dice «esto es otra sección» sin deslizar, que sugeriría un orden que las
 *   pestañas no tienen.
 * - **Respuesta registrada**: el punto del horario se llena con un pequeño rebote y la
 *   etiqueta aparece. Es el momento de la app que vale la pena firmar: la persona ve
 *   su «lo hice» llegar a su lugar en el día.
 *
 * **«Reducir movimiento» se respeta**: sin escala ni rebote, sólo un cambio de
 * opacidad más corto, que sigue diciendo que algo cambió. En el navegador lo lee de
 * `prefers-reduced-motion`.
 *
 * `useNativeDriver` hace que la animación corra en el hilo de la interfaz y no se
 * trabe si JavaScript está ocupado; en la web no existe y se apaga.
 */

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { AccessibilityInfo, Animated, Easing, Platform, type StyleProp, type ViewStyle } from 'react-native';

/** Las duraciones de la guía de impeccable para pantallas de trabajo. */
export const DURACION = {
  /** Confirmar una acción: 100–150 ms. */
  respuesta: 140,
  /** Un cambio de estado o de vista rutinario: 150–300 ms. */
  cambio: 220,
  /**
   * Entrar a la app, o pasar del acceso a la sesión: 300–500 ms, el rango de una
   * transición de vista. Es la única entrada larga, y ocurre una vez por apertura.
   */
  entrada: 420,
} as const;

const NATIVO = Platform.OS !== 'web';
/** Salida exponencial: arranca rápido y se posa. La que la guía pide para entradas. */
const SALIDA = Easing.out(Easing.exp);

export function useMovimientoReducido(): boolean {
  const [reducido, setReducido] = useState(false);
  useEffect(() => {
    let vivo = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((valor) => vivo && setReducido(valor));
    const suscripcion = AccessibilityInfo.addEventListener('reduceMotionChanged', setReducido);
    return () => {
      vivo = false;
      suscripcion.remove();
    };
  }, []);
  return reducido;
}

/**
 * Hace aparecer su contenido cada vez que cambia `clave`. El contenido nunca empieza
 * invisible del todo: arranca en 0,4 de opacidad, así que si algo falla la pantalla se
 * ve igual, sólo que sin transición.
 */
export function Aparece({
  clave,
  desde = 0.98,
  opacidadInicial = 0.4,
  duracion = DURACION.cambio,
  style,
  children,
}: {
  clave: string;
  /** Escala inicial. 1 la apaga y deja sólo la opacidad. */
  desde?: number;
  /** 0 sólo para la entrada de la app, que parte de una pantalla vacía. */
  opacidadInicial?: number;
  duracion?: number;
  style?: StyleProp<ViewStyle>;
  children: ReactNode;
}) {
  const reducido = useMovimientoReducido();
  const avance = useRef(new Animated.Value(1)).current;

  // `useLayoutEffect` y no `useEffect`: con este último la pestaña nueva se pintaba un
  // cuadro a opacidad completa antes de que arrancara la animación, y se veía un
  // parpadeo (medido con Playwright: primer cuadro en 1, luego 0,58).
  useLayoutEffect(() => {
    avance.setValue(0);
    Animated.timing(avance, {
      toValue: 1,
      duration: reducido ? Math.round(duracion * 0.6) : duracion,
      easing: SALIDA,
      useNativeDriver: NATIVO,
      // La salida exponencial termina en 0,999, no en 1: sin esto la pestaña se quedaba
      // en escala 0,99998 y el texto podía verse apenas borroso.
    }).start(() => avance.setValue(1));
  }, [clave, reducido, duracion, avance]);

  const escala = reducido ? 1 : desde;
  return (
    <Animated.View
      style={[
        style,
        {
          opacity: avance.interpolate({ inputRange: [0, 1], outputRange: [opacidadInicial, 1] }),
          transform: [{ scale: avance.interpolate({ inputRange: [0, 1], outputRange: [escala, 1] }) }],
        },
      ]}
    >
      {children}
    </Animated.View>
  );
}

/**
 * Un pequeño rebote al aparecer, para la marca de «hecho». Con movimiento reducido,
 * sólo la opacidad.
 */
export function Rebote({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const reducido = useMovimientoReducido();
  const avance = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (reducido) {
      Animated.timing(avance, { toValue: 1, duration: DURACION.respuesta, useNativeDriver: NATIVO }).start();
    } else {
      Animated.spring(avance, { toValue: 1, friction: 5, tension: 160, useNativeDriver: NATIVO }).start();
    }
  }, [reducido, avance]);

  return (
    <Animated.View
      style={[
        style,
        {
          opacity: avance.interpolate({ inputRange: [0, 0.5, 1], outputRange: [0, 1, 1] }),
          transform: [{ scale: reducido ? 1 : avance.interpolate({ inputRange: [0, 1], outputRange: [0.4, 1] }) }],
        },
      ]}
    >
      {children}
    </Animated.View>
  );
}
