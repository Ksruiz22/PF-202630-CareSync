/**
 * La app del paciente para el tercer agente: seguir el tratamiento y recibir los
 * recordatorios. El triaje y la primera cita siguen empezando en la PWA; aquí aparecen
 * en cuanto hay un caso, para que la persona no tenga que cambiar de lugar para verlos.
 *
 * Como en la PWA, después de cada escritura se vuelve a leer de ROBLE: el agente escribe
 * en la base, no aquí, y es la única forma de que la pantalla no mienta.
 */

import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, SafeAreaView, ScrollView, Text, View } from 'react-native';
import { agenteParaMensaje } from './src/agenda';
import { avisosDe } from './src/avisos';
import { SesionVencida, type Fuente, type Reporte } from './src/fuente';
import { fuenteRoble, mensajeDeError } from './src/fuenteRoble';
import { programar } from './src/notificaciones';
import { Acceso } from './src/pantallas/Acceso';
import { Asistente } from './src/pantallas/Asistente';
import { Avisos } from './src/pantallas/Avisos';
import { Hoy } from './src/pantallas/Hoy';
import { MiPlan } from './src/pantallas/MiPlan';
import { AvisoEmergencia, Boton, Tarjeta } from './src/piezas';
import { estilosDe, useColores } from './src/tema';
import { idDe, type AgenteDestino, type Identidad, type Tratamiento, type Turno } from './src/tipos';

type Pestana = 'hoy' | 'plan' | 'avisos' | 'asistente';

const PESTANAS: { clave: Pestana; nombre: string }[] = [
  { clave: 'hoy', nombre: 'Hoy' },
  { clave: 'plan', nombre: 'Mi plan' },
  { clave: 'avisos', nombre: 'Avisos' },
  { clave: 'asistente', nombre: 'Asistente' },
];

export default function App() {
  const c = useColores();
  const [quien, setQuien] = useState<Identidad | null>(null);
  const [fuente, setFuente] = useState<Fuente>(fuenteRoble);
  const [arrancando, setArrancando] = useState(true);

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

  const contenido = arrancando ? (
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

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: c.papel }}>
      <StatusBar style="auto" />
      {/* En el navegador se muestra del ancho de un teléfono: es lo que se está probando. */}
      <View style={Platform.OS === 'web' ? { flex: 1, width: '100%', maxWidth: 480, alignSelf: 'center' } : { flex: 1 }}>
        {contenido}
      </View>
    </SafeAreaView>
  );
}

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

  return (
    <View style={{ flex: 1, backgroundColor: c.papel }}>
      <AvisoEmergencia />
      {fuente.esDemo ? (
        <View style={{ backgroundColor: c.ambarClaro, paddingHorizontal: 16, paddingVertical: 6 }}>
          <Text style={{ color: c.ambar, fontSize: 13 }}>
            Demostración: datos de ejemplo, no se guarda nada en CareSync.
          </Text>
        </View>
      ) : null}

      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingTop: 12, gap: 8 }}>
        <View style={{ flex: 1 }}>
          <Text style={e.fino}>CareSync</Text>
          <Text accessibilityRole="header" style={{ color: c.tinta, fontSize: 22, fontWeight: '700' }}>
            Hola, {primerNombre(quien.nombre)}
          </Text>
        </View>
        <Pressable accessibilityRole="button" onPress={alSalir} style={{ minHeight: 44, justifyContent: 'center', paddingHorizontal: 8 }}>
          <Text style={{ color: c.primario, fontSize: 14, fontWeight: '600' }}>Salir</Text>
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
                <Text style={{ color: activo ? c.sobrePrimario : c.primario, fontSize: 13, fontWeight: '600' }}>
                  {String(tratamiento.caso.motivo ?? 'Tu caso').slice(0, 28)}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
      ) : null}

      {error ? (
        <Text accessibilityRole="alert" style={{ color: c.rojo, fontSize: 14, paddingHorizontal: 16, paddingTop: 8 }}>
          {error}
        </Text>
      ) : null}

      <View style={{ flex: 1 }}>
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
      </View>

      {actual ? (
        <View
          accessibilityRole="tablist"
          style={{ flexDirection: 'row', borderTopWidth: 1, borderTopColor: c.borde, backgroundColor: c.papelAlto }}
        >
          {PESTANAS.map(({ clave, nombre }) => {
            const activa = pestana === clave;
            return (
              <Pressable
                key={clave}
                accessibilityRole="tab"
                accessibilityState={{ selected: activa }}
                onPress={() => setPestana(clave)}
                style={{
                  flex: 1,
                  minHeight: 52,
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderTopWidth: 2,
                  borderTopColor: activa ? c.primario : 'transparent',
                }}
              >
                <Text style={{ color: activa ? c.primario : c.tintaSuave, fontSize: 13, fontWeight: '600' }}>
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
