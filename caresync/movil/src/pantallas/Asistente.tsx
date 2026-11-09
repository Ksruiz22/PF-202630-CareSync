/**
 * La conversación con el agente. Todo lo que no es un sí o un no pasa por aquí: cómo se
 * siente, una duda, una señal de alarma, cambiar una cita. A qué agente va lo decide
 * `agenteParaMensaje`, y por qué casi siempre no se sugiere ninguno está ahí.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { Boton } from '../piezas';
import { estilosDe, F, T, useColores } from '../tema';
import type { Turno } from '../tipos';

/**
 * Para empezar sin tener que inventar la primera frase. Son de seguimiento a propósito:
 * la conversación sin agente elegido va al de seguimiento cuando hay plan
 * (`agenteParaMensaje`), y cambiar una cita ya tiene su botón en «Hoy», que la manda
 * al de agenda.
 */
const SUGERENCIAS = [
  'Me siento mejor que ayer',
  'Tengo una duda sobre lo que me indicaron',
  'Me está costando seguir el plan',
  'Me apareció un síntoma nuevo',
];

export function Asistente({
  turnos,
  pensando,
  error,
  enviar,
}: {
  turnos: Turno[];
  pensando: boolean;
  error: string;
  enviar: (mensaje: string) => void;
}) {
  const c = useColores();
  const e = estilosDe(c);
  const [mensaje, setMensaje] = useState('');
  const lista = useRef<ScrollView>(null);

  useEffect(() => {
    lista.current?.scrollToEnd({ animated: false });
  }, [turnos.length, pensando]);

  function mandar() {
    const texto = mensaje.trim();
    if (!texto || pensando) return;
    setMensaje('');
    enviar(texto);
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={100}
      style={{ flex: 1 }}
    >
      <ScrollView
        ref={lista}
        style={{ flex: 1 }}
        showsVerticalScrollIndicator={Platform.OS !== 'web'}
        contentContainerStyle={[{ padding: 16, gap: 8 }, turnos.length === 0 ? { flexGrow: 1, justifyContent: 'center' } : null]}
        accessibilityLiveRegion="polite"
      >
        {/* Antes, una línea de texto arriba y la pantalla en blanco: no quedaba claro
            qué se podía preguntar ni que lo lee el profesional. */}
        {turnos.length === 0 ? (
          <View style={{ alignItems: 'center', gap: 12 }}>
            <View
              style={{
                width: 56,
                height: 56,
                borderRadius: 28,
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: c.primarioSuave,
              }}
            >
              <Ionicons name="chatbubbles" size={26} color={c.primario} />
            </View>
            <Text style={{ color: c.tinta, fontSize: T.titulo, fontFamily: F.negrita, textAlign: 'center' }}>
              Cuéntame cómo vas
            </Text>
            <Text style={[e.fino, { textAlign: 'center', maxWidth: 300 }]}>
              No soy personal de salud: lo que me cuentas lo lee tu profesional. Si es una
              emergencia, llama al 123.
            </Text>
            <View style={{ alignSelf: 'stretch', gap: 8, marginTop: 4 }}>
              {SUGERENCIAS.map((sugerencia) => (
                <Pressable
                  key={sugerencia}
                  accessibilityRole="button"
                  disabled={pensando}
                  onPress={() => enviar(sugerencia)}
                  style={({ pressed }) => ({
                    minHeight: 44,
                    justifyContent: 'center',
                    paddingHorizontal: 14,
                    borderRadius: 12,
                    backgroundColor: c.papelAlto,
                    opacity: pressed ? 0.8 : 1,
                  })}
                >
                  <Text style={{ color: c.primario, fontSize: T.texto, fontFamily: F.negrita }}>{sugerencia}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        ) : null}
        {turnos.map((turno, indice) => (
          <View
            key={indice}
            style={{
              alignSelf: turno.quien === 'yo' ? 'flex-end' : 'flex-start',
              maxWidth: '85%',
              borderRadius: 14,
              paddingHorizontal: 12,
              paddingVertical: 8,
              backgroundColor: turno.quien === 'yo' ? c.primario : c.papelAlto,
              borderWidth: turno.quien === 'yo' ? 0 : 1,
              borderColor: c.borde,
            }}
          >
            <Text style={{ color: turno.quien === 'yo' ? c.sobrePrimario : c.tinta, fontSize: T.texto, lineHeight: 23, fontFamily: F.regular }}>
              {turno.texto}
            </Text>
          </View>
        ))}
        {pensando ? (
          <View style={{ alignSelf: 'flex-start', flexDirection: 'row', gap: 8, alignItems: 'center' }}>
            <ActivityIndicator color={c.primario} />
            <Text style={e.fino}>El asistente está respondiendo…</Text>
          </View>
        ) : null}
        {error ? (
          <Text accessibilityRole="alert" style={{ color: c.rojo, fontSize: T.fino, fontFamily: F.regular }}>
            {error}
          </Text>
        ) : null}
      </ScrollView>

      <View style={{ flexDirection: 'row', gap: 8, padding: 12, borderTopWidth: 1, borderTopColor: c.borde, backgroundColor: c.papelAlto }}>
        <TextInput
          accessibilityLabel="Tu mensaje"
          placeholder="Escribe aquí"
          placeholderTextColor={c.tintaSuave}
          value={mensaje}
          onChangeText={setMensaje}
          onSubmitEditing={mandar}
          style={[e.campo, { flex: 1 }]}
        />
        <Boton texto="Enviar" desactivado={pensando || !mensaje.trim()} alPulsar={mandar} />
      </View>
    </KeyboardAvoidingView>
  );
}
