# Datos y herramientas

La referencia de las dos cosas que hay que mirar juntas para entender el sistema: **qué
guarda** y **qué puede hacer un agente con lo guardado**.

Este documento es descriptivo, no normativo. La fuente de verdad del esquema es
[`app/esquema/bootstrap_roble.mjs`](../app/esquema/bootstrap_roble.mjs) y la del
catálogo es
[`lambdas/comun/caresync_comun/catalogo_herramientas.py`](../lambdas/comun/caresync_comun/catalogo_herramientas.py);
si esta página y el código discrepan, manda el código y esta página está mal. Para el
*por qué* de las decisiones, [`arquitectura.md`](arquitectura.md); para operar ROBLE,
[`runbook-roble.md`](runbook-roble.md).

## Las catorce tablas

`_id UUID` lo pone ROBLE en todas y no se declara. Los `timestamp` se escriben en ISO
8601. Una columna marcada `·` admite nulos.

### `perfiles` — el rol de cada cuenta

| Columna | Tipo | |
|---|---|---|
| `user_id` | text | El `sub` del token de ROBLE. La clave real de la tabla |
| `nombre` | text | |
| `email` | text | |
| `rol` | text | `paciente` · `profesional` · `admin_cmu` · `admin_cae` · `admin_plataforma` |
| `centro` | text | `·` `CMU` o `CAE`. Nulo para `paciente` y `admin_plataforma` |
| `creado_en` | timestamp | |

**Es la única fuente del rol en las dos capas.** Lo era a medias hasta el 2026-08-27,
cuando ROBLE dejó de aceptar el campo `extra` en `register` y se quitó la segunda
fuente; el síntoma de tenerla era una persona que veía la vista de administración y
recibía 403 en cada herramienta. Más de una fila para el mismo `user_id` es una
anomalía y las dos capas la tratan como «sin perfil» → `paciente`.

### `casos` — un episodio de atención

