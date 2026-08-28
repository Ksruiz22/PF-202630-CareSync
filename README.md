# CareSync Agentic Network

Red de agentes que acompaña a un miembro de la comunidad de Uninorte entre una
consulta y la siguiente: hace el triaje inicial, agenda con el profesional que
corresponde, y hace seguimiento de la adherencia al plan. Proyecto Final de la
Universidad del Norte.

## Qué hace, en una frase por agente

- **Triaje** — conversa sobre el malestar, decide si es salud física (CMU) o
  mental (CAE), asigna un nivel de urgencia, y **nunca** intenta diagnosticar.
- **Agenda y logística** — busca disponibilidad, reserva el cupo, y avisa al
  profesional con el resumen del caso antes de la cita.
- **Seguimiento** — pregunta cómo va la persona, registra adherencia al plan,
  y alerta al profesional si hay un retroceso.

Los tres corren sobre **un mismo tiempo de ejecución**: lo que cambia entre uno
y otro es el prompt, las herramientas que se le declaran al modelo, y los
roles que pueden invocarlo. El traspaso entre agentes es explícito — cuando el
de triaje canaliza un caso, el orquestador sigue la misma conversación con el
de agenda, sin que la persona note el cambio.

## Por qué el diseño de seguridad no es un detalle

Este es un prototipo académico, sin validación clínica, hablando con personas
sobre su salud. Tres decisiones no son negociables y están reforzadas en más
de una capa —protocolo, prompt, y Bedrock Guardrails— para que fallar en una
no tumbe las demás:

- **El modelo nunca diagnostica ni prescribe.** No dice qué enfermedad tiene
  la persona, ni indica, suspende o cambia un medicamento. El plan clínico lo
  escribe el profesional en su propia interfaz; el agente resume y pregunta,
  no trata.
- **Ante la duda, se sobre-deriva, nunca se subestima.** Toda la escala de
  urgencia está calibrada para errar hacia mandar a alguien a atención de más
  antes que de menos. Ver el fundamento de esa decisión en
  [`protocolos/triaje-v0.md`](protocolos/triaje-v0.md).
- **Una señal de alarma interrumpe todo lo demás.** Dolor de pecho, ideación
  suicida, pérdida de conciencia — cualquiera de la lista en
  [`protocolos/triaje-v0.md`](protocolos/triaje-v0.md) dispara
  `escalar_urgencia` de inmediato, sin seguir clasificando. Se prueba aparte
  del resto del banco de casos porque una sola falla ahí ya es inaceptable,
  sin importar qué tan bien vaya el promedio general.

## Dónde está cada cosa

| Carpeta | Qué hay |
|---|---|
| `infra/` | Terraform de todo el plano de AWS. 40 recursos, sin VPC y sin base de datos |
| `infra/arranque/` | Lo que hay que crear una vez y a mano: estado, bloqueo, identidad de GitHub |
| `lambdas/` | Tres funciones en Python 3.12 y el paquete común `caresync_comun` |
| `protocolos/` | El protocolo de triaje y la ruta de emergencia, en Markdown, versionados con el código |
| `evaluacion/` | Banco de ~40 casos sintéticos y el script que mide el acierto de ruta, nivel de urgencia y escalamiento |
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

Para correr la evaluación del triaje contra un entorno ya desplegado:

```bash
cd evaluacion
export CARESYNC_API_URL="<salida de terraform>"
export CARESYNC_TOKENS_FILE="tokens.txt"   # un token de paciente de prueba por caso
python evaluar_triaje.py
```

## Estado del proyecto

<!-- TODO (equipo): marcar según el hito real alcanzado antes de cada
     reunión con el tutor. Referencia completa en la propuesta. -->

- [ ] Hito 1 — Alcance y arquitectura aprobados
- [ ] Hito 2 — Walking skeleton: login + mensaje + respuesta del modelo, en AWS
- [ ] Hito 3 — Demo 1: triaje canaliza correctamente 3 casos distintos
- [ ] Hito 4 — Agenda y logística funcionando de punta a punta
- [ ] Hito 5 — Seguimiento y alertas de retroceso
- [ ] Hito 6 — Las 4 vistas integradas
- [ ] Hito 7 — Cierre: pruebas E2E, documentación y sustentación

## Equipo

| | |
|---|---|
| **Alejandro Santiago** | Infraestructura y despliegues: cuenta AWS, Terraform, esquema de ROBLE, CI, observabilidad y costes |
| **Kevin Ruiz** | Agentes: prompts, catálogo de herramientas, protocolo de triaje, guardarraíles, evaluación |
| **Bernardo Álvarez** | Aplicación y experiencia: las cuatro vistas, sesión, accesibilidad |
