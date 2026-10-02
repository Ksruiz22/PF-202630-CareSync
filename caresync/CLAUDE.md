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
| El modo simulación de `/agente` (triaje de prueba sin efecto) | `_simular` y el bloque final de `lambdas/orquestador/handler.py` + `lambdas/pruebas/prueba_simulacion.py` |
| Lo que ve el profesional: agenda, historial de triajes, simulador | `app/src/vistas/Profesional.tsx` (las tres pestañas), `HistorialDeTriajes.tsx`, `SimuladorDeTriaje.tsx` |
| Leer el hilo de un caso desde la PWA | `app/src/conversaciones.ts` (dos miradas: la de la persona y la del profesional) |
| Criterios clínicos, niveles, matriz CMU/CAE | `protocolos/triaje-v0.md` (fuente única; se copia al paquete al construir) |
| Texto de emergencia | `protocolos/ruta-emergencia.md` (fuente única, la usan los 3 agentes) |
| Evaluación del triaje | `evaluacion/casos_evaluacion.json` + `evaluacion/evaluar_triaje.py` |
| Salvaguardas de contenido | `infra/bedrock.tf` |
| Probar que las salvaguardas aguantan | `evaluacion/casos_guardarrailes.json` + `evaluacion/evaluar_guardarrailes.py` |
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
   patrón del filtro de métrica de CloudWatch. Renombrarlo deja muda la alarma. Y al
   revés: **la simulación no puede emitir ese literal nunca**, ni cuando el modelo
   escala. Sus eventos van en minúsculas (`simulacion_atendida`, `simulacion_decision`
   …). Que el filtro mire hoy sólo el grupo de la función de herramientas no es la
   garantía: ampliarlo a todos los grupos es una línea de Terraform, y entonces cada
   simulación levantaría a alguien de la cama.
6. **`escalar_urgencia` nunca lanza excepción** y siempre devuelve el texto de la
   ruta de emergencia, aunque fallen las cuatro escrituras.
7. **El agente no promete contacto humano.** No hay teléfono ni nadie mirando la
   conversación; lo único real son los correos de las herramientas. Está en `_COMUN`.
8. **Un fallo de herramienta se anota como `[sistema]` en la conversación**
   (`_dejar_constancia_de_los_fallos`). Sin esa nota el modelo defiende en el turno
   siguiente una cita que nunca se agendó.
9. **La simulación no produce efectos, y se puede comprobar leyendo.** `_simular` no
   recibe el token —sin token no hay forma de llegar a la función de herramientas— y
   ninguna función del bloque llama a `_ejecutor`, `_lambda().invoke`, `abrir_caso`,
   `caso_visible`, `caso_abierto_de` ni `actualizar_caso`. Lo comprueba
   `prueba_simulacion.py` recorriendo el árbol del archivo, no el texto. Sólo escribe
   dos cosas: el hilo en `conversaciones` y la decisión en `eventos`.
10. **Un paciente nunca simula** (`ROLES_QUE_SIMULAN`). Si pudiera, una urgencia real
    quedaría atendida por un sandbox que no marca el caso, no escribe
    `urgencia_escalada` y no emite `ESCALAMIENTO`: la persona leería la ruta de
    emergencia y nadie se enteraría.

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
- **`evento(log, nombre, nivel=N)` hace desaparecer la línea.** `nivel` es un
  parámetro propio de `evento()`: el nivel de log. Pasarle el nivel de urgencia del
  protocolo (1 a 4) manda la línea por debajo de `DEBUG` y el evento entero —nombre y
  campos— no sale en CloudWatch, sin que nada falle. Pasó en `caso_canalizado` y se
  descubrió al buscar en el log una canalización que sí había ocurrido; el campo se
  llama ahora `nivel_urgencia`. **Lo encontró el frente de infraestructura en un
  archivo de agentes: queda para que Kevin lo revise.**
- **El atributo `hidden` pierde contra cualquier clase con `display`.** Lo oculta la
  hoja del navegador, y una regla de autor —`.pila { display: flex }`— la gana sin
  importar la especificidad. La vista del profesional esconde así su pestaña de
  agenda, y hasta que se añadió `[hidden] { display: none !important }` al reset de
  `estilos.css` se pintaban dos pestañas a la vez.
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

## Estado (al 26 de septiembre de 2026)

> Esta sección caduca. Si al leerla la fecha queda lejos, contrástala con `git log` y
> con `GET /salud` antes de fiarte, y actualízala o bórrala.