| Columna | Tipo | |
|---|---|---|
| `paciente_user_id` | text | |
| `paciente_nombre` `paciente_email` | text | Copiados al abrir el caso: sin claves ajenas, un `join` costaría una lectura extra por caso |
| `estado` | text | Ver [los estados](#los-estados-y-quién-los-escribe) |
| `centro` | text | `·` Nulo hasta que el triaje canaliza |
| `nivel_urgencia` | int4 | `·` 1 emergencia · 2 prioritario (72 h) · 3 regular (7 días) · 4 orientación |
| `motivo` | text | `·` |
| `resumen_triaje` | text | `·` Lo escribe el agente de triaje para el profesional que atenderá |
| `creado_en` `actualizado_en` | timestamp | |

### `conversaciones` — el hilo completo

| Columna | Tipo | |
|---|---|---|
| `caso_id` | text | |
| `agente` | text | `triaje` · `agenda` · `seguimiento` |
| `autor` | text | Quién habla en ese mensaje |
| `contenido` | text | |
| `creado_en` | timestamp | |

Es **lo más sensible del sistema** y por eso vive en ROBLE —infraestructura de la
universidad— y no en AWS. No pasa por CloudWatch: los logs llevan identificadores y
métricas, nunca el texto.

### `profesionales` y `horarios` — de quién y cuándo hay agenda

| `profesionales` | Tipo | |
|---|---|---|
| `user_id` | text | `·` Vincula con una cuenta de ROBLE. Nulo mientras no la tenga |
| `nombre` | text | |
| `email` | text | `·` A donde se le avisa de un caso nuevo |
| `centro` | text | `CMU` o `CAE` |
| `especialidad` | text | `·` |
| `activo` | bool | |

| `horarios` | Tipo | |
|---|---|---|
| `profesional_id` | text | |
| `dia_semana` | int4 | **0 = lunes … 6 = domingo.** No es la convención de `Date.getDay()`, que empieza en domingo |
| `hora_inicio` `hora_fin` | text | `HH:MM` en hora de Bogotá |
| `minutos_cupo` | int4 | Duración de cada espacio; 30 por defecto |
| `modalidad` | text | `·` `presencial` o `virtual` |
| `activo` | bool | |

Un horario es una **plantilla semanal**, no una agenda. La agenda son los `cupos`, que
alguien tiene que publicar: `horarios` dice «los martes de 8 a 12», `cupos` dice «el
martes 9 de septiembre a las 8:30».

### `cupos` — la agenda materializada

| Columna | Tipo | |
|---|---|---|
| `centro` `profesional_id` | text | |
| `inicio` `fin` | timestamp | |
| `estado` | text | `libre` → `reservado` → `confirmado` |
| `modalidad` | text | `·` |
| `caso_id` | text | `·` Quién lo tiene, mientras lo tiene |
| `reserva_testigo` | text | `·` **La columna que hace posible reservar sin escrituras condicionales** |
| `reservado_en` | timestamp | `·` |

ROBLE no tiene `UPDATE ... WHERE estado = 'libre'`, así que reservar es *escribir un
testigo único, releer y comprobar que el testigo que quedó es el mío*. Si es de otro,
se perdió la carrera y se ofrecen alternativas. La otra mitad del patrón la hace la
Lambda de recordatorios cada 15 minutos: devolver a `libre` lo que quedó `reservado`
sin confirmar. Ver `reservar_cupo` en
[`roble_acceso.py`](../lambdas/comun/caresync_comun/roble_acceso.py).

### `citas` — la reserva confirmada

| Columna | Tipo | |
|---|---|---|
| `caso_id` `cupo_id` `profesional_id` | text | |
| `profesional_user_id` `profesional_nombre` | text | `·` Copiados para no releer `profesionales` en cada pantalla |
| `paciente_user_id` `centro` | text | |
| `inicio` `fin` | timestamp | |
| `estado` | text | `confirmada` → `atendida` |
| `creado_en` | timestamp | |

### `planes` e `indicaciones` — lo que dice el profesional

| `planes` | Tipo | |
|---|---|---|
| `caso_id` | text | |
| `profesional_user_id` | text | |
| `profesional_nombre` | text | `·` |
| `resumen` | text | |
| `creado_en` | timestamp | |

| `indicaciones` | Tipo | |
|---|---|---|
| `caso_id` `plan_id` | text | |
| `texto` | text | |
| `frecuencia` | text | `·` En lenguaje natural: «cada 12 horas», «cada 2 días», «semanal» |
| `activa` | bool | Desactivarla detiene sus recordatorios futuros |
| `creado_en` | timestamp | |

**Ningún agente escribe aquí.** El plan clínico lo redacta una persona en la vista del
profesional; el modelo lo lee para acompañar y no puede añadir, quitar ni cambiar una
indicación. Es la línea más importante del diseño y está sostenida por el catálogo de
herramientas, no por el prompt: no existe ninguna herramienta que escriba en estas dos
tablas.

### `adherencia` y `evolucion` — lo que reporta la persona

| `adherencia` | Tipo | |
|---|---|---|
| `caso_id` `indicacion_id` | text | |
| `cumplida` | bool | |
| `nota` | text | `·` El motivo, si no la cumplió. Es lo que el profesional necesita leer |
| `reportado_en` | timestamp | |

| `evolucion` | Tipo | |
|---|---|---|
| `caso_id` | text | |
| `escala` | int4 | 0 (peor que nunca) a 10 (como antes de todo esto) |
| `nota` | text | `·` |
| `reportado_en` | timestamp | |

### `eventos` — la bitácora que ve el profesional

| Columna | Tipo | |
|---|---|---|
| `caso_id` | text | `·` |
| `tipo` | text | |
| `severidad` | text | |
| `actor_user_id` `actor_rol` | text | `·` |
| `detalle` | jsonb | `·` |
| `creado_en` | timestamp | |

**No es el log técnico**, que está en CloudWatch. Aquí queda lo que una persona
necesita ver: cada herramienta que escribe deja rastro, y los escalamientos de
urgencia también.

### `recordatorios` — lo prometido, con fecha

| Columna | Tipo | |
|---|---|---|
| `caso_id` `indicacion_id` | text | |
| `programado_para` | timestamp | |
| `estado` | text | `pendiente` → `enviado` · `no_entregado` · `cancelado` |
| `canal` | text | |
| `texto` | text | |
| `creado_en` | timestamp | |
| `enviado_en` | timestamp | `·` |
| `detalle` | text | `·` Por qué no salió, recortado a 300 caracteres |

Se materializan por adelantado en la tabla y no se calculan al vuelo, para que quede
rastro de **qué se le prometió a la persona y cuándo**.

### `ajustes` — clave/valor

| Columna | Tipo | |
|---|---|---|
| `clave` | text | `UNIQUE` |
| `valor` | text | `·` Siempre texto, aunque sea un número |
| `actualizado_en` | timestamp | |
| `actualizado_por` | text | `·` |

Clave/valor y no una columna por ajuste: añadir un ajuste no debe necesitar `alter`,
que ninguna cuenta de la aplicación tiene. El catálogo cerrado de claves válidas vive
en [`app/src/ajustes.ts`](../app/src/ajustes.ts) y **cada definición dice quién lee el
valor**; si un ajuste se queda sin lector, se borra del catálogo. Es la única tabla que
las Lambdas no tocan.

## Quién escribe cada tabla

Las dos capas escriben en ROBLE, y no en las mismas tablas. Sirve para saber dónde
buscar cuando algo aparece mal:

| Tabla | PWA | Lambdas |
|---|---|---|
| `perfiles` | crea (registro) · actualiza (vista de plataforma) | sólo lee |
| `casos` | actualiza (el profesional al guardar el plan) | **crea y actualiza** |
| `conversaciones` | sólo lee | **crea** |
| `profesionales` | crea y actualiza (plataforma) | sólo lee |
| `horarios` | crea y actualiza (plataforma) | sólo lee |
| `cupos` | crea en lote (publicar agenda) | **actualiza** (reserva, confirma, libera) |
| `citas` | actualiza (`atendida`) | **crea** |
| `planes` | **crea** (profesional) | sólo lee |
| `indicaciones` | **crea en lote y desactiva** (profesional) | sólo lee |
| `adherencia` | sólo lee | **crea** |
| `evolucion` | sólo lee | **crea** |
| `eventos` | sólo lee | **crea** |
| `recordatorios` | sólo lee | **crea y actualiza** |
| `ajustes` | crea y actualiza (plataforma) | no la toca |

**Nada borra filas.** No hay una sola llamada a `delete` en el proyecto: un caso
cerrado se marca, no se elimina. La consecuencia —qué hacer con filas huérfanas— está
en [`runbook-roble.md`](runbook-roble.md#filas-huérfanas).

Qué rol de ROBLE autoriza cada una de esas escrituras es otra capa y está en
[`runbook-roble.md`](runbook-roble.md#permisos-en-la-consola-de-roble). Recordar que
**una tabla sin permiso devuelve 500, no 403**.

## Los estados, y quién los escribe

### `casos`

| Estado | Lo escribe | |
|---|---|---|
| `abierto` | Lambda, al abrir el caso | Aún sin centro ni nivel |
| `canalizado` | `canalizar_caso` | Cierra el triaje y traspasa a agenda |
| `agendado` | `agendar_cita` | Al confirmar la cita |
| `en_seguimiento` | El profesional al guardar el plan · el primer reporte de `registrar_evolucion` | Sin ese segundo camino, quien reporta caería otra vez en el agente de agenda |
| `urgencia_escalada` | `escalar_urgencia` | No es terminal: se sigue acompañando a la persona |
| `atendido` | **nadie** | Está declarado y se lee, pero ninguna ruta lo escribe |
| `cerrado` | **nadie** | Igual: se filtra por él en tres pantallas y nada lo produce |

Los dos últimos son deuda conocida, no un descuido de este documento. Hoy un caso vive
para siempre en `en_seguimiento`: `agente_por_defecto` manda a seguimiento con
`atendido` o `en_seguimiento`, así que el comportamiento es el correcto, pero **nadie
puede cerrar un caso** y las listas de las vistas crecen sin tope. Cerrarlo bien pide
decidir quién lo cierra (el profesional, con un botón) y qué pasa con los
recordatorios pendientes — la Lambda ya los cancela cuando el caso está `cerrado`, así
que la mitad del trabajo está hecha.

### `cupos` y `citas`

`libre` → `reservado` → `confirmado`, con la vuelta `reservado` → `libre` que hace la
reconciliación. Las citas van `confirmada` → `atendida`.

## El catálogo de herramientas

Nueve herramientas. Una sola definición para dos consumidores: el orquestador la
traduce al `toolSpec` de la API Converse, y la función de herramientas la usa para
validar qué le piden y con qué rol.

| Herramienta | Roles | Escribe | Argumentos del modelo |
|---|---|---|---|
| `consultar_estado_caso` | paciente · profesional · admin CMU · admin CAE | | — |
| `canalizar_caso` | paciente | ● | `centro` `nivel_urgencia` `resumen` |
| `escalar_urgencia` | paciente · profesional | ● | `motivo` |
| `consultar_disponibilidad` | paciente · admin CMU · admin CAE | | `dias_adelante` |
| `agendar_cita` | paciente · admin CMU · admin CAE | ● | `cupo_id` |
| `notificar_profesional` | paciente · admin CMU · admin CAE | ● | — |
| `consultar_plan` | paciente · profesional | | — |
| `registrar_evolucion` | paciente | ● | `escala` `nota` |
| `registrar_adherencia` | paciente | ● | `indicacion_id` `cumplida` `nota` |

Tres reglas que este catálogo hace cumplir **en código y no en el prompt**, porque un
prompt se puede ignorar:

- **Qué rol puede usar cada herramienta.** `permitida(nombre, rol)` se comprueba en la
  función de herramientas, que es donde ocurre el efecto.
- **Qué herramientas ve cada agente.** El modelo no puede llamar a lo que no se le
  declara, así que la separación entre agentes es real.
- **`caso_id` nunca es un argumento del modelo.** Lo pone el orquestador desde la
  sesión. Si el modelo pudiera elegirlo, podría pedir el caso de otra persona.

Una herramienta marcada `escribe` deja rastro en `eventos` y no se puede llamar dos
veces en la misma vuelta.

`admin_plataforma` **no aparece en ninguna fila**: reparte roles y mantiene el
directorio, y no tiene nada que hacer en la conversación de un caso. Que no pueda
hablar con los agentes es deliberado, y es lo que hace que no necesite ver casos ni
conversaciones.

## Los tres agentes

Un solo tiempo de ejecución. Lo que los distingue es el prompt, la lista de
herramientas y los roles que pueden invocarlos:

| Agente | Roles | Herramientas | Traspasa |
|---|---|---|---|
| **Triaje** | paciente | `consultar_estado_caso` `escalar_urgencia` `canalizar_caso` | a **agenda**, cuando `canalizar_caso` tiene éxito |
| **Agenda y logística** | paciente · admin CMU · admin CAE | `consultar_estado_caso` `consultar_disponibilidad` `agendar_cita` `notificar_profesional` `escalar_urgencia` | — |
| **Seguimiento** | paciente · profesional | `consultar_estado_caso` `consultar_plan` `registrar_evolucion` `registrar_adherencia` `escalar_urgencia` | — |

El agente lo elige el servidor a partir del **estado del caso**, no de la vista que
llamó: quien vuelve a escribir tres días después cae en seguimiento y no repite el
triaje. Y el traspaso es explícito y de un solo salto —triaje → agenda—: la persona ve
una sola conversación, el sistema dos agentes con permisos distintos. Un tercer salto
sería una cadena que nadie puede seguir.

`escalar_urgencia` la llevan los tres, y por eso el texto exacto de la ruta de
emergencia va en el prompt de todos: el que escale tiene que saber decirlo.

El protocolo de triaje no está en el código sino en
[`protocolos/triaje-v0.md`](../protocolos/triaje-v0.md), que se hornea en el paquete de
la Lambda. Si el archivo faltara, el agente no improvisa: se le dice explícitamente que
no tiene protocolo, canaliza con nivel 2 y avisa de que un profesional revisará el
caso.

## El bucle

Cinco vueltas como máximo (`MAX_VUELTAS`), 800 tokens de respuesta, y un guardrail de
Bedrock si está configurado. Al agotar las vueltas se pide una respuesta final **sin
herramientas**, para que la persona reciba algo dicho y no un error. Cuando una
herramienta falla, el error no sube: se le devuelve al modelo como resultado, que es lo
que le permite explicarlo o intentar otra cosa.

El diagrama de secuencia de todo esto está en [`diagramas.md`](diagramas.md).
