# Manual de desarrollo

## 1. Propósito del documento

Este documento es la guía técnica para comprender, mantener y extender **CareSync Agentic Network**. Está dirigido a un equipo que continúe el proyecto: explica cómo está organizado el repositorio, dónde vive cada parte del sistema, qué reglas no se deben romper y qué problemas ya costaron tiempo una vez. La instalación paso a paso está en [Instalación.md](./Instalación.md) y el diseño completo, en el [Informe Final](./InformeFinal.md).

Un mapa más detallado y vivo, escrito para quien trabaja en el código, está en `caresync/CLAUDE.md`. Este manual resume lo esencial.

## 2. Descripción general del proyecto desde la perspectiva de desarrollo

CareSync es un sistema de tres agentes de inteligencia artificial (triaje, agenda y seguimiento) que comparten el estado de un caso guardado en ROBLE. Técnicamente es una arquitectura sin servidores propios: dos clientes (una PWA y una app móvil) hablan con ROBLE para los datos y con un API en AWS Lambda para conversar con los agentes. Toda la infraestructura de AWS está declarada en Terraform y se despliega desde GitHub Actions.

El desarrollo se organizó en tres frentes con responsable: infraestructura y despliegues (Alejandro Santiago), agentes, protocolo y evaluación (Kevin Ruiz), y aplicación y experiencia (Bernardo Álvarez).

### 2.1 Tecnologías principales

- **Frontend web:** React 18, Vite 5 y TypeScript (PWA)
- **Frontend móvil:** React Native 0.76 con Expo SDK 52 y TypeScript
- **Backend:** Python 3.12 en AWS Lambda (arm64), detrás de un HTTP API de API Gateway
- **Inteligencia artificial:** Amazon Bedrock (Claude Haiku 4.5) con la Converse API y Bedrock Guardrails; Amazon Transcribe para el dictado
- **Base de datos y autenticación:** ROBLE (OPENLAB, Uninorte), con su SDK `roble-client` en los clientes y `roble` en Python
- **Contenedores:** no se usan
- **Infraestructura adicional:** Terraform, GitHub Actions con OIDC, Amplify Hosting, SES, EventBridge Scheduler, CloudWatch, SNS y Parameter Store

### 2.2 Componentes principales

- **PWA:** cinco vistas por rol (paciente, profesional, administrativo del CMU y del CAE, y plataforma).
- **App móvil:** la app del paciente para el seguimiento: horario de tomas, plan, avisos de cita y asistente.
- **Orquestador (API de agentes):** identifica a quien escribe, elige el agente por el estado del caso, ejecuta el ciclo con el modelo y el traspaso; también ordena el plan dictado y firma la sesión de dictado.
- **Servicio de herramientas:** ejecuta las 14 herramientas que pueden pedir los agentes, tras comprobar de nuevo el permiso.
- **Servicio de recordatorios:** corre cada 15 minutos; envía recordatorios y avisos de cita, libera reservas vencidas y anota silencios.
- **Base de datos:** las 14 tablas de ROBLE.
- **Servicios externos:** Bedrock, Transcribe, SES y la alarma de CloudWatch y SNS.

## 3. Estructura del repositorio

### 3.1 Árbol general del repositorio

```text
/
├── .github/workflows/        # revision, infra, app y destruir
├── README.md                 # resumen y enlaces a los entregables
├── Primer_Informe_CareSync.md
├── SegundoInforme.md
├── InformeFinal.md
├── Instalación.md
├── Desarrollo.md
├── CareSync.md, propuesta-caresync.html   # propuesta original
└── caresync/                 # el proyecto
    ├── CLAUDE.md             # mapa de trabajo, invariantes y trampas
    ├── app/                  # PWA
    │   ├── src/              # vistas, componentes, cliente del API y de ROBLE
    │   └── esquema/          # bootstrap_roble.mjs: las 14 tablas
    ├── movil/                # app móvil (Expo)
    ├── lambdas/
    │   ├── orquestador/      # agentes, ciclo con el modelo, plan y dictado
    │   ├── herramientas/     # triaje, agenda y seguimiento
    │   ├── recordatorios/    # la función por reloj
    │   ├── comun/caresync_comun/   # catálogo, acceso a ROBLE, correo, registro
    │   └── pruebas/          # pruebas sin red
    ├── protocolos/           # triaje, ruta de emergencia y orientación
    ├── evaluacion/           # bancos de casos, evaluadores e informes
    ├── infra/                # Terraform (y arranque/)
    ├── scripts/              # construir, desplegar, probar, esquema
    └── docs/                 # arquitectura, despliegue, ROBLE, rediseño
```

