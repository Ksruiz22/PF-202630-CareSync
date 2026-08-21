#!/usr/bin/env bash
# Despliega la infraestructura de CareSync.
#
#   scripts/desplegar.sh            muestra el plan y pide confirmación
#   scripts/desplegar.sh --plan     sólo el plan, no aplica nada
#   scripts/desplegar.sh --si       aplica sin preguntar (para CI)
#
# El orden importa y por eso está en un script y no en el README: los zips tienen
# que existir antes de `terraform plan`, porque las funciones declaran una
# `precondition` sobre el archivo y el plan falla —a propósito— si falta.
#
# Este mismo script es el que ejecuta GitHub Actions (`--plan` en los pull requests,
# `--si` en main). Una sola implementación del despliegue: si el flujo de CI tuviera
# sus propios pasos de terraform, el día que divergieran nadie se enteraría hasta
# que el despliegue de una persona y el de CI dieran resultados distintos.
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=entorno.sh
source "${raiz}/scripts/entorno.sh"

modo="${1:-interactivo}"
tfvars="${raiz}/infra/${CARESYNC_ENTORNO}.tfvars"

[ -f "${tfvars}" ] || { echo "No existe ${tfvars}" >&2; exit 1; }

# ------------------------------------------------- comprobaciones previas
echo "==> Comprobando herramientas"
for herramienta in terraform aws python3; do
  command -v "${herramienta}" >/dev/null || { echo "Falta ${herramienta}" >&2; exit 1; }
done
terraform version | head -1

echo "==> Comprobando la cuenta"
# Que las credenciales apunten a la cuenta que se espera. Aplicar esta
# infraestructura sobre otra cuenta crearía recursos con nombres genéricos
# difíciles de rastrear. Esta comprobación es la que sustituye al `profile` que
# antes fijaba el proveedor: en CI no hay perfiles, sólo credenciales de OIDC, y
# lo que importa no es de dónde salen sino a qué cuenta llegan.
credenciales="${AWS_PROFILE:-variables de entorno}"
cuenta_real="$(aws sts get-caller-identity --query Account --output text)"
if [ "${cuenta_real}" != "${CARESYNC_CUENTA}" ]; then
  echo "Las credenciales (${credenciales}) apuntan a ${cuenta_real}, se esperaba ${CARESYNC_CUENTA}" >&2
  exit 1
fi
echo "    cuenta ${cuenta_real} · credenciales ${credenciales}"

if [ "${modo}" = "--plan" ]; then
  # El rol que planifica en los pull requests es de sólo lectura y no puede
  # invocar el modelo. Sondearlo aquí daría un aviso falso en cada PR.
  echo "==> Sin sonda de Bedrock (modo plan)"
else
  echo "==> Comprobando el acceso al modelo de Bedrock"
  # Debe coincidir con `var.modelo_id` en infra/variables.tf. Se repite aquí porque
  # antes del primer `apply` no hay salida de Terraform que consultar.
  modelo="${CARESYNC_MODELO:-us.anthropic.claude-haiku-4-5-20251001-v1:0}"
  # Un `converse` mínimo cuesta una fracción de centavo y evita descubrir en la
  # demo que el acceso al modelo nunca se habilitó en la consola.
  if aws bedrock-runtime converse \
      --model-id "${modelo}" \
      --messages '[{"role":"user","content":[{"text":"ping"}]}]' \
      --inference-config '{"maxTokens":5}' >/dev/null 2>&1; then
    echo "    ${modelo} responde"
  else
    echo "    AVISO: ${modelo} no respondió." >&2
    echo "           Habilita el acceso al modelo en la consola de Bedrock (Model access)." >&2
    echo "           El despliegue continúa: la infraestructura se crea igual." >&2
  fi
fi

# ------------------------------------------------------------- artefactos
echo "==> Construyendo los paquetes de Lambda"
"${raiz}/scripts/construir_paquetes.sh"

# ------------------------------------------------------------- terraform
cd "${raiz}/infra"

echo "==> Comprobando el bucket del estado"
# El estado está en S3 (infra/backend.tf) y ese bucket no lo crea este módulo.
# Sin esta comprobación, `init` falla con un error de S3 que no dice qué hacer.
bucket_estado="caresync-tfstate-${CARESYNC_CUENTA}"
if ! aws s3api head-bucket --bucket "${bucket_estado}" >/dev/null 2>&1; then
  echo "No existe (o no es accesible) el bucket ${bucket_estado}." >&2
  echo "Se crea una sola vez desde una máquina:  cd infra/arranque && terraform apply" >&2
  exit 1
fi

echo "==> terraform init"
# `-upgrade` sólo a petición. Por omisión se respeta `.terraform.lock.hcl`, que es
# justamente para lo que se versiona: que CI y las tres máquinas del equipo usen la
# misma versión del proveedor. Un `-upgrade` en cada ejecución de CI reescribiría el
# candado en el ejecutor y la coincidencia sería casualidad.
terraform init -input=false \
  -backend-config="key=${CARESYNC_ENTORNO}/terraform.tfstate" \
  ${CARESYNC_TF_UPGRADE:+-upgrade}

echo "==> terraform validate"
terraform validate

echo "==> terraform plan"
terraform plan -input=false -var-file="${CARESYNC_ENTORNO}.tfvars" -out=plan.tfplan

if [ "${modo}" = "--plan" ]; then
  echo "==> Sólo plan. El archivo queda en infra/plan.tfplan"
  exit 0
fi

if [ "${modo}" != "--si" ]; then
  read -r -p "¿Aplicar este plan? [escribe «si»] " respuesta
  [ "${respuesta}" = "si" ] || { echo "Cancelado."; rm -f plan.tfplan; exit 1; }
fi

echo "==> terraform apply"
terraform apply -input=false plan.tfplan
rm -f plan.tfplan

# ------------------------------------------------------------------ salida
echo
echo "==> Desplegado. Comprobación de salud:"
salud="$(terraform output -raw endpoint_salud)"
curl -sS "${salud}" | python3 -m json.tool || echo "    (la sonda no respondió todavía)"

echo
echo "==> Pendiente a mano:"
terraform output -json pendiente_manual | python3 -c \
  'import json,sys; [print("    -", x) for x in json.load(sys.stdin)]'

echo
echo "==> Para publicar la aplicación web:  scripts/publicar_app.sh"
