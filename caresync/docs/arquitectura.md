# Arquitectura

Este documento explica **por qué** el sistema tiene esta forma y, sobre todo, qué
compromisos se aceptaron a sabiendas. Lo que hace cada archivo está en su
encabezado; aquí están las decisiones que no caben en un comentario.

## La división que lo explica todo

**Los datos de salud no están en AWS.** Viven en ROBLE (OPENLAB, Uninorte), que es
gratuito para estudiantes y donde ya está la autenticación. AWS tiene el
razonamiento y la mensajería.

```
   Navegador (PWA)
        │  ├── login / lectura y escritura de datos ──────────► ROBLE  (Postgres + auth)
        │  └── POST /agente  con el token de ROBLE
        ▼
   API Gateway HTTP API
        │
        ▼
   Lambda orquestador ──── Converse ────► Bedrock (Claude Haiku 4.5 + guardrail)
        │  ▲                                   │
        │  └──── resultado de la herramienta ──┘
        ▼
   Lambda herramientas ──── con el token del llamante ───────► ROBLE
        │
        └── escalamiento ──► SES (correo) · SNS (aviso) · log ESCALAMIENTO

   EventBridge Scheduler ──► Lambda recordatorios ──► ROBLE + SES
                             (cuenta de servicio, SSM)
```

Consecuencias que conviene tener presentes:

- **No hay base de datos en AWS.** Ni RDS, ni DynamoDB para la aplicación, ni VPC.
  La única tabla de DynamoDB del proyecto es el bloqueo del estado de Terraform.
- **Las Lambdas no tienen credenciales de datos.** Actúan con el token del propio
  llamante, así que un usuario no puede leer por la API nada que ROBLE no le
  dejaría leer. La única excepción está aislada y es explícita: la Lambda de
  recordatorios corre por reloj, no tiene un usuario que la autorice y usa una
  cuenta de servicio cuya contraseña vive en Parameter Store.
- **El coste tiende a cero cuando nadie usa el sistema.** Todo es por invocación.

## Tres agentes, un tiempo de ejecución

Un solo `Agente` como estructura de datos —clave, nombre, roles que lo pueden
invocar, herramientas y traspaso— y tres instancias. No hay tres Lambdas ni tres
servicios: lo que cambia entre un agente y otro es el prompt, la lista de
herramientas y quién puede hablarle.

| Agente | Roles que lo invocan | Herramientas |
|---|---|---|
| Triaje | paciente | `consultar_estado_caso`, `escalar_urgencia`, `canalizar_caso` |
| Agenda y logística | paciente, administrativo (CMU y CAE) | `consultar_estado_caso`, `consultar_disponibilidad`, `consultar_profesionales`, `agendar_cita`, `notificar_profesional`, `escalar_urgencia` |
| Seguimiento | paciente, profesional | `consultar_estado_caso`, `consultar_plan`, `registrar_evolucion`, `registrar_adherencia`, `escalar_urgencia` |

**El traspaso es explícito y uno solo:** cuando `canalizar_caso` tiene éxito, el
caso pasa de triaje a agenda. No hay un enrutador que decida por su cuenta; el
traspaso está declarado en el propio agente (`traspaso=("canalizar_caso", AGENDA)`)
y ocurre porque una herramienta concreta funcionó.

Qué agente atiende cuando la aplicación no pide uno se deduce **del estado del
caso**, no de la pantalla que llamó (`agente_por_defecto`). Alguien que vuelve a
escribir tres días después cae en seguimiento en lugar de repetir el triaje.

### Una conversación puede no ser sobre ningún caso

El personal de un centro pregunta también por su propia operación —quién atiende,
con qué horario, dónde queda hueco—, y eso no es de nadie en concreto. Esa
conversación no tiene caso: se guarda en un hilo propio de quien pregunta
(`consulta:<user_id>` en la columna `caso_id` de `conversaciones`, que es texto
libre) y el agente se elige por el rol, porque no hay estado del que deducirlo.

