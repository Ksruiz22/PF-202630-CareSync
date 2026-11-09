/**
 * Entrar, o pedir el correo para cambiar la contraseña.
 *
 * Registrarse sigue en la web (ver el README). Recuperar la contraseña sí está aquí:
 * quien la olvidó en el teléfono no debería tener que buscar la PWA para eso. Es la
 * misma recuperación que la PWA —pide el correo, ROBLE manda el enlace— y el cambio en
 * sí ocurre en la página de ROBLE, así que la app nunca ve el token. Ver
 * `pedirEnlaceDeContrasena` en `fuenteRoble.ts`.
 *
 * El formulario va arriba y no centrado: centrado en vertical dejaba media pantalla
 * vacía encima, y al abrir el teclado saltaba de sitio.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import type { Fuente } from '../fuente';
import { fuenteDemo } from '../fuenteDemo';
import { fuenteRoble, mensajeDeError, pedirEnlaceDeContrasena } from '../fuenteRoble';
import { Boton, Tarjeta } from '../piezas';
import { estilosDe, F, useColores } from '../tema';
import type { Identidad } from '../tipos';

const HAY_DEMO = process.env.EXPO_PUBLIC_DEMO === '1';

type Modo = 'entrar' | 'recuperar';

export function Acceso({
  alEntrar,
}: {
  alEntrar: (quien: Identidad, fuente: Fuente) => void;
}) {
  const c = useColores();
  const e = estilosDe(c);
  const [modo, setModo] = useState<Modo>('entrar');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [enviado, setEnviado] = useState(false);

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

  async function pedirEnlace() {
    setOcupado(true);
    setError('');
    try {
      await pedirEnlaceDeContrasena(email);
      // Una vez enviado se quita el botón: cada pedido manda un correo, gasta cupo de
      // la IP y anula el enlace anterior.
      setEnviado(true);
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setOcupado(false);
    }
  }

  function cambiarA(nuevo: Modo) {
    setModo(nuevo);
    setError('');
    setEnviado(false);
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={{ flex: 1, backgroundColor: c.papel }}
    >
      <ScrollView
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={Platform.OS !== 'web'}
        contentContainerStyle={{ flexGrow: 1, padding: 16, paddingTop: 48, gap: 16 }}
      >
        <View style={{ alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <View
            style={{
              width: 64,
              height: 64,
              borderRadius: 20,
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: c.primario,
            }}
          >
            <Ionicons name="heart" size={32} color={c.sobrePrimario} />
          </View>
          <Text accessibilityRole="header" style={{ color: c.tinta, fontSize: 30, fontFamily: F.negrita }}>
            CareSync
          </Text>
          <Text style={[e.fino, { fontSize: 15, textAlign: 'center' }]}>
            Tu tratamiento y tus recordatorios, en un solo lugar.
          </Text>
        </View>

        {modo === 'entrar' ? (
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
            <Enlace texto="¿Olvidaste tu contraseña?" alPulsar={() => cambiarA('recuperar')} derecha />
            {error ? (
              <Text accessibilityRole="alert" style={{ color: c.rojo, fontSize: 14, fontFamily: F.regular }}>
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
        ) : (
          <Tarjeta titulo="Recuperar la contraseña">
            <Text style={e.texto}>
              Escribe el correo de tu cuenta y te enviaremos un enlace para poner una
              contraseña nueva.
            </Text>
            <Text nativeID="etiqueta-correo-recuperar" style={e.fino}>Correo</Text>
            <TextInput
              accessibilityLabelledBy="etiqueta-correo-recuperar"
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              value={email}
              onChangeText={setEmail}
              editable={!enviado}
              onSubmitEditing={() => void pedirEnlace()}
              style={[e.campo, enviado ? { color: c.tintaSuave } : null]}
            />
            {enviado ? (
              <View accessibilityRole="alert" style={{ backgroundColor: c.verdeClaro, borderRadius: 12, padding: 12 }}>
                <Text style={{ color: c.verde, fontSize: 14, lineHeight: 20, fontFamily: F.regular }}>
                  Si ese correo tiene cuenta, te llegó un enlace para cambiar la contraseña.
                  Revisa también el spam. Después vuelve aquí y entra con la nueva.
                </Text>
              </View>
            ) : (
              <Boton
                texto={ocupado ? 'Un momento…' : 'Enviar el enlace'}
                desactivado={ocupado || !email.trim()}
                alPulsar={() => void pedirEnlace()}
              />
            )}
            {error ? (
              <Text accessibilityRole="alert" style={{ color: c.rojo, fontSize: 14, fontFamily: F.regular }}>
                {error}
              </Text>
            ) : null}
            <Text style={e.fino}>Si entras con Google en la web, no necesitas contraseña.</Text>
            <Enlace texto="Volver a entrar" alPulsar={() => cambiarA('entrar')} />
          </Tarjeta>
        )}

        {HAY_DEMO && modo === 'entrar' ? (
          <Boton suave texto="Ver demostración" alPulsar={() => void entrar(fuenteDemo)} />
        ) : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Enlace({ texto, alPulsar, derecha }: { texto: string; alPulsar: () => void; derecha?: boolean }) {
  const c = useColores();
  return (
    <Pressable
      accessibilityRole="button"
      onPress={alPulsar}
      style={{ minHeight: 36, justifyContent: 'center', alignSelf: derecha ? 'flex-end' : 'flex-start' }}
    >
      <Text style={{ color: c.primario, fontSize: 15, fontFamily: F.negrita }}>{texto}</Text>
    </Pressable>
  );
}
