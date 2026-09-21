/**
 * Estado de sesión compartido: quién entró, y cómo entrar y salir.
 *
 * Un contexto de React y no una librería de estado: hay un solo dato global —la
 * identidad— y añadir una dependencia para eso sería peor que escribir veinte
 * líneas.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  completarGoogle,
  entrar as entrarEnRoble,
  esSesionInvalida,
  hayRegresoDeGoogle,
  haySesionGuardada,
  identidad,
  iniciarConGoogle,
  mensajeDeError,
  olvidarSesion,
  salir as salirDeRoble,
  type Identidad,
} from './roble';

interface Sesion {
  quien: Identidad | null;
  cargando: boolean;
  error: string;
  entrar: (email: string, password: string) => Promise<void>;
  /** Manda la pestaña a Google; si vuelve, vuelve por el efecto de más abajo. */
  entrarConGoogle: () => Promise<void>;
  salir: () => Promise<void>;
  /** Vuelve a leer la identidad; útil tras cambiar el perfil en ROBLE. */
  refrescar: () => Promise<void>;
}

const Contexto = createContext<Sesion | null>(null);

export function ProveedorDeSesion({ children }: { children: ReactNode }) {
  const [quien, setQuien] = useState<Identidad | null>(null);
  // Arranca en `true` sólo si hay algo que restaurar —o un regreso de Google que
  // canjear—: sin nada de eso, la pantalla de acceso tiene que aparecer de inmediato
  // y no tras un parpadeo.
  const [cargando, setCargando] = useState(haySesionGuardada() || hayRegresoDeGoogle());
  const [error, setError] = useState('');

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      setQuien(await identidad());
      setError('');
    } catch (fallo) {
      if (esSesionInvalida(fallo)) {
        // El token guardado ya no sirve y el refresco tampoco: se descarta en
        // silencio. Decirle «tu sesión venció» a quien acaba de abrir la
        // aplicación por primera vez en el día sería ruido.
        olvidarSesion();
        setQuien(null);
      } else {
        setError(mensajeDeError(fallo));
      }
    } finally {
      setCargando(false);
    }
  }, []);

  /**
   * El canje del regreso de Google, antes de que la pantalla de acceso pinte nada.
   *
   * `completarGoogle` memoriza su promesa, así que la segunda ejecución que hace
   * `StrictMode` en desarrollo espera el mismo resultado en vez de reintentar un
   * código ya gastado.
   */
  const completar = useCallback(async () => {
    setCargando(true);
    try {
      setQuien(await completarGoogle());
      setError('');
    } catch (fallo) {
      // Aquí sí se dice: la persona acaba de volver de Google esperando entrar.
      olvidarSesion();
      setQuien(null);
      setError(mensajeDeError(fallo));
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    // El regreso manda: trae una sesión nueva que sustituye a cualquier guardada.
    if (hayRegresoDeGoogle()) {
      void completar();
      return;
    }
    if (haySesionGuardada()) void cargar();
  }, [cargar, completar]);

  const valor = useMemo<Sesion>(
    () => ({
      quien,
      cargando,
      error,
      entrar: async (email, password) => {
        setCargando(true);
        setError('');
        try {
          setQuien(await entrarEnRoble(email, password));
        } catch (fallo) {
          olvidarSesion();
          setError(
            esSesionInvalida(fallo) ? 'Correo o contraseña incorrectos.' : mensajeDeError(fallo)
          );
          throw fallo;
        } finally {
          setCargando(false);
        }
      },
      entrarConGoogle: async () => {
        setCargando(true);
        setError('');
        try {
          await iniciarConGoogle();
          // Sin `setCargando(false)` a propósito: si esto no lanzó, la pestaña ya va
          // camino a Google y el botón debe quedarse quieto hasta que se vaya.
        } catch (fallo) {
          setError(mensajeDeError(fallo));
          setCargando(false);
          throw fallo;
        }
      },
      salir: async () => {
        await salirDeRoble();
        setQuien(null);
        setError('');
      },
      refrescar: cargar,
    }),
    [quien, cargando, error, cargar]
  );

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSesion(): Sesion {
  const sesion = useContext(Contexto);
  if (!sesion) throw new Error('useSesion se usó fuera de ProveedorDeSesion');
  return sesion;
}
