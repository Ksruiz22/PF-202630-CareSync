/**
 * Lo que ve quien administra la instalación, no un centro.
 *
 * Tres cosas que ninguna otra pantalla puede hacer:
 *
 * 1. **Cuentas y roles.** Quién se registró y qué rol tiene. Hasta ahora dar un rol
 *    exigía correr `esquema_roble.sh --perfil` **con las credenciales de esa
 *    persona**, porque el `user_id` es el `sub` que sólo se conoce estando dentro de
 *    su sesión. Eso deja de hacer falta aquí por un detalle: al registrarse, la PWA
 *    ya escribió su fila de `perfiles` con su `sub` dentro, así que esta pantalla lo
 *    lee de la tabla en lugar de tener que averiguarlo.
 * 2. **Profesionales y horarios.** La tabla `profesionales` no es lo mismo que un
 *    `perfiles.rol = profesional`: el rol decide qué pantalla ve una cuenta, y la
 *    fila de `profesionales` —con sus `horarios`— es lo que hace que exista agenda.
 *    Tener las dos cosas en un sitio es lo que evita el «este centro no tiene
 *    profesionales activos con horarios registrados» sin saber por qué.
 * 3. **Ajustes de la plataforma**, con la regla que impone `ajustes.ts`: un ajuste
 *    sólo existe si algo lo lee, y la pantalla dice quién lo lee.
 *
 * **Esta pantalla no muestra casos, conversaciones ni datos clínicos, y es
 * deliberado.** Administrar cuentas no requiere leer el motivo de consulta de nadie.
 * El rol `admin_plataforma` tampoco tiene agentes ni herramientas en el backend: si
 * llama al orquestador recibe un 403 limpio.
 *
 * ------------------------------------------------------------------------------
 * **Por qué esta pantalla no basta por sí sola.** Nada de lo que hay aquí es una
 * comprobación de seguridad: el navegador ejecuta el código de quien lo tiene abierto,
 * así que quien pueda escribir `perfiles` se asciende con o sin esta pantalla. Lo que
 * de verdad lo impide es un permiso de ROBLE, y por eso `perfiles:update` **no** está
 * en el rol `user` que hereda toda cuenta registrada, sino en el rol `plataforma`, que
 * sólo tienen las cuentas administrativas. Lo mismo vale para `profesionales:update`,
 * `horarios:update` y `ajustes:update`, que también viven sólo ahí.
 *
 * La consecuencia práctica, y es la que se olvida: **si esta pantalla da un 500 al
 * guardar, el rol de ROBLE de la cuenta es lo primero que hay que mirar**, porque una
 * tabla sin permiso no devuelve 403. Ver docs/runbook-roble.md.
 * ------------------------------------------------------------------------------
 */

import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  CATALOGO,
  guardarAjuste,
  leerAjustes,
  problemaDeAjuste,
  type Ajustes,
  type DefinicionDeAjuste,
} from '../ajustes';
import { Aviso, Cargando, Tarjeta, Vacio } from '../componentes/Piezas';
import { diaSemanaLegible, diasDeLaSemana, rolLegible } from '../formato';
import { esFalloDeServidor, mensajeDeError, roble } from '../roble';
import { useSesion } from '../sesion';
import {
  esVerdad,
  idDe,
  ROLES,
  type Centro,
  type Horario,
  type Perfil,
  type Profesional,
  type Rol,
} from '../tipos';

type Pestana = 'usuarios' | 'profesionales' | 'ajustes';

const CENTROS: readonly Centro[] = ['CMU', 'CAE'];

interface Datos {
  perfiles: Perfil[];
  profesionales: Profesional[];
  horarios: Horario[];
  ajustes: Ajustes;
}

const VACIO: Datos = { perfiles: [], profesionales: [], horarios: [], ajustes: {} };

/**
 * Una escritura, su mensaje de éxito y la tabla que toca.
 *
 * La tabla no es decoración: cuando ROBLE responde 5xx, lo más probable es que al rol
 * `user` le falte `<tabla>:update`, y decirlo con el nombre de la tabla ahorra la
 * tarde que documenta el runbook.
 *
 * `accion` devuelve `Promise<unknown>` y no `Promise<void>`: los métodos del SDK
 * devuelven la fila escrita, y aquí no se mira. Pedir `void` obligaría a envolver cada
 * llamada en una función asíncrona que descarta el resultado, que es ruido.
 */
