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
 *
 * **Los intentos son un recurso escaso y esta pantalla es la que los gasta.** ROBLE
 * permite 5 registros por hora y 10 inicios de sesión cada 15 minutos **por IP**;
 * pasado eso responde `ThrottlerException: Too Many Requests` y no hay forma de
 * apurarlo. De ahí dos decisiones de aquí abajo: el registro hace **un solo**
 * inicio de sesión —antes hacía dos, uno para escribir el perfil y otro para
 * entrar— y la contraseña se valida contra la política de ROBLE **antes** de
 * pedirle la cuenta, porque un 400 por contraseña floja cuesta un quinto del cupo
 * de la hora.
 */

import { useState, type FormEvent } from 'react';
import { mensajeDeError, roble } from '../roble';
import { useSesion } from '../sesion';
import { Aviso } from '../componentes/Piezas';

type Modo = 'entrar' | 'registrar';

export function Acceso() {
  const { entrar, refrescar, cargando, error } = useSesion();
  const [modo, setModo] = useState<Modo>('entrar');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [nombre, setNombre] = useState('');
  const [propio, setPropio] = useState('');
  const [ocupado, setOcupado] = useState(false);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setPropio('');

    if (modo === 'registrar') {
      const problema = problemaDeContrasena(password);
      if (problema) {
        // Se corta aquí a propósito: ROBLE rechazaría esta contraseña con un 400 y
        // ese intento cuenta contra los cinco registros de la hora.
        setPropio(problema);
        return;
      }
    }

    setOcupado(true);
    try {
      if (modo === 'registrar') {
        await crearCuenta(email, password, nombre);
      }
      // El único inicio de sesión de todo el flujo, también al registrarse.
      await entrar(email, password);
      if (modo === 'registrar') {
        // Con la sesión ya abierta: el perfil necesita el `sub` del token, y
        // `refrescar` relee la identidad —sin volver a autenticarse— para que el
        // nombre aparezca en la pantalla que viene.
        if (await crearPerfil(email, nombre)) await refrescar();
      }
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
            aria-describedby={modo === 'registrar' ? 'regla-contrasena' : undefined}
          />
          {modo === 'registrar' && (
            <small id="regla-contrasena">
              Mínimo 8 caracteres, con una mayúscula, una minúscula, un número y un símbolo.
            </small>
          )}
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

async function crearCuenta(email: string, password: string, nombre: string): Promise<void> {
  // `register` y no `registerWithVerification`: en un prototipo que se demuestra
  // en clase, esperar un código por correo rompe la demostración. Cambiarlo es una
  // línea cuando el proyecto salga de la fase de prueba.
  await roble.register({
    email: email.trim().toLowerCase(),
    password,
    name: nombre.trim(),
  });
}

/** Escribe la fila de `perfiles` de la cuenta que acaba de entrar. */
async function crearPerfil(email: string, nombre: string): Promise<boolean> {
  try {
    const usuario = await roble.currentUser();
    await roble.create('perfiles', {
      user_id: String(usuario.sub),
      nombre: nombre.trim(),
      email: email.trim().toLowerCase(),
      rol: 'paciente',
      centro: null,
      creado_en: new Date().toISOString(),
    });
    return true;
  } catch (fallo) {
    // Sin fila en `perfiles` la cuenta entra igual y se comporta como paciente en
    // las dos capas, que es el rol que este formulario da. Lo que falta es el
    // nombre —se muestra el correo— y se arregla después con `--perfil`.
    console.warn('No se pudo crear el perfil; se entra como paciente sin nombre', fallo);
    return false;
  }
}

/**
 * La política de contraseñas de ROBLE, comprobada aquí para no gastar un registro.
 *
 * Es la que responde su API en el 400: mínimo 8 caracteres, una mayúscula, una
 * minúscula, un número y un símbolo. Está copiada y por tanto puede quedar desfasada;
 * el que manda sigue siendo ROBLE, y si un día acepta algo que aquí se rechaza el
 * costo es un mensaje de más, no una cuenta que no se puede crear.
 */
function problemaDeContrasena(password: string): string | null {
  const falta: string[] = [];
  if (password.length < 8) falta.push('8 caracteres');
  if (!/[A-ZÁÉÍÓÚÑ]/.test(password)) falta.push('una mayúscula');
  if (!/[a-záéíóúñ]/.test(password)) falta.push('una minúscula');
  if (!/[0-9]/.test(password)) falta.push('un número');
  if (!/[^A-Za-z0-9]/.test(password)) falta.push('un símbolo');
  if (falta.length === 0) return null;
  return `A la contraseña le falta ${falta.join(', ')}. ROBLE no la aceptaría.`;
}