### 3.2 Descripción de directorios y archivos relevantes

- **`caresync/app/`**: la PWA. `src/vistas/` tiene una vista por rol más el historial y el simulador de triajes; `src/componentes/` las piezas compartidas (conversación, editor del plan, progreso); `agente.ts` es el cliente del API; `roble.ts`, el de ROBLE; `dictado.ts` y `consulta.ts`, el dictado y la propuesta del plan.
- **`caresync/movil/`**: la app móvil. `src/pantallas/` (Acceso, Hoy, Mi plan, Avisos, Asistente), `src/fuenteRoble.ts` (datos y agente), `src/agenda.ts` (horario de tomas) y `src/avisos.ts` (notificaciones).
- **`caresync/lambdas/`**: el backend en Python, con una carpeta por función y el código común en una capa compartida.
- **`caresync/protocolos/`**: la única copia de los textos clínicos que usan los agentes.
- **`caresync/evaluacion/`**: los bancos de casos (`casos_*.json`), los evaluadores (`evaluar_*.py`) y sus informes (`informes/`), que son la evidencia de las métricas.
- **`caresync/infra/`**: Terraform. `dev.tfvars` tiene la configuración del entorno; `arranque/` crea una sola vez lo que Actions necesita para desplegar.
- **`caresync/scripts/`**: los *scripts* que usan tanto CI como las personas (§6).
- **`caresync/docs/`**: la documentación técnica detallada.

## 4. Organización de la solución a nivel de código

### 4.1 Organización por módulos o capas

- **Presentación:** la PWA y la app móvil. No contienen reglas de seguridad: esconder un botón no es un permiso.
- **Orquestación:** `lambdas/orquestador/`. Decide qué agente atiende, qué herramientas ve el modelo y cómo se arma el historial.
- **Lógica de negocio:** `lambdas/herramientas/`. Lo único que tiene efectos sobre el caso por decisión de un agente.
- **Persistencia:** `lambdas/comun/caresync_comun/roble_acceso.py`, la única puerta hacia ROBLE desde el backend.
- **Conocimiento clínico:** `protocolos/`, separado del código.

### 4.2 Relación entre componentes del sistema y código fuente

| Si hay que cambiar… | Empezar por |
|---|---|
| Cómo habla o decide un agente | `lambdas/orquestador/agentes.py` |
| Añadir o cambiar una herramienta | `lambdas/comun/caresync_comun/catalogo_herramientas.py` **y** `lambdas/herramientas/handler.py` |
| La lógica de una herramienta | `lambdas/herramientas/{triaje,agenda,seguimiento}.py` |
| Los plazos de cada nivel | `lambdas/comun/caresync_comun/plazos.py` |
| El ciclo con el modelo, la caché o la salvaguarda | `lambdas/orquestador/bedrock_conversa.py` |
| Autorización, traspaso e historial | `lambdas/orquestador/handler.py` |
| El plan dictado | `app/src/componentes/EditorDelPlan.tsx`, `app/src/consulta.ts` y `lambdas/orquestador/plan_propuesta.py` |
| El dictado por voz | `app/src/dictado.ts` y `lambdas/orquestador/dictado.py` |
| Los recordatorios y avisos de cita | `lambdas/recordatorios/handler.py`; en el teléfono, `movil/src/avisos.ts` |
| Las frecuencias de los recordatorios | `lambdas/comun/caresync_comun/frecuencia.py` y su espejo `app/src/frecuencia.ts` |
| Criterios clínicos y niveles | `protocolos/triaje-v0.md` |
| El texto de emergencia | `protocolos/ruta-emergencia.md` |
| Las salvaguardas | `infra/bedrock.tf` |
| Las columnas de las tablas | `app/esquema/bootstrap_roble.mjs` |

