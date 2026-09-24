# CareSync: especificación funcional para el rediseño del frontend

Este documento describe **qué hace hoy** la interfaz de CareSync, para rediseñar su
aspecto sin perder ningún comportamiento. Cubre dos pantallas:

1. **Administración de plataforma** (rol `admin_plataforma`): pestañas *Usuarios y
   roles*, *Profesionales* y *Ajustes*.
2. **Paciente** (rol `paciente`): chat con el asistente y panel lateral del caso.

Todo lo que está aquí es obligatorio salvo que diga lo contrario. Los textos entre
comillas son la copia actual en español; se puede mejorar la redacción, pero **no
quitar información ni avisos de seguridad**.

---

## 0. Restricciones técnicas (leer antes de generar código)

- **Stack:** React 18 + TypeScript + Vite. **No es Next.js.** No usar `"use client"`,
  `next/link`, `next/image`, `next/font`, server actions, rutas de `app/` ni nada del
  runtime de Next.
- **Sin enrutador.** La pantalla se elige por el rol de quien inició sesión. No hay
  URLs por vista; las pestañas son estado local.
- **Estilos:** hoy es un único CSS global sin Tailwind. Si el rediseño usa Tailwind o
  shadcn/ui, debe funcionar como plugin de Vite; indicarlo explícitamente.
- **Solo presentación.** Generar componentes que **reciban datos y callbacks por
  props** (contratos en §4 y §5). No escribir llamadas a APIs, `fetch`, ni datos
  simulados dentro de los componentes finales: la capa de datos existente
  (`roble.ts`, `agente.ts`, `ajustes.ts`, `sesion.tsx`) no se toca y se conecta
  después.
- **Idioma de la UI:** español (Colombia). Fechas y horas en zona `America/Bogota`,
  formato 24 h.
- **Accesibilidad que ya existe y debe conservarse:** pestañas con `role="tablist"` /
  `role="tab"` / `aria-selected`; avisos con `role="alert"` (error) o `role="status"`;
  botón de desplegar con `aria-expanded`; botón de ícono con `aria-label`; indicador
  "escribiendo" con `aria-live="polite"`; etiqueta de campo de chat solo para lectores
  de pantalla.
- **Responsive:** debe funcionar en celular (~400 px). Es una PWA.

---

## 1. Piezas comunes (usadas por ambas pantallas)

| Pieza | Comportamiento |
|---|---|
| **Cabecera** | Título, subtítulo opcional y botón **Salir** (con ícono) que cierra sesión. |
| **Aviso global** | Franja arriba de toda pantalla autenticada, cualquier rol. Muestra el texto del ajuste `aviso_global`. Si está vacío o solo tiene espacios, **no se renderiza nada**. |
| **Aviso** | Tres tipos: `info` (éxito/nota), `error` (`role="alert"`), `urgente` (con ícono de alerta). |
| **Cargando** | Texto con puntos suspensivos y `aria-live="polite"`, p. ej. "Buscando tu caso…". |
| **Vacío** | Mensaje de estado vacío dentro de una tarjeta. |
| **Tarjeta** | Título, ícono opcional, elemento extra opcional a la derecha (contador o etiqueta). |
| **Etiqueta de estado** | Estados del caso → texto: `abierto` "En triaje", `canalizado` "Canalizado", `agendado` "Con cita", `atendido` "Atendido", `en_seguimiento` "En seguimiento", `urgencia_escalada` "Urgencia escalada", `cerrado` "Cerrado". Estado desconocido: se muestra el texto crudo. Cada estado necesita un color propio. |
| **Nivel de urgencia** | 1 "Emergencia · ahora" (**visualmente distinto de todos los demás + ícono de alerta**), 2 "Prioritario · 72 h", 3 "Regular · 7 días", 4 "Orientación · sin cita", vacío/0 "Sin clasificar". |