Sin caso el catálogo recorta lo que se le declara al modelo: sólo las herramientas
marcadas `necesita_caso=False`, que son las que se responden sabiendo únicamente el
centro de quien pregunta. Las demás no se declaran, y la Lambda de herramientas las
rechaza igual si llegaran sin caso. El centro sale del perfil del actor en ROBLE, no
de nada que el modelo haya leído, así que una consulta general no puede terminar
leyendo la agenda del otro centro.

### El modo simulación: un triaje de prueba sin efecto

`POST /agente` tiene un segundo camino. Con `simulacion: true` en el cuerpo, la
petición no pasa por `_conversar` sino por `_simular`, y el profesional puede
conversar con el agente de triaje **como si fuera quien consulta**, para ver a qué
centro y a qué nivel lo lleva lo que se le cuenta. Existe porque el banco de 40 casos
mide el triaje contra un guion escrito de antemano, y eso no sustituye a que alguien
con criterio clínico lo pruebe a mano con el caso que se le acaba de ocurrir.

Lo que lo hace seguro no es un filtro, es que **no hay camino hasta el efecto**:

- `_simular` **no recibe el token**, así que no tiene con qué invocar la función de
  herramientas. Las tres del triaje se le declaran al modelo —sin ellas no habría
  decisión que medir— pero las ejecuta un ejecutor en seco que valida los argumentos
  igual y devuelve un resultado con la misma forma que el real más un `simulado:
  true`. La bifurcación está arriba, en `_atender`, para que esto se pueda comprobar
  leyendo.
- **Un paciente no puede simular** (`ROLES_QUE_SIMULAN` es profesional y los dos
  administrativos de centro). Si pudiera, una urgencia real escrita en la vista del
  paciente quedaría atendida por el sandbox: leería la ruta de emergencia, el caso no
  se marcaría, no se escribiría `urgencia_escalada` y no se emitiría `ESCALAMIENTO`,
  así que la alarma no sonaría y nadie se enteraría.
- **Ningún evento de la simulación lleva el literal `ESCALAMIENTO`**, en ningún caso
  y aunque el modelo escale. De ese literal cuelga el filtro de métrica que levanta a
  una persona.
- **No hay traspaso.** Un solo agente y una sola vuelta: el de agenda consultaría
  cupos reales y ofrecería horas que existen.

Lo que sí es real: el modelo, el protocolo horneado en el paquete, el guardarrail, las
salvaguardas, la garantía de la ruta de emergencia y la memoria del hilo entre turnos.
Es decir, todo lo que se está evaluando.

Y se guardan dos cosas, las dos `create` del rol `user` de ROBLE:

- **El hilo**, en `conversaciones`, bajo `simulacion:<user_id>:<slug>`. Es el tercer
  uso de `caso_id` como texto libre, junto a `consulta:<user_id>`. El turno humano se
  anota con `autor="paciente"` a propósito: con el rol real, `_historial` le pondría
  delante la marca `[profesional que atiende]` y el modelo dejaría de hablarle a un
  paciente, con lo que se estaría midiendo otra cosa. De quién fue la simulación queda
  constancia en el prefijo del hilo y en el `actor_user_id` del evento.
- **Cada decisión**, en `eventos` como `simulacion_triaje`, con el centro y el nivel.
  De ahí sale el recuento de cuánto coincidió el modelo con el criterio del
  profesional, que la vista guarda como `simulacion_valoracion`.

Al prompt se le pasan un actor y un caso sintéticos, construidos por el orquestador y
que no se escriben en ninguna parte. El invariante sigue en pie: la identidad la pone
el orquestador y no el modelo; lo que cambia es que aquí la pone fingida, y la
verdadera va a la bitácora.

La deuda que esto deja, consciente: la validación de argumentos y la tabla de plazos
del ejecutor en seco son copias reducidas de `herramientas/handler._argumentos` y de
`triaje._plazo`. Importarlas significaría tener aquí un camino hasta las herramientas
de verdad, que es justo lo que no puede existir. Si cambian los plazos del protocolo,
hay que tocar los dos sitios.