## 5. Contenedores

El proyecto **no usa contenedores**. La PWA es un sitio estático en Amplify, el backend son funciones Lambda empaquetadas como archivos zip y los datos viven en ROBLE. No hay ningún servicio propio de larga duración que justifique una imagen.

### 5.1 Contenedores utilizados

Ninguno.

### 5.2 Archivos relacionados con contenedores

Ninguno. El equivalente son los paquetes de Lambda que arma `scripts/construir_paquetes.sh`.

### 5.3 Construcción y ejecución de contenedores

No aplica. Para construir los paquetes de Lambda: `scripts/construir_paquetes.sh`.

### 5.4 Redes, puertos y volúmenes

No hay red privada ni volúmenes. El único puerto relevante en desarrollo es el **5173**, el único origen local que admite el API por CORS.

### 5.5 Recomendaciones para modificar contenedores

Si un equipo futuro necesitara un servicio de larga duración (por ejemplo, para pasar a invocación asíncrona o para alojar un adaptador hacia los sistemas del CMU y el CAE), conviene declararlo en Terraform como el resto y mantener la regla de que los datos de salud no salen de ROBLE.

## 6. Scripts y automatizaciones

### 6.1 Scripts principales

| Script | Para qué |
|---|---|
| `scripts/pruebas.sh` | Corre todas las pruebas sin red; las descubre por patrón (`prueba_*.py`) |
| `scripts/construir_paquetes.sh` | Arma los paquetes de las Lambdas y copia los protocolos dentro; falla si falta uno |
| `scripts/desplegar.sh --plan` | Planifica Terraform desde una máquina (aplicar se hace en Actions) |
| `scripts/publicar_app.sh` | Compila la PWA con la URL del API y la publica en Amplify |
| `scripts/esquema_roble.sh` | Crea las 14 tablas en ROBLE (una vez) |
| `scripts/destruir.sh` | Destruye el entorno; solo para una emergencia con Actions caído |
| `scripts/entorno.sh` | Variables comunes: perfil, región y certificados (se carga con `source`) |
| `scripts/ca_corporativa.sh` | Genera el paquete de certificados en una red con inspección TLS |
| `npm run dev` / `npm run build` (en `app/`) | Desarrollo y construcción de la PWA (`build` incluye la verificación de tipos) |
| `npm run web` / `npm run prueba` / `npm run typecheck` (en `movil/`) | App móvil en el navegador, prueba del horario de tomas y tipos |
| `evaluacion/evaluar_*.py` | Evaluadores de triaje, salvaguardas, concurrencia y seguimiento contra el sistema real |

### 6.2 Ubicación de scripts auxiliares

Los de operación están en `caresync/scripts/`; los de evaluación, en `caresync/evaluacion/`; el de la copia de trabajo de la app móvil, en `caresync/movil/scripts/`. Los archivos temporales de cada persona van a `_scratch/<fecha>/`, que no se versiona.

### 6.3 Consideraciones para su uso

- `scripts/desplegar.sh --si` y `scripts/destruir.sh` existen solo para emergencias: el lugar para aplicar y destruir son los flujos de GitHub Actions.
- Los evaluadores usan una cuenta de **paciente** de prueba y disparan de verdad la alarma de escalamiento en cada caso de alarma: hay que avisar antes.
- La pausa de 6 s entre turnos de los evaluadores responde al límite de ROBLE (100 operaciones por minuto por IP). Bajarla llena la corrida de errores 429.
- La consola de Windows usa la codificación cp1252: la salida de consola de los *scripts* va en ASCII.

## 7. Variables de entorno

### 7.1 Variables requeridas

| Dónde | Variables |
|---|---|
| PWA | `VITE_API_URL`, `VITE_ROBLE_BASE_URL`, `VITE_ROBLE_CONTRACT_ID` |
| App móvil | `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_ROBLE_BASE_URL`, `EXPO_PUBLIC_ROBLE_CONTRACT_ID`, `EXPO_PUBLIC_DEMO` (opcional) |
| Evaluadores | `CARESYNC_API_URL`, `CARESYNC_EMAIL`, `CARESYNC_PASSWORD` |
| Lambdas | Las pone Terraform: URL y contrato de ROBLE, nombres de las funciones, remitente de correo, idioma del dictado, entre otras |

