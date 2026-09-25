#!/usr/bin/env bash
# Corre todas las pruebas que no necesitan red, AWS ni un token de ROBLE.
#
#   lambdas/pruebas/prueba_*.py   permisos, orquestador, herramientas, recordatorios
#   evaluacion/prueba_*.py        la lógica de los evaluadores
#
# Cada archivo es un proceso aparte a propósito: las pruebas sustituyen módulos
# (`boto3`, el log de una herramienta, `requests`) y compartir intérprete haría que
# el orden de ejecución cambiara el resultado.
#
# Se buscan por patrón y no por lista para que una prueba nueva entre sola en CI,
# sin tocar `revision.yml`.
#
# En Windows el intérprete se llama `python`; se usa ese si no hay `python3`, o el
# que diga PYTHON_BIN, como en `construir_paquetes.sh`.
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-$(command -v python3 || command -v python)}"

fallidas=()
total=0
for prueba in "${raiz}"/lambdas/pruebas/prueba_*.py "${raiz}"/evaluacion/prueba_*.py; do
  [[ -e "${prueba}" ]] || continue
  total=$((total + 1))
  nombre="${prueba#"${raiz}/"}"

  if salida="$(cd "$(dirname "${prueba}")" && "${python_bin}" "$(basename "${prueba}")" 2>&1)"; then
    echo "ok     ${nombre} ($(grep -c '^  ok' <<<"${salida}") comprobaciones)"
  else
    echo "FALLA  ${nombre}"
    echo "${salida}" | sed 's/^/       /'
    fallidas+=("${nombre}")
  fi
done

echo
if ((${#fallidas[@]})); then
  echo "${#fallidas[@]} de ${total} archivos de prueba fallaron."
  exit 1
fi
echo "Los ${total} archivos de prueba pasan."
