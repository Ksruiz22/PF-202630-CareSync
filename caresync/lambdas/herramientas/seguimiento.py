"""Herramientas de seguimiento: el plan, cómo va la persona y qué está cumpliendo.

Dos criterios que este módulo sostiene:

**El plan lo escribe el profesional, nunca el agente.** Aquí sólo se lee. No hay
ninguna herramienta que cree o modifique una indicación, y eso es una decisión de
alcance: un agente que pudiera cambiar un tratamiento sería otro proyecto, con
otras exigencias de validación.

**El agente registra, no interpreta.** `registrar_evolucion` guarda el número que
la persona dio y la frase con la que lo dijo. Si la comparación con el reporte
anterior sugiere un empeoramiento, la herramienta lo señala como dato —
`empeoro`— para que el agente decida escalar; no lo escala por su cuenta ni le
dice a la persona que va peor.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from caresync_comun import reloj
from caresync_comun.registro import evento, registro
from caresync_comun.roble_acceso import CASO_SEGUIMIENTO, AccesoRoble, fila_id

log = registro(__name__)

# Cuánto tiene que bajar la escala entre dos reportes para considerarlo un
# empeoramiento y no la variación normal de cómo alguien se siente un día u otro.
CAIDA_RELEVANTE = int(os.environ.get("CAIDA_RELEVANTE", "3"))
ESCALA_PREOCUPANTE = int(os.environ.get("ESCALA_PREOCUPANTE", "3"))
# Dentro de esta ventana, la misma escala que el último reporte es ese reporte otra
# vez y no uno nuevo. Una hora: nadie reporta dos veces lo mismo tan seguido a
# propósito, y al día siguiente el mismo número sí es un dato.
VENTANA_REPETIDO = timedelta(hours=1)


# ------------------------------------------------------------------- consultar

def consultar_plan(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    caso_id = str(fila_id(caso))

    plan = acceso.plan_del_caso(caso_id)
    indicaciones = acceso.indicaciones_activas(caso_id)
    adherencia = acceso.adherencia_del_caso(caso_id)
    evolucion = acceso.evolucion_del_caso(caso_id)

    por_indicacion: dict[str, list[dict[str, Any]]] = {}
    for fila in adherencia:
        por_indicacion.setdefault(str(fila.get("indicacion_id")), []).append(fila)

    return {
        "tiene_plan": bool(plan),
        "plan": {
            "resumen": (plan or {}).get("resumen"),
            "escrito_por": (plan or {}).get("profesional_nombre"),
            "escrito_el": reloj.humano((plan or {}).get("creado_en")),
        }
        if plan
        else None,
        "indicaciones": [_indicacion(i, por_indicacion) for i in indicaciones],
        "evolucion": [
            {
                "escala": e.get("escala"),
                "nota": e.get("nota"),
                "cuando": reloj.humano(e.get("reportado_en")),
            }
            for e in evolucion[-5:]
        ],
        "ultimo_reporte": reloj.humano(evolucion[-1].get("reportado_en")) if evolucion else None,
        "instruccion": (
            "No preguntes nada que ya esté aquí. Si no hay plan todavía, dile que "
            "el profesional aún no lo ha escrito y no lo suplas tú."
        ),
    }


def _indicacion(
    indicacion: dict[str, Any], por_indicacion: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    indicacion_id = str(fila_id(indicacion))
    reportes = sorted(
        por_indicacion.get(indicacion_id, []), key=lambda r: str(r.get("reportado_en") or "")
    )
    ultimo = reportes[-1] if reportes else None

    return {
        "indicacion_id": indicacion_id,
        "texto": indicacion.get("texto"),
        "frecuencia": indicacion.get("frecuencia"),
        "reportes": len(reportes),
        "ultimo_reporte": reloj.humano(ultimo.get("reportado_en")) if ultimo else None,
        "ultima_cumplida": ultimo.get("cumplida") if ultimo else None,
    }


# -------------------------------------------------------------------- evolución

def registrar_evolucion(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    caso_id = str(fila_id(caso))
    escala = int(argumentos["escala"])
    nota = str(argumentos.get("nota") or "")

    previos = acceso.evolucion_del_caso(caso_id)
    anterior = _escala_de(previos[-1]) if previos else None

    # El mismo número hace un momento es el mismo reporte, no uno nuevo. Pasó en una
    # prueba de punta a punta: la persona dijo «no hice las gárgaras» y el agente, en
    # vez de registrar la adherencia, volvió a registrar el 3 de antes. Quedaron dos
    # filas de evolución y dos alertas de retroceso por una sola caída.
    if previos and anterior == escala:
        cuando = reloj.desde_iso(previos[-1].get("reportado_en"))
        if cuando and reloj.ahora() - cuando < VENTANA_REPETIDO:
            return {
                "ok": True,
                "repetido": True,
                "escala": escala,
                "instruccion": (
                    "Ese reporte ya estaba registrado hace un momento: no se guardó otra "
                    "vez. Si la persona habló de una indicación, eso va con "
                    "registrar_adherencia."
                ),
            }

    acceso.registrar_evolucion(caso_id=caso_id, escala=escala, nota=nota)
    _marcar_en_seguimiento(acceso, caso, caso_id)

    empeoro = anterior is not None and (anterior - escala) >= CAIDA_RELEVANTE
    preocupante = escala <= ESCALA_PREOCUPANTE

    if empeoro or preocupante:
        acceso.registrar_evento(
            caso_id=caso_id,
            tipo="evolucion_desfavorable",
            severidad="alta",
            detalle={"escala": escala, "anterior": anterior, "nota": nota[:400]},
        )
        evento(
            log,
            "evolucion_desfavorable",
            caso_id=caso_id,
            escala=escala,
            anterior=anterior,
        )

    return {
        "ok": True,
        "escala": escala,
        "escala_anterior": anterior,
        "empeoro": empeoro,
        "instruccion": (
            "Revisa si hay una señal de alarma del protocolo y, si la hay, llama a "
            "escalar_urgencia. Si no la hay, no le digas a la persona que va peor: "
            "eso lo valora el profesional, que ya quedó avisado."
        )
        if (empeoro or preocupante)
        else "Agradece el reporte en una frase y no lo interpretes.",
    }


def _escala_de(fila: dict[str, Any]) -> int | None:
    try:
        return int(fila.get("escala"))
    except (TypeError, ValueError):
        return None


def _marcar_en_seguimiento(acceso: AccesoRoble, caso: dict[str, Any], caso_id: str) -> None:
    """El primer reporte mueve el caso a seguimiento.

    Importa porque `agente_por_defecto` deriva de este estado: sin el cambio, la
    persona volvería a caer en el agente de agenda la próxima vez que escriba.
    """
    if caso.get("estado") in (CASO_SEGUIMIENTO, "cerrado", "urgencia_escalada"):
        return
    try:
        acceso.actualizar_caso(caso_id, {"estado": CASO_SEGUIMIENTO})
    except Exception as exc:  # noqa: BLE001 - el reporte ya quedó guardado
        evento(log, "estado_no_actualizado", caso_id=caso_id, detalle=type(exc).__name__)


# ------------------------------------------------------------------ adherencia

def registrar_adherencia(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    caso_id = str(fila_id(caso))
    indicacion_id = str(argumentos["indicacion_id"])
    cumplida = bool(argumentos["cumplida"])
    nota = str(argumentos.get("nota") or "")

    # La indicación tiene que ser de este caso. El identificador se lo dio
    # `consultar_plan`, pero un modelo puede arrastrar uno de otro turno y no se
    # va a escribir adherencia sobre el plan de otra persona.
    activas = {str(fila_id(i)): i for i in acceso.indicaciones_activas(caso_id)}
    indicacion = activas.get(indicacion_id)
    if not indicacion:
        # Se devuelve, no se lanza, y con las indicaciones de verdad: es lo que pasa
        # cuando el modelo arrastra un identificador de un turno anterior —los
        # resultados de herramientas no vuelven en el historial—, y así lo corrige en
        # esta misma vuelta. Lanzado, el modelo leía sólo «No entendí la solicitud»
        # (el `publico` de serie): en una prueba del 14/10 se quedó sin registrar que
        # la persona no había hecho las gárgaras.
        evento(log, "indicacion_no_encontrada", caso_id=caso_id)
        return {
            "error": "Ese identificador no está en el plan activo de este caso.",
            "indicaciones_activas": [
                {"indicacion_id": clave, "texto": fila.get("texto")} for clave, fila in activas.items()
            ],
            "instruccion": (
                "Elige de esta lista la indicación de la que habló la persona y vuelve a "
                "llamar a registrar_adherencia con su indicacion_id, ahora."
            ),
        }

    acceso.registrar_adherencia(
        caso_id=caso_id, indicacion_id=indicacion_id, cumplida=cumplida, nota=nota
    )

    if not cumplida:
        acceso.registrar_evento(
            caso_id=caso_id,
            tipo="indicacion_no_cumplida",
            detalle={"indicacion_id": indicacion_id, "motivo": nota[:400]},
        )

    return {
        "ok": True,
        "indicacion": indicacion.get("texto"),
        "cumplida": cumplida,
        "instruccion": (
            "No insistas ni la regañes. Pregunta qué se lo dificultó, en una frase, "
            "y con eso cierras."
        )
        if not cumplida
        else "Reconócelo en una frase corta y cierra.",
    }
