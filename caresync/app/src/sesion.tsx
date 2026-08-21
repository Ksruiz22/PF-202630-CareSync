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
  entrar as entrarEnRoble,
  esSesionInvalida,
  haySesionGuardada,
  identidad,
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
  salir: () => Promise<void>;
  /** Vuelve a leer la identidad; útil tras cambiar el perfil en ROBLE. */
  refrescar: () => Promise<void>;
}

const Contexto = createContext<Sesion | null>(null);

export function ProveedorDeSesion({ children }: { children: ReactNode }) {
  const [quien, setQuien] = useState<Identidad | null>(null);
  // Arranca en `true` sólo si hay algo que restaurar: sin sesión guardada, la
  // pantalla de acceso tiene que aparecer de inmediato y no tras un parpadeo.
  const [cargando, setCargando] = useState(haySesionGuardada());
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

  useEffect(() => {
    if (haySesionGuardada()) void cargar();
  }, [cargar]);

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
