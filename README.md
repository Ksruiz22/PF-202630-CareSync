# CareSync Agentic Network

Red de agentes que acompaña a un miembro de la comunidad Uninorte desde el primer
síntoma hasta que se recupera: hace el **triaje** inicial, lo canaliza al Centro Médico
Uninorte (CMU) o al Centro de Acompañamiento Estudiantil (CAE), le **agenda** con el
profesional que corresponde y hace el **seguimiento** de la adherencia al plan que le
indicaron.

**Proyecto Final — Universidad del Norte, 2026-30.** Prototipo académico: no es un
producto sanitario y no hay validación clínica del protocolo de triaje.

## Cómo está organizado el repositorio

La raíz guarda los entregables de la asignatura. **El sistema está en
[`caresync/`](caresync/)**, y su
[`README`](caresync/README.md) es el índice técnico.

| | |
|---|---|
| [`CareSync.md`](CareSync.md) | La propuesta: alcance, agentes, reparto del equipo, riesgos |
| [`PrimerInforme.md`](PrimerInforme.md) | El informe formal: problema, justificación, objetivos, solución, estado del arte y plan de trabajo |
| [`propuesta-caresync.html`](propuesta-caresync.html) | El documento visual autocontenido, con el cronograma |
| [`caresync/`](caresync/) | **El sistema**: infraestructura, Lambdas, PWA, protocolos y documentación técnica |

## Por dónde empezar a leer

| Si quieres saber… | Lee |
|---|---|
| qué hace el sistema y dónde está cada cosa | [`caresync/README.md`](caresync/README.md) |
| **por qué** tiene esta forma, y qué compromisos se aceptaron | [`caresync/docs/arquitectura.md`](caresync/docs/arquitectura.md) |
| los diagramas: contexto, contenedores, secuencias, estados | [`caresync/docs/diagramas.md`](caresync/docs/diagramas.md) |
| las catorce tablas y el catálogo de herramientas | [`caresync/docs/datos-y-herramientas.md`](caresync/docs/datos-y-herramientas.md) |
| cómo desplegarlo de cero | [`caresync/docs/despliegue.md`](caresync/docs/despliegue.md) |
| cómo operar ROBLE, y qué hacer cuando algo falla | [`caresync/docs/runbook-roble.md`](caresync/docs/runbook-roble.md) |
| qué preguntas hace el triaje y en qué orden | [`caresync/protocolos/triaje-v0.md`](caresync/protocolos/triaje-v0.md) |

## Las tres decisiones que explican el resto

**Los datos de salud no están en AWS.** Viven en **ROBLE** (OPENLAB, Uninorte), que es
gratuito para estudiantes y donde ya está la autenticación. AWS tiene el razonamiento y
la mensajería: Bedrock, Lambda, API Gateway, EventBridge Scheduler, SES. No hay base de
datos en AWS, ni VPC.

**Las Lambdas no tienen credenciales de datos.** Actúan con el token de quien llama, así
que por la API nadie puede leer lo que ROBLE no le dejaría leer. La única excepción está
aislada y es explícita: la función de recordatorios corre por reloj, no tiene un usuario
que la autorice, y usa una cuenta de servicio cuya contraseña vive en Parameter Store.

**El plan clínico lo escribe una persona.** El modelo acompaña, pregunta y registra; no
diagnostica, no indica medicamentos y no puede escribir en las tablas del plan —no por
instrucción del prompt, sino porque no existe ninguna herramienta que lo permita.

## Correr algo

```bash
cd caresync/app && npm ci && npm run dev
```

La infraestructura **se aplica en GitHub Actions, no en local**: el estado de Terraform
es compartido y dos personas aplicando a la vez se pisan. En local se planifica:

```bash
cd caresync && source scripts/entorno.sh && scripts/desplegar.sh --plan
```

El recorrido completo —arranque con OIDC, variables del repositorio, lo que queda por
hacer a mano— está en [`caresync/docs/despliegue.md`](caresync/docs/despliegue.md).

## Equipo

| | |
|---|---|
| **Alejandro Santiago** | Infraestructura y despliegues: cuenta AWS, Terraform, esquema de ROBLE, CI, observabilidad y costes |
| **Kevin Ruiz** | Agentes: prompts, catálogo de herramientas, protocolo de triaje, guardarraíles |
| **Bernardo Álvarez** | Aplicación y experiencia: las cinco vistas, sesión, accesibilidad |

## Abstract

A network of specialized agents that supports members of the Uninorte community from
the onset of initial symptoms through to recovery. Depending on the need, the system
routes the person to either the Uninorte Medical Center or the Student Support Center,
and follows up on adherence after care is received. Health data and authentication live
in ROBLE (OPENLAB, Uninorte); AWS provides reasoning (Bedrock) and messaging only.
Final project, Universidad del Norte — academic prototype, not a medical device.