Mensajes de error estándar que las pantallas pueden mostrar: "Tu sesión venció.
Vuelve a entrar.", "Tu cuenta no tiene permiso para esto.", "Eso no existe o ya no
está disponible.", "ROBLE está con problemas. Intenta en un momento.", y un mensaje de
límite de intentos. El texto puede ser largo (varias frases); el aviso debe admitirlo.

---

## 2. Pantalla: Administración de plataforma

### 2.1 Estructura general

- **Cabecera:** título "Plataforma". Subtítulo:
  `{nombre} · {N} cuenta(s) · {N} profesional(es) activo(s) · {N} con horario`
  con plural correcto en cada parte.
  - *Profesional activo*: su campo `activo` es verdadero **o no existe**.
  - *Con horario*: profesional activo que tiene al menos un horario activo.
- **Tres pestañas:** "Usuarios y roles" (**por defecto**), "Profesionales", "Ajustes".
- **Área de mensajes** encima del contenido, compartida por las tres pestañas:
  un aviso de error y un aviso de éxito. Ambos persisten al cambiar de pestaña. Toda
  acción nueva los limpia antes de ejecutarse.
- **Carga inicial:** "Leyendo cuentas, profesionales y ajustes…" en lugar del
  contenido de la pestaña.
- **Tras una acción exitosa** se muestra el mensaje de éxito y se recargan todos los
  datos. Tras un fallo, se muestra el error y no se recarga.
- **Estado ocupado:** una acción en curso a la vez. El botón que la lanzó se
  desactiva y cambia su texto ("Guardando…", "Añadiendo…", "Creando…").
- **Esta pantalla no muestra casos, conversaciones ni datos clínicos.** No añadir
  métricas ni accesos a ellos.

### 2.2 Pestaña "Usuarios y roles"

**Tarjeta "Usuarios"** con contador del total de cuentas.

- Línea de resumen por rol, solo roles con al menos una cuenta:
  "3 paciente · 2 profesional · 1 administración de plataforma" (separador " · ").
- **Campo Buscar** (tipo búsqueda, placeholder "nombre, correo o rol"). Filtra sin
  distinguir mayúsculas por nombre, correo, rol crudo, rol legible y centro.
- Texto de ayuda: "Aquí sólo aparecen las cuentas que tienen fila en «perfiles». Si a
  alguien le falló la escritura del perfil al registrarse, entra como paciente y no se
  ve en esta lista: que vuelva a entrar a la aplicación o que corra
  `esquema_roble.sh --perfil paciente` con su cuenta."
- Lista ordenada alfabéticamente por nombre (o correo si no hay nombre).
- Sin resultados: "Ninguna cuenta coincide."

**Cada fila de usuario:**

- Nombre (o "(sin nombre)"), correo (o "sin correo").
- Si es la cuenta de quien está conectado: etiqueta **"tu cuenta"** y, **en lugar de
  los controles**, el texto: "{Rol}[ · {centro}]. Tu propio rol no se cambia aquí:
  quitártelo te dejaría sin esta pantalla y sin forma de volver salvo el script."
- Si no es su cuenta:
  - **Selector Rol:** Paciente, Profesional, Administración CMU, Administración CAE,
    Administración de plataforma. Un rol desconocido en los datos se trata como
    Paciente.
  - **Selector Centro:** "Sin centro", CMU, CAE. **Solo habilitado si el rol elegido
    es Profesional.**
  - Reglas al cambiar el rol:
    - Administración CMU → centro pasa a CMU automáticamente.
    - Administración CAE → centro pasa a CAE automáticamente.
    - Profesional → conserva el centro que estuviera elegido.
    - Paciente / Administración de plataforma → centro vacío.
  - **Validación:** rol Profesional sin centro → texto de error "Un profesional
    necesita centro." bajo la fila.
  - **Botón Guardar:** deshabilitado si no hay cambios respecto a lo guardado, si hay
    error de validación o mientras guarda. Éxito: "{Nombre} ahora es {rol}[ del
    {centro}]. Tiene que salir y volver a entrar."
  - Los cambios sin guardar de cada fila se conservan mientras se escribe en el
    buscador.

