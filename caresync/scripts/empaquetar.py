#!/usr/bin/env python3
"""Crea zips reproducibles para Lambda.

Existe en lugar de una línea con `zip` por dos razones concretas:

* **`zip` no siempre está instalado**, y Python 3.12 sí, porque es el mismo
  runtime que se despliega.
* **El zip tiene que ser reproducible.** Terraform guarda el hash del archivo en
  el estado, así que un zip con marcas de tiempo distintas en cada corrida haría
  que `plan` mostrara un cambio en las tres funciones cada vez que alguien
  ejecuta el build, sin que el código haya cambiado. Aquí se fija la fecha de
  todas las entradas y se ordenan alfabéticamente: mismo contenido, mismo hash.

Uso:
    python3 empaquetar.py <directorio_origen> <archivo.zip>
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

# 1980-01-01, el instante más antiguo que admite el formato zip. El valor no
# importa; que sea constante, sí.
FECHA_FIJA = (1980, 1, 1, 0, 0, 0)

EXCLUIDOS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".DS_Store", ".ruff_cache"}


def archivos(raiz: Path) -> list[Path]:
    encontrados = [
        ruta
        for ruta in raiz.rglob("*")
        if ruta.is_file()
        and not any(parte in EXCLUIDOS for parte in ruta.parts)
        and ruta.suffix not in (".pyc", ".pyo")
    ]
    # El orden de `rglob` depende del sistema de archivos; ordenar es parte de
    # que el resultado sea reproducible.
    return sorted(encontrados, key=lambda r: r.relative_to(raiz).as_posix())


def empaquetar(origen: Path, destino: Path) -> int:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino.unlink()

    contenidos = archivos(origen)
    if not contenidos:
        raise SystemExit(f"El directorio {origen} está vacío: no hay nada que empaquetar")

    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for ruta in contenidos:
            interno = ruta.relative_to(origen).as_posix()
            info = zipfile.ZipInfo(interno, date_time=FECHA_FIJA)
            # 0o644 para archivos normales, 0o755 para lo ejecutable. Lambda no
            # ejecuta nada del paquete directamente, pero un permiso 000 rompería
            # la lectura del módulo.
            ejecutable = ruta.suffix in (".sh",) or (ruta.stat().st_mode & 0o100)
            info.external_attr = (0o755 if ejecutable else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, ruta.read_bytes())

    return len(contenidos)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    origen = Path(sys.argv[1]).resolve()
    destino = Path(sys.argv[2]).resolve()
    if not origen.is_dir():
        raise SystemExit(f"No existe el directorio {origen}")

    cantidad = empaquetar(origen, destino)
    tamano = destino.stat().st_size / 1024
    print(f"  {destino.name}: {cantidad} archivos, {tamano:.0f} KiB")


if __name__ == "__main__":
    main()