Los valores del entorno del proyecto están en [Instalación.md](./Instalación.md#22-variables-de-entorno).

### 7.2 Variables por ambiente

Hay un solo ambiente desplegado, `dev`, configurado en `infra/dev.tfvars`. En desarrollo local, la PWA y la app móvil apuntan a ese mismo API y a la misma ROBLE. Un ambiente nuevo sería otro archivo `.tfvars` con su propio estado.

### 7.3 Archivos de configuración

- `app/.env` y `movil/.env`: variables de los clientes (`movil/entorno.ejemplo` es la plantilla).
- `evaluacion/.env`: la cuenta de prueba de los evaluadores.
- `infra/dev.tfvars`: configuración del entorno; se versiona porque no lleva secretos.
- `app/esquema/semilla.example.json`: plantilla de datos de ejemplo para ROBLE.

### 7.4 Manejo seguro de secretos

- La única credencial del sistema, la cuenta de servicio de ROBLE, vive en Parameter Store y la carga una persona. Terraform crea el parámetro con un relleno y no vuelve a mirarlo.
- Ningún `.env`, llave, certificado ni estado de Terraform se versiona: lo impide el `.gitignore` de la raíz y el de `caresync/`.
- GitHub Actions no tiene llaves de AWS: asume un rol por OIDC, y solo `main` de este repositorio puede asumir el rol de escritura.
- Las contraseñas de las cuentas de prueba y de demostración no se suben al repositorio.

## 8. Flujo de trabajo de desarrollo

### 8.1 Preparación del entorno

Clonar el repositorio, instalar las dependencias de `app/` y `movil/`, crear los `.env` y, en una red corporativa, generar el paquete de certificados. El detalle está en [Instalación.md](./Instalación.md#3-instalación-para-ambiente-de-desarrollo).

### 8.2 Desarrollo de nuevas funcionalidades

- Crear una rama con prefijo y autor: `feat/…`, `fix/…`, `docs/…` o las iniciales (`kr-…`).
- Antes de tocar una regla de seguridad, leer las invariantes (§11.2): si un cambio rompe una, hay que decirlo explícitamente en el *pull request*.
- Si el cambio toca el *prompt*, el protocolo o las salvaguardas, medirlo con los evaluadores, primero en local y después contra lo desplegado, y guardar el informe en `evaluacion/informes/`.
- Una columna nueva en ROBLE se agrega desde su consola SQL **antes** de desplegar el código que la escribe.

### 8.3 Ejecución de pruebas y validaciones

```bash
source scripts/entorno.sh
python3 -m compileall -q lambdas scripts
scripts/pruebas.sh
scripts/construir_paquetes.sh
cd app && npm run build
```

### 8.4 Integración de cambios

Todo cambio entra a `main` por *pull request*, con revisión de otra persona del equipo y el flujo `revision.yml` en verde. Fusionar en `main` despliega: no hay una puerta de aprobación aparte, porque el plan gratuito de un repositorio privado no la ofrece.

## 9. Dependencias y servicios externos

### 9.1 Servicios externos integrados

| Servicio | Para qué |
|---|---|
| ROBLE (OPENLAB) | Autenticación (contraseña y Google) y las 14 tablas |
| Amazon Bedrock y Guardrails | El modelo de los agentes y la propuesta del plan; salvaguardas de contenido |
| Amazon Transcribe | Dictado por voz en tiempo real |
| Amazon SES | Correos al profesional y al paciente, avisos de cita y escalamientos |
| EventBridge Scheduler | Disparo de los recordatorios cada 15 minutos |
| CloudWatch y SNS | *Logs*, métrica y alarma de escalamiento |
| Amplify Hosting | Publicación de la PWA |
| GitHub Actions | Integración y despliegue continuos |

### 9.2 Requisitos de acceso

Un equipo nuevo necesita: acceso de escritura al repositorio; acceso a la cuenta de AWS del proyecto (para el arranque, Parameter Store, SES y la consola); la cuenta de ROBLE con el contrato del proyecto (para el esquema, los roles y la consola SQL); y una cuenta de paciente de prueba para los evaluadores. Para desplegar no hace falta ser administrador del repositorio: los roles de AWS están escritos en los flujos.

### 9.3 Consideraciones de desarrollo y pruebas

- **Las pruebas no tocan la red**: `lambdas/pruebas/entorno.py` sustituye `boto3`, `requests` y el SDK de ROBLE cuando faltan.
- **No hay un ambiente de pruebas separado**: los evaluadores corren contra el sistema desplegado, con datos sintéticos y cuentas de prueba.
- **La app móvil tiene un modo de demostración** (`EXPO_PUBLIC_DEMO=1`) con datos en memoria que no tocan ROBLE.
- **El simulador de triaje** del profesional permite probar al agente sin ningún efecto real.
- **Límites de ROBLE por IP**: 100 operaciones por minuto, 10 inicios de sesión cada 15 minutos y 5 registros por hora.

## 10. Convenciones del proyecto

### 10.1 Convenciones de código

- **Todo en español**: funciones, variables, comentarios, *commits* y los textos de los agentes (español de Colombia, tuteando).
- **Los comentarios explican el porqué, no el qué**, y suelen contar qué se rompió antes. No se rebajan a un resumen.
- Python 3.12 sin dependencias más allá de las de la capa; TypeScript estricto en los dos clientes.

### 10.2 Convenciones de repositorio

- Ramas con prefijo y autor; *pull request* a `main`.
- *Commits* agrupados por tema, con mensaje en español, en infinitivo, voz impersonal y sin tildes («Identificar el cupo por su hora…»), con un cuerpo que explique el porqué.
- Los temporales van a `_scratch/<fecha>/` y no se versionan.

### 10.3 Convenciones de documentación

- `caresync/CLAUDE.md` es el mapa de trabajo; su sección de estado caduca y hay que contrastarla con `git log` y `GET /salud`.
- Cada corrida de un evaluador deja su informe sin editar en `evaluacion/informes/`, y su índice (`README.md`) explica el antes y el después.
- El protocolo tiene historial de revisiones dentro del propio archivo.

## 11. Problemas frecuentes y recomendaciones

### 11.1 Problemas frecuentes

- **Una columna que no existe produce un 400 en toda la actualización.** Comprobar contra `bootstrap_roble.mjs` antes de escribir un campo nuevo.
- **Un identificador inventado por el modelo rompe PostgreSQL** y se lee como «la base no responde». Por eso las citas se identifican por la hora del cupo y no por su identificador.
- **ROBLE solo filtra por igualdad**: sin rangos, orden ni paginación. Eso se hace en memoria; no intentar «arreglarlo».
- **La Converse API exige alternancia estricta** de papeles en el historial y que el último mensaje sea del usuario.
- **En conversaciones largas, el modelo deja de llamar herramientas** e imita la prosa del historial. Lo contienen la herramienta obligatoria de la agenda, las notas `[sistema]` y el control de citas inventadas: no quitar ninguno sin repetir la prueba de punta a punta.
- **Bogotá es UTC −05:00 fijo**: no mezclar las funciones de hora que asumen UTC (lo que viene de ROBLE) y hora local (lo que dice el modelo).
- **Pasarle a `evento()` el parámetro `nivel`** con el nivel de urgencia hace desaparecer la línea del *log* sin error: el campo se llama `nivel_urgencia`.

### 11.2 Deuda técnica conocida

- El estado `atendido` del caso no se distingue de `en_seguimiento`.
- No hay notificaciones *push* desde el servidor: las de la app móvil son locales, programadas al abrirla.
- El correo usa un remitente temporal de Gmail; los escalamientos van a un buzón del equipo, no al CAE real.
- Falta medir M6, M7 (contra lo desplegado) y la latencia, y ampliar las pruebas de uso a profesionales y administradores.
- La lógica de frecuencias está repetida entre el backend y la PWA, y las horas de las tomas en la app móvil son una convención sin validación clínica.
- Revisar que el rol base de ROBLE no pueda leer todas las tablas por su API.

### 11.3 Recomendaciones para continuidad

Las reglas que no se deben romper sin decirlo explícitamente:

1. **El modelo nunca aporta la identidad**: el caso, el *token* y el rol los pone el orquestador.
2. **Los permisos se comprueban en código, dos veces**: al declarar las herramientas y antes del efecto. Un *prompt* no es un control de acceso.
3. **El plan clínico lo escribe el profesional**: ninguna herramienta crea o modifica una indicación, y la propuesta del plan no guarda nada.
4. **El protocolo tiene una sola copia**, en `protocolos/`.
5. **`ESCALAMIENTO`, literal y en mayúsculas**, es el patrón de la alarma; la simulación nunca puede emitirlo.
6. **`escalar_urgencia` nunca lanza excepción** y siempre devuelve la ruta de emergencia.
7. **El agente no promete contacto humano** que no existe.
8. **Un fallo de herramienta se anota como `[sistema]`** en la conversación.
9. **La simulación no produce efectos** y **un paciente nunca simula**.

Y tres recomendaciones: medir cada cambio del agente antes de fusionarlo, empezar el trabajo futuro por la validación clínica del protocolo, y no aplicar Terraform desde una máquina.

## 12. Historial de decisiones técnicas relevantes

| Decisión | Fecha aproximada | Razón |
|---|---|---|
| ROBLE en lugar de Supabase | Fase 0 | Mantener los datos de salud dentro de la universidad |
| Vite en lugar de Next.js | Fase 0 | La PWA se sirve estática, sin renderizado en servidor |
| Terraform en lugar de AWS CDK; Amplify en lugar de Vercel | Fase 0 | Familiaridad del equipo y todo en una misma cuenta |
| Ciclo de herramientas propio sobre la Converse API | Fase 1 | Control del traspaso, del número de vueltas y del límite de 30 s |
| Protocolo en el *prompt* con caché, sin RAG | Fase 1 | Cabe completo en el contexto y es un solo documento |
| Reserva por reconciliación con testigo | Fase 3 | ROBLE no tiene transacciones |
| Quinto rol (plataforma) | 31-ago | Asignar roles sin tocar la consola de ROBLE |
| Quitar el tema denegado de disuasión de urgencia | 26-sep | Bloqueaba la respuesta correcta a las alarmas |
| La ruta de emergencia no depende de la respuesta del modelo | 26-sep | La salvaguarda podía cortar esa respuesta |
| Historial de triajes y simulador | 2-oct | Un resumen no permite juzgar si el triaje fue bueno |
| Dictado con Amazon Transcribe y no con el navegador | 13-oct | La Web Speech API de Chrome envía el audio a Google |
| App móvil con Expo | 30-oct | Notificaciones programadas en el teléfono |
| Agenda obligada a usar una herramienta en su primera vuelta | 2-nov | El modelo daba citas por hechas sin agendarlas |
| Migración a ROBLE producción; el código pone el identificador | 4 y 5-nov | La importación perdió el valor por defecto del identificador |
| Quien pierde una reserva cede y no libera el cupo | 5-nov | Error real encontrado por el evaluador de concurrencia |
| Remitente de correo temporal en Gmail | 6-nov | La política DMARC de Uninorte podía mandar los correos a cuarentena |

## 13. Referencias relacionadas

- [Informe Final](./InformeFinal.md), [Instalación.md](./Instalación.md), [Segundo Informe](./SegundoInforme.md) y [Primer Informe](./Primer_Informe_CareSync.md)
- `caresync/CLAUDE.md`: mapa de trabajo, invariantes y trampas
- `caresync/docs/arquitectura.md`: por qué el sistema es así
- `caresync/docs/despliegue.md` y `caresync/docs/runbook-roble.md`: despliegue y operación de ROBLE
- `caresync/evaluacion/informes/README.md`: índice de las mediciones
- `caresync/movil/README.md` y `caresync/movil/DESIGN.md`: la app móvil
- Documentación oficial: [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/), [Amazon Transcribe](https://docs.aws.amazon.com/transcribe/), [AWS Lambda](https://docs.aws.amazon.com/lambda/), [Terraform](https://developer.hashicorp.com/terraform/docs), [React](https://react.dev/), [Vite](https://vitejs.dev/) y [Expo](https://docs.expo.dev/)
