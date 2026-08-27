/**
 * Entrar y crear cuenta.
 *
 * El registro crea la cuenta y después escribe su fila en `perfiles`, que es el
 * único sitio donde vive el rol. **No se declara nada en `extra`**: ROBLE dejó de
 * aceptar ese campo en `register` el 2026-08-27 —«El campo extra 'role' no está
 * permitido»— y tener dos fuentes del rol ya era un problema por sí solo, porque
 * la Lambda prefería `extra` y esta aplicación nunca lo miró.
 *
 * Si la escritura del perfil falla, el registro no falla: sin fila la cuenta entra
 * igual y las dos capas la tratan como `paciente`, que es exactamente el rol que
 * este formulario iba a darle. Lo que se pierde es el nombre.
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
  await roble.register({ email: correo, password, name: nombre.trim() });

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
    // Sin fila en `perfiles` la cuenta entra igual y se comporta como paciente en
    // las dos capas, que es el rol que este formulario da. Lo que falta es el
    // nombre —se muestra el correo— y se arregla después con `--perfil`.
    console.warn('No se pudo crear el perfil; se entra como paciente sin nombre', fallo);
  }
}
