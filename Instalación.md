# Instalación y despliegue

Guía para instalar, ejecutar y desplegar **CareSync Agentic Network**. El código del proyecto vive en la carpeta `caresync/` del repositorio; la raíz guarda los informes y los flujos de GitHub Actions (`.github/workflows/`). Todos los comandos de esta guía se ejecutan desde `caresync/`, salvo donde se indica.

## 1. Descripción general de la solución

### 1.1 Lenguajes y tecnologías utilizadas

| Parte | Tecnología |
|---|---|
| PWA (todos los roles) | TypeScript, React 18, Vite 5 |
| App móvil del paciente | TypeScript, React Native 0.76 con Expo SDK 52 |
| Backend | Python 3.12 en AWS Lambda (arm64), detrás de un HTTP API de API Gateway |
| Inteligencia artificial | Amazon Bedrock (Claude Haiku 4.5) con Bedrock Guardrails; Amazon Transcribe para el dictado |
| Datos y autenticación | ROBLE (OPENLAB, Universidad del Norte): PostgreSQL administrado y autenticación |
| Correo, automatización y observabilidad | Amazon SES, EventBridge Scheduler, CloudWatch y SNS |
| Infraestructura y despliegue | Terraform ≥ 1.5.7 (proveedor de AWS 6.x), GitHub Actions con OIDC, AWS Amplify Hosting |

### 1.2 Componentes de la solución

| Componente | Carpeta | Dónde corre |
|---|---|---|
| PWA | `app/` | Amplify Hosting; en desarrollo, `localhost:5173` |
| App móvil | `movil/` | Teléfono con Expo Go, o el navegador |
| Orquestador de agentes | `lambdas/orquestador/` | Lambda detrás de `POST /agente`, `POST /plan/propuesta`, `POST /dictado/sesion` y `GET /salud` |
| Servicio de herramientas | `lambdas/herramientas/` | Lambda invocada por el orquestador |
| Servicio de recordatorios | `lambdas/recordatorios/` | Lambda disparada cada 15 minutos |
| Código común | `lambdas/comun/caresync_comun/` | Capa compartida de las tres Lambdas |
| Protocolos de los agentes | `protocolos/` | Se copian dentro del paquete del orquestador al construir |
| Infraestructura | `infra/` | Terraform, aplicado desde GitHub Actions |
| Esquema de datos | `app/esquema/bootstrap_roble.mjs` | Crea las 14 tablas en ROBLE |
| Evaluadores | `evaluacion/` | Una máquina del equipo, contra el sistema desplegado |

## 2. Requisitos previos

### 2.1 Software requerido

| Herramienta | Versión | Para qué |
|---|---|---|
| Git | cualquiera reciente | Clonar el repositorio |
| Node.js y npm | 20 | PWA, app móvil y *script* del esquema |
| Python | 3.12 | Lambdas, pruebas y evaluadores |
| Terraform | ≥ 1.5.7 | Solo para planificar en local o para el arranque |
| AWS CLI | v2 | Solo para el arranque y cargar parámetros |
| Expo Go | la de la tienda | Solo para abrir la app móvil en un teléfono |

Además, para desplegar: una cuenta de AWS con acceso al modelo Claude Haiku 4.5 en Bedrock (región `us-east-1`), un proyecto en ROBLE con su contrato y acceso de escritura al repositorio en GitHub.

### 2.2 Variables de entorno

Ninguna variable de los clientes es un secreto: son las mismas direcciones públicas que la PWA lleva en su paquete. Los archivos `.env` no se versionan (`.gitignore`).

**PWA (`app/.env`)**

| Variable | Valor del entorno del proyecto |
|---|---|
| `VITE_API_URL` | `https://ow2vz6k279.execute-api.us-east-1.amazonaws.com` |
| `VITE_ROBLE_BASE_URL` | `https://roble-api.openlab.uninorte.edu.co` |
| `VITE_ROBLE_CONTRACT_ID` | `caresync_099060687b` |

**App móvil (`movil/.env`, a partir de `movil/entorno.ejemplo`)**

