/**
 * Entrar y crear cuenta.
 *
 * El registro pone el rol en `extra.role` del usuario de ROBLE y además intenta
 * escribir una fila en `perfiles`. Las dos cosas porque la Lambda lee el rol de
 * los dos sitios: primero del usuario, y si no está, de `perfiles`. Si la tabla
 * no admite la escritura desde una cuenta recién creada —lo normal, según cómo
 * queden los permisos por rol en la consola de ROBLE—, el registro no falla: el
 * rol declarado en `extra` es suficiente para entrar como paciente.
 *
 * Un rol distinto de `paciente` no se puede pedir desde aquí. Los profesionales y
 * el personal administrativo los crea quien administra el contrato, y eso es
 * deliberado: si la pantalla de registro dejara elegir «admin_cmu», cualquiera
 * con un correo vería la agenda del centro.
 */

import { useState, type FormEvent } from 'react';
import { mensajeDeError, roble } from '../roble';
import { useSesion } from '../sesion';
import { Aviso } from '../componentes/Piezas';

type Modo = 'entrar' | 'registrar';

export function Acceso() {
  const { entrar, cargando, error } = useSesion();
  const [modo, setModo] = useState<Modo>('entrar');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [nombre, setNombre] = useState('');
  const [propio, setPropio] = useState('');
  const [ocupado, setOcupado] = useState(false);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setPropio('');
    setOcupado(true);
    try {
      if (modo === 'registrar') {
        await registrar(email, password, nombre);
      }
      await entrar(email, password);
    } catch (fallo) {
      // El error de `entrar` ya lo publica el contexto de sesión; aquí sólo se
      // atrapa el del registro para no dejarlo sin explicación.
      if (modo === 'registrar') setPropio(mensajeDeError(fallo));
    } finally {
      setOcupado(false);
    }
  }

  const trabajando = ocupado || cargando;

  return (
    <main className="acceso">
      <div className="marca">
        <img src="/icono.svg" alt="" width={56} height={56} />
        <h1>CareSync</h1>
        <p>Acompañamiento en salud del campus. Universidad del Norte.</p>
      </div>

      <form onSubmit={enviar}>
        <div className="pestanas" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={modo === 'entrar'}
            onClick={() => setModo('entrar')}
          >
            Entrar
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={modo === 'registrar'}
            onClick={() => setModo('registrar')}
          >
            Crear cuenta
          </button>
        </div>

        {modo === 'registrar' && (
          <label>
            Nombre completo
            <input
              type="text"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              autoComplete="name"
              required
              minLength={3}
            />
          </label>
        )}

        <label>
          Correo institucional
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </label>

        <label>
          Contraseña
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={modo === 'entrar' ? 'current-password' : 'new-password'}
            required
            minLength={8}
          />
        </label>

        <button type="submit" className="principal" disabled={trabajando}>
          {trabajando ? 'Un momento…' : modo === 'entrar' ? 'Entrar' : 'Crear cuenta y entrar'}
        </button>

        {(propio || error) && <Aviso tipo="error">{propio || error}</Aviso>}
      </form>

      <p className="descargo">
        Prototipo académico. Lo que escribas aquí lo puede leer el equipo de
        desarrollo del proyecto durante las pruebas.
      </p>
    </main>
  );
}

async function registrar(email: string, password: string, nombre: string): Promise<void> {
  const correo = email.trim().toLowerCase();

  // `register` y no `registerWithVerification`: en un prototipo que se demuestra
  // en clase, esperar un código por correo rompe la demostración. Cambiarlo es una
  // línea cuando el proyecto salga de la fase de prueba.
  await roble.register({
    email: correo,
    password,
    name: nombre.trim(),
    extra: { role: 'paciente' },
  });

  try {
    await roble.login({ email: correo, password });
    const usuario = await roble.currentUser();
    await roble.create('perfiles', {
      user_id: String(usuario.sub),
      nombre: nombre.trim(),
      email: correo,
      rol: 'paciente',
      centro: null,
      creado_en: new Date().toISOString(),
    });
  } catch (fallo) {
    // Sin fila en `perfiles` la cuenta funciona igual: el rol viaja en `extra`.
    console.warn('No se pudo crear el perfil; se sigue con el rol declarado', fallo);
  }
}
