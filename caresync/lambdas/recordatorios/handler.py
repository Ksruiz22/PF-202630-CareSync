"""Trabajo por reloj: recordatorios, vigilancia y reconciliación.

EventBridge Scheduler despierta esta función cada 15 minutos. Es la única parte
del sistema sin una persona detrás, y por eso la única que usa la cuenta de
servicio de ROBLE.

Hace cuatro tareas, en este orden y de forma independiente: si una falla, las
otras se ejecutan igual. El motivo es que la tercera —vigilar— es la que puede
detectar que alguien lleva tres días sin reportar nada, y no puede quedar
bloqueada porque el envío de un correo se cayera.

1. **Reconciliar.** Devuelve a «libre» los cupos que quedaron reservados y sin
   confirmar. Es la mitad que le falta al patrón de `reservar_cupo`.
2. **Materializar.** Convierte las indicaciones activas del plan en
   recordatorios con fecha y hora concretas. Se hace por adelantado y en la base
   —y no calculando al vuelo— para que quede rastro de qué se le prometió a la
   persona y cuándo.
3. **Enviar.** Manda los que ya toca y los marca.
4. **Vigilar.** Busca silencios: indicaciones sin reporte y casos sin evolución.
   Un silencio no es una alarma clínica, pero sí es lo que el profesional
   necesita ver antes de la siguiente consulta.

Nada de esto reintenta a mano: si la invocación falla entera, Scheduler la
reintenta, y todas las tareas son idempotentes dentro de la misma ventana.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from caresync_comun import correo, reloj
from caresync_comun.errores import ErrorDeCareSync
from caresync_comun.registro import evento, registro
from caresync_comun.roble_acceso import (
    CASO_CERRADO,
    AccesoRoble,
    fila_id,
)

log = registro("recordatorios")

VENTANA_MINUTOS = int(os.environ.get("VENTANA_MINUTOS", "20"))
HORAS_SIN_ADHERENCIA = int(os.environ.get("HORAS_SIN_ADHERENCIA", "36"))
DIAS_SIN_EVOLUCION = int(os.environ.get("DIAS_SIN_EVOLUCION", "3"))
MINUTOS_RESERVA = int(os.environ.get("MINUTOS_RESERVA", "2"))

# Ningún recordatorio sale de madrugada. Un correo a las 3 a.m. no ayuda a nadie
# a tomarse algo y sí enseña a la persona a ignorar los avisos.
HORA_MINIMA = 7
HORA_MAXIMA = 20

# Tope por invocación. Con los volúmenes de un prototipo no se alcanza; está para
# que un error de datos no convierta una corrida en cientos de correos.
MAX_ENVIOS = 40


def manejar(entrada: dict[str, Any] | None = None, contexto: Any = None) -> dict[str, Any]:
    inicio = reloj.ahora()
    resumen: dict[str, Any] = {"corrida": reloj.iso(inicio), "tareas": {}}

    try:
        acceso = AccesoRoble.como_servicio()
    except ErrorDeCareSync as exc:
        # Sin cuenta de servicio no hay nada que hacer, y hay que verlo en el log
        # con el mensaje exacto: es el fallo típico de un despliegue nuevo en el
        # que aún no se cargaron las credenciales en Parameter Store.
        evento(log, "servicio_sin_credenciales", detalle=exc.mensaje)
        return {"ok": False, "motivo": exc.mensaje}

    try:
        for nombre, tarea in (
            ("reconciliar", _reconciliar),
            ("materializar", _materializar),
            ("enviar", _enviar),
            ("vigilar", _vigilar),
        ):
            try:
                resumen["tareas"][nombre] = tarea(acceso)
            except Exception as exc:  # noqa: BLE001 - una tarea no arrastra a las otras
                log.exception("tarea_fallida", extra={"caresync": {"tarea": nombre}})
                resumen["tareas"][nombre] = {"error": type(exc).__name__}
    finally:
        acceso.cerrar()

    resumen["ok"] = all("error" not in r for r in resumen["tareas"].values())
    evento(log, "corrida_terminada", **{k: v for k, v in resumen["tareas"].items()})
    return resumen


# ------------------------------------------------------------- 1. reconciliar

def _reconciliar(acceso: AccesoRoble) -> dict[str, Any]:
    return {"cupos_liberados": acceso.liberar_reservas_vencidas(minutos=MINUTOS_RESERVA)}


# ------------------------------------------------------------ 2. materializar

def _materializar(acceso: AccesoRoble) -> dict[str, Any]:
    """Programa el siguiente recordatorio de cada indicación activa.

    Sólo el siguiente, no la serie completa: el profesional puede desactivar una
    indicación mañana, y una serie ya escrita seguiría enviándose. Uno a la vez
    hace que desactivar la indicación baste para que dejen de salir.
    """
    creados = 0
    omitidos = 0
    casos: dict[str, dict[str, Any] | None] = {}

    for indicacion in acceso.todas_las_indicaciones_activas():
        indicacion_id = fila_id(indicacion)
        caso_id = str(indicacion.get("caso_id") or "")
        if not indicacion_id or not caso_id:
            omitidos += 1
            continue

        if caso_id not in casos:
            try:
                casos[caso_id] = acceso.caso(caso_id)
            except ErrorDeCareSync:
                casos[caso_id] = None
        caso = casos[caso_id]
        if not caso or caso.get("estado") == CASO_CERRADO:
            omitidos += 1
            continue

        existentes = acceso.recordatorios_de_indicacion(indicacion_id)
        if any(r.get("estado") == "pendiente" for r in existentes):
            continue

        intervalo = _intervalo(indicacion.get("frecuencia"))
        if not intervalo:
            # Una indicación de una sola vez ("acude al control") no genera serie.
            omitidos += 1
            continue

        ultimo = _ultimo_programado(existentes)
        base = (ultimo + intervalo) if ultimo else reloj.ahora() + intervalo
        cuando = _hora_decente(max(base, reloj.ahora() + timedelta(minutes=5)))

        acceso.programar_recordatorio(
            caso_id=caso_id,
            indicacion_id=indicacion_id,
            cuando=cuando,
            texto=str(indicacion.get("texto") or "Tienes una indicación pendiente"),
        )
        creados += 1

    return {"creados": creados, "omitidos": omitidos}


def _intervalo(frecuencia: Any) -> timedelta | None:
    """Traduce la frecuencia que escribió el profesional a un intervalo.

    Es texto libre a propósito: el profesional escribe en su interfaz, no elige
    de una lista. Lo que no se entiende no se convierte en una serie de correos,
    se omite y queda contado en el resumen de la corrida.
    """
    texto = str(frecuencia or "").strip().lower()
    if not texto:
        return None

    for palabra, delta in (
        ("cada 4 horas", timedelta(hours=4)),
        ("cada 6 horas", timedelta(hours=6)),
        ("cada 8 horas", timedelta(hours=8)),
        ("cada 12 horas", timedelta(hours=12)),
        ("dos veces al día", timedelta(hours=12)),
        ("diaria", timedelta(days=1)),
        ("diario", timedelta(days=1)),
        ("cada día", timedelta(days=1)),
        ("semanal", timedelta(days=7)),
        ("cada semana", timedelta(days=7)),
    ):
        if palabra in texto:
            return delta
    return None


def _ultimo_programado(recordatorios: list[dict[str, Any]]) -> datetime | None:
    momentos = [
        m
        for m in (reloj.desde_iso(r.get("programado_para")) for r in recordatorios)
        if m is not None
    ]
    return max(momentos) if momentos else None


def _hora_decente(momento: datetime) -> datetime:
    """Empuja un instante a la siguiente hora razonable en Bogotá."""
    local = reloj.en_bogota(momento)
    if local is None:
        return momento
    if local.hour < HORA_MINIMA:
        local = local.replace(hour=HORA_MINIMA, minute=0, second=0, microsecond=0)
    elif local.hour >= HORA_MAXIMA:
        local = (local + timedelta(days=1)).replace(
            hour=HORA_MINIMA, minute=0, second=0, microsecond=0
        )
    return local


# ------------------------------------------------------------------ 3. enviar

def _enviar(acceso: AccesoRoble) -> dict[str, Any]:
    hasta = reloj.mas(minutos=VENTANA_MINUTOS)
    pendientes = acceso.recordatorios_pendientes(hasta=hasta)[:MAX_ENVIOS]

    enviados = 0
    fallidos = 0
    casos: dict[str, dict[str, Any] | None] = {}

    for recordatorio in pendientes:
        recordatorio_id = fila_id(recordatorio)
        caso_id = str(recordatorio.get("caso_id") or "")
        if not recordatorio_id:
            continue

        if caso_id not in casos:
            try:
                casos[caso_id] = acceso.caso(caso_id)
            except ErrorDeCareSync:
                casos[caso_id] = None
        caso = casos[caso_id]

        if not caso or caso.get("estado") == CASO_CERRADO:
            acceso.marcar_recordatorio(
                recordatorio_id, estado="cancelado", detalle="el caso ya no está activo"
            )
            continue

        salio = correo.enviar(
            para=str(caso.get("paciente_email") or ""),
            asunto="[CareSync] Recordatorio de tu plan",
            cuerpo="\n".join(
                [
                    f"Hola {caso.get('paciente_nombre') or ''}".strip() + ",",
                    "",
                    str(recordatorio.get("texto") or ""),
                    "",
                    "Cuando puedas, entra a CareSync y cuéntanos si lo cumpliste. "
                    "Con eso el profesional sabe cómo vas.",
                ]
            ),
        )

        # `enviado` aunque el correo no salga: el estado describe que esta
        # corrida ya lo atendió. Si quedara pendiente, la siguiente corrida lo
        # reintentaría cada 15 minutos para siempre. El detalle guarda qué pasó.
        acceso.marcar_recordatorio(
            recordatorio_id,
            estado="enviado" if salio else "no_entregado",
            detalle="" if salio else "SES no aceptó el mensaje o no hay remitente verificado",
        )
        enviados += int(salio)
        fallidos += int(not salio)

    return {"enviados": enviados, "no_entregados": fallidos, "revisados": len(pendientes)}


# ----------------------------------------------------------------- 4. vigilar

def _vigilar(acceso: AccesoRoble) -> dict[str, Any]:
    """Detecta silencios y los deja anotados en la bitácora del caso.

    No manda alarmas a AWS ni escala urgencias: un silencio no es una urgencia.
    Lo que hace es que el profesional, al abrir el caso, vea «lleva tres días sin
    reportar» en lugar de tener que deducirlo de la ausencia de filas.
    """
    limite_adherencia = reloj.mas(horas=-HORAS_SIN_ADHERENCIA)
    limite_evolucion = reloj.mas(dias=-DIAS_SIN_EVOLUCION)

    por_caso: dict[str, list[dict[str, Any]]] = {}
    for indicacion in acceso.todas_las_indicaciones_activas():
        caso_id = str(indicacion.get("caso_id") or "")
        if caso_id:
            por_caso.setdefault(caso_id, []).append(indicacion)

    sin_adherencia = 0
    sin_evolucion = 0

    for caso_id, indicaciones in por_caso.items():
        try:
            caso = acceso.caso(caso_id)
        except ErrorDeCareSync:
            continue
        if caso.get("estado") == CASO_CERRADO:
            continue

        reportes = acceso.adherencia_del_caso(caso_id)
        ultimo_por_indicacion: dict[str, datetime] = {}
        for reporte in reportes:
            momento = reloj.desde_iso(reporte.get("reportado_en"))
            clave = str(reporte.get("indicacion_id") or "")
            if momento and (clave not in ultimo_por_indicacion or momento > ultimo_por_indicacion[clave]):
                ultimo_por_indicacion[clave] = momento

        calladas = []
        for indicacion in indicaciones:
            # Si nunca reportó, la referencia es cuándo se creó la indicación: no
            # se puede acusar de silencio a alguien a quien se le indicó algo
            # hace una hora.
            referencia_indicacion = ultimo_por_indicacion.get(str(fila_id(indicacion))) or reloj.desde_iso(
                indicacion.get("creado_en")
            )
            if referencia_indicacion and referencia_indicacion < limite_adherencia:
                calladas.append(indicacion)

        if calladas and not _ya_anotado(acceso, caso_id, "sin_adherencia", limite_adherencia):
            acceso.registrar_evento(
                caso_id=caso_id,
                tipo="sin_adherencia",
                severidad="alta",
                detalle={
                    "horas": HORAS_SIN_ADHERENCIA,
                    "indicaciones": [str(i.get("texto") or "")[:120] for i in calladas],
                },
            )
            evento(log, "sin_adherencia", caso_id=caso_id, indicaciones=len(calladas))
            sin_adherencia += 1

        evolucion = acceso.evolucion_del_caso(caso_id)
        ultima = reloj.desde_iso(evolucion[-1].get("reportado_en")) if evolucion else None
        referencia = ultima or reloj.desde_iso(caso.get("actualizado_en"))
        if referencia and referencia < limite_evolucion and not _ya_anotado(
            acceso, caso_id, "sin_evolucion", limite_evolucion
        ):
            acceso.registrar_evento(
                caso_id=caso_id,
                tipo="sin_evolucion",
                severidad="alta",
                detalle={"dias": DIAS_SIN_EVOLUCION, "ultimo": reloj.iso(referencia)},
            )
            evento(log, "sin_evolucion", caso_id=caso_id)
            sin_evolucion += 1

    return {
        "casos_revisados": len(por_caso),
        "sin_adherencia": sin_adherencia,
        "sin_evolucion": sin_evolucion,
    }


def _ya_anotado(acceso: AccesoRoble, caso_id: str, tipo: str, desde: datetime) -> bool:
    """Evita repetir la misma anotación en cada corrida de 15 minutos."""
    for registro_evento in acceso.eventos_del_caso(caso_id):
        if registro_evento.get("tipo") != tipo:
            continue
        cuando = reloj.desde_iso(registro_evento.get("creado_en"))
        if cuando and cuando > desde:
            return True
    return False