**Tarjeta "Qué hace cada rol"** (informativa, lista de definición):
- Paciente: "Triaje, su caso y su seguimiento. Es el rol que da el registro."
- Profesional: "Su agenda y el plan de sus pacientes. Necesita **centro**, y además
  una fila en «Profesionales» vinculada a su cuenta para que le aparezcan citas."
- Administración CMU / CAE: "El tablero de su centro y el agente de agenda. El centro
  sale del rol."
- Administración de plataforma: "Esta pantalla. No ve casos ni conversaciones."

### 2.3 Pestaña "Profesionales"

**Tarjeta "Profesionales"** con contador (total, incluye inactivos).

- Texto: "Una fila aquí es alguien que *atiende*: de esto salen los cupos. El rol de
  la cuenta se cambia en la otra pestaña y son cosas distintas —se puede tener agenda
  sin cuenta, y cuenta sin agenda—."
- Lista ordenada por centro y luego por nombre.
- Vacío: "Todavía no hay profesionales. El formulario de abajo crea el primero."

**Cada fila de profesional (estado cerrado):**

- Nombre (o "(sin nombre)").
- Etiqueta de centro (o "—").
- Especialidad (o "sin especialidad") con **botón de ícono lápiz** (`title` y
  `aria-label` "Editar especialidad").
- Etiqueta "inactivo" si aplica.
- "{N} horario(s)" — cuenta solo horarios activos.
- **Botón "Horarios y cuenta"** / "Cerrar" (`aria-expanded`). **Solo un profesional
  desplegado a la vez**; abrir otro cierra el anterior.
- **Botón "Desactivar" / "Activar"** según estado. Sin confirmación. Éxito:
  - al desactivar: "{Nombre} queda inactivo: no se le publican cupos nuevos."
  - al activar: "{Nombre} vuelve a estar activo."

**Edición de especialidad en línea** (al pulsar el lápiz):

- El texto se reemplaza por un campo con foco automático, placeholder "Medicina
  general, Psicología…", precargado con el valor actual.
- **Guardar** (botón o tecla Enter) y **Cancelar** (enlace o tecla Escape; descarta).
- Se recortan espacios. Si el valor no cambió, no se guarda nada. Vacío se guarda
  como "sin especialidad".
- Éxito: "Especialidad de {Nombre} actualizada."

**Panel desplegado — "Cuenta vinculada":**

- Estado actual: "Hoy: {nombre de la cuenta}." o, si no hay: "Sin cuenta. La agenda
  funciona igual, pero esta persona no puede entrar a ver sus citas: se buscan por
  «profesional_user_id»."
- **Selector "Cuenta con rol profesional":** "Sin cuenta" + cuentas cuyo rol es
  Profesional.
- **Botón "Vincular":** deshabilitado si la selección es igual a la actual. Elegir
  "Sin cuenta" desvincula. Éxito: "Cuenta vinculada." / "Cuenta desvinculada."
- Si no hay ninguna cuenta con rol profesional: "Ninguna cuenta tiene rol profesional
  todavía. Se le da en la pestaña de usuarios."

**Panel desplegado — "Horarios":**

- Lista ordenada lunes → domingo. Cada horario: día, "HH:MM–HH:MM", "{min} min ·
  {modalidad}" (por defecto 30 y presencial), etiqueta "inactivo" si aplica, y enlace
  **"Desactivar" / "Activar"**. Sin confirmación. Éxito: "Horario desactivado. Los
  cupos ya publicados no se borran." / "Horario activado."