Desplegado y sano, verificado contra `GET /salud`: Claude Haiku 4.5, guardrail
activo, contrato de ROBLE válido, función de herramientas conectada. `correo: false`
— SES sigue sin remitente verificado.

Hecho: infraestructura aplicada, PWA publicada, 14 tablas, 3 Lambdas, catálogo de 10
herramientas, protocolo con fundamento, criterios medibles e historial de revisiones,
banco de 40 casos **con guion de respuestas** y banco adversarial de 24 intentos.

**Medido**, por primera vez, con el antes y el después en `evaluacion/informes/`
(el índice está en su `README.md`). Con los PR #18 a #21 desplegados: alarmas
escaladas 36/36 en tres corridas (M2), centro correcto 23/26 (M1, 88,5 %), un
sub-triaje (M3), ninguna respuesta prohibida en el banco adversarial (M8) y ninguna
consulta legítima bloqueada.

La salvaguarda deniega dos temas, diagnóstico y prescripción. Había un tercero,
`sustituir_urgencia`, y se quitó: reconocía el asunto de la urgencia y no la postura,
y cortaba justo la respuesta correcta a una alarma (12 de 12 el 24/09). Qué política
actúa en cada respuesta lo dice `salvaguardas_detalle` en la respuesta de `/agente`.

Pendiente:

- **Operación** (Alejandro): el remitente de SES; las credenciales de servicio en
  Parameter Store; la causa de un 500 puntual del 26/09 hacia las 19:33
  (`fallo_no_previsto` en CloudWatch), que no se reprodujo al repetir el caso; y el
  filtro `MISCONDUCT` de entrada, que todavía corta «certificado para justificar una
  falla».
- **Agenda**: al 26/09 no hay ningún cupo libre a futuro en ninguno de los dos
  centros. Los profesionales y sus horarios existen, pero los cupos publicados
  vencieron el 24/09, y sin publicarlos de nuevo desde la vista administrativa el
  agente de agenda responde siempre que no hay espacios.
- **Triaje**: dos sobre-derivaciones a urgencias y un sub-triaje, descritos caso por
  caso en el índice de informes.

Deuda conocida: el ciclo de vida del caso. `atendido` y `cerrado` se leen y se
filtran pero **ninguna ruta los escribe**, así que un caso se queda en seguimiento
para siempre. La evaluación ya no depende de eso: el rol `user` de ROBLE tiene
`casos:update`, y los evaluadores cierran su propio caso al terminar cada
conversación (`evaluacion/cuenta_roble.py`).

**CI sí corre las pruebas**, y esta sección decía lo contrario hasta que se comprobó:
el paso «pruebas» de `revision.yml` llama a `scripts/pruebas.sh`, que las busca **por
patrón** —`lambdas/pruebas/prueba_*.py` y `evaluacion/prueba_*.py`— así que una prueba
nueva entra en CI sin tocar el flujo. Son 8 archivos y ninguno toca la red, AWS ni un
token de ROBLE: `entorno.py` sustituye `boto3`, `requests` y el SDK de ROBLE cuando
faltan. Antes de dar por hecho que algo no se prueba, `scripts/pruebas.sh`.

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
# evaluacion/.env (lo ignora git): una cuenta de paciente que no se use en la demo
CARESYNC_API_URL=https://ow2vz6k279.execute-api.us-east-1.amazonaws.com
CARESYNC_EMAIL=...
CARESYNC_PASSWORD=...
```

El evaluador inicia sesión solo, renueva el token si vence a media corrida y cierra
cada caso al terminar, así que una cuenta alcanza para todo el banco. Cada caso de
alarma dispara de verdad la alarma de `ESCALAMIENTO`: avisa a quien reciba el SNS
antes de correr los 40.

```bash
cd evaluacion
python evaluar_triaje.py --solo cmu-01,alarma-mental-01   # prueba barata primero
python evaluar_triaje.py                                  # los 40, ~15 min
python evaluar_triaje.py --desde-crudo                    # rehacer el informe sin gastar cuota
```

Después de tocar el guardrail (`infra/bedrock.tf`) o el prompt común:

```bash
python evaluar_guardarrailes.py --solo falso_positivo   # primero: que no bloquee lo legítimo
python evaluar_guardarrailes.py                         # los 24 intentos
```

Y las pruebas de los evaluadores, que no tocan la red ni gastan un token:

```bash
python prueba_evaluar.py && python prueba_guardarrailes.py && python prueba_cuenta.py
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
