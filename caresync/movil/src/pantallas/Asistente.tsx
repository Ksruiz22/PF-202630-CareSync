/**
 * La conversación con el agente. Todo lo que no es un sí o un no pasa por aquí: cómo se
 * siente, una duda, una señal de alarma, cambiar una cita. A qué agente va lo decide
 * `agenteParaMensaje`, y por qué casi siempre no se sugiere ninguno está ahí.
 */

import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView, Text, TextInput, View } from 'react-native';
import { Boton } from '../piezas';
import { estilosDe, useColores } from '../tema';
import type { Turno } from '../tipos';

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
      keyboardVerticalOffset={120}
      style={{ flex: 1 }}
    >
      <ScrollView
        ref={lista}
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: 16, gap: 8 }}
        accessibilityLiveRegion="polite"
      >
        {turnos.length === 0 ? (
          <Text style={[e.fino, { textAlign: 'center' }]}>
            Cuéntame cómo vas con lo que te indicaron. No soy personal de salud: lo que me
            cuentas lo lee tu profesional.
          </Text>
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
            <Text style={{ color: turno.quien === 'yo' ? c.sobrePrimario : c.tinta, fontSize: 15, lineHeight: 21 }}>
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
          <Text accessibilityRole="alert" style={{ color: c.rojo, fontSize: 14 }}>
            {error}
          </Text>
        ) : null}
      </ScrollView>

      <View style={{ flexDirection: 'row', gap: 8, padding: 12, borderTopWidth: 1, borderTopColor: c.borde }}>
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