### Los permisos se comprueban dos veces

Las cinco vistas de la PWA son presentación: esconder un botón no es un permiso.
Lo que autoriza de verdad son dos capas independientes:

1. `permitida(nombre, rol)` en el catálogo de herramientas, dentro de la Lambda:
   el rol del llamante decide qué herramientas existen para él, y el orquestador
   ni siquiera las declara al modelo.
2. ROBLE, con el token del llamante. Si la primera capa tuviera un hueco, la
   segunda sigue negando la lectura.

Y el rol no lo dice el cliente: sale de consultar `/me` en ROBLE con el token
recibido.

### El plan clínico lo escribe una persona

La pantalla del profesional es el único sitio donde se escribe un plan, y no hay
herramienta que lo cree. El modelo resume, ordena y pregunta; no prescribe. Esto no
es una limitación técnica, es el límite del alcance: un prototipo universitario no
propone tratamientos.

### Quién ve la conversación, y a cambio de qué

Durante la mayor parte del proyecto la respuesta fue «nadie más que la persona»: el
profesional atendía con el resumen del triaje y no con la transcripción. El motivo era
bueno y sigue valiendo para atender —para una consulta hace falta el resumen, y leer
el hilo entero de cada caso es una intromisión sin motivo—, pero no cubría el trabajo
que faltaba: **revisar si el triaje estuvo bien hecho**. El resumen lo escribió el
mismo agente al que se quiere evaluar, así que juzgarlo con su propio resumen no es
revisar nada.

Así que el profesional ve el hilo completo, y en el único sitio donde eso tiene ese
propósito: la pestaña de **historial de triajes**. La consulta —la pestaña de agenda—
no lo muestra. Y el acceso no es gratis:

- **Cada apertura de un hilo escribe un `hilo_consultado` en `eventos`**, con quién lo
  abrió y cuántos turnos vio. Es lo que convierte «el profesional puede leerlo todo»
  en «puede leerlo todo y se sabe cuándo lo hizo». La bitácora del caso es el único
  sitio donde esto queda: ROBLE no tiene registro de auditoría propio.
- **La pantalla lo dice antes y después de abrirlo.** Un registro que quien lo activa
  no conoce no es trazabilidad.
- Se listan los casos **del centro** y no sólo los propios, porque mirar únicamente el
  trabajo del agente sobre los pacientes de uno no permite ver un patrón. Los que
  tienen cita con quien mira van marcados.

Lo que no cambió es quién escribe: nadie puede añadir una nota desde esa pantalla. Un
campo de texto allí habría creado un canal de notas clínicas sin trazabilidad, que es
justo lo que el resto del sistema evita.

Y el `admin_plataforma` sigue sin ver ni casos ni conversaciones: administra la
instalación, no la atención.

### El bucle de herramientas

`bedrock_conversa.py` implementa el ciclo de Converse: el modelo pide una
herramienta, se ejecuta, se le devuelve el resultado, y otra vuelta. Con
`MAX_VUELTAS = 5`, que es un cortacircuitos: un modelo que se empeña en llamar a la
misma herramienta gasta dinero y tiempo, y cinco vueltas bastan para cualquier
conversación que este sistema tenga sentido en sostener.

Las instrucciones y el protocolo de triaje —varios miles de tokens que no cambian
entre mensajes— se envían con caché de prompt. El protocolo se copia **dentro del
paquete** de la Lambda en lugar de leerse de S3 o de Parameter Store: así el
protocolo desplegado es exactamente el que está en el commit.

## Limitaciones de ROBLE que se asumieron

Ninguna de estas es un olvido. Están aquí para que quien lea el código no intente
"arreglar" lo que es una adaptación deliberada.

### `read` sólo compara por igualdad

No hay `LIKE`, ni rangos, ni orden, ni paginación. Todo el filtrado por fecha, el
orden y los recortes se hacen **en memoria**, después de leer. Es sostenible con los
volúmenes de un prototipo y se nota en el código: `porFechaDescendente`,
`porInicioAscendente`, `casoVigente` y compañía son funciones de ordenación que en
un backend propio serían un `ORDER BY`.

