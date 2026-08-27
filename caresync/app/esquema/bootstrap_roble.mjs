/**
 * Crea el esquema de CareSync en ROBLE.
 *
 *   scripts/esquema_roble.sh                     # crea las 13 tablas
 *   scripts/esquema_roble.sh --semilla           # + profesionales y horarios de prueba
 *   scripts/esquema_roble.sh --perfil profesional CMU
 *
 * **Las credenciales no se escriben en ningún archivo.** Salen de `ROBLE_EMAIL` y
 * `ROBLE_PASSWORD` si están en el entorno, y si no, se piden por teclado con la
 * escritura oculta. Este proyecto vive en una carpeta sincronizada con la nube: un
 * `.env` con la contraseña del contrato se subiría solo.
 *
 * **Es idempotente.** Una tabla que ya existe se cuenta y se sigue. Se puede
 * ejecutar tantas veces como haga falta, que es justo lo que pasa mientras se
 * afina el esquema.
 *
 * **Por qué existe.** `createTable` es el único mecanismo de creación de tablas que
 * documenta el SDK de ROBLE. Hacerlo con trece formularios en la consola web es
 * media hora de clics, imposible de repetir igual y de revisar en el repositorio.
 * Aquí el esquema es código, que es lo que pide este proyecto.
 *
 * Vive dentro de `app/` a propósito: así resuelve `roble-client` desde el
 * `node_modules` de la PWA y no hace falta un segundo `package.json` con la misma
 * dependencia y su propio candado de versiones.
 */

import { createInterface } from 'node:readline';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import process from 'node:process';
import { createRobleClient } from 'roble-client';

const AQUI = dirname(fileURLToPath(import.meta.url));

/*
 * Los tipos van en un solo sitio porque son la parte más frágil del archivo: son
 * los que ROBLE traduce a columnas de PostgreSQL, y si alguna versión de la
 * plataforma no acepta uno de estos nombres, se cambia aquí y no en trece sitios.
 * El error que devuelve ROBLE se imprime con el nombre de la tabla y la columna,
 * para que se sepa exactamente qué ajustar.
 */
//
// Los nombres son los que publica ROBLE en su documentación de tipos, no los
// alias de SQL: `int4` y no `integer`, `bool` y no `boolean`. PostgreSQL acepta
// las dos formas, pero quien valida aquí es la API de ROBLE y su lista es la de
// la izquierda de https://roble.test-openlab.uninorte.edu.co/docs/database/types
// (`int2 int4 int8 float4 float8 numeric json jsonb text varchar uuid date time
// timestamp timestamptz bool geography`).
const T = {
  texto: 'text',
  entero: 'int4',
  logico: 'bool',
  momento: 'timestamp',
  json: 'jsonb',
};

/**
 * El esquema.
 *
 * No hay claves ajenas: ROBLE no las expone en `createTable` y la integridad
 * referencial la sostiene el módulo de acceso a datos. Está anotado en
 * docs/arquitectura.md como una limitación asumida, no como un olvido.
 *
 * `_id` no se declara: lo pone ROBLE en cada tabla.
 */
