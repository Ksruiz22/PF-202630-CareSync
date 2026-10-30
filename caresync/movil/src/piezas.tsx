import type { ReactNode } from 'react';
import { Pressable, Text, View } from 'react-native';
import { estilosDe, useColores } from './tema';

export function Tarjeta({
  titulo,
  extra,
  children,
}: {
  titulo?: string;
  extra?: ReactNode;
  children: ReactNode;
}) {
  const c = useColores();
  const e = estilosDe(c);
  return (
    <View style={e.tarjeta}>
      {titulo ? (
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <Text accessibilityRole="header" style={[e.tituloTarjeta, { flexShrink: 1 }]}>
            {titulo}
          </Text>
          {extra}
        </View>
      ) : null}
      {children}
    </View>
  );
}

export function Boton({
  texto,
  alPulsar,
  suave,
  desactivado,
}: {
  texto: string;
  alPulsar: () => void;
  suave?: boolean;
  desactivado?: boolean;
}) {
  const c = useColores();
  const e = estilosDe(c);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!desactivado }}
      disabled={desactivado}
      onPress={alPulsar}
      style={({ pressed }) => [
        suave ? e.botonSuave : e.boton,
        { opacity: desactivado ? 0.5 : pressed ? 0.8 : 1 },
      ]}
    >
      <Text style={suave ? e.textoBotonSuave : e.textoBoton}>{texto}</Text>
    </Pressable>
  );
}

type Tono = 'verde' | 'ambar' | 'coral' | 'neutro';

export function Etiqueta({ texto, tono = 'neutro' }: { texto: string; tono?: Tono }) {
  const c = useColores();
  const colores: Record<Tono, [string, string]> = {
    verde: [c.verdeClaro, c.verde],
    ambar: [c.ambarClaro, c.ambar],
    coral: [c.coralClaro, c.coral],
    neutro: [c.primarioSuave, c.primario],
  };
  const [fondo, tinta] = colores[tono];
  return (
    <View style={{ backgroundColor: fondo, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3 }}>
      <Text style={{ color: tinta, fontSize: 12, fontWeight: '600' }}>{texto}</Text>
    </View>
  );
}

/** El mismo aviso que la PWA tiene arriba de la vista del paciente, siempre a la vista. */
export function AvisoEmergencia() {
  const c = useColores();
  return (
    <View
      accessibilityRole="alert"
      style={{ backgroundColor: c.rojoClaro, paddingHorizontal: 16, paddingVertical: 8 }}
    >
      <Text style={{ color: c.rojo, fontSize: 13, lineHeight: 18 }}>
        <Text style={{ fontWeight: '700' }}>¿Estás en peligro inmediato? </Text>
        Llama a la línea de emergencias del campus o al 123.
      </Text>
    </View>
  );
}
