# Variables de entorno comunes. Se carga con `source`, no se ejecuta:
#
#   source scripts/entorno.sh
#
# Dos cosas que resuelve y que no son evidentes:
#
# **El perfil.** Todo va contra la cuenta 539091491293. En una máquina se llega
# ahí con el perfil `team_devops_jamar`; fijarlo aquí evita el accidente de aplicar
# Terraform sobre la cuenta que estuviera en `AWS_PROFILE` por defecto. En GitHub
# Actions no hay perfiles y el perfil no se exporta (ver más abajo). La garantía
# común a los dos casos es la comprobación de `CARESYNC_CUENTA` en desplegar.sh.
#
# **La inspección TLS corporativa.** La red de la empresa reemplaza el
# certificado de los sitios que se visitan por uno propio, así que el SDK de AWS
# rechaza la conexión con `CERTIFICATE_VERIFY_FAILED` hasta que se le pasa el
# paquete de CA que incluye ese emisor. `AWS_CA_BUNDLE` sólo se exporta si el
# archivo existe: en una red sin inspección, sobra.
#
# Cómo generar el paquete, una sola vez: scripts/ca_corporativa.sh. El detalle y el
# por qué de cada variable están en docs/despliegue.md.

# El perfil sólo en una máquina de una persona.
#
# En GitHub Actions las credenciales llegan por OIDC como variables de entorno
# (`AWS_ACCESS_KEY_ID` y compañía) y no hay ningún `~/.aws/config`. Si aquí se
# exportara `AWS_PROFILE`, la CLI buscaría un perfil inexistente y fallaría con
# «The config profile (team_devops_jamar) could not be found» — un error que no dice
# nada sobre la causa real. Por eso se comprueba antes.
if [ -z "${CI:-}" ] && [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [ -z "${AWS_WEB_IDENTITY_TOKEN_FILE:-}" ]; then
  export AWS_PROFILE="${AWS_PROFILE:-team_devops_jamar}"
fi
export AWS_REGION="${AWS_REGION:-us-east-1}"
export AWS_DEFAULT_REGION="${AWS_REGION}"

# Cuenta esperada. `desplegar.sh` la compara con la real antes de aplicar.
export CARESYNC_CUENTA="${CARESYNC_CUENTA:-539091491293}"
export CARESYNC_ENTORNO="${CARESYNC_ENTORNO:-dev}"

_ca="${CARESYNC_CA_BUNDLE:-$HOME/.aws/ca-corporativa.pem}"
if [ -f "${_ca}" ]; then
  # Cuatro variables porque son cuatro almacenes de confianza distintos y ninguno
  # lee los de los otros. Faltó aprenderlo a golpes:
  #   AWS_CA_BUNDLE       CLI y SDK de AWS (botocore)
  #   REQUESTS_CA_BUNDLE  requests, que es lo que usa el SDK de ROBLE en Python
  #   NODE_EXTRA_CA_CERTS Node: npm, Vite y el script del esquema
  #   SSL_CERT_FILE       Go, y por tanto Terraform hablando con su registro.
  #                       `AWS_CA_BUNDLE` no le sirve: el proveedor de AWS lo
  #                       respeta, pero la descarga del proveedor no.
  #   CURL_CA_BUNDLE      curl, que sube el paquete de la PWA a Amplify
  export AWS_CA_BUNDLE="${_ca}"
  export REQUESTS_CA_BUNDLE="${_ca}"
  export NODE_EXTRA_CA_CERTS="${_ca}"
  export SSL_CERT_FILE="${_ca}"
  export CURL_CA_BUNDLE="${_ca}"
elif [ -z "${CI:-}" ]; then
  # Aviso, no error: en una red doméstica el despliegue funciona sin esto. En CI
  # no se avisa porque ahí la ausencia es lo correcto: los ejecutores de GitHub
  # salen a internet sin inspección y el paquete corporativo no existe ni hace falta.
  echo "entorno.sh: sin paquete de CA en ${_ca}." >&2
  echo "            Si la red inspecciona TLS, generalo (ver el encabezado de este archivo)." >&2
fi
unset _ca

# Terraform no consulta si hay una versión más nueva de sí mismo. La versión la
# fija el flujo (1.5.7) y no la elige quien ejecuta, así que el aviso no sirve de
# nada; lo que sí hace es una llamada de red en cada invocación y una segunda línea
# de salida imprevisible, que es lo que rompió el despliegue una vez.
export CHECKPOINT_DISABLE=1

# Terraform escribe su caché de proveedores aquí para no volver a bajar 600 MB
# en cada clon del repositorio.
export TF_PLUGIN_CACHE_DIR="${TF_PLUGIN_CACHE_DIR:-$HOME/.terraform.d/plugin-cache}"
mkdir -p "${TF_PLUGIN_CACHE_DIR}"

# `.terraform/` fuera del árbol del proyecto.
#
# El repositorio vive en una carpeta sincronizada con OneDrive y `.terraform/`
# guarda el proveedor de AWS desempaquetado: más de 600 MB que la sincronización
# subiría archivo por archivo, cada vez que cambie la versión del proveedor. Con
# TF_DATA_DIR, Terraform lo pone en la caché del usuario y en el proyecto sólo
# quedan los .tf y el estado.
export TF_DATA_DIR="${TF_DATA_DIR:-$HOME/.cache/caresync/terraform-${CARESYNC_ENTORNO}}"
mkdir -p "${TF_DATA_DIR}"

# Dónde se compila la PWA, por el mismo motivo: `node_modules` son diez mil
# archivos que no tienen por qué sincronizarse a la nube.
export CARESYNC_DIR_COMPILACION="${CARESYNC_DIR_COMPILACION:-$HOME/.cache/caresync/app}"

echo "entorno.sh: credenciales=${AWS_PROFILE:-entorno} region=${AWS_REGION} entorno=${CARESYNC_ENTORNO}"