const ESQUEMA = {
  perfiles: [
    ['user_id', T.texto],
    ['nombre', T.texto],
    ['email', T.texto],
    ['rol', T.texto],
    ['centro', T.texto, true],
    ['creado_en', T.momento],
  ],

  casos: [
    ['paciente_user_id', T.texto],
    ['paciente_nombre', T.texto],
    ['paciente_email', T.texto],
    ['estado', T.texto],
    ['centro', T.texto, true],
    ['nivel_urgencia', T.entero, true],
    ['motivo', T.texto, true],
    ['resumen_triaje', T.texto, true],
    ['creado_en', T.momento],
    ['actualizado_en', T.momento],
  ],

  // El hilo completo de la conversación. Es lo más sensible del sistema y por eso
  // vive en ROBLE —infraestructura de la universidad— y no en AWS.
  conversaciones: [
    ['caso_id', T.texto],
    ['agente', T.texto],
    ['autor', T.texto],
    ['contenido', T.texto],
    ['creado_en', T.momento],
  ],

  profesionales: [
    ['user_id', T.texto, true],
    ['nombre', T.texto],
    ['email', T.texto, true],
    ['centro', T.texto],
    ['especialidad', T.texto, true],
    ['activo', T.logico],
  ],

  horarios: [
    ['profesional_id', T.texto],
    // 0 = lunes … 6 = domingo. La misma convención en `agenda_cupos.ts`.
    ['dia_semana', T.entero],
    ['hora_inicio', T.texto],
    ['hora_fin', T.texto],
    ['minutos_cupo', T.entero],
    ['modalidad', T.texto, true],
    ['activo', T.logico],
  ],

  // `reserva_testigo` es la columna que hace posible reservar sin escrituras
  // condicionales: ver `reservar_cupo` en roble_acceso.py.
  cupos: [
    ['centro', T.texto],
    ['profesional_id', T.texto],
    ['inicio', T.momento],
    ['fin', T.momento],
    ['estado', T.texto],
    ['modalidad', T.texto, true],
    ['caso_id', T.texto, true],
    ['reserva_testigo', T.texto, true],
    ['reservado_en', T.momento, true],
  ],

  citas: [
    ['caso_id', T.texto],
    ['cupo_id', T.texto],
    ['profesional_id', T.texto],
    ['profesional_user_id', T.texto, true],
    ['profesional_nombre', T.texto, true],
    ['paciente_user_id', T.texto],
    ['centro', T.texto],
    ['inicio', T.momento],
    ['fin', T.momento],
    ['estado', T.texto],
    ['creado_en', T.momento],
  ],

  planes: [
    ['caso_id', T.texto],
    ['profesional_user_id', T.texto],
    ['profesional_nombre', T.texto, true],
    ['resumen', T.texto],
    ['creado_en', T.momento],
  ],

  indicaciones: [
    ['caso_id', T.texto],
    ['plan_id', T.texto],
    ['texto', T.texto],
    ['frecuencia', T.texto, true],
    ['activa', T.logico],
    ['creado_en', T.momento],
  ],

  adherencia: [
    ['caso_id', T.texto],
    ['indicacion_id', T.texto],
    ['cumplida', T.logico],
    ['nota', T.texto, true],
    ['reportado_en', T.momento],
  ],

  evolucion: [
    ['caso_id', T.texto],
    // 0 (peor que nunca) a 10 (como antes). Lo valida el catálogo de herramientas.
    ['escala', T.entero],
    ['nota', T.texto, true],
    ['reportado_en', T.momento],
  ],

  // La bitácora que ve el profesional. No es el log técnico: ese está en CloudWatch.
  eventos: [
    ['caso_id', T.texto, true],
    ['tipo', T.texto],
    ['severidad', T.texto],
    ['actor_user_id', T.texto, true],
    ['actor_rol', T.texto, true],
    ['detalle', T.json, true],
    ['creado_en', T.momento],
  ],

  recordatorios: [
    ['caso_id', T.texto],
    ['indicacion_id', T.texto],
    ['programado_para', T.momento],
    ['estado', T.texto],
    ['canal', T.texto],
    ['texto', T.texto],
    ['creado_en', T.momento],
    ['enviado_en', T.momento, true],
    ['detalle', T.texto, true],
  ],
};

const ROLES = ['paciente', 'profesional', 'admin_cmu', 'admin_cae'];

// ------------------------------------------------------------------ argumentos

function opciones(argv) {
  const flags = new Set(argv.filter((a) => a.startsWith('--')));
  const sueltos = argv.filter((a) => !a.startsWith('--'));
  return {
    semilla: flags.has('--semilla'),
    soloPerfil: flags.has('--perfil'),
    sinTablas: flags.has('--sin-tablas'),
    rol: sueltos[0],
    centro: sueltos[1],
  };
}

// ----------------------------------------------------------------- credenciales

async function preguntar(texto, { oculto = false } = {}) {
  const lector = createInterface({ input: process.stdin, output: process.stdout, terminal: true });
  if (oculto) {
    // Se silencia el eco escribiendo por encima de lo que el usuario teclea. Es el
    // recurso que hay en Node sin dependencias; no oculta la longitud, pero evita
    // que la contraseña quede en la pantalla y en el desplazamiento de la terminal.
    lector._writeToOutput = (cadena) => {
      if (cadena.trim().length > 0 && !cadena.includes(texto)) return;
      lector.output.write(cadena);
    };
  }
  const respuesta = await new Promise((resolver) => lector.question(texto, resolver));
  lector.close();
  if (oculto) process.stdout.write('\n');
  return respuesta.trim();
}

async function credenciales() {
  const email = process.env.ROBLE_EMAIL || (await preguntar('Correo de ROBLE: '));
  const password = process.env.ROBLE_PASSWORD || (await preguntar('Contraseña: ', { oculto: true }));
  if (!email || !password) {
    throw new Error('Sin credenciales no se puede crear el esquema.');
  }
  return { email, password };
}

// ---------------------------------------------------------------------- tablas

/**
 * Distingue «ya existía» de «falló».
 *
 * ROBLE no devuelve un código propio para la tabla duplicada, así que hay que
 * mirar el mensaje. Se acepta cualquier variante que hable de existencia o
 * duplicado, en español o en inglés; lo que no encaje se trata como error real,
 * porque tragarse un fallo de esquema es peor que repetir una tabla.
 */
