/**
 * La app del paciente para el tercer agente: seguir el tratamiento y recibir los
 * recordatorios. El triaje y la primera cita siguen empezando en la PWA; aquí aparecen
 * en cuanto hay un caso, para que la persona no tenga que cambiar de lugar para verlos.
 *
 * Como en la PWA, después de cada escritura se vuelve a leer de ROBLE: el agente escribe
 * en la base, no aquí, y es la única forma de que la pantalla no mienta.
 */

import {
  AtkinsonHyperlegible_400Regular,
  AtkinsonHyperlegible_700Bold,
  useFonts,
} from '@expo-google-fonts/atkinson-hyperlegible';
import Ionicons from '@expo/vector-icons/Ionicons';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, ScrollView, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { agenteParaMensaje } from './src/agenda';
import { avisosDe } from './src/avisos';
import { SesionVencida, type Fuente, type Reporte } from './src/fuente';
import { fuenteRoble, mensajeDeError } from './src/fuenteRoble';
import { programar } from './src/notificaciones';
import { Acceso } from './src/pantallas/Acceso';
import { Asistente } from './src/pantallas/Asistente';
import { Avisos } from './src/pantallas/Avisos';
import { Hoy, porResponder } from './src/pantallas/Hoy';
import { MiPlan } from './src/pantallas/MiPlan';
import { Aparece, DURACION } from './src/movimiento';
import { AvisoEmergencia, Boton, Etiqueta, Tarjeta } from './src/piezas';
import { estilosDe, F, useColores } from './src/tema';
import { idDe, type AgenteDestino, type Identidad, type Tratamiento, type Turno } from './src/tipos';

type Pestana = 'hoy' | 'plan' | 'avisos' | 'asistente';
type NombreDeIcono = keyof typeof Ionicons.glyphMap;

/** Con icono además del nombre: con sólo texto, la pestaña activa se distinguía apenas por una raya. */
const PESTANAS: { clave: Pestana; nombre: string; icono: NombreDeIcono; activo: NombreDeIcono }[] = [
  { clave: 'hoy', nombre: 'Hoy', icono: 'today-outline', activo: 'today' },
  { clave: 'plan', nombre: 'Mi plan', icono: 'clipboard-outline', activo: 'clipboard' },
  { clave: 'avisos', nombre: 'Avisos', icono: 'notifications-outline', activo: 'notifications' },
  { clave: 'asistente', nombre: 'Asistente', icono: 'chatbubbles-outline', activo: 'chatbubbles' },
];

