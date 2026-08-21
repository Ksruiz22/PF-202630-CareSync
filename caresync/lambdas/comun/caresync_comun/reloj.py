"""El tiempo, en un solo sitio.

Dos decisiones que conviene no repensar en cada archivo:

* **Se guarda siempre en UTC.** ROBLE es PostgreSQL y la columna es
  `timestamptz`; mezclar husos en la base es la forma más rápida de que un
  recordatorio salga con cinco horas de diferencia.
* **Se muestra siempre en hora de Bogotá.** Es la única zona en la que viven
  los usuarios de este sistema, y aparece en los correos y en lo que dice el
  agente.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:  # El runtime de Lambda trae la base de husos del sistema.
    from zoneinfo import ZoneInfo

    BOGOTA = ZoneInfo("America/Bogota")
except Exception:  # pragma: no cover - entornos sin tzdata
    # Colombia no aplica horario de verano, así que el desfase fijo es correcto
    # y no una aproximación.
    BOGOTA = timezone(timedelta(hours=-5), name="America/Bogota")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def ahora() -> datetime:
    """Instante actual en UTC, con zona explícita."""
    return datetime.now(timezone.utc)


def iso(momento: datetime | None = None) -> str:
    """Texto ISO 8601 en UTC, tal como se guarda en ROBLE."""
    return (momento or ahora()).astimezone(timezone.utc).isoformat()


def desde_iso(texto: str | None) -> datetime | None:
    """Interpreta lo que devuelve ROBLE, que no siempre trae zona.

    Un `timestamptz` de PostgreSQL puede llegar como `...+00:00`, como `...Z` o
    sin sufijo. Sin zona se asume UTC, que es lo que este sistema escribe.
    """
    if not texto:
        return None
    limpio = str(texto).strip().replace("Z", "+00:00")
    try:
        momento = datetime.fromisoformat(limpio)
    except ValueError:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def en_bogota(momento: datetime | str | None) -> datetime | None:
    instante = desde_iso(momento) if isinstance(momento, str) else momento
    return instante.astimezone(BOGOTA) if instante else None


def humano(momento: datetime | str | None) -> str:
    """Fecha y hora como se le dicen a una persona."""
    local = en_bogota(momento)
    if not local:
        return "sin fecha"
    return f"{DIAS[local.weekday()]} {local.day:02d}/{local.month:02d} a las {local:%H:%M}"


def mas(minutos: int = 0, horas: int = 0, dias: int = 0) -> datetime:
    return ahora() + timedelta(minutes=minutos, hours=horas, days=dias)
