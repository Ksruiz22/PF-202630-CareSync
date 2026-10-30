import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, TextInput, View } from 'react-native';
import type { Fuente } from '../fuente';
import { fuenteDemo } from '../fuenteDemo';
import { fuenteRoble, mensajeDeError } from '../fuenteRoble';
import { Boton, Tarjeta } from '../piezas';
import { estilosDe, useColores } from '../tema';
import type { Identidad } from '../tipos';

const HAY_DEMO = process.env.EXPO_PUBLIC_DEMO === '1';

export function Acceso({
  alEntrar,
}: {
  alEntrar: (quien: Identidad, fuente: Fuente) => void;
}) {
  const c = useColores();
  const e = estilosDe(c);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [ocupado, setOcupado] = useState(false);

  async function entrar(fuente: Fuente) {
    setOcupado(true);
    setError('');
    try {
      alEntrar(await fuente.entrar(email, password), fuente);
    } catch (fallo) {
      setError(mensajeDeError(fallo));
      setOcupado(false);
    }
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={{ flex: 1, backgroundColor: c.papel }}
    >
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', padding: 16, gap: 16 }}>
        <View style={{ gap: 6 }}>
          <Text accessibilityRole="header" style={{ color: c.primario, fontSize: 30, fontWeight: '700' }}>
            CareSync
          </Text>
          <Text style={e.texto}>Tu tratamiento y tus recordatorios, en un solo lugar.</Text>
        </View>

        <Tarjeta>
          <Text nativeID="etiqueta-correo" style={e.fino}>Correo</Text>
          <TextInput
            accessibilityLabelledBy="etiqueta-correo"
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            value={email}
            onChangeText={setEmail}
            style={e.campo}
          />
          <Text nativeID="etiqueta-clave" style={e.fino}>Contraseña</Text>
          <TextInput
            accessibilityLabelledBy="etiqueta-clave"
            secureTextEntry
            autoComplete="current-password"
            value={password}
            onChangeText={setPassword}
            onSubmitEditing={() => void entrar(fuenteRoble)}
            style={e.campo}
          />
          {error ? (
            <Text accessibilityRole="alert" style={{ color: c.rojo, fontSize: 14 }}>
              {error}
            </Text>
          ) : null}
          <Boton
            texto={ocupado ? 'Entrando…' : 'Entrar'}
            desactivado={ocupado || !email || !password}
            alPulsar={() => void entrar(fuenteRoble)}
          />
          <Text style={e.fino}>
            Usa la misma cuenta de CareSync. Si aún no tienes una, créala en la web, donde
            también empieza tu triaje.
          </Text>
        </Tarjeta>

        {HAY_DEMO ? (
          <Boton suave texto="Ver demostración" alPulsar={() => void entrar(fuenteDemo)} />
        ) : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
