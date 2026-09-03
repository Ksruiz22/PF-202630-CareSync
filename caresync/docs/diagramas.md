# Diagramas

Los diagramas del sistema, en Mermaid. GitHub los renderiza en la web; en un editor
hace falta la extensión, y para el informe se exportan desde
[mermaid.live](https://mermaid.live) pegando el bloque.

**En Mermaid y no en una imagen** por la misma razón por la que los protocolos están en
Markdown: un `.png` exportado de una herramienta de dibujo se desactualiza en silencio y
nadie lo nota en una revisión de código. Aquí el diagrama se lee en el diff.

Cada diagrama dice qué archivo describe. Si uno discrepa del código, el código manda y
el diagrama es el que hay que corregir.

- [1. Contexto](#1-contexto)
- [2. Contenedores](#2-contenedores)
- [3. Una vuelta del bucle de herramientas](#3-una-vuelta-del-bucle-de-herramientas)
- [4. Reservar un cupo sin escrituras condicionales](#4-reservar-un-cupo-sin-escrituras-condicionales)
- [5. Estados del caso](#5-estados-del-caso)
- [6. Estados del cupo](#6-estados-del-cupo)
- [7. El trabajo por reloj](#7-el-trabajo-por-reloj)
- [8. Las dos capas de autorización](#8-las-dos-capas-de-autorización)

## 1. Contexto

Quién usa el sistema y con qué habla. La división que lo explica todo: **los datos de
salud están en ROBLE, no en AWS**.

```mermaid
flowchart TB
    paciente["Paciente<br/>estudiante, docente,<br/>colaborador, egresado"]
    profesional["Profesional<br/>médico o psicólogo<br/>del CMU o del CAE"]
    admincentro["Administración<br/>de centro<br/>CMU o CAE"]
    adminplat["Administración<br/>de plataforma"]

    caresync["<b>CareSync</b><br/>Red de agentes de acompañamiento"]

    roble[("ROBLE — OPENLAB Uninorte<br/>Postgres + autenticación<br/><b>los datos de salud</b>")]
    bedrock["Amazon Bedrock<br/>Claude Haiku 4.5 + guardrail"]
    correo["SES · SNS<br/>correo y avisos"]

    paciente --> caresync
    profesional --> caresync
    admincentro --> caresync
    adminplat --> caresync

    caresync <--> roble
    caresync --> bedrock
    caresync --> correo

    classDef persona fill:#e8eef7,stroke:#4a6fa5,color:#1a2a3a
    classDef externo fill:#f2f2f2,stroke:#888,color:#333
    classDef sistema fill:#d8e8dc,stroke:#3f7d54,color:#12301d
    class paciente,profesional,admincentro,adminplat persona
    class roble,bedrock,correo externo
    class caresync sistema
```

La conversación completa de un caso vive en ROBLE y **no pasa por CloudWatch**: los
logs llevan identificadores y métricas, nunca el texto de lo que alguien contó.

## 2. Contenedores

Qué se despliega y quién habla con quién. Corresponde a
[`infra/`](../infra/), [`lambdas/`](../lambdas/) y [`app/`](../app/); el razonamiento
está en [`arquitectura.md`](arquitectura.md).

```mermaid
flowchart TB
    navegador["<b>PWA</b><br/>React + Vite + TypeScript<br/>cinco vistas por rol<br/><i>Amplify Hosting</i>"]

    subgraph aws["AWS · us-east-1 · sin VPC y sin base de datos"]
        apigw["API Gateway HTTP API<br/>POST /agente · GET /salud"]
        orq["<b>Lambda orquestador</b><br/>autoriza, elige agente,<br/>corre el bucle"]
        herr["<b>Lambda herramientas</b><br/>ejecuta la acción<br/>con el token del llamante"]
        rec["<b>Lambda recordatorios</b><br/>cuenta de servicio"]
        sched["EventBridge Scheduler<br/>cada 15 minutos"]
        ssm[("Parameter Store<br/>credenciales de servicio")]
        logs["CloudWatch<br/>logs, métricas, alarmas"]
        bedrock["Bedrock<br/>Converse + guardrail"]
        ses["SES"]
        sns["SNS<br/>escalamientos"]
    end

    roble[("<b>ROBLE</b><br/>14 tablas + auth")]

    navegador -- "login, leer y escribir datos" --> roble
    navegador -- "POST /agente<br/>con el token de ROBLE" --> apigw
    apigw --> orq
    orq -- "valida el token<br/>y lee el caso" --> roble
    orq <-- "Converse" --> bedrock
    orq -- "invoke, con el token<br/>del llamante" --> herr
    herr --> roble
    herr --> ses
    herr --> sns
    sched --> rec
    rec --> ssm
    rec --> roble
    rec --> ses
    orq --> logs
    herr --> logs
    rec --> logs

    classDef lambda fill:#e8eef7,stroke:#4a6fa5,color:#1a2a3a
    classDef datos fill:#f7f0e0,stroke:#a5834a,color:#3a2e1a
    class orq,herr,rec lambda
    class roble,ssm datos
```

Tres cosas que este diagrama deja ver de un golpe:

- **No hay base de datos en AWS.** Ni RDS, ni DynamoDB para la aplicación, ni VPC. La
  única tabla de DynamoDB del proyecto es el bloqueo del estado de Terraform.
- **Las Lambdas no tienen credenciales de datos.** Actúan con el token de quien llama,
  así que por la API nadie lee lo que ROBLE no le dejaría leer.
- **La excepción está aislada y es explícita.** La Lambda de recordatorios corre por
  reloj, no tiene un usuario que la autorice, y es la única que usa una cuenta de
  servicio cuya contraseña vive en Parameter Store.

## 3. Una vuelta del bucle de herramientas

El camino de un mensaje. Describe
[`lambdas/orquestador/handler.py`](../lambdas/orquestador/handler.py) y
[`bedrock_conversa.py`](../lambdas/orquestador/bedrock_conversa.py).

```mermaid
sequenceDiagram
    autonumber
    participant P as Persona
    participant A as PWA
    participant O as Orquestador
    participant R as ROBLE
    participant B as Bedrock
    participant H as Lambda herramientas

    P->>A: escribe un mensaje
    A->>O: POST /agente + token de ROBLE
    O->>R: ¿quién es este token?
    R-->>O: user_id, y su fila de perfiles
    O->>R: el caso abierto, o abre uno
    R-->>O: caso + hilo de la conversación
    Note over O: elige el agente por rol<br/>y por estado del caso,<br/>no por lo que diga el cliente

    loop hasta 5 vueltas
        O->>B: Converse: prompt + hilo + herramientas del agente
        B-->>O: pide una herramienta
        O->>H: invoke, con el token del llamante
        H->>R: lee o escribe el dominio
        R-->>H: resultado
        H->>R: deja rastro en eventos
        H-->>O: resultado de la herramienta
        Note over O,B: si la herramienta falla,<br/>el error se le devuelve al modelo<br/>en lugar de subir como 500
    end

    B-->>O: respuesta final, sin más herramientas
    O->>R: guarda los mensajes en conversaciones
    O-->>A: texto + estado del caso
    A-->>P: respuesta

    Note over O: si el caso quedó canalizado,<br/>el traspaso a agenda ocurre<br/>en esta misma petición
```

Al agotar las cinco vueltas se pide una respuesta final **sin herramientas**: la
persona recibe algo dicho y no un error, y el gasto tiene tope.

## 4. Reservar un cupo sin escrituras condicionales

El patrón que compensa la limitación más incómoda de ROBLE: no hay
`UPDATE ... WHERE estado = 'libre'` ni transacciones. Describe `reservar_cupo` en
[`roble_acceso.py`](../lambdas/comun/caresync_comun/roble_acceso.py).

```mermaid
sequenceDiagram
    autonumber
    participant H as Lambda herramientas
    participant R as ROBLE
    participant Rec as Lambda recordatorios

    H->>R: lee el cupo
    R-->>H: estado libre
    H->>R: escribe estado=reservado,<br/>caso_id y un testigo único
    H->>R: relee el cupo
    R-->>H: el testigo que quedó

    alt el testigo es el mío
        H->>R: crea la cita, cupo=confirmado,<br/>caso=agendado
        H-->>H: cita confirmada
    else el testigo es de otro
        Note over H: se perdió la carrera:<br/>no se toca nada
        H-->>H: devuelve alternativas al modelo
    end

    Note over Rec,R: la otra mitad del patrón:<br/>cada 15 minutos devuelve a libre<br/>lo que quedó reservado sin confirmar
```

## 5. Estados del caso

Describe las constantes `CASO_*` de
[`roble_acceso.py`](../lambdas/comun/caresync_comun/roble_acceso.py) y quién las
escribe. **Dos estados están declarados y nadie los escribe**, y el diagrama lo dice en
lugar de dibujar un ciclo de vida que no existe.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> abierto: el orquestador abre el caso
    abierto --> canalizado: canalizar_caso<br/>(fija centro y nivel)
    canalizado --> agendado: agendar_cita
    agendado --> en_seguimiento: el profesional guarda el plan
    en_seguimiento --> en_seguimiento: registrar_evolucion<br/>registrar_adherencia

    abierto --> urgencia_escalada: escalar_urgencia
    canalizado --> urgencia_escalada: escalar_urgencia
    agendado --> urgencia_escalada: escalar_urgencia
    en_seguimiento --> urgencia_escalada: escalar_urgencia

    atendido: atendido<br/>(nadie lo escribe)
    cerrado: cerrado<br/>(nadie lo escribe)
    en_seguimiento --> cerrado: sin implementar
    cerrado --> [*]
```

`urgencia_escalada` **no es terminal**: escalar activa la ruta de emergencia del campus
y después se sigue acompañando a la persona.

`atendido` y `cerrado` se leen —tres pantallas filtran por `cerrado`, y
`agente_por_defecto` manda a seguimiento con `atendido`— pero ninguna ruta los escribe.
Hoy un caso vive para siempre en `en_seguimiento`. Cerrarlo pide decidir quién lo hace
y qué pasa con los recordatorios pendientes; esa mitad ya está resuelta, porque el
trabajo por reloj los cancela cuando el caso está `cerrado`.

## 6. Estados del cupo

```mermaid
stateDiagram-v2
    direction LR
    [*] --> libre: publicar agenda<br/>(personal administrativo)
    libre --> reservado: reservar_cupo escribe el testigo
    reservado --> confirmado: el testigo era mío → se crea la cita
    reservado --> libre: reconciliación cada 15 min<br/>(quedó sin confirmar)
```

La agenda no nace sola: `horarios` es una plantilla semanal y alguien tiene que
publicar los `cupos` desde la vista administrativa. Hay un tope de 400 filas por tanda,
para que un clic no pueda escribir miles de filas en ROBLE.

## 7. El trabajo por reloj

Cuatro tareas independientes cada 15 minutos: si una falla, las otras corren igual.
Describe [`lambdas/recordatorios/handler.py`](../lambdas/recordatorios/handler.py).

```mermaid
flowchart TB
    sched["EventBridge Scheduler<br/>rate(15 minutes) · America/Bogota"] --> rec

    subgraph rec["Lambda recordatorios · cuenta de servicio de SSM"]
        direction TB
        t1["<b>1. Reconciliar</b><br/>cupos reservados sin confirmar → libre"]
        t2["<b>2. Materializar</b><br/>indicaciones activas → recordatorios con fecha"]
        t3["<b>3. Enviar</b><br/>los que ya toca, y marcarlos"]
        t4["<b>4. Vigilar</b><br/>silencios: sin adherencia, sin evolución"]
        t1 --> t2 --> t3 --> t4
    end

    t2 --> roble[("ROBLE")]
    t1 --> roble
    t3 --> ses["SES"]
    t3 --> roble
    t4 --> roble

    classDef tarea fill:#e8eef7,stroke:#4a6fa5,color:#1a2a3a
    class t1,t2,t3,t4 tarea
```

Nada reintenta a mano: si la invocación falla entera, Scheduler la repite, y las cuatro
tareas son idempotentes dentro de la misma ventana. Un silencio no es una alarma
clínica, pero es lo que el profesional necesita ver antes de la siguiente consulta.

## 8. Las dos capas de autorización

**Esconder un botón no es un permiso.** Lo que autoriza de verdad son dos capas
independientes, y esto es lo que hay que tener en la cabeza para depurar un 403 o un
500.

```mermaid
flowchart TB
    persona["Alguien con sesión"] --> vista

    vista["<b>La vista de la PWA</b><br/>presentación: qué se ve"]
    vista -.->|"no autoriza nada"| nada["esconder un botón<br/>no es un permiso"]

    vista --> capa1
    capa1{"<b>Capa 1 · catálogo de herramientas</b><br/>permitida(nombre, rol)<br/><i>dentro de la Lambda</i>"}
    capa1 -->|no| p403["403 · «tu cuenta no tiene<br/>permiso para esto»"]
    capa1 -->|sí| capa2

    capa2{"<b>Capa 2 · permisos por tabla de ROBLE</b><br/>el rol de la cuenta en el contrato"}
    capa2 -->|falta el permiso| p500["<b>500</b>, no 403<br/>ROBLE no distingue"]
    capa2 -->|sí| efecto["la escritura ocurre<br/>y deja rastro en eventos"]

    classDef mal fill:#f7e8e8,stroke:#a54a4a,color:#3a1a1a
    classDef bien fill:#d8e8dc,stroke:#3f7d54,color:#12301d
    class p403,p500,nada mal
    class efecto bien
```

Las dos capas leen **roles distintos que se llaman parecido**, y confundirlos cuesta una
tarde:

| | Dónde vive | Qué decide |
|---|---|---|
| **Rol de CareSync** | la columna `rol` de `perfiles` | qué ve la persona y qué herramientas puede llamar |
| **Rol de ROBLE** | la cuenta, en la consola del contrato | si la consulta a la tabla se permite |

Un `admin_plataforma` necesita **los dos**: la fila en `perfiles` y el rol `plataforma`
en ROBLE. Y los permisos de ROBLE viajan en el token, así que un cambio de rol surte
efecto **en el siguiente inicio de sesión**, no antes. Ver
[`runbook-roble.md`](runbook-roble.md#roles).