function yaExistia(error) {
  const texto = String(error?.message ?? error).toLowerCase();
  return (
    texto.includes('already exist') ||
    texto.includes('ya existe') ||
    texto.includes('duplicate') ||
    texto.includes('duplicad')
  );
}

/**
 * Distingue «ROBLE no me deja» de «ROBLE no entiende el esquema».
 *
 * Importa porque el consejo es opuesto y el mensaje equivocado cuesta una tarde:
 * ante un fallo de autorización no hay nada que corregir en este archivo. ROBLE
 * responde `No se pudo determinar el rol del usuario` cuando al rol de la cuenta le
 * falta el permiso `alter`, y `createTable` autoriza antes de mirar las columnas. El
 * mensaje engaña: el rol existe, es el permiso el que no está.
 */
function esFalloDeAutorizacion(mensaje) {
  const texto = mensaje.toLowerCase();
  return (
    texto.includes('rol') ||
    texto.includes('permis') ||
    texto.includes('autoriz') ||
    texto.includes('401') ||
    texto.includes('403')
  );
}

function columnas(definicion) {
  return definicion.map(([name, type, nullable]) => ({
    name,
    type,
    nullable: nullable === true,
  }));
}

async function crearTablas(cliente) {
  let creadas = 0;
  let existentes = 0;
  const fallos = [];

  for (const [tabla, definicion] of Object.entries(ESQUEMA)) {
    try {
      await cliente.createTable(tabla, columnas(definicion));
      creadas += 1;
      console.log(`  + ${tabla} (${definicion.length} columnas)`);
    } catch (error) {
      if (yaExistia(error)) {
        existentes += 1;
        console.log(`  = ${tabla} ya estaba`);
        continue;
      }
      fallos.push({ tabla, mensaje: String(error?.message ?? error) });
      console.error(`  ! ${tabla}: ${error?.message ?? error}`);
    }
  }

  console.log(`\n  ${creadas} creadas, ${existentes} ya estaban, ${fallos.length} con error`);
  if (fallos.length > 0) {
    if (fallos.every((fallo) => esFalloDeAutorizacion(fallo.mensaje))) {
      console.error(
        '\nNo es el esquema: ROBLE rechazó las tablas por autorización, así que no hay' +
          ' nada que corregir aquí. Crear una tabla necesita el permiso `alter`, que el' +
          ' rol predeterminado `user` no tiene —ni debería tener, porque lo hereda toda' +
          ' cuenta que se registre—. El camino que funciona es la Consola SQL de la' +
          ' consola web, con el esquema de este archivo como referencia:' +
          ' ver docs/runbook-roble.md.'
      );
    } else {
      console.error(
        '\nRevisa los tipos en la constante T de este archivo, o crea a mano las tablas' +
          ' que fallaron siguiendo docs/runbook-roble.md.'
      );
    }
  }
  return fallos.length === 0;
}

// ---------------------------------------------------------------------- perfil

/**
 * Escribe la fila de `perfiles` de la cuenta con la que se acaba de entrar.
 *
 * Es la única forma honesta de asignar un rol: `user_id` tiene que ser exactamente
 * el `sub` que ROBLE le da a esa cuenta, y ese valor sólo se conoce estando dentro
 * de la sesión. Cada persona del equipo ejecuta esto una vez con sus credenciales,
 * o quien administre el contrato lo hace por cada cuenta.
 */
async function fijarPerfil(cliente, rol, centro) {
  if (!ROLES.includes(rol)) {
    throw new Error(`Rol no válido: ${rol}. Usa uno de ${ROLES.join(', ')}.`);
  }
  const conCentro = rol === 'profesional';
  if (conCentro && !['CMU', 'CAE'].includes(String(centro))) {
    throw new Error('Un profesional necesita centro: CMU o CAE.');
  }

  const usuario = await cliente.currentUser();
  const userId = String(usuario.sub);
  // Los roles administrativos llevan el centro implícito en el nombre del rol, y
  // el backend lo impone; escribirlo aquí es sólo para que la tabla se lea bien.
  const centroFinal = rol === 'admin_cmu' ? 'CMU' : rol === 'admin_cae' ? 'CAE' : centro ?? null;

  const existentes = await cliente.read('perfiles', { user_id: userId });
  const datos = {
    user_id: userId,
    nombre: String(usuario.name ?? usuario.email ?? ''),
    email: String(usuario.email ?? ''),
    rol,
    centro: centroFinal,
  };

  if (existentes.length > 0) {
    const id = existentes[0]._id ?? existentes[0].id;
    await cliente.update('perfiles', String(id), datos);
    console.log(`  = perfil actualizado: ${datos.email} → ${rol}${centroFinal ? ` (${centroFinal})` : ''}`);
  } else {
    await cliente.create('perfiles', { ...datos, creado_en: new Date().toISOString() });
    console.log(`  + perfil creado: ${datos.email} → ${rol}${centroFinal ? ` (${centroFinal})` : ''}`);
  }
}

