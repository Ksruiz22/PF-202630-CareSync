#!/usr/bin/env bash
# Compila la PWA y la publica en Amplify Hosting.
#
#   scripts/publicar_app.sh
#
# El despliegue es manual (`create-deployment` + subida de un zip) porque la app
# de Amplify no tiene repositorio conectado; el por qué está en infra/amplify.tf.
#
# Lo importante de este script es de dónde salen las variables de la compilación:
# **de las salidas de Terraform, no de un .env versionado**. Vite hornea las
# variables `VITE_*` en el bundle en tiempo de compilación, así que si la URL del
# API la escribiera una persona a mano, un `apply` que recreara el API dejaría la
# aplicación apuntando a un endpoint que ya no existe, y sin error visible.
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=entorno.sh
source "${raiz}/scripts/entorno.sh"

app="${raiz}/app"
infra="${raiz}/infra"
rama="main"

for herramienta in npm rsync python3 terraform aws curl; do
  command -v "${herramienta}" >/dev/null || { echo "Falta ${herramienta}" >&2; exit 1; }
done

# ---------------------------------------------- variables desde Terraform
cd "${infra}"

# El init es necesario aunque aquí no se aplique nada: el estado vive en S3 y
# `terraform output` no puede leerlo sin haber configurado el backend. En una
# máquina donde ya se desplegó esto no hace nada; en un ejecutor de GitHub
# Actions, que empieza con el repositorio recién clonado, es lo que hace que el
# resto del script funcione.
echo "==> terraform init (para leer el estado remoto)"
terraform init -input=false -backend-config="key=${CARESYNC_ENTORNO}/terraform.tfstate" >/dev/null

echo "==> Leyendo las salidas de Terraform"
api_url="$(terraform output -raw api_url)"
app_id="$(terraform output -raw amplify_app_id)"
pwa_url="$(terraform output -raw pwa_url)"
roble_base="$(terraform output -json roble | python3 -c 'import json,sys; print(json.load(sys.stdin)["base_url"])')"
roble_cid="$(terraform output -json roble | python3 -c 'import json,sys; print(json.load(sys.stdin)["contract_id"])')"

echo "    api      ${api_url}"
echo "    amplify  ${app_id} (${pwa_url})"
echo "    roble    ${roble_cid}"

# ------------------------------------------------------------- compilación
#
# Se compila **fuera del árbol del proyecto**, en una carpeta de caché del usuario.
# El proyecto vive en una carpeta sincronizada con OneDrive, y `node_modules` son
# más de diez mil archivos que no aportan nada al repositorio y que la
# sincronización subiría uno por uno cada vez que cambie una dependencia. Se copian
# las fuentes, se instala allí y de allí sale el `dist/`.
compilacion="${CARESYNC_DIR_COMPILACION:-${HOME}/.cache/caresync/app}"
mkdir -p "${compilacion}"

echo "==> Copiando las fuentes a ${compilacion}"
rsync -a --delete --exclude node_modules --exclude dist "${app}/" "${compilacion}/"

cd "${compilacion}"
if [ ! -d node_modules ] || [ package-lock.json -nt node_modules ]; then
  echo "==> npm ci"
  npm ci --no-audit --no-fund
fi

echo "==> vite build"
# Se pasan por el entorno del proceso y no por un archivo: así no queda un .env
# con la configuración del despliegue tirado en el árbol de trabajo.
VITE_API_URL="${api_url%/}" \
VITE_ROBLE_BASE_URL="${roble_base}" \
VITE_ROBLE_CONTRACT_ID="${roble_cid}" \
VITE_ENTORNO="${CARESYNC_ENTORNO}" \
  npm run build

# ---------------------------------------------------------------- publicar
echo "==> Empaquetando dist/"
zip_salida="${raiz}/.build/app.zip"
mkdir -p "$(dirname "${zip_salida}")"
python3 "${raiz}/scripts/empaquetar.py" "${compilacion}/dist" "${zip_salida}"

echo "==> Creando el despliegue en Amplify"
respuesta="$(aws amplify create-deployment --app-id "${app_id}" --branch-name "${rama}")"
url_subida="$(printf '%s' "${respuesta}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["zipUploadUrl"])')"
job_id="$(printf '%s' "${respuesta}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["jobId"])')"

echo "==> Subiendo el paquete"
curl -sS -X PUT -T "${zip_salida}" "${url_subida}"

echo "==> Iniciando el despliegue (job ${job_id})"
aws amplify start-deployment \
  --app-id "${app_id}" \
  --branch-name "${rama}" \
  --job-id "${job_id}" >/dev/null

# Amplify tarda unos segundos en servir la versión nueva; sin esperar, abrir la
# URL enseña la anterior y parece que el despliegue no hizo nada.
echo "==> Esperando a que termine"
for _ in $(seq 1 30); do
  estado="$(aws amplify get-job --app-id "${app_id}" --branch-name "${rama}" --job-id "${job_id}" \
    --query 'job.summary.status' --output text)"
  case "${estado}" in
    SUCCEED) echo "    ${estado}"; break ;;
    FAILED|CANCELLED) echo "    ${estado}: revisa la consola de Amplify" >&2; exit 1 ;;
    *) printf '    %s\r' "${estado}"; sleep 5 ;;
  esac
done

echo
echo "==> Publicado: ${pwa_url}"