export default function App() {
  const c = useColores();
  const [quien, setQuien] = useState<Identidad | null>(null);
  const [fuente, setFuente] = useState<Fuente>(fuenteRoble);
  const [arrancando, setArrancando] = useState(true);
  // Se espera a la fuente para no pintar la app dos veces: con la del sistema primero
  // y la propia un instante después, cada texto cambia de ancho y la pantalla salta.
  // Si no carga, `useFonts` devuelve un error y la app sigue con la del sistema.
  const [fuentesListas, errorDeFuentes] = useFonts({
    AtkinsonHyperlegible_400Regular,
    AtkinsonHyperlegible_700Bold,
  });

  useEffect(() => {
    void fuenteRoble
      .restaurar()
      .then(setQuien)
      .finally(() => setArrancando(false));
  }, []);

  const alSalir = useCallback(() => {
    void fuente.salir();
    setQuien(null);
    setFuente(fuenteRoble);
  }, [fuente]);

  const fase = arrancando || !(fuentesListas || errorDeFuentes) ? 'arranque' : quien ? 'sesion' : 'acceso';
  const contenido = fase === 'arranque' ? (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
      <ActivityIndicator color={c.primario} />
    </View>
  ) : quien ? (
    <Sesion quien={quien} fuente={fuente} alSalir={alSalir} />
  ) : (
    <Acceso
      alEntrar={(identidad, elegida) => {
        setFuente(elegida);
        setQuien(identidad);
      }}
    />
  );

  // El `SafeAreaView` de React Native sólo respeta los bordes en iOS: en Android la
  // barra de pestañas quedaba bajo la barra de gestos del sistema. El de
  // `safe-area-context` cubre los dos; el borde de abajo lo pone la barra de pestañas,
  // para que su fondo llegue hasta el filo de la pantalla.
  return (
    <SafeAreaProvider>
      <SafeAreaView edges={['top', 'left', 'right']} style={{ flex: 1, backgroundColor: c.papel }}>
        <StatusBar style="auto" />
        {/* En el navegador se muestra del ancho de un teléfono: es lo que se está probando. */}
        <View style={Platform.OS === 'web' ? { flex: 1, width: '100%', maxWidth: 480, alignSelf: 'center' } : { flex: 1 }}>
          {/* La app entra con un fundido al abrirse, y otra vez al pasar del acceso a
              la sesión o al salir: son cambios de lugar, no de pestaña. El indicador
              de carga no lo lleva, para no animar dos veces seguidas. */}
          {fase === 'arranque' ? (
            contenido
          ) : (
            <Aparece clave={fase} opacidadInicial={0} desde={0.97} duracion={DURACION.entrada} style={{ flex: 1 }}>
              {contenido}
            </Aparece>
          )}
        </View>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const TITULOS: Record<Pestana, string> = {
  hoy: 'CareSync',
  plan: 'Mi plan',
  avisos: 'Avisos',
  asistente: 'Asistente',
};

function Sesion({
  quien,
  fuente,
  alSalir,
}: {
  quien: Identidad;
  fuente: Fuente;
  alSalir: () => void;
}) {
  const c = useColores();
  const e = estilosDe(c);
  const abajo = useSafeAreaInsets().bottom;
  const [tratamientos, setTratamientos] = useState<Tratamiento[]>([]);
  const [casoId, setCasoId] = useState('');
  const [pestana, setPestana] = useState<Pestana>('hoy');
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');
  const [pensando, setPensando] = useState(false);
  const [errorChat, setErrorChat] = useState('');
  const [pendiente, setPendiente] = useState<Turno | null>(null);
  const [ahora, setAhora] = useState(() => new Date());

  const cargar = useCallback(async () => {
    try {
      const leidos = await fuente.tratamientos(quien);
      setTratamientos(leidos);
      setAhora(new Date());
      setError('');
    } catch (fallo) {
      if (fallo instanceof SesionVencida) alSalir();
      else setError(mensajeDeError(fallo));
    } finally {
      setCargando(false);
    }
  }, [fuente, quien, alSalir]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  // Con la app abierta, una toma tiene que pasar a «ya es hora» sin recargar.
  useEffect(() => {
    const reloj = setInterval(() => setAhora(new Date()), 60 * 1000);
    return () => clearInterval(reloj);
  }, []);

  // El caso con plan más reciente, porque esta app es para seguir un tratamiento. Sin
  // ninguno, el más reciente, para mostrar al menos en qué va.
  const actual = useMemo(
    () =>
      tratamientos.find((t) => idDe(t.caso) === casoId) ??
      tratamientos.find((t) => t.plan) ??
      tratamientos[0] ??
      null,
    [tratamientos, casoId]
  );

  const avisos = useMemo(() => avisosDe(tratamientos, ahora), [tratamientos, ahora]);
  const reprogramar = useCallback(() => {
    void programar(avisosDe(tratamientos, new Date())).catch((fallo) =>
      console.warn('No se pudieron programar los avisos', fallo)
    );
  }, [tratamientos]);
  useEffect(reprogramar, [reprogramar]);

  const reportar = useCallback(
    async (reporte: Omit<Reporte, 'tratamiento'>) => {
      if (!actual) return;
      await fuente.reportar(quien, { ...reporte, tratamiento: actual });
      await cargar();
    },
    [actual, fuente, quien, cargar]
  );

  const conversar = useCallback(
    (mensaje: string, agente?: AgenteDestino) => {
      if (!actual || pensando) return;
      setPestana('asistente');
      setPensando(true);
      setErrorChat('');
      setPendiente({ quien: 'yo', texto: mensaje });
      void fuente
        .hablar(mensaje, idDe(actual.caso), agente)
        .then(() => cargar())
        .catch((fallo) => {
          if (fallo instanceof SesionVencida) alSalir();
          else setErrorChat(mensajeDeError(fallo));
        })
        .finally(() => {
          setPendiente(null);
          setPensando(false);
        });
    },
    [actual, pensando, fuente, cargar, alSalir]
  );

  const turnos = actual ? [...actual.turnos, ...(pendiente ? [pendiente] : [])] : [];
  const pendientesHoy = actual ? porResponder(actual, ahora) : 0;

  // Una sola fila de cabecera, con el nombre de la pestaña. Antes eran tres bandas
  // fijas —emergencia en dos renglones, la franja de demostración y «CareSync / Hola»—
  // que se comían unos 160 px de cada pestaña y no decían en cuál se estaba. En Hoy la
  // cabecera sólo lleva la marca: el saludo es el panel de resumen de la pantalla.
  const titulo = TITULOS[pestana];

  return (
    <View style={{ flex: 1, backgroundColor: c.papel }}>
      <AvisoEmergencia />

      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingTop: 8, gap: 8 }}>
        <View style={{ flex: 1 }}>
          <Text
            accessibilityRole="header"
            numberOfLines={1}
            style={{ color: pestana === 'hoy' ? c.primario : c.tinta, fontSize: pestana === 'hoy' ? 20 : 26, fontFamily: F.negrita }}
          >
            {titulo}
          </Text>
        </View>
        {fuente.esDemo ? (
          <View accessibilityLabel="Demostración: datos de ejemplo, no se guarda nada en CareSync.">
            <Etiqueta tono="ambar" texto="Demostración" />
          </View>
        ) : null}
        <Pressable accessibilityRole="button" onPress={alSalir} style={{ minHeight: 44, justifyContent: 'center', paddingHorizontal: 8 }}>
          <Text style={{ color: c.primario, fontSize: 15, fontFamily: F.negrita }}>Salir</Text>
        </Pressable>
      </View>

      {tratamientos.length > 1 ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={{ flexGrow: 0 }}
          contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 10, gap: 8 }}
        >
          {tratamientos.map((tratamiento) => {
            const activo = idDe(tratamiento.caso) === idDe(actual?.caso);
            return (
              <Pressable
                key={idDe(tratamiento.caso)}
                accessibilityRole="button"
                accessibilityState={{ selected: activo }}
                onPress={() => setCasoId(idDe(tratamiento.caso))}
                style={{
                  minHeight: 36,
                  justifyContent: 'center',
                  borderRadius: 18,
                  paddingHorizontal: 12,
                  backgroundColor: activo ? c.primario : c.primarioSuave,
                }}
              >
                <Text style={{ color: activo ? c.sobrePrimario : c.primario, fontSize: 13, fontFamily: F.negrita }}>
                  {String(tratamiento.caso.motivo ?? 'Tu caso').slice(0, 28)}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
      ) : null}

      {error ? (
        <Text accessibilityRole="alert" style={{ color: c.rojo, fontSize: 14, fontFamily: F.regular, paddingHorizontal: 16, paddingTop: 8 }}>
          {error}
        </Text>
      ) : null}

      {/* Cada pestaña entra con un fade-through corto: ver `movimiento.tsx`. */}
      <Aparece clave={pestana} style={{ flex: 1 }}>
        {cargando ? (
          <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
            <ActivityIndicator color={c.primario} />
          </View>
        ) : !actual ? (
          <View style={{ padding: 16 }}>
            <Tarjeta titulo="Todavía no tienes un caso abierto">
              <Text style={e.texto}>
                Cuando necesites atención, empieza en la web de CareSync: allí el asistente te
                orienta y te conecta con el centro que corresponde. Tu tratamiento aparecerá aquí.
              </Text>
              <Boton suave texto="Volver a revisar" alPulsar={() => void cargar()} />
            </Tarjeta>
          </View>
        ) : pestana === 'hoy' ? (
          <Hoy
            nombre={primerNombre(quien.nombre)}
            tratamiento={actual}
            reportar={reportar}
            conversar={conversar}
            abrirAsistente={() => setPestana('asistente')}
            ahora={ahora}
          />
        ) : pestana === 'plan' ? (
          <MiPlan tratamiento={actual} conversar={conversar} ahora={ahora} />
        ) : pestana === 'avisos' ? (
          <Avisos avisos={avisos} alActivar={reprogramar} />
        ) : (
          <Asistente
            turnos={turnos}
            pensando={pensando}
            error={errorChat}
            enviar={(mensaje) => conversar(mensaje, agenteParaMensaje(actual))}
          />
        )}
      </Aparece>

      {actual ? (
        <View
          accessibilityRole="tablist"
          style={{
            flexDirection: 'row',
            borderTopWidth: 1,
            borderTopColor: c.borde,
            backgroundColor: c.papelAlto,
            paddingBottom: abajo,
          }}
        >
          {PESTANAS.map(({ clave, nombre, icono, activo }) => {
            const activa = pestana === clave;
            // El contador va en «Hoy»: es lo único que espera una respuesta de la
            // persona. Los avisos son futuros y no hay nada que «leer» en ellos.
            const cuenta = clave === 'hoy' ? pendientesHoy : 0;
            return (
              <Pressable
                key={clave}
                accessibilityRole="tab"
                accessibilityState={{ selected: activa }}
                accessibilityLabel={cuenta > 0 ? `${nombre}, ${cuenta} por responder` : nombre}
                onPress={() => setPestana(clave)}
                style={{ flex: 1, minHeight: 56, alignItems: 'center', justifyContent: 'center', gap: 2, paddingTop: 6 }}
              >
                <View
                  style={{
                    paddingHorizontal: 16,
                    paddingVertical: 2,
                    borderRadius: 999,
                    backgroundColor: activa ? c.primarioSuave : 'transparent',
                  }}
                >
                  <Ionicons name={activa ? activo : icono} size={22} color={activa ? c.primario : c.tintaSuave} />
                  {cuenta > 0 ? (
                    <View
                      style={{
                        position: 'absolute',
                        top: -2,
                        right: 6,
                        minWidth: 18,
                        height: 18,
                        borderRadius: 9,
                        paddingHorizontal: 4,
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: c.coral,
                      }}
                    >
                      <Text style={{ color: c.sobrePrimario, fontSize: 11, fontFamily: F.negrita }}>{cuenta}</Text>
                    </View>
                  ) : null}
                </View>
                <Text style={{ color: activa ? c.primario : c.tintaSuave, fontSize: 12, fontFamily: activa ? F.negrita : F.regular }}>
                  {nombre}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}
    </View>
  );
}

function primerNombre(nombre: string): string {
  const primero = nombre.trim().split(/\s+/)[0] ?? '';
  return primero.split('@')[0] || 'de nuevo';
}
