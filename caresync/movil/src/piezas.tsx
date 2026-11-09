import { Children, Fragment, type ReactNode } from 'react';
import { Linking, Platform, Pressable, ScrollView, Text, View, type ScrollViewProps } from 'react-native';
import { estilosDe, F, S, T, useColores } from './tema';

/**
 * Una superficie con título. Se usa para lo que es una unidad propia —la próxima cita,
 * cómo te sientes—, no como contenedor por defecto: las listas van en `Seccion`.
 */
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
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: S.s }}>
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

/**
 * Una lista agrupada: el título va sobre el fondo y las filas en una sola superficie,
 * separadas por una línea fina. Es el patrón de lista de los ajustes del teléfono, que
 * la gente ya sabe leer. Antes cada grupo era una tarjeta con borde y título dentro, y
 * la pantalla se volvía una pila de cajas iguales donde nada pesaba más que nada.
 */
export function Seccion({ titulo, extra, children }: { titulo: string; extra?: ReactNode; children: ReactNode }) {
  const c = useColores();
  const e = estilosDe(c);
  const filas = Children.toArray(children).filter(Boolean);
  return (
    <View style={{ gap: S.s }}>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: S.s, paddingHorizontal: S.xs }}>
        <Text accessibilityRole="header" style={[e.seccion, { flexShrink: 1 }]}>
          {titulo}
        </Text>
        {extra}
      </View>
      <View style={[e.tarjeta, { paddingVertical: S.xs, gap: 0 }]}>
        {filas.map((fila, indice) => (
          <Fragment key={indice}>
            {indice > 0 ? <View style={e.separador} /> : null}
            <View style={{ paddingVertical: S.m }}>{fila}</View>
          </Fragment>
        ))}
      </View>
    </View>
  );
}

/**
 * Desactivado no es «el mismo botón más pálido»: con opacidad, un «Entrar» al 50 % se
 * leía como un fallo de color y no como «todavía no». Se pinta con el borde como fondo
 * y la tinta suave, que es como se ve cualquier cosa inactiva en la app.
 */
export function Boton({
  texto,
  alPulsar,
  suave,
  desactivado,
  compacto,
}: {
  texto: string;
  alPulsar: () => void;
  suave?: boolean;
  desactivado?: boolean;
  /** Para filas con varias acciones: 44 de alto, el mínimo táctil, en vez de 48. */
  compacto?: boolean;
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
        suave || desactivado ? e.botonSuave : e.boton,
        // Menos relleno lateral: en el horario de Hoy dos botones comparten el ancho
        // que dejan la columna de horas y el riel, y a 360 px partían el texto.
        compacto ? { minHeight: 44, paddingHorizontal: S.s } : null,
        desactivado ? { backgroundColor: c.borde } : null,
        { opacity: pressed ? 0.8 : 1 },
      ]}
    >
      <Text
        style={[
          suave ? e.textoBotonSuave : e.textoBoton,
          desactivado ? { color: c.tintaSuave } : null,
          compacto ? { fontSize: 15 } : null,
        ]}
      >
        {texto}
      </Text>
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
      <Text style={{ color: tinta, fontSize: T.pie, fontFamily: F.negrita }}>{texto}</Text>
    </View>
  );
}

/**
 * El mismo aviso que la PWA tiene arriba de la vista del paciente, siempre a la vista.
 *
 * En una línea y con el número como botón: antes ocupaba dos renglones en cada
 * pestaña, y en un teléfono saber a quién llamar sirve menos que poder llamar.
 */
export function AvisoEmergencia() {
  const c = useColores();
  return (
    <View
      accessibilityRole="alert"
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: S.s,
        backgroundColor: c.rojoClaro,
        paddingHorizontal: S.l,
        paddingVertical: S.xs,
      }}
    >
      <Text style={{ flex: 1, color: c.rojo, fontSize: T.pie, lineHeight: 18, fontFamily: F.regular }}>
        <Text style={{ fontFamily: F.negrita }}>¿En peligro inmediato?</Text> Llama al 123.
      </Text>
      <Pressable
        accessibilityRole="link"
        accessibilityLabel="Llamar al 123"
        onPress={() => void Linking.openURL('tel:123')}
        style={({ pressed }) => ({
          minHeight: 32,
          justifyContent: 'center',
          paddingHorizontal: S.m,
          borderRadius: 999,
          backgroundColor: c.rojo,
          opacity: pressed ? 0.8 : 1,
        })}
      >
        <Text style={{ color: c.rojoClaro, fontSize: T.pie, fontFamily: F.negrita }}>Llamar</Text>
      </Pressable>
    </View>
  );
}

/**
 * El `ScrollView` de cada pestaña. En el navegador se esconde la barra de desplazamiento:
 * la app se muestra del ancho de un teléfono y la barra de escritorio se metía entre
 * las tarjetas y el borde. En el teléfono queda la del sistema, que sólo aparece al
 * desplazar.
 */
export function Desplazable(props: ScrollViewProps & { children: ReactNode }) {
  return (
    <ScrollView
      showsVerticalScrollIndicator={Platform.OS !== 'web'}
      {...props}
      contentContainerStyle={[{ padding: S.l, gap: S.xl, paddingBottom: S.xxl }, props.contentContainerStyle]}
    />
  );
}
