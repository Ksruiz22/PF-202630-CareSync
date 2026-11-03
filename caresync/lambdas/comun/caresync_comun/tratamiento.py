"""Las indicaciones del plan que se cumplen en una cita: un control o una serie de sesiones.

Lo comparten `consultar_plan`, que le dice al agente de seguimiento si hay algo por
agendar, y las herramientas de agenda, que lo agendan. Una sola regla: si cada una
contara las citas a su manera, el agente ofrecería un control que la agenda después no
reconoce como pendiente.

Una cita pertenece a una indicación por `citas.indicacion_id`, que escriben las
herramientas de agenda al tomar el espacio (columna del 29/10). El plazo sale de
`indicaciones.plazo_dias`, contado desde el día en que el profesional escribió el plan:
«control en dos semanas» es alrededor del día 14, no mañana.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from caresync_comun import reloj
from caresync_comun.roble_acceso import CITA_CONFIRMADA, cita_por_delante, fila_id

# Tipo de indicación → tipo de cita (`citas.tipo`). Sólo estas dos se agendan.
SE_AGENDAN = {"control": "control", "sesiones": "sesion"}

# Sin plazo dictado, un control se busca en el mes siguiente; una sesión, en las dos
# semanas siguientes, porque una serie no espera un mes entre una y otra.
DIAS_SIN_PLAZO = 30
DIAS_PARA_LA_SESION = 14


def citas_de(indicacion: dict[str, Any], citas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    propia = str(fila_id(indicacion) or "")
    return [c for c in citas if propia and str(c.get("indicacion_id") or "") == propia]


def hechas(citas: list[dict[str, Any]], *, ahora: datetime | None = None) -> int:
    """Las citas que cuentan como cumplidas.

    Las atendidas, y también las confirmadas que ya terminaron sin que nadie las
    marcara: si el profesional no guardó un plan en ese control, la persona igual fue,
    y volver a ofrecérselo sería pedirle que repita una consulta que ya tuvo. Las
    canceladas y las de `no_asistio` no cuentan.
    """
    momento = ahora or reloj.ahora()
    total = 0
    for cita in citas:
        estado = str(cita.get("estado") or CITA_CONFIRMADA)
        fin = reloj.desde_iso(cita.get("fin"))
        if estado == "atendida" or (estado == CITA_CONFIRMADA and fin and fin <= momento):
            total += 1
    return total


def estado(
    indicacion: dict[str, Any], citas: list[dict[str, Any]], *, ahora: datetime | None = None
) -> dict[str, Any]:
    """Cómo va la indicación respecto de sus citas: agendada, por agendar o completa."""
    suyas = citas_de(indicacion, citas)
    por_delante = sorted(
        (c for c in suyas if cita_por_delante(c, ahora=ahora)), key=lambda c: str(c.get("inicio") or "")
    )
    cumplidas = hechas(suyas, ahora=ahora)
    total = _sesiones(indicacion) if indicacion.get("tipo") == "sesiones" else 1
    return {
        "por_delante": por_delante[0] if por_delante else None,
        "hechas": cumplidas,
        "completa": total is not None and cumplidas >= total,
    }


def pendiente(
    indicaciones: list[dict[str, Any]], citas: list[dict[str, Any]], *, ahora: datetime | None = None
) -> dict[str, Any] | None:
    """La primera indicación de control o de sesiones que todavía necesita una cita."""
    candidatas = sorted(
        (i for i in indicaciones if i.get("tipo") in SE_AGENDAN),
        key=lambda i: str(i.get("creado_en") or ""),
    )
    for indicacion in candidatas:
        situacion = estado(indicacion, citas, ahora=ahora)
        if not situacion["por_delante"] and not situacion["completa"]:
            return indicacion
    return None


def ventana(indicacion: dict[str, Any], *, ahora: datetime | None = None) -> tuple[datetime, datetime]:
    """Desde y hasta cuándo se busca la cita de esta indicación.

    Un control con plazo se busca alrededor de su fecha, con una tolerancia de un
    cuarto del plazo y nunca menos de dos días: a las dos semanas, entre el día 11 y
    el 17. Si esa fecha ya pasó, desde ahora: el control sigue haciendo falta.
    """
    momento = ahora or reloj.ahora()
    plazo = _entero(indicacion.get("plazo_dias"))
    if indicacion.get("tipo") == "control" and plazo:
        escrito = reloj.desde_iso(indicacion.get("creado_en")) or momento
        objetivo = escrito + timedelta(days=plazo)
        holgura = timedelta(days=max(2, plazo // 4))
        desde = max(momento, objetivo - holgura)
        return desde, max(objetivo + holgura, desde + timedelta(days=2))
    dias = DIAS_PARA_LA_SESION if indicacion.get("tipo") == "sesiones" else DIAS_SIN_PLAZO
    return momento, momento + timedelta(days=dias)


def _sesiones(indicacion: dict[str, Any]) -> int | None:
    """Cuántas tiene la serie; sin número, la serie no se da por completa sola."""
    return _entero(indicacion.get("sesiones"))


def _entero(valor: Any) -> int | None:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None
