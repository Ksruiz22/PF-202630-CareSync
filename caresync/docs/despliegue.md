# Despliegue

Dos reglas que explican todo lo demás:

1. **La infraestructura se aplica en GitHub Actions, no en una máquina.** El estado
   está compartido en S3; dos personas aplicando a la vez se pisan. Hay un solo
   camino: pull request → plan revisable → `main` → apply.
2. **Los secretos los carga una persona, no el repositorio.** Ni Terraform ni
   Actions conocen la contraseña de la cuenta de servicio de ROBLE. Terraform crea
   el parámetro con un relleno y deja de mirarlo (`ignore_changes`).

Lo que sí se hace desde una máquina: `infra/arranque/` una vez, cargar las
credenciales de ROBLE, crear las tablas de ROBLE y mirar planes.

## Dónde está cada cosa en el repositorio

El repositorio es `Ksruiz22/PF-202630-CareSync` y su raíz **no** es esta carpeta: en
la raíz están los entregables de la asignatura y este proyecto vive en `caresync/`.
Eso obliga a una asimetría que conviene tener presente al editar un workflow, porque
GitHub sólo ejecuta lo que encuentra en `.github/workflows/` de la raíz:

| | Ruta |
|---|---|
| Workflows | `.github/workflows/` (raíz del repositorio) |
| Todo lo demás del proyecto | `caresync/` |

De ahí que cada trabajo declare `working-directory: caresync` y que los filtros de
`paths` lleven ese prefijo. La trampa: eso vale para los `run:`, no para los `with:`
de un `uses:`, que se resuelven siempre contra la raíz — `cache-dependency-path`
tiene que decir `caresync/app/package-lock.json`.

## De cero a desplegado

### 1. Una vez: el arranque

Crea el bucket del estado, la tabla de bloqueo, el proveedor de identidad de GitHub
y los dos roles que asume Actions. No puede correr en Actions porque es lo que crea
la identidad de Actions. El detalle está en [`infra/arranque/README.md`](../infra/arranque/README.md).

`arranque.tfvars` ya está en el repositorio con `repositorio =
"Ksruiz22/PF-202630-CareSync"`; se versiona porque no lleva secretos y porque cambiar
qué repositorio puede desplegar en la cuenta debe dejar rastro en un commit.

```bash
source scripts/entorno.sh
cd infra/arranque
terraform init && terraform apply -var-file=arranque.tfvars
```

### 2. Comprobar que los ARN coinciden

No hay nada que configurar en *Settings*: **desplegar no requiere ser admin del
repositorio**, y eso es deliberado. Los ARN de los dos roles están escritos
literalmente en los workflows, así que basta comparar:

```bash
terraform -chdir=infra/arranque output rol_plan rol_apply
grep -rn role-to-assume ../.github/workflows/
```

Dos decisiones detrás de esto, por si algún día se quieren revertir:

- **Los ARN van en el YAML, no en `vars.*`.** Un ARN de rol no es un secreto —lo que
  protege la cuenta es la política de confianza, que sólo acepta un `sub` de este
  repositorio—, y las variables se administran en *Settings*, que exige admin.
  Escribirlos en el archivo deja el despliegue en manos de cualquiera con permiso de
  escritura, y cambiar de rol o de cuenta queda registrado en un commit.
- **El trabajo de despliegue no declara `environment:`.** Sería la puerta de
  aprobación humana, pero en un repositorio privado de plan gratuito los environments
  y sus reglas de protección no están disponibles. La política de confianza acepta el
  `sub` con environment y sin él, así que añadirlo el día que el repositorio sea
  público o de pago es una línea en `infra.yml` y ningún cambio en IAM.

Lo que sigue conteniendo el despliegue es el `sub` del token: sólo `main` de este
repositorio puede asumir el rol de escritura. Lo que se pierde con esto es la
aprobación previa — entrar en `main` aplica.

### 3. Empujar a `main`

`.github/workflows/infra.yml` construye los paquetes de Lambda, planifica y aplica
los cuarenta recursos, y deja en el resumen del trabajo la lista de lo que queda
por hacer a mano. Después, `.github/workflows/app.yml` compila la PWA con la URL
real del API y la publica en Amplify.

### 4. Una vez: lo que Actions no puede hacer

```bash
source scripts/entorno.sh

# Las credenciales de la cuenta de servicio de ROBLE. Las usa sólo la Lambda de
# recordatorios, que corre por reloj y no tiene un usuario que la autorice.
aws ssm put-parameter --overwrite --name /caresync/dev/roble/servicio/email \
  --type String --value 'svc-caresync@uninorte.edu.co'
aws ssm put-parameter --overwrite --name /caresync/dev/roble/servicio/password \
  --type SecureString --value '...'

# Las catorce tablas de ROBLE. Pide el correo y la contraseña por consola.
scripts/esquema_roble.sh
```

Y verificar en SES la dirección de `correo_remitente` cuando llegue el correo de
AWS. Mientras esté vacía en `infra/dev.tfvars`, el sistema registra los envíos en el
log en lugar de mandarlos, y no se crean ni el presupuesto ni los avisos.

## Los flujos

| Flujo | Cuándo | Credenciales | Qué hace |
|---|---|---|---|
| `revision.yml` | todo pull request y `main` | ninguna | `terraform fmt`/`validate`, `bash -n`, `compileall`, construye los paquetes, `tsc` + `vite build` |
| `infra.yml` | pull request que toque `infra/`, `lambdas/`, `protocolos/`, `scripts/` | `caresync-ci-plan` (sólo lectura) | plan, y lo publica en el resumen |
| `infra.yml` | empujón a `main` | `caresync-ci-apply` | plan + apply + sonda de salud |
| `app.yml` | `app/` cambia, o `infra.yml` terminó bien | `caresync-ci-apply` | compila la PWA y la publica en Amplify |
| `destruir.yml` | **sólo a mano**, desde `main` | `caresync-ci-apply` | `plan -destroy` al resumen y lo aplica |

