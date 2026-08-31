#!/usr/bin/env bash
# Destruye la infraestructura de CareSync de un entorno.
#
#   scripts/destruir.sh            muestra el plan de destrucción y pide confirmación
#   scripts/destruir.sh --plan     sólo el plan, no destruye nada
#   scripts/destruir.sh --si       destruye sin preguntar (para CI)
#
# Lo ejecuta `.github/workflows/destruir.yml` con `--plan` y luego con `--si`, por
# el mismo motivo que el despliegue: una sola implementación, para que lo que hace
# el botón de GitHub y lo que hace una persona no puedan divergir.
#
# ---------------------------------------------------------------------------
# Lo que esto NO destruye, y no es un olvido:
#
#   * El arranque (infra/arranque/): el bucket del estado, la tabla de bloqueo, el
#     proveedor OIDC y los dos roles de CI. Están en otro módulo y en otro estado.
#     Si esto los borrara, borraría la identidad con la que Actions entra en la
#     cuenta —o sea, la forma de volver a desplegar y la de volver a destruir— y
#     dejaría al estado sin bucket donde vivir a mitad de la operación. El rol que
#     usa CI tiene además un `Deny` explícito sobre ellos: aunque este script lo
#     intentara, IAM diría no.
#
#   * Los datos. Viven en ROBLE, que no es AWS, y siguen ahí después de esto. Las
#     catorce tablas también: `scripts/esquema_roble.sh` no hay que volver a
#     ejecutarlo.
#
# Lo que sí desaparece y hay que reponer a mano después de un despliegue nuevo está
# en la lista que este script imprime al terminar.
# ---------------------------------------------------------------------------
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
version_terraform="$(terraform version)"
echo "${version_terraform%%$'\n'*}"

echo "==> Comprobando la cuenta"
credenciales="${AWS_PROFILE:-variables de entorno}"
cuenta_real="$(aws sts get-caller-identity --query Account --output text)"
if [ "${cuenta_real}" != "${CARESYNC_CUENTA}" ]; then
  echo "Las credenciales (${credenciales}) apuntan a ${cuenta_real}, se esperaba ${CARESYNC_CUENTA}" >&2
  exit 1
fi
echo "    cuenta ${cuenta_real} · entorno ${CARESYNC_ENTORNO} · credenciales ${credenciales}"

# ------------------------------------------------------------- artefactos
# Los cuatro .zip sólo tienen que existir, no ser correctos: lo único que Terraform
# comprueba sobre ellos es una `precondition` con `fileexists` (infra/lambdas.tf), y
# el contenido no se lee al destruir. Así que aquí se rellenan con archivos vacíos en
# vez de llamar a `construir_paquetes.sh`: un botón de destruir tiene que funcionar
# también el día que el build no funcione —que es justo el día en que se quiere
# usar—, y `pip install` depende de la red.
#
# El relleno no puede terminar desplegado: este script no aplica nada, y
# `desplegar.sh` reconstruye los paquetes de verdad antes de cada plan.
echo "==> Rellenando los paquetes que falten (sólo para que el plan se pueda calcular)"
mkdir -p "${raiz}/dist"
for paquete in capa orquestador herramientas recordatorios; do
  archivo="${raiz}/dist/${paquete}.zip"
  if [ ! -f "${archivo}" ]; then
    : > "${archivo}"
    echo "    ${paquete}.zip vacío (no se sube: esto sólo destruye)"
  fi
done

# ------------------------------------------------------------- terraform
cd "${raiz}/infra"

echo "==> Comprobando el bucket del estado"
bucket_estado="caresync-tfstate-${CARESYNC_CUENTA}"
if ! aws s3api head-bucket --bucket "${bucket_estado}" >/dev/null 2>&1; then
  echo "No existe (o no es accesible) el bucket ${bucket_estado}." >&2
  echo "Sin estado no hay nada que destruir: o nunca se aplicó, o el arranque no existe." >&2
  exit 1
fi

echo "==> terraform init"
terraform init -input=false \
  -backend-config="key=${CARESYNC_ENTORNO}/terraform.tfstate"

echo "==> terraform plan -destroy"
# El plan se guarda y luego se aplica ese archivo, no se usa `destroy -auto-approve`:
# lo que se borra es exactamente lo que se mostró, y no lo que hubiera cambiado en el
# estado entre una cosa y la otra.
terraform plan -destroy -input=false -var-file="${CARESYNC_ENTORNO}.tfvars" -out=destruir.tfplan

if [ "${modo}" = "--plan" ]; then
  echo "==> Sólo plan. El archivo queda en infra/destruir.tfplan"
  exit 0
fi

if [ "${modo}" != "--si" ]; then
  echo
  echo "Esto destruye la infraestructura del entorno «${CARESYNC_ENTORNO}» en la cuenta ${cuenta_real}."
  read -r -p "Para confirmar, escribe el nombre del entorno: " respuesta
  # Se pide el nombre del entorno y no un «si»: obliga a mirar cuál se está
  # destruyendo. Un «si» se contesta sin leer.
  if [ "${respuesta}" != "${CARESYNC_ENTORNO}" ]; then
    echo "Cancelado."
    rm -f destruir.tfplan
    exit 1
  fi
fi

echo "==> terraform apply (el plan de destrucción)"
terraform apply -input=false destruir.tfplan
rm -f destruir.tfplan

# ------------------------------------------------------------------ salida
cat <<'TXT'

==> Destruido. Lo que hay que reponer si se vuelve a desplegar:

    - Las credenciales de la cuenta de servicio de ROBLE en Parameter Store.
      Los parámetros se borraron con todo lo demás, incluida la contraseña.
    - La verificación en SES del correo remitente y del de emergencias: las
      identidades se recrean sin verificar y AWS manda el correo otra vez.
    - La confirmación de la suscripción al tema de SNS de los avisos.
    - La URL de la PWA cambia: Amplify da un dominio nuevo al recrear la app.

    Lo que NO hay que reponer: las catorce tablas de ROBLE y sus datos, que no
    están en AWS. Tampoco el arranque, que sigue intacto.
TXT