// --------------------------------------------------------------------- semilla

/**
 * Profesionales y horarios de prueba, desde `esquema/semilla.json`.
 *
 * El archivo no está en el repositorio y su ejemplo sí: lleva nombres y correos de
 * personas, y aunque sean inventados, la costumbre de versionar datos de personas
 * es la que termina subiendo los reales.
 *
 * Los cupos **no** se siembran aquí: los genera el personal administrativo desde la
 * aplicación, con el botón que llama a `agenda_cupos.ts`. Tener dos generadores de
 * agenda sería tener dos verdades sobre a qué hora atiende un centro.
 */
async function sembrar(cliente) {
  const ruta = join(AQUI, 'semilla.json');
  let contenido;
  try {
    contenido = JSON.parse(await readFile(ruta, 'utf8'));
  } catch {
    console.log(
      `  Sin ${ruta}. Copia semilla.example.json, ajústalo y vuelve a ejecutar con --semilla.`
    );
    return;
  }

  for (const profesional of contenido.profesionales ?? []) {
    const yaEsta = await cliente.read('profesionales', { nombre: profesional.nombre });
    const fila =
      yaEsta.length > 0
        ? yaEsta[0]
        : await cliente.create('profesionales', {
            user_id: profesional.user_id ?? null,
            nombre: profesional.nombre,
            email: profesional.email ?? null,
            centro: profesional.centro,
            especialidad: profesional.especialidad ?? null,
            activo: true,
          });

    const profesionalId = String(fila._id ?? fila.id ?? idInsertado(fila));
    if (!profesionalId || profesionalId === 'undefined') {
      console.error(`  ! ${profesional.nombre}: ROBLE no devolvió el id; se salta su horario`);
      continue;
    }
    console.log(`  ${yaEsta.length > 0 ? '=' : '+'} ${profesional.nombre} (${profesional.centro})`);

    const horarios = await cliente.read('horarios', { profesional_id: profesionalId });
    if (horarios.length > 0) {
      console.log(`      ya tiene ${horarios.length} horarios`);
      continue;
    }
    for (const horario of profesional.horarios ?? []) {
      await cliente.create('horarios', {
        profesional_id: profesionalId,
        dia_semana: horario.dia_semana,
        hora_inicio: horario.hora_inicio,
        hora_fin: horario.hora_fin,
        minutos_cupo: horario.minutos_cupo ?? 30,
        modalidad: horario.modalidad ?? 'presencial',
        activo: true,
      });
    }
    console.log(`      + ${(profesional.horarios ?? []).length} horarios`);
  }

  console.log(
    '\n  Los cupos los publica el personal administrativo desde la aplicación,' +
      ' con el botón «Publicar cupos».'
  );
}

function idInsertado(resultado) {
  const insertadas = resultado?.inserted;
  if (Array.isArray(insertadas) && insertadas.length > 0) {
    return insertadas[0]?._id ?? insertadas[0]?.id;
  }
  return undefined;
}

// ----------------------------------------------------------------------- main

async function principal() {
  const opts = opciones(process.argv.slice(2));

  const baseUrl = process.env.VITE_ROBLE_BASE_URL ?? process.env.ROBLE_BASE_URL;
  const contractId = process.env.VITE_ROBLE_CONTRACT_ID ?? process.env.ROBLE_CONTRACT_ID;
  if (!baseUrl || !contractId) {
    throw new Error(
      'Faltan ROBLE_BASE_URL y ROBLE_CONTRACT_ID. scripts/esquema_roble.sh los toma de infra/dev.tfvars.'
    );
  }

  console.log(`ROBLE ${contractId} en ${baseUrl}\n`);
  const { email, password } = await credenciales();

  const cliente = createRobleClient({ baseUrl, contractId, timeoutMs: 30000 });
  await cliente.login({ email, password });
  console.log(`Sesión abierta como ${email}\n`);

  let todoBien = true;

  if (opts.soloPerfil) {
    await fijarPerfil(cliente, opts.rol, opts.centro);
  } else {
    if (!opts.sinTablas) {
      console.log('Creando tablas:');
      todoBien = await crearTablas(cliente);
    }
    if (opts.semilla) {
      console.log('\nSembrando profesionales y horarios:');
      await sembrar(cliente);
    }
  }

  // No se llama a `logout()`: cerraría también la sesión que la persona pueda tener
  // abierta en el navegador con la misma cuenta. Basta con descartar los tokens.
  cliente.clearTokens();
  if (!todoBien) process.exitCode = 1;
}

principal().catch((error) => {
  console.error(`\nFalló: ${error?.message ?? error}`);
  process.exitCode = 1;
});