| Variable | Valor |
|---|---|
| `EXPO_PUBLIC_API_URL` | El mismo API |
| `EXPO_PUBLIC_ROBLE_BASE_URL` | La misma ROBLE |
| `EXPO_PUBLIC_ROBLE_CONTRACT_ID` | El mismo contrato |
| `EXPO_PUBLIC_DEMO` | `1` muestra «Ver demostración», con datos de ejemplo que no tocan ROBLE |

**Evaluadores (`evaluacion/.env`)**

| Variable | Valor |
|---|---|
| `CARESYNC_API_URL` | El API desplegado |
| `CARESYNC_EMAIL`, `CARESYNC_PASSWORD` | Una cuenta de **paciente** de prueba que no se use en la demostración |

**Infraestructura (`infra/dev.tfvars`, versionado porque no lleva secretos):** entorno, región, URL y contrato de ROBLE, remitente y buzón de emergencias del correo, presupuesto mensual (USD 20), retención de *logs* (14 días) y cadencia de los recordatorios (`rate(15 minutes)`).

**Secretos:** la única credencial del sistema es la cuenta de servicio de ROBLE que usa la función de recordatorios. Vive en AWS Systems Manager Parameter Store (`/caresync/dev/roble/servicio/email` y `/caresync/dev/roble/servicio/password`) y la carga una persona; ni Terraform ni GitHub Actions la conocen.

## 3. Instalación para ambiente de desarrollo

### 3.1 Desarrollo sin contenedores

#### 3.1.1 Clonar el repositorio

```bash
git clone https://github.com/Ksruiz22/PF-202630-CareSync.git
cd PF-202630-CareSync/caresync
```

#### 3.1.2 Instalar dependencias

```bash
# PWA
cd app && npm ci && cd ..

# App móvil (si el repositorio está en OneDrive, mejor en una copia fuera de él:
# movil/scripts/copia_de_trabajo.sh la crea en ~/_scratch/<fecha>/movil)
cd movil && npm ci && cd ..

# Backend: las pruebas no necesitan instalar nada, pero para ejecutar los evaluadores
python3 -m pip install requests
```

#### 3.1.3 Configurar variables de entorno

Crear `app/.env` y `movil/.env` con los valores de la §2.2. En una red corporativa con inspección TLS, generar una vez el paquete de certificados y cargar el entorno:

```bash
scripts/ca_corporativa.sh      # solo si la red reemplaza los certificados
source scripts/entorno.sh      # perfil de AWS, región y certificados
```

#### 3.1.4 Ejecutar servicios requeridos

No hay servicios locales que levantar. La PWA y la app móvil en desarrollo usan el API desplegado y la ROBLE del proyecto. El orquestador y las herramientas no se ejecutan en local para el uso diario: se prueban con las pruebas sin red (§5) y se despliegan desde GitHub Actions.

#### 3.1.5 Iniciar la aplicación

```bash
# PWA en http://localhost:5173
cd app && npm run dev

# App móvil en el navegador, también en el puerto 5173
cd movil && npm run web

# App móvil en el teléfono: escanear el QR con Expo Go, en la misma red Wi-Fi
cd movil && npx expo start
```

El puerto **5173** no es arbitrario: es el único origen de desarrollo que el API admite por CORS (`infra/locales.tf`) y el único destino local registrado en ROBLE para el inicio de sesión con Google. Con otro puerto, ROBLE funciona pero el asistente falla.

### 3.2 Desarrollo con contenedores

**No aplica.** CareSync no usa contenedores: la PWA es un sitio estático, el backend son funciones Lambda y los datos viven en ROBLE, un servicio administrado. No hay ningún servicio propio que empaquetar en una imagen, y el desarrollo local usa directamente el API y la ROBLE del proyecto.

#### 3.2.1 Construcción de contenedores

No aplica.

#### 3.2.2 Ejecución del entorno

No aplica.

#### 3.2.3 Servicios disponibles

No aplica.

#### 3.2.4 Apagado del entorno

No aplica.

## 4. Despliegue

### 4.1 Arquitectura de despliegue

