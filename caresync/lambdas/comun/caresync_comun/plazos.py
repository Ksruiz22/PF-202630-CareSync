"""Los plazos del protocolo de triaje, para el código que tiene que hacerlos cumplir.

La fuente es el Paso 2 de `protocolos/triaje-v0.md`: nivel 2 en 72 horas, nivel 3 en
7 días, nivel 4 sin cita. Están aquí y no sólo en el protocolo porque el protocolo lo
lee el modelo y estos números los tiene que aplicar una herramienta. Hasta el 29/10
sólo existían como texto, y `consultar_disponibilidad` devolvía los cupos más
cercanos sin mirar el nivel: un caso de nivel 2 podía salir con cita a seis días sin
que nada lo marcara.

Si el protocolo cambia un plazo, cambia aquí en el mismo commit.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

# Sólo los niveles que tienen cita. El 1 no se agenda (es la ruta de emergencia) y el
# 4 es una orientación: si la persona pide cita, se le busca sin plazo.
PLAZOS: dict[int, timedelta] = {
    2: timedelta(hours=72),
    3: timedelta(days=7),
}

TEXTO: dict[int, str] = {1: "ahora", 2: "72 horas", 3: "7 días", 4: "sin cita"}


def nivel_de(caso: dict[str, Any] | None) -> int | None:
    """El nivel de urgencia del caso como entero, o `None` si no tiene.

    ROBLE lo devuelve a veces como texto, y un caso recién abierto no tiene ninguno.
    """
    try:
        nivel = int((caso or {}).get("nivel_urgencia") or 0)
    except (TypeError, ValueError):
        return None
    return nivel if 1 <= nivel <= 4 else None


def plazo_de(nivel: int | None) -> timedelta | None:
    return PLAZOS.get(nivel) if nivel else None


def texto_de(nivel: int | None) -> str:
    return TEXTO.get(nivel or 0, "7 días")
