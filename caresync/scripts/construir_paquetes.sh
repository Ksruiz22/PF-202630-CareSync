#!/usr/bin/env bash
# Construye los cuatro artefactos que Terraform necesita en dist/.
#
#   dist/capa.zip           dependencias de PyPI + el paquete compartido
#   dist/orquestador.zip    handler + agentes + protocolos
#   dist/herramientas.zip   handler + las nueve herramientas + ruta de emergencia
#   dist/recordatorios.zip  handler del trabajo por reloj
#
# Terraform NO construye esto: no sabe ejecutar pip de forma reproducible, y un
# `null_resource` con `local-exec` haría que el resultado dependiera de la máquina
# que corre `apply`. Aquí el build es explícito y su salida es un artefacto.
#
# Los protocolos se copian dentro de los paquetes en lugar de leerse de S3 o de
# Parameter Store para que el protocolo desplegado sea exactamente el que está en
# el commit: una versión del código y una del protocolo, juntas.
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
lambdas="${raiz}/lambdas"
protocolos="${raiz}/protocolos"
dist="${raiz}/dist"
build="${raiz}/.build"

python_bin="${PYTHON_BIN:-python3}"

# Lambda corre arm64 (Graviton: ~20 % más barato por la misma memoria), así que
# las ruedas hay que bajarlas para esa plataforma y no para la de esta máquina.
plataforma="manylinux2014_aarch64"
version_python="3.12"

echo "==> Limpiando ${build} y ${dist}"
rm -rf "${build}" "${dist}"
mkdir -p "${dist}"

# --------------------------------------------------------------------- capa
echo "==> Capa: dependencias para ${plataforma} / Python ${version_python}"
destino_capa="${build}/capa/python"
mkdir -p "${destino_capa}"

# --only-binary y --platform juntos son obligatorios: sin ellos pip compilaría
# charset-normalizer para x86_64 y la función fallaría al importar requests con
# un error de arquitectura que no dice nada.
"${python_bin}" -m pip install \
  --requirement "${lambdas}/requirements-capa.txt" \
  --target "${destino_capa}" \
  --platform "${plataforma}" \
  --python-version "${version_python}" \
  --implementation cp \
  --only-binary=:all: \
  --upgrade \
  --quiet

echo "==> Capa: paquete compartido caresync_comun"
cp -r "${lambdas}/comun/caresync_comun" "${destino_capa}/"

# Metadatos de pip que no aportan nada en tiempo de ejecución y sí pesan.
find "${destino_capa}" -maxdepth 1 -type d -name '*.dist-info' -exec rm -rf {} +
find "${destino_capa}" -type d -name '__pycache__' -prune -exec rm -rf {} +

"${python_bin}" "${raiz}/scripts/empaquetar.py" "${build}/capa" "${dist}/capa.zip"

# ---------------------------------------------------------------- funciones
empacar_funcion() {
  local nombre="$1"
  shift
  local destino="${build}/${nombre}"

  echo "==> Función ${nombre}"
  mkdir -p "${destino}"
  cp "${lambdas}/${nombre}"/*.py "${destino}/"

  # Los protocolos que esa función necesita, si necesita alguno.
  if [ "$#" -gt 0 ]; then
    mkdir -p "${destino}/protocolos"
    for archivo in "$@"; do
      cp "${protocolos}/${archivo}" "${destino}/protocolos/"
    done
  fi

  "${python_bin}" "${raiz}/scripts/empaquetar.py" "${destino}" "${dist}/${nombre}.zip"
}

# El orquestador inyecta el protocolo completo en el prompt del agente de triaje.
empacar_funcion orquestador triaje-v0.md ruta-emergencia.md
# Herramientas sólo devuelve el texto de la ruta de emergencia; no clasifica.
empacar_funcion herramientas ruta-emergencia.md
empacar_funcion recordatorios

# ------------------------------------------------------------------ resumen
echo
echo "==> Listo. Artefactos en dist/:"
ls -lh "${dist}" | tail -n +2 | awk '{printf "    %-22s %s\n", $9, $5}'
echo
echo "    Siguiente paso:  scripts/desplegar.sh"
