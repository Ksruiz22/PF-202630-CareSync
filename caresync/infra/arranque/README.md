# `infra/arranque/`

Lo que hay que crear antes de que GitHub Actions pueda crear el resto. Se aplica
**una vez**, desde una máquina, con las credenciales de quien administra la cuenta
539091491293.

```bash
source scripts/entorno.sh
cd infra/arranque
cp arranque.tfvars.ejemplo arranque.tfvars   # y escribe el repositorio real
terraform init
terraform apply -var-file=arranque.tfvars
```

## Por qué esto no corre en Actions

Crea la identidad con la que Actions entra en la cuenta. Ejecutarlo en Actions
exigiría que Actions ya tuviera credenciales, que es lo que este módulo produce.
El resto del despliegue —los cuarenta recursos de `infra/`— sí corre en Actions y
nunca desde una máquina.

## Su estado es local y se puede perder

No se versiona (`.gitignore` excluye `*.tfstate`) y no está en S3, porque el
bucket de S3 lo crea este módulo. Si se pierde, no hay que borrar nada: se importa.

```bash
terraform import -var-file=arranque.tfvars aws_s3_bucket.estado caresync-tfstate-539091491293
terraform import -var-file=arranque.tfvars aws_dynamodb_table.bloqueo caresync-tflock
terraform import -var-file=arranque.tfvars 'aws_iam_openid_connect_provider.github[0]' \
  arn:aws:iam::539091491293:oidc-provider/token.actions.githubusercontent.com
terraform import -var-file=arranque.tfvars aws_iam_role.plan caresync-ci-plan
terraform import -var-file=arranque.tfvars aws_iam_role.apply caresync-ci-apply
```

Los tres recursos de configuración del bucket (versionado, cifrado, bloqueo de
acceso público, ciclo de vida) se importan con el nombre del bucket como id.

## Después del apply

`terraform output siguiente_paso` lo dice, pero en resumen:

1. `AWS_ROL_PLAN` y `AWS_ROL_APPLY` como **variables** del repositorio (no como
   secretos: un ARN de rol no es secreto y verlo en el log ayuda a diagnosticar).
2. El environment `aws-dev` en GitHub, con revisores si se quiere que un humano
   apruebe cada despliegue.
3. Las credenciales de ROBLE en Parameter Store, a mano. Ver `infra/ssm.tf`.

## Los dos roles

| Rol | Lo asume | Puede |
|---|---|---|
| `caresync-ci-plan` | pull requests del repositorio autorizado | leer la cuenta y bloquear el estado |
| `caresync-ci-apply` | `main` / environment `aws-dev` | todo menos IAM, más IAM sobre `caresync-*` |

Son dos porque un pull request ejecuta código que todavía no ha revisado nadie.
El rol de los pull requests no crea, borra ni modifica nada.

La contrapartida honesta del rol de plan está anotada en `ci.tf`: para refrescar
los parámetros `SecureString` necesita `kms:Decrypt`, así que puede leer la
contraseña de servicio de ROBLE. Lo que lo contiene es que sólo lo asume un
repositorio concreto y que GitHub no da token de OIDC a los pull requests de un
fork.
