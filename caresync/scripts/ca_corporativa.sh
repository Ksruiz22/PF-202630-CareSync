#!/usr/bin/env bash
# Construye el paquete de certificados que la red corporativa hace necesario.
#
#   scripts/ca_corporativa.sh
#
# El problema: la red de la empresa (Cato Networks) inspecciona TLS. Cuando una
# herramienta abre https://registry.terraform.io, lo que recibe no es el certificado
# de HashiCorp sino uno emitido al vuelo por «Cato-Networks-Server-...», firmado por
# una raíz que no está en ningún almacén de confianza público. El resultado es
# siempre el mismo error con distintas palabras:
#
#   terraform  x509: certificate signed by unknown authority
#   aws cli    SSL: CERTIFICATE_VERIFY_FAILED
#   node       unable to get local issuer certificate
#
# La solución no es desactivar la verificación —eso deja la conexión sin protección
# alguna— sino añadir la raíz de la inspección al conjunto de emisores de confianza,
# junto a los del sistema.
#
# Se guarda en $HOME/.aws/ y no en el repositorio: no es secreto, pero es propio de
# esta máquina y de esta red, y en otra red el archivo estorba.
#
# Ejecutar de nuevo cuando el error reaparezca: la raíz de Cato rota cada cierto
# tiempo, y cuando cambia, este script vuelve a capturarla.
set -euo pipefail

destino="${CARESYNC_CA_BUNDLE:-$HOME/.aws/ca-corporativa.pem}"

# Los servicios que el proyecto necesita alcanzar. Se consultan todos porque la
# inspección no es uniforme: hoy `sts` pasa sin tocar y `bedrock-runtime` va
# interceptado, y eso puede cambiar sin avisar.
hosts=(
  registry.terraform.io
  sts.us-east-1.amazonaws.com
  bedrock-runtime.us-east-1.amazonaws.com
  lambda.us-east-1.amazonaws.com
  amplify.us-east-1.amazonaws.com
  roble-api.test-openlab.uninorte.edu.co
  registry.npmjs.org
)

command -v openssl >/dev/null || { echo "Falta openssl" >&2; exit 1; }

sistema="/etc/ssl/certs/ca-certificates.crt"
[ -f "${sistema}" ] || { echo "No encuentro el almacén del sistema en ${sistema}" >&2; exit 1; }

trabajo="$(mktemp -d)"
trap 'rm -rf "${trabajo}"' EXIT

echo "==> Capturando cadenas"
for host in "${hosts[@]}"; do
  if openssl s_client -showcerts -connect "${host}:443" -servername "${host}" </dev/null 2>/dev/null \
    | awk '/BEGIN CERTIFICATE/,/END CERTIFICATE/' >> "${trabajo}/cadena.pem"; then
    echo "    ${host}"
  else
    # Un host inalcanzable no aborta: puede estar caído o no existir en esta región.
    echo "    ${host}: no respondió, se omite" >&2
  fi
done

[ -s "${trabajo}/cadena.pem" ] || { echo "No se capturó ningún certificado" >&2; exit 1; }

echo "==> Quedándose con los emisores únicos"
csplit -z -f "${trabajo}/cert" -b "%03d.pem" "${trabajo}/cadena.pem" '/BEGIN CERTIFICATE/' '{*}' >/dev/null

# Se deduplica por huella y no por contenido: el mismo certificado llega con saltos
# de línea distintos según el servidor.
: > "${trabajo}/salida.pem"
for cert in "${trabajo}"/cert*.pem; do
  huella="$(openssl x509 -in "${cert}" -noout -fingerprint -sha256 2>/dev/null | cut -d= -f2 || true)"
  [ -n "${huella}" ] || continue
  grep -qxF "${huella}" "${trabajo}/huellas" 2>/dev/null && continue
  echo "${huella}" >> "${trabajo}/huellas"
  cat "${cert}" >> "${trabajo}/salida.pem"
  sujeto="$(openssl x509 -in "${cert}" -noout -subject | sed 's/^subject=//')"
  echo "    ${sujeto}"
done

echo "==> Añadiendo el almacén del sistema"
cat "${sistema}" >> "${trabajo}/salida.pem"

mkdir -p "$(dirname "${destino}")"
mv "${trabajo}/salida.pem" "${destino}"
chmod 644 "${destino}"

echo
echo "==> ${destino} ($(grep -c 'BEGIN CERTIFICATE' "${destino}") certificados)"
echo "    scripts/entorno.sh lo exporta solo. Comprueba con:"
echo "      source scripts/entorno.sh && aws sts get-caller-identity"