Cuando un volumen deje de caber, la salida no es paginar a mano: es mover esa
consulta a una *saved query* y llamarla con `executeQuery`.

### No hay claves ajenas

`createTable` no las expone. La integridad referencial la sostiene el módulo de
acceso a datos (`roble_acceso.py`) y nada impide, a nivel de base de datos, una fila
huérfana. De ahí que el código sea explícito donde importa: al registrar un plan, si
ROBLE no devuelve el identificador del plan, se lanza un error **antes** de crear las
indicaciones, en lugar de crearlas apuntando a la nada.

### No hay escrituras condicionales ni transacciones

Esto es lo que más forma le da al código.

**Reservar un cupo** no puede ser un `UPDATE ... WHERE libre = true`, porque no hay
forma de condicionar la escritura. El patrón es *reservar, releer y reconciliar*: se
escribe la reserva con un testigo propio (`reserva_testigo`), se vuelve a leer la
fila y se comprueba que el testigo que quedó es el nuestro. Si no lo es, ganó otro y
se busca otro cupo. Y como una reserva puede quedar a medias si el proceso muere,
`liberar_reservas_vencidas()` recoge las que llevan demasiado tiempo sin confirmar.

**Registrar un plan** son cuatro escrituras sin transacción que las envuelva, así
que el orden no es estético: plan → indicaciones → cita `atendida` → caso
`en_seguimiento`. La última es la que hace que el siguiente mensaje del paciente lo
atienda el agente de seguimiento; si algo falla antes, el caso sigue donde estaba y
se puede repetir sin duplicar el estado final.

### La sesión en `localStorage`

El SDK de JavaScript de ROBLE no persiste la sesión: la guarda en memoria y ofrece
`onTokenUpdate` para que la aplicación decida dónde ponerla. (El de Python sí tiene
un almacén enchufable; es una diferencia real entre los dos.)

La PWA persiste los dos tokens en `localStorage` y los restaura al arrancar, que es
lo que hace que recargar la página no eche a nadie. Una cookie `HttpOnly` sería
mejor, pero no hay backend propio que la ponga: el navegador habla directamente con
ROBLE y con el API Gateway.

**La consecuencia, dicha claro: un XSS en la aplicación expondría el token.** Lo que
se hace al respecto es reducir la superficie —React escapa por defecto, el único
punto que escribe en el DOM a mano (`main.tsx`, cuando el arranque falla) usa
`textContent` y no `innerHTML`, y en `localStorage` no vive nada más que los dos
tokens— y dejarlo escrito aquí en lugar de dejarlo pasar.

### Entrar con Google

ROBLE sabe hablar con Google, pero **el SDK no**: `roble-client` 3.0 no tiene ni un
método de inicio de sesión social. Las dos llamadas están escritas a mano con `fetch`
en `app/src/roble.ts`, contra las mismas rutas del contrato que usa el SDK para todo
lo demás. No están documentadas; se descubrieron probando contra la API de la
instancia de pruebas el 21 de septiembre de 2026.

1. `POST /auth/<contrato>/auth/google/start` con `{ redirect }` devuelve `{ url, state }`.
2. La persona autoriza en Google, que devuelve el código **a ROBLE**, no a la PWA.
3. ROBLE redirige al destino con `?code=…` (o `?error=…&error_description=…`).
4. `POST /auth/<contrato>/auth/token` con `{ code }` devuelve los dos tokens, que se
   guardan igual que los del inicio de sesión con contraseña.

Cuatro cosas de ese flujo condicionan el código:

- **`redirect` es el *nombre* de un destino registrado en la consola de ROBLE**, no
  una URL. Están dados de alta dos, `default` (la PWA de Amplify) y `local`
  (`http://localhost:5173/`), y la PWA elige por el host porque el servidor de
  desarrollo no pasa por `publicar_app.sh`, que es quien inyecta las variables. Que
  el servidor no acepte URLs arbitrarias es lo correcto: si las aceptara, sería un
  redirector abierto con el código de sesión en la mano.
