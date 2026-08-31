#!/usr/bin/env bash
# Crea el esquema de CareSync en ROBLE.
#
#   scripts/esquema_roble.sh                        # las 14 tablas
#   scripts/esquema_roble.sh --semilla              # + profesionales y horarios
#   scripts/esquema_roble.sh --perfil profesional CMU
#   scripts/esquema_roble.sh --perfil admin_cmu
#   scripts/esquema_roble.sh --perfil admin_plataforma
#
# El trabajo de verdad lo hace app/esquema/bootstrap_roble.mjs; este envoltorio
# resuelve tres cosas incómodas:
#
#   1. De dónde salen la URL y el contrato de ROBLE: de infra/dev.tfvars, que es el
#      mismo archivo del que los toma Terraform. Un segundo sitio donde escribirlos
#      es un segundo sitio donde equivocarse.
#   2. Dónde vive `node_modules`: fuera de la carpeta sincronizada con OneDrive.
#   3. Que la contraseña la pida el script y no quede en el entorno ni en un archivo.
#
# La contraseña se teclea cuando el script la pida. Si se prefiere pasarla por
# entorno —en CI, por ejemplo—, se usan ROBLE_EMAIL y ROBLE_PASSWORD.
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=entorno.sh
source "${raiz}/scripts/entorno.sh"

app="${raiz}/app"
tfvars="${raiz}/infra/${CARESYNC_ENTORNO}.tfvars"

for herramienta in node npm rsync python3; do
  command -v "${herramienta}" >/dev/null || { echo "Falta ${herramienta}" >&2; exit 1; }
done

[ -f "${tfvars}" ] || { echo "No existe ${tfvars}" >&2; exit 1; }

# Un lector mínimo de tfvars: `clave = "valor"`. No es HCL completo y no pretende
# serlo; si algún día estas variables dejan de ser cadenas simples, esto se cambia
# por `terraform output`, que exige haber aplicado antes.
leer_tfvars() {
  python3 - "$1" "$2" <<'PY'
import re, sys
ruta, clave = sys.argv[1], sys.argv[2]
patron = re.compile(rf'^\s*{re.escape(clave)}\s*=\s*"([^"]*)"')
for linea in open(ruta, encoding='utf-8'):
    encaje = patron.match(linea)
    if encaje:
        print(encaje.group(1))
        break
PY
}

ROBLE_BASE_URL="$(leer_tfvars "${tfvars}" roble_base_url)"
ROBLE_CONTRACT_ID="$(leer_tfvars "${tfvars}" roble_contract_id)"
export ROBLE_BASE_URL ROBLE_CONTRACT_ID

[ -n "${ROBLE_BASE_URL}" ] || { echo "Falta roble_base_url en ${tfvars}" >&2; exit 1; }
[ -n "${ROBLE_CONTRACT_ID}" ] || { echo "Falta roble_contract_id en ${tfvars}" >&2; exit 1; }

compilacion="${CARESYNC_DIR_COMPILACION:-${HOME}/.cache/caresync/app}"
mkdir -p "${compilacion}"
rsync -a --delete --exclude node_modules --exclude dist "${app}/" "${compilacion}/"

cd "${compilacion}"
if [ ! -d node_modules ] || [ package-lock.json -nt node_modules ]; then
  echo "==> npm ci"
  npm ci --no-audit --no-fund
fi

node esquema/bootstrap_roble.mjs "$@"
