# CareSync Agentic Network

Red de agentes que acompaña a un paciente entre una consulta y la siguiente: hace el
triaje inicial, agenda con el profesional que corresponde y hace el seguimiento de la
adherencia al plan. Proyecto Final de la Universidad del Norte.

Tres agentes sobre un mismo tiempo de ejecución —**triaje**, **agenda y logística**,
**seguimiento**—; el rol de quien llama decide el prompt, las herramientas y los
permisos. El plan clínico lo escribe el profesional, nunca el modelo.

## Dónde está cada cosa

| Carpeta | Qué hay |
|---|---|
| `infra/` | Terraform de todo el plano de AWS. 40 recursos, sin VPC y sin base de datos |
| `infra/arranque/` | Lo que hay que crear una vez y a mano: estado, bloqueo, identidad de GitHub |
| `lambdas/` | Tres funciones en Python 3.12 y el paquete común `caresync_comun` |
| `protocolos/` | El protocolo de triaje y la ruta de emergencia, en Markdown, versionados con el código |
| `app/` | PWA en React + Vite + TypeScript: cuatro vistas, una por rol |
| `app/esquema/` | Creación de las trece tablas de ROBLE |
| `scripts/` | Entorno, construcción, despliegue, publicación, esquema, CA corporativa |
| `docs/` | Despliegue, arquitectura y el runbook de ROBLE |

## Los datos de salud no están en AWS

Viven en **ROBLE** (OPENLAB, Uninorte), que es gratuito para estudiantes y donde ya
está la autenticación. AWS tiene el razonamiento y la mensajería: Bedrock, Lambda,
API Gateway, EventBridge Scheduler, SES. Las Lambdas actúan con el token del propio
llamante, así que un usuario no puede leer por la API lo que ROBLE no le dejaría leer.

La consecuencia incómoda de esa elección está documentada, no escondida: ROBLE no
tiene escrituras condicionales ni transacciones, así que reservar un cupo es
*reservar, releer y reconciliar* con un testigo, y ordenar o filtrar se hace en
memoria porque `read` sólo compara por igualdad. Ver
[`docs/arquitectura.md`](docs/arquitectura.md).

## Empezar

```bash
source scripts/entorno.sh     # perfil de AWS, región, CA corporativa, cachés
scripts/desplegar.sh --plan   # ver qué se crearía
```

**La infraestructura se aplica en GitHub Actions, no aquí.** El estado es compartido
y dos personas aplicando a la vez se pisan. El recorrido completo —arranque con OIDC,
variables del repositorio, qué queda por hacer a mano— está en
[`docs/despliegue.md`](docs/despliegue.md).

Para trabajar en la PWA:

```bash
cd app && npm ci && npm run dev
```

## Equipo

| | |
|---|---|
| **Alejandro Santiago** | Infraestructura y despliegues: cuenta AWS, Terraform, esquema de ROBLE, CI, observabilidad y costes |
| **Kevin Ruiz** | Agentes: prompts, catálogo de herramientas, protocolo de triaje, guardarraíles |
| **Bernardo Álvarez** | Aplicación y experiencia: las cuatro vistas, sesión, accesibilidad |