- **El código sirve una sola vez** —el segundo canje responde 400 «Código inválido o
  expirado»—. Por eso el regreso se lee al importar el módulo y la promesa del canje
  está memorizada: `StrictMode` monta los efectos dos veces en desarrollo, y sin eso
  el segundo intento mostraría un error que no existe. En la misma lectura se borran
  los parámetros de la barra de direcciones, para que el código no quede en el
  historial ni en un `Referer` y recargar no reintente nada.
- **La PWA nunca ve el `client_secret`.** El intercambio con Google lo hace ROBLE
  desde su propio `callback`; en el navegador sólo hay un código de un solo uso.
- **Google afirma si el correo está verificado**, así que ROBLE vincula la entrada a
  la cuenta que ya tenga ese correo en lugar de crear una segunda. Entrar y
  registrarse son el mismo acto y el botón es el mismo en las dos pestañas: no hay
  «cuenta de Google» aparte de la de contraseña.

Lo que sí falta y hay que poner: la fila de `perfiles`. Una cuenta que llega por
Google no pasa por el formulario de registro, así que `roble.ts` la crea con rol
`paciente` —nunca uno administrativo, que lo asigna quien administra el contrato— y
con el nombre de `GET /auth/<contrato>/me`, el único sitio que lo devuelve:
`currentUser()` consulta `/verify-token`, y ese sólo trae `sub` y `email`.

La configuración del proveedor (cliente de Google, secreto, destinos) está en
`runbook-roble.md`.

## Decisiones de infraestructura

- **Los grupos de logs se declaran en Terraform**, no se dejan crear a Lambda. Si
  los crea Lambda no tienen retención ("nunca expiran") y los permisos de escritura
  del rol tienen que apuntar a `*` en lugar de a un ARN concreto.
- **arm64 (Graviton)**: mismo comportamiento, ~20 % más barato. Obliga a bajar las
  ruedas de PyPI para `manylinux2014_aarch64`, que es la razón de que
  `construir_paquetes.sh` pase `--platform` y `--only-binary`.
- **Terraform no construye los zips.** No sabe ejecutar `pip` de forma reproducible,
  y un `null_resource` con `local-exec` haría que el artefacto dependiera de la
  máquina que aplica. El build es un paso explícito y su salida es un artefacto.
- **El escalamiento tiene alarma propia.** No es una alarma de infraestructura, es
  de producto: cada `escalar_urgencia` deja la marca `ESCALAMIENTO` en el log, un
  filtro de métrica la cuenta y una alarma avisa por SNS. Llega a una persona
  aunque SES falle.
- **Publicar la agenda es una acción de la aplicación, no de una Lambda.** Convertir
  `horarios` en `cupos` lo dispara alguien del personal administrativo con un botón,
  porque abrir dos semanas de agenda es una decisión, no un automatismo.
- **Bogotá es `-05:00` y no hay horario de verano.** El desplazamiento está fijo en
  una constante de `agenda_cupos.ts`. Si Colombia adoptara horario de verano, ese
  archivo es lo primero que habría que cambiar.

## Lo que queda fuera, a propósito

Sin VPC. Sin base de datos propia en AWS. Sin tiempo real (la PWA relee tras cada
turno de conversación, que para esta cadencia es indistinguible y mucho más simple).
Una sola región, `us-east-1`, donde Bedrock sirve el modelo. Un entorno permanente.
Sin datos clínicos reales en la demo.

Y sin CDK: la propuesta original decía CDK y la implementación es **Terraform**
—decisión del equipo—, así que las menciones a CDK en `CareSync.md` y en
`propuesta-caresync.html` están desactualizadas.

## Para desplegar

[`docs/despliegue.md`](despliegue.md). En una frase: la infraestructura se aplica en
GitHub Actions y nunca desde una máquina, porque el estado es compartido.
