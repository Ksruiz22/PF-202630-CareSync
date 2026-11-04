#!/usr/bin/env bash
# Copia la app al sistema de archivos de WSL, instala y la sirve en el puerto 5173.
#
# No se trabaja desde /mnt/c: ahí `node_modules` se sincronizaría entero con OneDrive
# y Metro iría por el mount 9p. Los fuentes siguen siendo los del repositorio; esta
# copia se puede borrar sin perder nada. Se vuelve a correr para traer los cambios.
set -euo pipefail

origen="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destino="${HOME}/_scratch/$(date +%F)/movil"

mkdir -p "${destino}"
tar -C "${origen}" --exclude=node_modules --exclude=.expo --exclude=dist -cf - . | tar -C "${destino}" -xf -
cd "${destino}"

[ -f .env ] || cp entorno.ejemplo .env

if [ ! -d node_modules ] || [ package.json -nt node_modules ]; then
  npm install --no-audit --no-fund
fi

if [ "${1:-}" = "--solo-copiar" ]; then
  exit 0
fi
exec npx expo start --web --port 5173