- Vacío: "Sin horarios. Sin esto no se pueden publicar cupos."
- **Formulario "Añadir horario"** (en línea, bajo la lista):

  | Campo | Control | Inicial | Reglas |
  |---|---|---|---|
  | Día | selector lunes…domingo (valor 0 = lunes … 6 = domingo) | lunes | — |
  | Desde | hora | 08:00 | obligatorio |
  | Hasta | hora | 12:00 | obligatorio; > Desde |
  | Minutos por cupo | número | 30 | obligatorio; mín. 5, máx. 180 |
  | Modalidad | selector | Presencial | Presencial / Virtual |

  - Errores en vivo: "La hora de fin tiene que ser posterior a la de inicio." y "Un
    cupo de menos de cinco minutos no es un cupo." Con error, el botón se deshabilita.
  - Botón "Añadir horario" ("Añadiendo…"). Tras crear, el formulario vuelve a sus
    valores iniciales. Éxito: "Horario añadido. Los cupos se publican desde la vista
    del centro."

**Tarjeta "Añadir profesional":**

| Campo | Control | Reglas |
|---|---|---|
| Nombre | texto | obligatorio, mín. 3 caracteres **sin contar espacios de los extremos** |
| Correo | email | opcional; formato email; se guarda en minúsculas |
| Centro | selector CMU / CAE | CMU por defecto |
| Especialidad | texto, placeholder "Medicina general, Psicología…" | opcional |
| Cuenta (opcional) | selector "Sin cuenta" + cuentas con rol Profesional | opcional |

- Botón "Crear" ("Creando…"). Se crea activo y el formulario se limpia. Éxito:
  "Profesional creado. Ábrelo para ponerle horarios: sin horarios no hay cupos."

**Fuera de alcance (no existe hoy, no inventarlo):** eliminar profesionales u
horarios, editar un horario existente, editar nombre/correo/centro de un profesional
ya creado.

### 2.4 Pestaña "Ajustes"

**Tarjeta "Ajustes de la plataforma"** (ícono de engranaje). Texto: "Cada ajuste dice
quién lo lee. No hay ninguno que no esté conectado a algo: un interruptor que no hace
nada es peor que no tenerlo."

La lista de ajustes **se genera a partir de un catálogo** (no está fija en el
componente). Cada ajuste tiene: etiqueta, tipo (`numero` | `texto`), texto de ayuda,
"Lo lee `{origen}`" (en fuente monoespaciada), mínimo/máximo (número) o largo máximo
(texto). Hoy hay dos:

| Ajuste | Control | Reglas y errores |
|---|---|---|
| **Días de agenda que publica cada tanda** — ayuda: "Cuántos días hacia adelante abre el botón «Publicar cupos» del personal administrativo. Más días es más agenda abierta y más filas en ROBLE." Lo lee `Administrativo.tsx → generarCupos()` | número | entero ("Tiene que ser un número entero."), mín. 1 ("El mínimo es 1."), máx. 60 ("El máximo es 60."). Vacío cuenta como bajo el mínimo. |
| **Aviso para todas las pantallas** — ayuda: "Se muestra arriba de todo a cualquiera que entre, con el rol que sea. Vacío para no mostrar nada. Sirve para «el CMU no atiende el viernes», no para instrucciones permanentes." Lo lee `App.tsx → <AvisoGlobal />` | área de texto, 2 filas | máx. 240 caracteres (el campo impide escribir más; mostrar contador es una mejora bienvenida) |

- **Un botón Guardar por ajuste**, deshabilitado si no cambió, si tiene error o
  mientras guarda. El error se muestra junto al botón. Éxito: "«{etiqueta}» guardado."
- Tras guardar, el campo muestra el valor que quedó almacenado.

**Tarjeta "Lo que no se configura desde aquí"** (informativa):
- Centros: "CMU y CAE están en el código y en los roles. Añadir un tercero es un
  cambio de esquema, no un ajuste."
