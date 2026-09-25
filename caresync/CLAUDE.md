# CareSync — contexto de trabajo

Complementa el `CLAUDE.md` de la raíz (reglas de `_scratch/`, que siguen vigentes).
Aquí está el mapa del sistema y lo que no se debe romper.

El trabajo está repartido en tres frentes, y quien te escribe suele estar en uno:

| | |
|---|---|
| **Alejandro Santiago** | Infraestructura y despliegues: cuenta AWS, Terraform, esquema de ROBLE, CI, observabilidad y costes |
| **Kevin Ruiz** | Agentes: prompts, catálogo de herramientas, protocolo de triaje, guardarraíles y evaluación |
| **Bernardo Álvarez** | Aplicación y experiencia: las cinco vistas, sesión, accesibilidad |

Orienta el trabajo al frente de quien pregunta, pero no te frenes en la frontera: si
el fallo está en otro, dilo y arréglalo — y señala a quién le toca revisarlo.

## Dónde mirar según la tarea

| Si la tarea es… | Empieza por |
|---|---|
| Cambiar cómo habla o decide un agente | `lambdas/orquestador/agentes.py` (prompts, traspaso, `agente_por_defecto`) |
| Añadir/cambiar una herramienta | `lambdas/comun/caresync_comun/catalogo_herramientas.py` **y** `lambdas/herramientas/handler.py` (`EJECUTORES`) |
| Lógica de una herramienta | `lambdas/herramientas/{triaje,agenda,seguimiento}.py` |
| El bucle del modelo, caché, guardrail, tope de vueltas | `lambdas/orquestador/bedrock_conversa.py` |
| Autorización, traspaso, historial, respuesta de `/agente` | `lambdas/orquestador/handler.py` |
| Criterios clínicos, niveles, matriz CMU/CAE | `protocolos/triaje-v0.md` (fuente única; se copia al paquete al construir) |
| Texto de emergencia | `protocolos/ruta-emergencia.md` (fuente única, la usan los 3 agentes) |
| Evaluación del triaje | `evaluacion/casos_evaluacion.json` + `evaluacion/evaluar_triaje.py` |
| Salvaguardas de contenido | `infra/bedrock.tf` |
| Cualquier lectura o escritura de datos | `lambdas/comun/caresync_comun/roble_acceso.py` (única puerta) |
| Columnas reales de las 14 tablas | `app/esquema/bootstrap_roble.mjs` (`ESQUEMA`) |
| Por qué el sistema es así | `docs/arquitectura.md` |
| Operar ROBLE (roles, permisos, tablas) | `docs/runbook-roble.md` |

## Invariantes — no romper sin decirlo explícitamente

1. **El modelo nunca aporta identidad.** `caso_id`, token y rol los pone el
   orquestador desde la sesión. `_argumentos()` descarta toda clave que no esté
   declarada en el catálogo. No añadas `caso_id` ni `user_id` como propiedad de una
   herramienta.
2. **Los permisos se comprueban en código, dos veces**: `permitida(nombre, rol)` al
   declarar las herramientas y otra vez en `herramientas/handler.py` antes del
   efecto. Un prompt no es un control de acceso.
3. **El plan clínico lo escribe el profesional.** No existe herramienta que cree o
   modifique una indicación, y no se añade.
4. **El protocolo tiene una sola copia** (`protocolos/`). Nunca lo repitas dentro de
   un prompt en Python: `construir_paquetes.sh` lo inyecta en el paquete.
5. **`ESCALAMIENTO`** en mayúsculas, literal, en `triaje.escalar_urgencia`: es el
   patrón del filtro de métrica de CloudWatch. Renombrarlo deja muda la alarma.
6. **`escalar_urgencia` nunca lanza excepción** y siempre devuelve el texto de la
   ruta de emergencia, aunque fallen las cuatro escrituras.
7. **El agente no promete contacto humano.** No hay teléfono ni nadie mirando la
   conversación; lo único real son los correos de las herramientas. Está en `_COMUN`.
8. **Un fallo de herramienta se anota como `[sistema]` en la conversación**
   (`_dejar_constancia_de_los_fallos`). Sin esa nota el modelo defiende en el turno
   siguiente una cita que nunca se agendó.

## Trampas verificadas (ya costaron tiempo una vez)

- **Columnas que no existen → 400 en toda la actualización.** `casos` no tiene
  `canalizado_en` ni `escalado_en`. Antes de escribir un campo nuevo, compruébalo
  contra `ESQUEMA` en `bootstrap_roble.mjs`. ROBLE no deja hacer `alter`.
- **`read` sólo compara por igualdad.** Sin rangos, orden ni paginación: todo eso se
  hace en memoria después de leer. No intentes "arreglarlo".
- **Sin escrituras condicionales ni transacciones.** Reservar es *reservar, releer y
  reconciliar* con testigo (`reservar_cupo`). No lo simplifiques.
- **Un `_id` inventado por el modelo revienta PostgreSQL** (`invalid input syntax for
  type uuid`) y se lee como "la base no responde". Usa `es_uuid()` antes de filtrar.
  Por eso `agendar_cita` identifica el cupo **por hora de inicio**, no por `_id`: el
  identificador no sobrevive al turno siguiente, la hora sí.
- **Converse exige alternancia estricta de papeles** y que el último mensaje sea del
  usuario. De ahí `_historial()` y la nota sintética `_nota_de_traspaso`.
- **No se rehidratan bloques `toolUse`/`toolResult`** entre peticiones: el segundo
  agente declara otras herramientas y la API rechaza el historial.