type Ejecutar = (
  clave: string,
  tabla: string,
  accion: () => Promise<unknown>,
  exito: string
) => Promise<void>;

export function Plataforma() {
  const { quien, salir } = useSesion();
  const [datos, setDatos] = useState<Datos>(VACIO);
  const [pestana, setPestana] = useState<Pestana>('usuarios');
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');
  const [nota, setNota] = useState('');
  const [ocupado, setOcupado] = useState('');

  const cargar = useCallback(async () => {
    try {
      setDatos(await leerTodo());
      setError('');
    } catch (fallo) {
      setError(mensajeDeError(fallo));
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const ejecutar = useCallback<Ejecutar>(
    async (clave, tabla, accion, exito) => {
      setOcupado(clave);
      setError('');
      setNota('');
      try {
        await accion();
        setNota(exito);
        await cargar();
      } catch (fallo) {
        setError(explicarFallo(fallo, tabla));
      } finally {
        setOcupado('');
      }
    },
    [cargar]
  );

  const resumen = useMemo(() => contar(datos), [datos]);

  return (
    <div className="panel plataforma">
      <header className="cabecera">
        <div>
          <h1>Plataforma</h1>
          <p>
            {quien?.nombre} · {resumen.cuentas} cuenta{resumen.cuentas === 1 ? '' : 's'} ·{' '}
            {resumen.profesionalesActivos} profesional
            {resumen.profesionalesActivos === 1 ? '' : 'es'} activo
            {resumen.profesionalesActivos === 1 ? '' : 's'} · {resumen.conHorario} con horario
          </p>
        </div>
        <button type="button" className="secundario" onClick={() => void salir()}>
          Salir
        </button>
      </header>

      <div className="pestanas" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={pestana === 'usuarios'}
          onClick={() => setPestana('usuarios')}
        >
          Usuarios y roles
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={pestana === 'profesionales'}
          onClick={() => setPestana('profesionales')}
        >
          Profesionales
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={pestana === 'ajustes'}
          onClick={() => setPestana('ajustes')}
        >
          Ajustes
        </button>
      </div>

      {error && <Aviso tipo="error">{error}</Aviso>}
      {nota && <Aviso>{nota}</Aviso>}

      {cargando ? (
        <Cargando que="Leyendo cuentas, profesionales y ajustes" />
      ) : pestana === 'usuarios' ? (
        <SeccionUsuarios
          perfiles={datos.perfiles}
          miUserId={quien?.userId ?? ''}
          ocupado={ocupado}
          ejecutar={ejecutar}
        />
      ) : pestana === 'profesionales' ? (
        <SeccionProfesionales
          profesionales={datos.profesionales}
          horarios={datos.horarios}
          perfiles={datos.perfiles}
          ocupado={ocupado}
          ejecutar={ejecutar}
        />
      ) : (
        <SeccionAjustes
          ajustes={datos.ajustes}
          quien={quien?.email ?? ''}
          ocupado={ocupado}
          ejecutar={ejecutar}
        />
      )}
    </div>
  );
}

// ------------------------------------------------------------------- usuarios

interface Cambio {
  rol: Rol;
  centro: Centro | '';
}

function SeccionUsuarios({
  perfiles,
  miUserId,
  ocupado,
  ejecutar,
}: {
  perfiles: Perfil[];
  miUserId: string;
  ocupado: string;
  ejecutar: Ejecutar;
}) {
  const [filtro, setFiltro] = useState('');
  const [cambios, setCambios] = useState<Record<string, Cambio>>({});

  const visibles = useMemo(() => filtrar(perfiles, filtro), [perfiles, filtro]);

  const porRol = useMemo(() => {
    const cuenta: Record<string, number> = {};
    for (const perfil of perfiles) {
      const rol = rolDe(perfil);
      cuenta[rol] = (cuenta[rol] ?? 0) + 1;
    }
    return cuenta;
  }, [perfiles]);

  return (
    <>
      <Tarjeta
        titulo="Usuarios"
        extra={<span className="contador neutro">{perfiles.length}</span>}
      >
        <p className="fino">
          {ROLES.filter((rol) => porRol[rol]).map((rol, indice) => (
            <span key={rol}>
              {indice > 0 ? ' · ' : ''}
              {porRol[rol]} {rolLegible(rol).toLowerCase()}
            </span>
          ))}
        </p>

        <label>
          Buscar
          <input
            type="search"
            value={filtro}
            onChange={(evento) => setFiltro(evento.target.value)}
            placeholder="nombre, correo o rol"
          />
        </label>

        <p className="fino">
          Aquí sólo aparecen las cuentas que tienen fila en «perfiles». Si a alguien le
          falló la escritura del perfil al registrarse, entra como paciente y no se ve
          en esta lista: que vuelva a entrar a la aplicación o que corra
          <code> esquema_roble.sh --perfil paciente</code> con su cuenta.
        </p>

        {visibles.length === 0 ? (
          <Vacio>Ninguna cuenta coincide.</Vacio>
        ) : (
          <ul className="filas">
            {visibles.map((perfil) => {
              const id = idDe(perfil);
              return (
                <FilaDeUsuario
                  key={id}
                  perfil={perfil}
                  esMiCuenta={String(perfil.user_id ?? '') === miUserId && miUserId !== ''}
                  cambio={cambios[id]}
                  alCambiar={(nuevo) => setCambios((previo) => ({ ...previo, [id]: nuevo }))}
                  ocupado={ocupado}
                  ejecutar={ejecutar}
                />
              );
            })}
          </ul>
        )}
      </Tarjeta>

      <Tarjeta titulo="Qué hace cada rol">
        <dl className="datos">
          <dt>Paciente</dt>
          <dd>Triaje, su caso y su seguimiento. Es el rol que da el registro.</dd>
          <dt>Profesional</dt>
          <dd>
            Su agenda y el plan de sus pacientes. Necesita <strong>centro</strong>, y
            además una fila en «Profesionales» vinculada a su cuenta para que le
            aparezcan citas.
          </dd>
          <dt>Administración CMU / CAE</dt>
          <dd>El tablero de su centro y el agente de agenda. El centro sale del rol.</dd>
          <dt>Administración de plataforma</dt>
          <dd>Esta pantalla. No ve casos ni conversaciones.</dd>
        </dl>
      </Tarjeta>
    </>
  );
}

function FilaDeUsuario({
  perfil,
  esMiCuenta,
  cambio,
  alCambiar,
  ocupado,
  ejecutar,
}: {
  perfil: Perfil;
  esMiCuenta: boolean;
  cambio: Cambio | undefined;
  alCambiar: (cambio: Cambio) => void;
  ocupado: string;
  ejecutar: Ejecutar;
}) {
  const id = idDe(perfil);
  const actual: Cambio = { rol: rolDe(perfil), centro: centroDe(perfil) };
  const editado = cambio ?? actual;
  const cambiado = editado.rol !== actual.rol || editado.centro !== actual.centro;
  const necesitaCentro = editado.rol === 'profesional';
  const problema = necesitaCentro && !editado.centro ? 'Un profesional necesita centro.' : '';
  const clave = `perfil:${id}`;

  function elegirRol(rol: Rol) {
    // El centro de un rol administrativo va implícito en el nombre del rol y el
    // backend lo impone; los otros dos roles no tienen centro. Sólo `profesional`
    // deja elegir, y por eso es el único caso en que se conserva lo ya escrito.
    const centro: Centro | '' =
      rol === 'admin_cmu'
        ? 'CMU'
        : rol === 'admin_cae'
          ? 'CAE'
          : rol === 'profesional'
            ? editado.centro
            : '';
    alCambiar({ rol, centro });
  }

  return (
    <li className="fila-usuario">
      <div className="identidad">
        <span className="quien">{String(perfil.nombre ?? '(sin nombre)')}</span>
        <span className="fino">{String(perfil.email ?? 'sin correo')}</span>
        {esMiCuenta && <span className="etiqueta e-agendado">tu cuenta</span>}
      </div>

      {esMiCuenta ? (
        <p className="fino">
          {rolLegible(actual.rol)}
          {actual.centro ? ` · ${actual.centro}` : ''}. Tu propio rol no se cambia aquí:
          quitártelo te dejaría sin esta pantalla y sin forma de volver salvo el script.
        </p>
      ) : (
        <div className="controles">
          <label>
            Rol
            <select
              value={editado.rol}
              onChange={(evento) => elegirRol(evento.target.value as Rol)}
            >
              {ROLES.map((rol) => (
                <option key={rol} value={rol}>
                  {rolLegible(rol)}
                </option>
              ))}
            </select>
          </label>

          <label>
            Centro
            <select
              value={editado.centro}
              disabled={!necesitaCentro}
              onChange={(evento) =>
                alCambiar({ ...editado, centro: evento.target.value as Centro | '' })
              }
            >
              <option value="">Sin centro</option>
              {CENTROS.map((centro) => (
                <option key={centro} value={centro}>
                  {centro}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            className="principal fino"
            disabled={!cambiado || Boolean(problema) || ocupado === clave}
            onClick={() =>
              void ejecutar(
                clave,
                'perfiles',
                () =>
                  roble.update('perfiles', id, {
                    rol: editado.rol,
                    centro: editado.centro || null,
                  }),
                `${String(perfil.nombre ?? perfil.email ?? 'La cuenta')} ahora es ${rolLegible(
                  editado.rol
                ).toLowerCase()}${editado.centro ? ` del ${editado.centro}` : ''}. Tiene que salir y volver a entrar.`
              )
            }
          >
            {ocupado === clave ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
      )}

      {problema && <span className="fino problema">{problema}</span>}
    </li>
  );
}

// -------------------------------------------------------------- profesionales

function SeccionProfesionales({
  profesionales,
  horarios,
  perfiles,
  ocupado,
  ejecutar,
}: {
  profesionales: Profesional[];
  horarios: Horario[];
  perfiles: Perfil[];
  ocupado: string;
  ejecutar: Ejecutar;
}) {
  const [abierto, setAbierto] = useState('');

  const ordenados = useMemo(
    () =>
      [...profesionales].sort(
        (a, b) =>
          String(a.centro ?? '').localeCompare(String(b.centro ?? '')) ||
          String(a.nombre ?? '').localeCompare(String(b.nombre ?? ''))
      ),
    [profesionales]
  );

  const candidatos = useMemo(
    () => perfiles.filter((perfil) => rolDe(perfil) === 'profesional'),
    [perfiles]
  );

  return (
    <>
      <Tarjeta
        titulo="Profesionales"
        extra={<span className="contador neutro">{profesionales.length}</span>}
      >
        <p className="fino">
          Una fila aquí es alguien que <em>atiende</em>: de esto salen los cupos. El rol
          de la cuenta se cambia en la otra pestaña y son cosas distintas —se puede
          tener agenda sin cuenta, y cuenta sin agenda—.
        </p>

        {ordenados.length === 0 ? (
          <Vacio>Todavía no hay profesionales. El formulario de abajo crea el primero.</Vacio>
        ) : (
          <ul className="filas">
            {ordenados.map((profesional) => {
              const id = idDe(profesional);
              return (
                <FilaDeProfesional
                  key={id}
                  profesional={profesional}
                  horarios={horarios.filter(
                    (horario) => String(horario.profesional_id ?? '') === id
                  )}
                  candidatos={candidatos}
                  perfiles={perfiles}
                  abierto={abierto === id}
                  alAbrir={() => setAbierto(abierto === id ? '' : id)}
                  ocupado={ocupado}
                  ejecutar={ejecutar}
                />
              );
            })}
          </ul>
        )}
      </Tarjeta>

      <FormularioDeProfesional candidatos={candidatos} ocupado={ocupado} ejecutar={ejecutar} />
    </>
  );
}

function FilaDeProfesional({
  profesional,
  horarios,
  candidatos,
  perfiles,
  abierto,
  alAbrir,
  ocupado,
  ejecutar,
}: {
  profesional: Profesional;
  horarios: Horario[];
  candidatos: Perfil[];
  perfiles: Perfil[];
  abierto: boolean;
  alAbrir: () => void;
  ocupado: string;
  ejecutar: Ejecutar;
}) {
  const id = idDe(profesional);
  const activo = profesional.activo === undefined || esVerdad(profesional.activo);
  const userId = String(profesional.user_id ?? '');
  const cuenta = perfiles.find((perfil) => String(perfil.user_id ?? '') === userId);
  const vivos = horarios.filter((horario) => horario.activo === undefined || esVerdad(horario.activo));
  const [vinculo, setVinculo] = useState(userId);

  return (
    <li className="fila-profesional">
      <div className="identidad">
        <span className="quien">{String(profesional.nombre ?? '(sin nombre)')}</span>
        <span className="etiqueta e-agendado">{String(profesional.centro ?? '—')}</span>
        <span className="fino">{String(profesional.especialidad ?? 'sin especialidad')}</span>
        {!activo && <span className="etiqueta">inactivo</span>}
        <span className="fino">
          {vivos.length} horario{vivos.length === 1 ? '' : 's'}
        </span>
      </div>

      <div className="controles">
        <button type="button" className="fino" onClick={alAbrir} aria-expanded={abierto}>
          {abierto ? 'Cerrar' : 'Horarios y cuenta'}
        </button>
        <button
          type="button"
          className="fino"
          disabled={ocupado === `profesional:${id}`}
          onClick={() =>
            void ejecutar(
              `profesional:${id}`,
              'profesionales',
              () => roble.update('profesionales', id, { activo: !activo }),
              activo
                ? `${String(profesional.nombre ?? 'El profesional')} queda inactivo: no se le publican cupos nuevos.`
                : `${String(profesional.nombre ?? 'El profesional')} vuelve a estar activo.`
            )
          }
        >
          {activo ? 'Desactivar' : 'Activar'}
        </button>
      </div>

      {abierto && (
        <div className="desplegado">
          <h3>Cuenta vinculada</h3>
          <p className="fino">
            {cuenta
              ? `Hoy: ${String(cuenta.nombre ?? cuenta.email ?? userId)}.`
              : 'Sin cuenta. La agenda funciona igual, pero esta persona no puede entrar a ver sus citas: se buscan por «profesional_user_id».'}
          </p>
          <div className="controles">
            <label>
              Cuenta con rol profesional
              <select value={vinculo} onChange={(evento) => setVinculo(evento.target.value)}>
                <option value="">Sin cuenta</option>
                {candidatos.map((perfil) => (
                  <option key={idDe(perfil)} value={String(perfil.user_id ?? '')}>
                    {String(perfil.nombre ?? perfil.email ?? perfil.user_id)}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="principal fino"
              disabled={vinculo === userId || ocupado === `vinculo:${id}`}
              onClick={() =>
                void ejecutar(
                  `vinculo:${id}`,
                  'profesionales',
                  () => roble.update('profesionales', id, { user_id: vinculo || null }),
                  vinculo ? 'Cuenta vinculada.' : 'Cuenta desvinculada.'
                )
              }
            >
              Vincular
            </button>
          </div>
          {candidatos.length === 0 && (
            <p className="fino">
              Ninguna cuenta tiene rol profesional todavía. Se le da en la pestaña de
              usuarios.
            </p>
          )}

          <h3>Horarios</h3>
          {horarios.length === 0 ? (
            <Vacio>Sin horarios. Sin esto no se pueden publicar cupos.</Vacio>
          ) : (
            <ul className="horarios">
              {[...horarios]
                .sort((a, b) => Number(a.dia_semana) - Number(b.dia_semana))
                .map((horario) => (
                  <FilaDeHorario
                    key={idDe(horario)}
                    horario={horario}
                    ocupado={ocupado}
                    ejecutar={ejecutar}
                  />
                ))}
            </ul>
          )}
          <FormularioDeHorario profesionalId={id} ocupado={ocupado} ejecutar={ejecutar} />
        </div>
      )}
    </li>
  );
}

function FilaDeHorario({
  horario,
  ocupado,
  ejecutar,
}: {
  horario: Horario;
  ocupado: string;
  ejecutar: Ejecutar;
}) {
  const id = idDe(horario);
  const activo = horario.activo === undefined || esVerdad(horario.activo);
  const clave = `horario:${id}`;

  return (
    <li>
      <span className="quien">{diaSemanaLegible(horario.dia_semana)}</span>
      <span className="cuando">
        {String(horario.hora_inicio ?? '—')}–{String(horario.hora_fin ?? '—')}
      </span>
      <span className="fino">
        {String(horario.minutos_cupo ?? 30)} min · {String(horario.modalidad ?? 'presencial')}
      </span>
      {!activo && <span className="etiqueta">inactivo</span>}
      <button
        type="button"
        className="enlace"
        disabled={ocupado === clave}
        onClick={() =>
          void ejecutar(
            clave,
            'horarios',
            () => roble.update('horarios', id, { activo: !activo }),
            activo
              ? 'Horario desactivado. Los cupos ya publicados no se borran.'
              : 'Horario activado.'
          )
        }
      >
        {activo ? 'Desactivar' : 'Activar'}
      </button>
    </li>
  );
}

const HORARIO_EN_BLANCO = {
  dia: '0',
  inicio: '08:00',
  fin: '12:00',
  minutos: '30',
  modalidad: 'presencial',
};

function FormularioDeHorario({
  profesionalId,
  ocupado,
  ejecutar,
}: {
  profesionalId: string;
  ocupado: string;
  ejecutar: Ejecutar;
}) {
  const [campos, setCampos] = useState(HORARIO_EN_BLANCO);
  const clave = `nuevo-horario:${profesionalId}`;

  // Las horas vienen de un `<input type="time">`, siempre «HH:MM» con cero delante,
  // así que compararlas como texto es correcto y no hace falta convertirlas.
  const problema =
    campos.fin <= campos.inicio
      ? 'La hora de fin tiene que ser posterior a la de inicio.'
      : Number(campos.minutos) < 5
        ? 'Un cupo de menos de cinco minutos no es un cupo.'
        : '';

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (problema) return;
    void ejecutar(
      clave,
      'horarios',
      async () => {
        await roble.create('horarios', {
          profesional_id: profesionalId,
          dia_semana: Number(campos.dia),
          hora_inicio: campos.inicio,
          hora_fin: campos.fin,
          minutos_cupo: Number(campos.minutos),
          modalidad: campos.modalidad,
          activo: true,
        });
        setCampos(HORARIO_EN_BLANCO);
      },
      'Horario añadido. Los cupos se publican desde la vista del centro.'
    );
  }

  return (
    <form className="formulario rejilla" onSubmit={enviar}>
      <label>
        Día
        <select value={campos.dia} onChange={(e) => setCampos({ ...campos, dia: e.target.value })}>
          {diasDeLaSemana().map((dia) => (
            <option key={dia.valor} value={String(dia.valor)}>
              {dia.nombre}
            </option>
          ))}
        </select>
      </label>
      <label>
        Desde
        <input
          type="time"
          value={campos.inicio}
          onChange={(e) => setCampos({ ...campos, inicio: e.target.value })}
          required
        />
      </label>
      <label>
        Hasta
        <input
          type="time"
          value={campos.fin}
          onChange={(e) => setCampos({ ...campos, fin: e.target.value })}
          required
        />
      </label>
      <label>
        Minutos por cupo
        <input
          type="number"
          min={5}
          max={180}
          value={campos.minutos}
          onChange={(e) => setCampos({ ...campos, minutos: e.target.value })}
          required
        />
      </label>
      <label>
        Modalidad
        <select
          value={campos.modalidad}
          onChange={(e) => setCampos({ ...campos, modalidad: e.target.value })}
        >
          <option value="presencial">Presencial</option>
          <option value="virtual">Virtual</option>
        </select>
      </label>
      <button
        type="submit"
        className="principal fino"
        disabled={Boolean(problema) || ocupado === clave}
      >
        {ocupado === clave ? 'Añadiendo…' : 'Añadir horario'}
      </button>
      {problema && <span className="fino problema">{problema}</span>}
    </form>
  );
}

const PROFESIONAL_EN_BLANCO = {
  nombre: '',
  email: '',
  centro: 'CMU' as Centro,
  especialidad: '',
  userId: '',
};

function FormularioDeProfesional({
  candidatos,
  ocupado,
  ejecutar,
}: {
  candidatos: Perfil[];
  ocupado: string;
  ejecutar: Ejecutar;
}) {
  const [campos, setCampos] = useState(PROFESIONAL_EN_BLANCO);
  const clave = 'nuevo-profesional';

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    void ejecutar(
      clave,
      'profesionales',
      async () => {
        await roble.create('profesionales', {
          nombre: campos.nombre.trim(),
          email: campos.email.trim().toLowerCase() || null,
          centro: campos.centro,
          especialidad: campos.especialidad.trim() || null,
          user_id: campos.userId || null,
          activo: true,
        });
        setCampos(PROFESIONAL_EN_BLANCO);
      },
      'Profesional creado. Ábrelo para ponerle horarios: sin horarios no hay cupos.'
    );
  }

  return (
    <Tarjeta titulo="Añadir profesional">
      <form className="formulario rejilla" onSubmit={enviar}>
        <label>
          Nombre
          <input
            type="text"
            value={campos.nombre}
            onChange={(e) => setCampos({ ...campos, nombre: e.target.value })}
            required
            minLength={3}
          />
        </label>
        <label>
          Correo
          <input
            type="email"
            value={campos.email}
            onChange={(e) => setCampos({ ...campos, email: e.target.value })}
          />
        </label>
        <label>
          Centro
          <select
            value={campos.centro}
            onChange={(e) => setCampos({ ...campos, centro: e.target.value as Centro })}
          >
            {CENTROS.map((centro) => (
              <option key={centro} value={centro}>
                {centro}
              </option>
            ))}
          </select>
        </label>
        <label>
          Especialidad
          <input
            type="text"
            value={campos.especialidad}
            onChange={(e) => setCampos({ ...campos, especialidad: e.target.value })}
            placeholder="Medicina general, Psicología…"
          />
        </label>
        <label>
          Cuenta (opcional)
          <select
            value={campos.userId}
            onChange={(e) => setCampos({ ...campos, userId: e.target.value })}
          >
            <option value="">Sin cuenta</option>
            {candidatos.map((perfil) => (
              <option key={idDe(perfil)} value={String(perfil.user_id ?? '')}>
                {String(perfil.nombre ?? perfil.email ?? perfil.user_id)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="principal fino" disabled={ocupado === clave}>
          {ocupado === clave ? 'Creando…' : 'Crear'}
        </button>
      </form>
    </Tarjeta>
  );
}

// --------------------------------------------------------------------- ajustes

function SeccionAjustes({
  ajustes,
  quien,
  ocupado,
  ejecutar,
}: {
  ajustes: Ajustes;
  quien: string;
  ocupado: string;
  ejecutar: Ejecutar;
}) {
  const [borrador, setBorrador] = useState<Ajustes>(ajustes);

  // Se resincroniza cuando el padre recarga: así, tras guardar, el campo muestra lo
  // que quedó escrito en ROBLE y no lo que se tecleó.
  useEffect(() => setBorrador(ajustes), [ajustes]);

  return (
    <>
      <Tarjeta titulo="Ajustes de la plataforma">
        <p className="fino">
          Cada ajuste dice quién lo lee. No hay ninguno que no esté conectado a algo:
          un interruptor que no hace nada es peor que no tenerlo.
        </p>
        {CATALOGO.map((definicion) => (
          <FilaDeAjuste
            key={definicion.clave}
            definicion={definicion}
            valor={borrador[definicion.clave] ?? definicion.predeterminado}
            guardado={ajustes[definicion.clave] ?? definicion.predeterminado}
            alEscribir={(valor) =>
              setBorrador((previo) => ({ ...previo, [definicion.clave]: valor }))
            }
            quien={quien}
            ocupado={ocupado}
            ejecutar={ejecutar}
          />
        ))}
      </Tarjeta>

      <Tarjeta titulo="Lo que no se configura desde aquí">
        <dl className="datos">
          <dt>Centros</dt>
          <dd>
            CMU y CAE están en el código y en los roles. Añadir un tercero es un cambio
            de esquema, no un ajuste.
          </dd>
          <dt>Protocolo de triaje</dt>
          <dd>
            Vive en <code>protocolos/triaje-v0.md</code> y viaja dentro del paquete de
            la Lambda: cambiarlo es un despliegue, con revisión en el pull request. Un
            campo de texto aquí sería editar criterio clínico sin dejar rastro.
          </dd>
          <dt>Correos y credenciales</dt>
          <dd>
            En Parameter Store y en las variables de Terraform. No pasan por el
            navegador.
          </dd>
        </dl>
      </Tarjeta>
    </>
  );
}

function FilaDeAjuste({
  definicion,
  valor,
  guardado,
  alEscribir,
  quien,
  ocupado,
  ejecutar,
}: {
  definicion: DefinicionDeAjuste;
  valor: string;
  guardado: string;
  alEscribir: (valor: string) => void;
  quien: string;
  ocupado: string;
  ejecutar: Ejecutar;
}) {
  const clave = `ajuste:${definicion.clave}`;
  const problema = problemaDeAjuste(definicion, valor);
  const cambiado = valor !== guardado;

  return (
    <div className="ajuste">
      <label>
        {definicion.etiqueta}
        {definicion.tipo === 'numero' ? (
          <input
            type="number"
            min={definicion.minimo}
            max={definicion.maximo}
            value={valor}
            onChange={(evento) => alEscribir(evento.target.value)}
          />
        ) : (
          <textarea
            rows={2}
            maxLength={definicion.largo}
            value={valor}
            onChange={(evento) => alEscribir(evento.target.value)}
          />
        )}
        <small>
          {definicion.ayuda} Lo lee <code>{definicion.loLee}</code>.
        </small>
      </label>
      <div className="controles">
        <button
          type="button"
          className="principal fino"
          disabled={!cambiado || Boolean(problema) || ocupado === clave}
          onClick={() =>
            void ejecutar(
              clave,
              'ajustes',
              () => guardarAjuste(definicion.clave, valor, quien),
              `«${definicion.etiqueta}» guardado.`
            )
          }
        >
          {ocupado === clave ? 'Guardando…' : 'Guardar'}
        </button>
        {problema && <span className="fino problema">{problema}</span>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------ datos

async function leerTodo(): Promise<Datos> {
  const [perfiles, profesionales, horarios, ajustes] = await Promise.all([
    leer<Perfil>('perfiles'),
    leer<Profesional>('profesionales'),
    leer<Horario>('horarios'),
    leerAjustes(),
  ]);
  return { perfiles, profesionales, horarios, ajustes };
}

/**
 * Una lectura que no tumba la pantalla.
 *
 * Se leen las tablas enteras, sin filtro: son las tres tablas pequeñas del sistema
 * —cuentas, quién atiende y su plantilla semanal— y quien administra la plataforma
 * las necesita completas. Las tablas grandes (casos, conversaciones) no se tocan.
 */
async function leer<T>(tabla: string): Promise<T[]> {
  try {
    return (await roble.read(tabla, {})) as T[];
  } catch (error) {
    console.warn(`No se pudo leer ${tabla}`, error);
    return [];
  }
}

function contar(datos: Datos) {
  const activos = datos.profesionales.filter(
    (fila) => fila.activo === undefined || esVerdad(fila.activo)
  );
  const conHorario = new Set(
    datos.horarios
      .filter((horario) => horario.activo === undefined || esVerdad(horario.activo))
      .map((horario) => String(horario.profesional_id ?? ''))
  );
  return {
    cuentas: datos.perfiles.length,
    profesionalesActivos: activos.length,
    conHorario: activos.filter((fila) => conHorario.has(idDe(fila))).length,
  };
}

function rolDe(perfil: Perfil): Rol {
  const texto = String(perfil.rol ?? '')
    .trim()
    .toLowerCase();
  return (ROLES as readonly string[]).includes(texto) ? (texto as Rol) : 'paciente';
}

function centroDe(perfil: Perfil): Centro | '' {
  const texto = String(perfil.centro ?? '')
    .trim()
    .toUpperCase();
  return texto === 'CMU' || texto === 'CAE' ? texto : '';
}

function filtrar(perfiles: Perfil[], filtro: string): Perfil[] {
  const buscado = filtro.trim().toLowerCase();
  const coincide = (perfil: Perfil) =>
    !buscado ||
    [perfil.nombre, perfil.email, perfil.rol, rolLegible(perfil.rol), perfil.centro]
      .map((campo) => String(campo ?? '').toLowerCase())
      .some((campo) => campo.includes(buscado));

  return perfiles
    .filter(coincide)
    .sort((a, b) => String(a.nombre ?? a.email ?? '').localeCompare(String(b.nombre ?? b.email ?? '')));
}

/**
 * El mensaje de un fallo de escritura, con la pista del permiso cuando toca.
 *
 * ROBLE responde **500** —no 403— cuando al rol le falta `<tabla>:update`, y este es
 * el sitio donde más probable es tropezar con eso: `profesionales`, `horarios` y
 * `ajustes` no estaban en la lista de permisos hasta que existió esta pantalla.
 */
function explicarFallo(fallo: unknown, tabla: string): string {
  const mensaje = mensajeDeError(fallo);
  if (!esFalloDeServidor(fallo)) return mensaje;
  return (
    `${mensaje} Si es la primera vez que usas esta pantalla, lo más probable es que al ` +
    `rol «user» de ROBLE le falte el permiso «${tabla}:update» —Configuración → ` +
    `PERMISOS en la consola—. Está en docs/runbook-roble.md.`
  );
}