- Protocolo de triaje: "Vive en `protocolos/triaje-v0.md` y viaja dentro del paquete
  de la Lambda: cambiarlo es un despliegue, con revisión en el pull request. Un campo
  de texto aquí sería editar criterio clínico sin dejar rastro."
- Correos y credenciales: "En Parameter Store y en las variables de Terraform. No
  pasan por el navegador."

---

## 3. Pantalla: Paciente

Diseño en **dos columnas** (se apilan en móvil): el **chat es el protagonista**, a la
izquierda o arriba; el panel lateral del caso a la derecha o abajo. **El paciente no
edita nada del panel lateral**: todo lo registra el asistente a partir de la
conversación. No añadir formularios, checkboxes de "cumplido" ni botones de agendar.

### 3.1 Cabecera y avisos

- Título: "Hola, {primer nombre}". Si el nombre es un correo, usar lo anterior a la
  `@`. **Si no hay nombre, el título es solo "Hola"** (no "Hola, hola").
- Subtítulo: "Cuéntale al asistente qué te pasa y él te acompaña desde ahí."
- Botón Salir.
- Aviso de error si falla la carga del caso.
- **Aviso urgente (obligatorio, muy visible)** cuando el caso tiene nivel de urgencia
  1: "Tu caso está marcado como emergencia. Si aún no has recibido ayuda, llama ya a
  la línea de emergencias del campus o al 123."

### 3.2 Chat con el asistente

- **Mensaje inicial del asistente** según el estado del caso:

  | Estado | Saludo |
  |---|---|
  | sin caso | "Hola. Soy el asistente de CareSync. Cuéntame qué te pasa y desde cuándo, con tus palabras. No soy personal de salud: te oriento y te conecto con quien sí lo es." |
  | `en_seguimiento` | "¿Cómo has estado desde la consulta? Cuéntame cómo vas con lo que te indicaron." |
  | `canalizado` | "Tu caso ya está canalizado. Si quieres, buscamos un espacio para tu cita." |
  | `agendado` | "Tu cita ya está agendada. Si algo cambió o tienes dudas, dime." |
  | otro | "Sigo aquí. Cuéntame en qué vamos." |

  El saludo debe calcularse **después** de cargar el caso (ver §6).
- **Hilo de mensajes** con tres tipos de burbuja, visualmente distinguibles:
  - `yo` — autor "Tú".
  - `agente` — autor: nombres de los agentes que intervinieron unidos por " → "
    (Triaje, Agenda y Logística, Seguimiento; p. ej. "Triaje → Agenda y Logística"),
    o "Asistente" si no viene ninguno.
  - `sistema` — autor "CareSync"; se usa para errores.
- **Acciones del asistente:** bajo una burbuja de agente, lista (con
  `aria-label="Lo que hizo el asistente"`) de lo que hizo, solo las exitosas:

  | Herramienta | Texto |
  |---|---|
  | canalizar_caso | Tu caso quedó canalizado al centro que corresponde |
  | escalar_urgencia | Se activó la ruta de urgencias y se avisó al equipo |
  | consultar_disponibilidad | Se revisaron los espacios disponibles |
  | agendar_cita | Tu cita quedó agendada |
  | notificar_profesional | El profesional ya tiene tu información |
  | registrar_evolucion | Se registró cómo te sientes |
  | registrar_adherencia | Se registró tu reporte del plan |
  | consultar_plan | Se revisó tu plan |
  | consultar_estado_caso | Se revisó el estado de tu caso |
  | (otra) | Se registró una acción |

  `escalar_urgencia` merece un tratamiento visual de alerta.
- **Indicador "escribiendo":** tres puntos animados mientras se espera respuesta,
  con texto oculto para lectores "El asistente está escribiendo".
- **Auto-scroll** suave al final del hilo con cada mensaje nuevo y al aparecer el
  indicador.