`revision.yml` es el único que funciona en un pull request venido de un fork:
GitHub no emite token de OIDC en esos, así que el plan no puede autenticarse. No es
un fallo que haya que arreglar, es la razón por la que un fork no puede tocar la
cuenta.

Los tres flujos ejecutan los mismos scripts de `scripts/` que se usan a mano. Si CI
tuviera sus propios pasos de `terraform`, el día que divergieran nadie se enteraría
hasta que el despliegue de una persona y el de CI dieran resultados distintos.

## Destruir el entorno

```bash
gh workflow run destruir.yml --ref main -f confirmacion='destruir dev' -f motivo='...'
```

O en la pestaña *Actions* → *destruir* → *Run workflow*. No tiene disparador
automático: sólo `workflow_dispatch`, que es lo que impide que un empujón borre el
entorno. Pide escribir `destruir dev` —el nombre del entorno, no un «sí», para que
haya que mirar cuál se está destruyendo— y sólo funciona desde `main`, porque la
política de confianza del rol no acepta el `sub` de ninguna otra rama.

Antes de borrar deja el `terraform plan -destroy` en el resumen del trabajo. No es
una puerta de aprobación, que en este repositorio no se puede tener: es el registro
de qué había cuando se borró.

**Qué sobrevive**, y no por descuido:

| | |
|---|---|
| El arranque | bucket del estado, tabla de bloqueo, proveedor OIDC y los dos roles de CI. Están en otro módulo y en otro estado, y el rol de CI tiene un `Deny` sobre ellos. Un destroy no deja la cuenta sin forma de volver a desplegar. |
| Los datos | viven en ROBLE, que no es AWS. Las catorce tablas también: `esquema_roble.sh` no hay que repetirlo. |

**Qué hay que reponer** al volver a desplegar: las credenciales de ROBLE en Parameter
Store (incluida la contraseña, que se borra con el parámetro), la verificación en SES
de los dos correos, y la confirmación de la suscripción al tema de SNS. La URL de la
PWA además cambia, porque Amplify da un dominio nuevo al recrear la aplicación. La
lista sale también en el resumen del trabajo y al final de `scripts/destruir.sh`.

A mano, para una emergencia con Actions caído, existe `scripts/destruir.sh` — pide el
nombre del entorno por consola. Vale la misma regla que para `desplegar.sh --si`: el
estado es compartido y el sitio para destruir es el flujo.

## Ejecutar los scripts en una máquina

```bash
source scripts/entorno.sh          # perfil, región, CA corporativa, TF_DATA_DIR
scripts/desplegar.sh --plan        # planificar: se puede y se debe
scripts/publicar_app.sh            # publicar la PWA: se puede
```

`scripts/desplegar.sh --si` sigue existiendo y aplica de verdad. Está para una
emergencia con Actions caído, no para el día a día; el bloqueo de DynamoDB es lo que
impide que coincida con un apply de CI.

### La primera vez tras pasar el estado a S3

Si en `$TF_DATA_DIR` quedó una inicialización con el backend local, `init` avisa de
que la configuración del backend cambió. No hay estado que migrar —nunca se aplicó
nada con el backend local— así que basta con empezar de cero:

```bash
rm -rf "${TF_DATA_DIR}"
```

## La red corporativa

La red de Jamar (Cato Networks) inspecciona TLS y reemplaza el certificado de los
sitios que se visitan. El síntoma es el mismo error con distintas palabras:

```
terraform  x509: certificate signed by unknown authority
aws cli    SSL: CERTIFICATE_VERIFY_FAILED
node       unable to get local issuer certificate
```

La solución no es desactivar la verificación, es añadir la raíz de la inspección al
conjunto de emisores de confianza:

```bash
scripts/ca_corporativa.sh
```

`scripts/entorno.sh` exporta el paquete resultante en **cinco** variables, porque son
cinco almacenes de confianza distintos y ninguno lee los de los otros:
`AWS_CA_BUNDLE` (botocore), `REQUESTS_CA_BUNDLE` (el SDK de ROBLE en Python),
`NODE_EXTRA_CA_CERTS` (npm y Vite), `SSL_CERT_FILE` (Go, y por tanto Terraform
hablando con su registro) y `CURL_CA_BUNDLE` (la subida del paquete a Amplify).

En GitHub Actions no hace falta nada de esto: el ejecutor sale a internet sin
inspección. `entorno.sh` detecta que está en CI y ni avisa de que falta el paquete.

## Por qué no hay `profile` en ninguna parte de Terraform

El bloque `backend` se evalúa antes que las variables y no admite interpolación, así
que un perfil sólo puede escribirse literal ahí. Tenerlo literal en el backend y
como variable en el proveedor son dos sitios que dicen lo mismo, y terminan diciendo
cosas distintas: el estado leído de una cuenta y los recursos aplicados en otra.

La resolución de credenciales queda en el entorno, que funciona igual en los dos
casos: `AWS_PROFILE=team_devops_jamar` en una máquina (lo pone `entorno.sh`, y sólo
si no hay credenciales de OIDC), y las variables que inyecta
`configure-aws-credentials` en Actions. Lo que garantiza que se aplica en la cuenta
correcta no es el perfil: es la comprobación de `CARESYNC_CUENTA` que hace
`desplegar.sh` antes de tocar nada.