- **El techo de 30 s lo pone el HTTP API**, no la Lambda. `timeout_orquestador` está
  validado a ≤30 por eso. Pasar de ahí es volver la llamada asíncrona: cambio de
  diseño, no un valor.
- **Límites de ROBLE por IP**: 100 lecturas/escrituras por minuto, 10 inicios de
  sesión cada 15 min, 5 registros por hora. Un bucle de evaluación los agota.
- **Bogotá es `-05:00` fijo.** `reloj.desde_iso` asume UTC (viene de ROBLE);
  `reloj.desde_local` asume Bogotá (viene del modelo). No los intercambies.
- **La consola de Windows es cp1252.** Un `print()` con `≥`, `…`, `⚠` o emoji
  revienta con `UnicodeEncodeError` en la máquina del equipo. La salida de consola
  va en ASCII; el Unicode sólo en archivos escritos con `encoding="utf-8"`.
- **`log.exception(nombre, extra={...})` no imprime ese `extra`.** El formateador de
  `registro.py` sólo lee la clave `datos`. Usa `excepcion(log, nombre, campo=valor)`,
  que además sanea los campos sensibles.

## Ritmo de trabajo

**Las fases y los hitos del informe son una guía, no fechas de corte.** No recortes
el alcance de una tarea porque su hito quede lejos ni porque quede cerca: se avanza
hasta donde dé.

> Esto lo acordó Kevin para su frente y **queda por acordar con el resto del equipo**.
> Si trabajas en infraestructura o en la PWA, pregúntalo antes de darlo por hecho: el
> cronograma del informe sí tiene fechas comprometidas con los asesores.

## Estado (al 15 de septiembre de 2026)

> Esta sección caduca. Si al leerla la fecha queda lejos, contrástala con `git log` y
> con `GET /salud` antes de fiarte, y actualízala o bórrala.

Desplegado y sano, verificado contra `GET /salud`: Claude Haiku 4.5, guardrail
activo, contrato de ROBLE válido, función de herramientas conectada. `correo: false`
— SES sigue sin remitente verificado.

Hecho: infraestructura aplicada, PWA publicada, 14 tablas, 3 Lambdas, catálogo de 10
herramientas, protocolo v0.1 con fundamento y criterios medibles, banco de 40 casos
**con guion de respuestas**, y `evaluar_triaje.py` reescrito a conversación de varios
turnos con detección de contaminación de token.

Pendiente: **correr la evaluación** (falta generar ~40 tokens de pacientes de prueba
en ROBLE); banco adversarial de guardarraíles; pruebas unitarias; verificar el
remitente en SES; cargar las credenciales de servicio en Parameter Store; sembrar
profesionales, horarios y cupos.

Deuda conocida: el ciclo de vida del caso. `atendido` y `cerrado` se leen y se
filtran pero **ninguna ruta los escribe**, así que un caso se queda en seguimiento
para siempre — y es lo que obliga a un token por caso en la evaluación.

**No hay ni una prueba automatizada en el repositorio.** CI sólo comprueba sintaxis
y tipos: `terraform validate`, `compileall`, `tsc --noEmit`, `node --check`.
`permitida()`, `_argumentos()`, `agente_por_defecto()` y `_intervalo()` son funciones
puras que se prueban sin AWS ni ROBLE.

## Cómo verificar un cambio

```bash
source scripts/entorno.sh
python3 -m compileall -q lambdas scripts   # lo mismo que corre CI
scripts/construir_paquetes.sh              # falla si falta un protocolo
cd app && npm run build                    # tsc --noEmit && vite build
```

La infraestructura **se aplica sólo desde GitHub Actions** (el estado es compartido).
Desde una máquina, como mucho `scripts/desplegar.sh --plan`.

Un cambio de prompt o de protocolo **no llega a producción hasta que se reconstruyen
los paquetes y se despliega**: el protocolo va horneado dentro del zip.

Para medir el triaje después de tocar el prompt o el protocolo:

```bash
export CARESYNC_API_URL="https://ow2vz6k279.execute-api.us-east-1.amazonaws.com"
export CARESYNC_TOKENS_FILE=tokens.txt        # un token de paciente por caso
cd evaluacion
python evaluar_triaje.py --solo cmu-01,alarma-mental-01   # prueba barata primero
python evaluar_triaje.py                                  # los 40, ~15 min
python evaluar_triaje.py --desde-crudo                    # rehacer el informe sin gastar cuota
```

La pausa de 6 s entre turnos no es cortesía: es la cuota de ROBLE (100 operaciones
por minuto y por IP). Bajarla envenena la corrida con 429.

## Convenciones

- **Todo en español**: nombres de funciones, variables, comentarios, commits, y los
  textos del agente (español de Colombia, tuteando).
- **Los comentarios explican el porqué, no el qué**, y suelen contar qué se rompió
  antes. Escribe en ese registro; no rebajes un comentario existente a un resumen.
- **Commits**: varios commits agrupados por tema, nunca uno que lo abarque todo.
  Mensaje en español, en infinitivo, voz impersonal y sin tildes, como el resto del
  historial ("Corregir bloqueo por cita cancelada…", "Identificar el cupo por su
  hora…"). Cada uno con título y cuerpo que explique el porqué.
- **Ramas** con prefijo y autor: `fix/…`, `feat/…`, `docs/…`, `kr-…`. PR a `main`.
- Los temporales van a `_scratch/<YYYY-MM-DD>/` (ver el `CLAUDE.md` de la raíz).