- **Redactor:**
  - Área de texto, 2 filas, placeholder "Cuéntame qué te pasa…", **máx. 2000
    caracteres**, etiqueta accesible "Escribe tu mensaje".
  - **Enter envía; Shift+Enter inserta salto de línea.**
  - Deshabilitado mientras se espera respuesta.
  - Botón "Enviar" ("Enviando…"), deshabilitado si el texto está vacío o solo tiene
    espacios, o mientras se espera.
  - Al enviar: el campo se vacía y el mensaje aparece de inmediato como burbuja `yo`.
- **Errores** (como burbuja `sistema`): "El asistente tardó demasiado. Vuelve a
  intentarlo." (45 s), "No hay conexión con CareSync.", o el mensaje del servidor. Si
  la sesión venció, además se cierra la sesión.
- Respuesta vacía del asistente: "Sigo aquí, pero no supe qué responder."
- **Descargo permanente** bajo el redactor (obligatorio, siempre visible, no un
  modal que se cierra): "Esto es un prototipo académico. No reemplaza una consulta con
  personal de salud. Si es una urgencia, llama a la línea de emergencias del campus o
  al 123."
- El historial del chat no persiste en pantalla al recargar (solo el saludo). Es el
  comportamiento actual; no hace falta diseñar carga de historial.

### 3.3 Panel lateral

Carga: "Buscando tu caso…". Tras cada respuesta del asistente el panel se recarga.

- **Sin caso:** tarjeta "Todavía no hay caso" — "Cuando le escribas al asistente se
  abre un caso y aquí verás en qué va."
- **Tarjeta "Tu caso"** con etiqueta de estado a la derecha:
  - Urgencia (componente Nivel).
  - Centro: "Centro Médico Universitario" (CMU), "Centro de Acompañamiento
    Estudiantil" (CAE) o "por definir".
  - Abierto: relativo — "ahora mismo", "hace N min", "hace N h", "hace N día(s)", o la
    fecha (dd mmm aaaa) si pasan de 30 días.
  - Resumen del triaje (párrafo), solo si existe.
- **Tarjeta "Tu cita"** (ícono de calendario):
  - Con cita: fecha y hora destacadas (p. ej. "martes, 14 de octubre, 10:30"),
    "{profesional o 'Profesional por asignar'} · {nombre del centro}", etiqueta de
    estado de la cita.
  - Sin cita: "Sin cita agendada. Pídele al asistente que te busque un espacio."
- **Tarjeta "Tu plan"** — solo si hay plan:
  - Resumen; "{profesional o 'Tu profesional'} · {fecha}".
  - Lista de indicaciones activas: texto; "{frecuencia o 'sin frecuencia'} ·
    {'X de Y cumplidas' o 'sin reportes'}".
  - Sin indicaciones: "Sin indicaciones activas."
- **Tarjeta "Cómo has ido"** — solo si hay reportes (máximo 5, el más reciente
  primero):
  - Cada uno: número de la escala 0–10 con color por franja (0–3 mal/rojo, 4–6
    medio/ámbar, 7–10 bien/verde; sin valor "—" neutro; **el 0 se muestra como "0"**),
    nota, "hace…".
  - Pie: "De 0 (peor que nunca) a 10 (como antes de todo esto). Lo registra el
    asistente con lo que tú le cuentas."

---

## 4. Contrato de props — Administración de plataforma

Los componentes deben aceptar estos datos (campos opcionales pueden faltar; booleanos
pueden llegar como `true`/`"true"`/`1`/`"t"` y ya vienen normalizados por la capa de
datos) y **emitir estos callbacks**. Los callbacks devuelven `Promise<void>`; el
componente no maneja errores, solo refleja `ocupado`.