El diagrama de despliegue está en la §12 del [Informe Final](./InformeFinal.md#12-despliegue-y-operación) (Figura 8). En resumen: la PWA en Amplify Hosting; el API en API Gateway con tres Lambdas en `us-east-1`; Bedrock, Transcribe, SES, EventBridge Scheduler, CloudWatch, SNS y Parameter Store como servicios administrados; y los datos en ROBLE producción, en la infraestructura de Uninorte. No hay red privada ni base de datos en AWS.

### 4.2 Proceso de actualización

La regla principal: **la infraestructura solo se aplica desde GitHub Actions**, porque el estado de Terraform es compartido y dos personas aplicando a la vez se pisarían.

1. Crear una rama y abrir un *pull request* a `main`.
2. El flujo `revision.yml` valida Terraform, compila Python, construye los paquetes, verifica los tipos, construye la PWA y corre las pruebas. Si el cambio toca `infra/`, `lambdas/`, `protocolos/` o `scripts/`, `infra.yml` publica el plan de Terraform en el resumen del trabajo.
3. Al fusionar en `main`, `infra.yml` construye los paquetes de Lambda, aplica Terraform y consulta `/salud`.
4. Si cambió `app/`, o si `infra.yml` terminó bien, `app.yml` compila la PWA con la URL real del API y la publica en Amplify.

Un cambio de *prompt* o de protocolo **no llega a producción hasta que se despliega**: el protocolo va dentro del paquete de la Lambda.

### 4.3 Despliegue sin contenedores

#### 4.3.1 Preparación del servidor

No hay servidores que preparar. Lo que sí se crea una vez, a mano, es el **arranque**: el almacenamiento del estado de Terraform, la tabla de bloqueo, el proveedor de identidad de GitHub y los dos roles que asume Actions. No puede correr en Actions porque es lo que crea su identidad. El detalle está en `infra/arranque/README.md`.

```bash
source scripts/entorno.sh
cd infra/arranque
terraform init && terraform apply -var-file=arranque.tfvars
```

#### 4.3.2 Instalación de dependencias

Las dependencias de las Lambdas se empaquetan solas: `scripts/construir_paquetes.sh` arma una capa compartida con las versiones fijas de `lambdas/requirements-capa.txt` (`roble` y `requests`) y copia los protocolos dentro del paquete del orquestador. Lo ejecuta `infra.yml`; en una máquina sirve para comprobar que no falta ningún protocolo.

#### 4.3.3 Configuración de la aplicación

Después del primer despliegue, una persona hace una sola vez lo que Actions no puede hacer:

```bash
source scripts/entorno.sh

# Credenciales de la cuenta de servicio de ROBLE (solo la usa la función de recordatorios)
aws ssm put-parameter --overwrite --name /caresync/dev/roble/servicio/email \
  --type String --value '<correo de la cuenta de servicio>'
aws ssm put-parameter --overwrite --name /caresync/dev/roble/servicio/password \
  --type SecureString --value '<contraseña>'

# Las 14 tablas de ROBLE (pide el correo y la contraseña por consola)
scripts/esquema_roble.sh
```

Y además: verificar en SES el remitente y el buzón de emergencias cuando llegue el correo de AWS, confirmar la suscripción al tema de SNS y, desde la vista de plataforma, asignar los roles de profesional y administrador. Mientras el remitente esté vacío en `infra/dev.tfvars`, el sistema registra los envíos en el *log* en lugar de mandarlos.

#### 4.3.4 Ejecución de la aplicación

Fusionar en `main`. El sistema queda disponible en la URL de Amplify, y `GET /salud` del API debe responder con el modelo, la salvaguarda, el contrato de ROBLE, la función de herramientas y el correo en buen estado.

#### 4.3.5 Actualización de versiones

Toda actualización sigue el flujo de la §4.2. Para planificar en una máquina sin aplicar: `scripts/desplegar.sh --plan`. Para retirar el entorno: el flujo manual `destruir.yml` (pestaña *Actions* → *destruir*), que pide escribir `destruir dev` y conserva el arranque y los datos de ROBLE. Al volver a desplegar hay que reponer las credenciales de Parameter Store, la verificación de SES y la suscripción de SNS, y la URL de la PWA cambia.

### 4.4 Despliegue con contenedores

**No aplica**, por las mismas razones de la §3.2.

#### 4.4.1 Construcción de imágenes

No aplica.

#### 4.4.2 Ejecución en servidor

No aplica.

#### 4.4.3 Variables de entorno y secretos

Ver la §2.2: los clientes reciben sus variables al compilar, las Lambdas las reciben de Terraform y el único secreto vive en Parameter Store.

#### 4.4.4 Persistencia y redes

Toda la persistencia está en ROBLE. En AWS solo se guardan el estado de Terraform, los parámetros y los *logs*, ninguno con datos de salud. No hay red privada: los servicios de AWS usados son administrados y se comunican por HTTPS.

#### 4.4.5 Actualización del despliegue

Ver la §4.2.

## 5. Verificación de funcionamiento

```bash
# Las pruebas sin red: 11 archivos, lo mismo que corre CI
scripts/pruebas.sh

# Compilación y paquetes
python3 -m compileall -q lambdas scripts
scripts/construir_paquetes.sh

# Tipos y construcción de la PWA y de la app móvil
cd app && npm run build && cd ..
cd movil && npm run typecheck && npm run prueba && cd ..

# El sistema desplegado
curl https://ow2vz6k279.execute-api.us-east-1.amazonaws.com/salud
```

Para comprobar el comportamiento de los agentes contra el sistema real, con la cuenta de `evaluacion/.env`:

```bash
cd evaluacion
python evaluar_triaje.py --solo cmu-01,alarma-mental-01   # prueba corta primero
python evaluar_triaje.py                                  # los 43 casos, unos 15 min
python evaluar_guardarrailes.py                           # los 26 intentos adversariales
```

Cada caso de alarma dispara de verdad la alarma de escalamiento: hay que avisar antes a quien la recibe.

## 6. Solución de problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `certificate signed by unknown authority` o `CERTIFICATE_VERIFY_FAILED` | Red corporativa con inspección TLS | `scripts/ca_corporativa.sh` y `source scripts/entorno.sh` |
| El asistente falla pero el inicio de sesión funciona | La PWA corre en un puerto distinto de 5173 | Usar el puerto 5173 |
| Respuestas 429 de ROBLE | Límite de 100 operaciones por minuto o de 10 inicios de sesión cada 15 minutos por IP | Esperar; no cerrar sesión; en una sala, abrir las sesiones antes |
| «La base de datos del proyecto no respondió» al crear filas | Tablas sin el valor por defecto del identificador tras una importación | El código ya genera el identificador; revisar que se esté usando la versión de `main` |
| 400 en toda una actualización | Se escribió una columna que no existe | Comprobar contra el esquema de `app/esquema/bootstrap_roble.mjs` y agregar la columna en ROBLE antes de desplegar |
| No llegan los correos | Remitente o destinatario sin verificar en SES | Verificar las direcciones en SES y revisar el correo no deseado |
| El agente de agenda dice que no hay espacios | No hay cupos publicados a futuro | Publicarlos desde la vista administrativa |
| Un cambio de *prompt* no se ve | No se ha desplegado | Fusionar en `main`: el protocolo va dentro del paquete |

## 7. Mantenimiento y actualización

- Antes de integrar un cambio, correr `scripts/pruebas.sh` y la construcción de la PWA.
- Después de tocar el *prompt*, el protocolo o las salvaguardas, volver a correr los evaluadores y guardar el informe en `evaluacion/informes/`.
- Mantener cupos publicados a futuro para que el agente de agenda tenga a dónde agendar.
- Revisar el presupuesto de AWS (alerta a USD 20 al mes) y la alarma de escalamiento.
- Toda columna nueva en ROBLE se agrega desde su consola SQL antes de desplegar el código que la escribe (`docs/runbook-roble.md`).

## 8. Referencias relacionadas

- [Informe Final](./InformeFinal.md) y [Manual de desarrollo](./Desarrollo.md)
- `caresync/docs/despliegue.md`: despliegue en detalle y decisiones detrás de los flujos
- `caresync/docs/runbook-roble.md`: operación de ROBLE (roles, permisos, tablas, Google)
- `caresync/infra/arranque/README.md`: el arranque de la cuenta
- `caresync/movil/README.md`: la app móvil
- Documentación de [Terraform](https://developer.hashicorp.com/terraform/docs), [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/), [Expo](https://docs.expo.dev/) y [Vite](https://vitejs.dev/)