```ts
type Rol = 'paciente' | 'profesional' | 'admin_cmu' | 'admin_cae' | 'admin_plataforma';
type Centro = 'CMU' | 'CAE';

interface Perfil { id: string; user_id: string; nombre?: string; email?: string; rol: Rol; centro: Centro | '' }
interface Profesional { id: string; nombre?: string; email?: string; centro?: Centro; especialidad?: string; activo: boolean; user_id?: string }
interface Horario { id: string; profesional_id: string; dia_semana: number /* 0=lunes */; hora_inicio: string; hora_fin: string; minutos_cupo: number; modalidad: 'presencial' | 'virtual'; activo: boolean }
interface DefinicionDeAjuste { clave: string; etiqueta: string; ayuda: string; loLee: string; tipo: 'numero' | 'texto'; minimo?: number; maximo?: number; largo?: number }

interface PlataformaProps {
  miNombre: string;
  miUserId: string;
  cargando: boolean;
  error: string;        // '' = sin error
  nota: string;         // '' = sin mensaje de éxito
  ocupado: string;      // clave de la acción en curso, '' = ninguna
  perfiles: Perfil[];
  profesionales: Profesional[];
  horarios: Horario[];
  catalogo: DefinicionDeAjuste[];
  ajustes: Record<string, string>; // valor guardado por clave
  validarAjuste: (def: DefinicionDeAjuste, valor: string) => string | null;
  onSalir(): void;
  onGuardarRol(perfilId: string, rol: Rol, centro: Centro | ''): Promise<void>;          // ocupado = `perfil:${perfilId}`
  onGuardarEspecialidad(profesionalId: string, valor: string): Promise<void>;            // `especialidad:${id}`
  onAlternarProfesional(profesionalId: string): Promise<void>;                          // `profesional:${id}`
  onVincular(profesionalId: string, userId: string /* '' = desvincular */): Promise<void>; // `vinculo:${id}`
  onAlternarHorario(horarioId: string): Promise<void>;                                  // `horario:${id}`
  onCrearHorario(profesionalId: string, h: { dia: number; inicio: string; fin: string; minutos: number; modalidad: string }): Promise<void>; // `nuevo-horario:${profesionalId}`
  onCrearProfesional(p: { nombre: string; email: string; centro: Centro; especialidad: string; userId: string }): Promise<void>;           // `nuevo-profesional`
  onGuardarAjuste(clave: string, valor: string): Promise<void>;                          // `ajuste:${clave}`
}
```

Los formularios deben limpiarse **solo si** la promesa se resuelve sin error.

## 5. Contrato de props — Paciente

```ts
type EstadoCaso = 'abierto' | 'canalizado' | 'agendado' | 'atendido' | 'en_seguimiento' | 'urgencia_escalada' | 'cerrado';

interface Turno {
  quien: 'yo' | 'agente' | 'sistema';
  texto: string;
  agentes?: string[];              // 'triaje' | 'agenda' | 'seguimiento'
  acciones?: { herramienta: string }[]; // ya filtradas a las exitosas
}

interface PacienteProps {
  nombre: string;
  cargando: boolean;
  error: string;
  caso: null | { estado: EstadoCaso; nivel_urgencia: number | null; centro: Centro | null; creado_en: string; resumen_triaje?: string };
  cita: null | { inicio: string; profesional_nombre?: string; centro?: Centro; estado: string };
  plan: null | { resumen: string; profesional_nombre?: string; creado_en: string };
  indicaciones: { id: string; texto: string; frecuencia?: string; cumplidas: number; reportes: number }[];
  evoluciones: { id: string; escala: number | null; nota?: string; reportado_en: string }[]; // ya limitadas a 5
  // chat
  turnos: Turno[];
  esperando: boolean;
  onEnviar(mensaje: string): void; // el componente recorta y no llama si está vacío o esperando
  onSalir(): void;
}
```

---

## 6. Defectos conocidos: corregir, no replicar

1. **Saludo del chat:** hoy siempre sale el de "sin caso" porque el chat se monta
   antes de que termine la carga. El rediseño debe mostrar el saludo que corresponde
   al estado real del caso (esperar a `cargando = false`, o actualizar el primer
   turno cuando llegue el caso).
2. **"Hola, hola"** cuando la cuenta no tiene nombre → debe decir "Hola".
3. **Nombre de profesional solo con espacios** pasa la validación → validar sobre el
   texto recortado.
4. **Editar especialidad pierde lo escrito si falla el guardado** → mantener el
   editor abierto con el texto hasta que el guardado tenga éxito.
5. **Cuenta vinculada que ya no tiene rol profesional:** el selector de "Vincular" no
   la muestra y aparece "Sin cuenta". Incluir la cuenta actualmente vinculada como
   opción aunque ya no sea profesional (marcada, p. ej., "(ya no es profesional)").

---

## 7. Lista de verificación de aceptación

Usar esta lista para revisar el diseño entregado. Cada casilla es un comportamiento
que existe hoy.

**Plataforma — general**
- [ ] Subtítulo con los tres conteos y plurales correctos
- [ ] Tres pestañas, "Usuarios y roles" por defecto, accesibles
- [ ] Avisos de error y éxito compartidos, persisten entre pestañas
- [ ] Estado de carga inicial
- [ ] Botón de la acción en curso deshabilitado y con texto de progreso

**Usuarios y roles**
- [ ] Contador y resumen por rol
- [ ] Buscador por nombre / correo / rol / centro; mensaje sin resultados
- [ ] Fila propia con etiqueta "tu cuenta" y sin controles
- [ ] Centro habilitado solo para Profesional; autoasignado para admin CMU/CAE
- [ ] Error "Un profesional necesita centro."
- [ ] Guardar deshabilitado sin cambios / con error
- [ ] Tarjeta "Qué hace cada rol"

**Profesionales**
- [ ] Orden por centro y nombre; contador; estado vacío
- [ ] Centro, especialidad, "inactivo", conteo de horarios activos
- [ ] Editar especialidad en línea: Enter guarda, Escape cancela, sin cambios no guarda
- [ ] Activar / desactivar profesional con mensajes
- [ ] Desplegable único "Horarios y cuenta"
- [ ] Vincular / desvincular cuenta; botón deshabilitado sin cambios; aviso sin candidatos
- [ ] Lista de horarios ordenada por día; activar / desactivar
- [ ] Formulario de horario: 5 campos, valores iniciales, dos validaciones, reinicio
- [ ] Formulario de profesional: 5 campos, validaciones, reinicio
- [ ] No se añadieron acciones inexistentes (eliminar, editar horario)

**Ajustes**
- [ ] Ajustes generados desde el catálogo, con ayuda y "Lo lee"
- [ ] Validación numérica (entero, mín., máx.) y de largo del texto
- [ ] Guardar por ajuste, deshabilitado sin cambios / con error
- [ ] Tarjeta "Lo que no se configura desde aquí"
- [ ] Aviso global visible arriba en todas las pantallas autenticadas; oculto si vacío

**Paciente**
- [ ] Saludo "Hola, {primer nombre}" / "Hola"
- [ ] Aviso urgente con nivel 1
- [ ] Saludo del asistente según estado del caso
- [ ] Burbujas `yo` / `agente` / `sistema` con autor correcto, cadena de agentes
- [ ] Lista de acciones traducidas; `escalar_urgencia` destacado
- [ ] Indicador "escribiendo" accesible; auto-scroll
- [ ] Enter envía, Shift+Enter salto de línea; 2000 caracteres; deshabilitado mientras espera
- [ ] Mensajes de error como burbuja de sistema
- [ ] Descargo de "prototipo académico / 123" siempre visible
- [ ] Panel: sin caso / Tu caso / Tu cita / Tu plan / Cómo has ido, con sus estados vacíos
- [ ] Colores de la escala 0–10 y el 0 visible como "0"
- [ ] Ninguna acción editable en el panel lateral
- [ ] Funciona a ~400 px de ancho
