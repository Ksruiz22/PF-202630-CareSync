"""Herramientas del triaje: mirar el caso, canalizarlo y escalar una urgencia.

`escalar_urgencia` es la operación más importante del sistema y la que menos se
puede permitir fallar en silencio. Por eso hace cuatro cosas y ninguna depende de
que la anterior haya salido bien:

1. Marca el caso, para que cualquier vista que lo abra lo vea escalado.
2. Escribe el evento en la bitácora de ROBLE, que es lo que ve el profesional.
3. Emite el evento `ESCALAMIENTO` en el log, del que cuelga una alarma de
   CloudWatch: es el único camino por el que un humano se entera en minutos.
4. Avisa por correo a la cuenta de emergencias, si SES está listo.

El texto que la persona recibe se devuelve siempre, incluso si los cuatro pasos
fallan: es lo único que de verdad no puede faltar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from caresync_comun import correo, reloj
from caresync_comun.config import config
from caresync_comun.errores import Conflicto
from caresync_comun.registro import evento, registro
from caresync_comun.roble_acceso import (
    CASO_CANALIZADO,
    CASO_URGENTE,
    AccesoRoble,
    fila_id,
)

log = registro(__name__)

_RESPALDO = (
    "Esto necesita atención ahora, no una cita. Llama a la línea de emergencias "
    "del campus o al 123. Si puedes, no te quedes solo."
)


def _ruta_emergencia() -> str:
    """El texto exacto que se le dice a la persona.

    Vive en `protocolos/ruta-emergencia.md`, que es su única copia en todo el
    repositorio; el script de construcción lo copia dentro de este paquete. Se
    lee del archivo y no se escribe aquí para que quien revise el protocolo
    —personal clínico, no el equipo de desarrollo— pueda cambiar la redacción sin
    tocar código.
    """
    try:
        texto = (Path(__file__).parent / "protocolos" / "ruta-emergencia.md").read_text(
            encoding="utf-8"
        )
    except OSError:
        return _RESPALDO
    return texto.strip() or _RESPALDO


RUTA_EMERGENCIA = _ruta_emergencia()


# ------------------------------------------------------------------- consultas

def consultar_estado_caso(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    """Todo lo que el sistema ya sabe del caso, para no volver a preguntarlo."""
    caso_id = str(fila_id(caso))

    citas = [
        {
            "cuando": reloj.humano(c.get("inicio")),
            "centro": c.get("centro"),
            "profesional": c.get("profesional_nombre"),
            "estado": c.get("estado"),
        }
        for c in acceso.citas_del_caso(caso_id)
    ]
    plan = acceso.plan_del_caso(caso_id)

    return {
        "estado": caso.get("estado"),
        "centro": caso.get("centro"),
        "nivel_urgencia": caso.get("nivel_urgencia"),
        "motivo": caso.get("motivo"),
        "resumen_triaje": caso.get("resumen_triaje"),
        "abierto_desde": reloj.humano(caso.get("creado_en")),
        "citas": citas,
        "tiene_plan": bool(plan),
        "indicaciones_activas": len(acceso.indicaciones_activas(caso_id)),
    }


# ------------------------------------------------------------------ canalizar

def canalizar_caso(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    """Cierra el triaje. Es la herramienta que dispara el traspaso a agenda."""
    caso_id = str(fila_id(caso))

    if caso.get("estado") not in (None, "", "abierto", CASO_URGENTE):
        # Volver a canalizar un caso ya canalizado le cambiaría el centro a
        # alguien que quizá ya tiene cita. Se le dice al modelo y sigue.
        raise Conflicto(
            f"Este caso ya está canalizado al {caso.get('centro')}. "
            "Continúa con lo que la persona necesita ahora."
        )

    centro = argumentos["centro"]
    nivel = int(argumentos["nivel_urgencia"])
    resumen = str(argumentos["resumen"])[:2000]

    # Sin `canalizado_en`: esa columna no existe en `casos` y ROBLE rechaza la
    # actualización entera con un 400 si se envía. Cuándo se canalizó ya está en dos
    # sitios —`actualizado_en`, que pone `actualizar_caso`, y el evento
    # `caso_canalizado` de aquí abajo—, así que no hace falta una tercera.
    acceso.actualizar_caso(
        caso_id,
        {
            "estado": CASO_CANALIZADO,
            "centro": centro,
            "nivel_urgencia": nivel,
            "resumen_triaje": resumen,
        },
    )
    acceso.registrar_evento(
        caso_id=caso_id,
        tipo="caso_canalizado",
        severidad="alta" if nivel <= 2 else "info",
        detalle={"centro": centro, "nivel_urgencia": nivel, "resumen": resumen},
    )
    evento(log, "caso_canalizado", caso_id=caso_id, centro=centro, nivel=nivel)

    # Nivel 1 es una emergencia por definición del protocolo: canalizarla sin
    # escalar dejaría a la persona esperando una cita.
    if nivel == 1:
        emergencia = escalar_urgencia(
            acceso, {**caso, "centro": centro}, {"motivo": "Nivel 1 asignado en la canalización"}
        )
        return {
            "ok": True,
            "centro": centro,
            "nivel_urgencia": nivel,
            "agendar": False,
            "decir_a_la_persona": emergencia["decir_a_la_persona"],
        }

    return {
        "ok": True,
        "centro": centro,
        "nivel_urgencia": nivel,
        "agendar": True,
        "plazo": _plazo(nivel),
        "siguiente": (
            "El caso pasa al agente de agenda, que continúa en esta misma "
            "conversación. No te despidas de la persona."
        ),
    }


def _plazo(nivel: int) -> str:
    return {1: "ahora", 2: "72 horas", 3: "7 días", 4: "sin cita"}.get(nivel, "7 días")


# --------------------------------------------------------------------- escalar

def escalar_urgencia(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    """Activa la ruta de emergencia. Nunca lanza excepción."""
    caso_id = str(fila_id(caso))
    motivo = str(argumentos.get("motivo") or "sin motivo declarado")[:500]

    # `ESCALAMIENTO` en mayúsculas y sin más: es el literal que busca el filtro
    # de métrica de CloudWatch del que cuelga la alarma. Renombrarlo la deja
    # muda sin que nada falle.
    evento(
        log,
        "ESCALAMIENTO",
        caso_id=caso_id,
        centro=caso.get("centro"),
        rol=acceso.actor.rol,
        motivo=motivo,
    )

    fallos: list[str] = []

    try:
        # Tampoco `escalado_en`: no es columna de `casos`. Aquí dolía más que en
        # `canalizar_caso`, porque este `except` se traga el 400 en `fallos` y la
        # ruta de emergencia se entregaba igual: el caso se quedaba sin marcar
        # urgente y nadie lo veía. El instante está en el evento `urgencia_escalada`.
        acceso.actualizar_caso(caso_id, {"estado": CASO_URGENTE, "nivel_urgencia": 1})
    except Exception as exc:  # noqa: BLE001 - la ruta se entrega igual
        fallos.append(f"caso: {type(exc).__name__}")

    try:
        acceso.registrar_evento(
            caso_id=caso_id,
            tipo="urgencia_escalada",
            severidad="critica",
            detalle={"motivo": motivo, "centro": caso.get("centro")},
        )
    except Exception as exc:  # noqa: BLE001
        fallos.append(f"bitacora: {type(exc).__name__}")

    avisado = False
    try:
        avisado = _avisar_emergencias(caso, caso_id=caso_id, motivo=motivo)
    except Exception as exc:  # noqa: BLE001
        fallos.append(f"correo: {type(exc).__name__}")

    if fallos:
        evento(log, "escalamiento_parcial", caso_id=caso_id, fallos=fallos)

    return {
        "ok": True,
        "decir_a_la_persona": RUTA_EMERGENCIA,
        "avisado_el_equipo": avisado,
        "agendar": False,
        "instruccion": (
            "Di ese texto tal cual, antes de cualquier otra cosa. No agendes ni "
            "sigas preguntando por síntomas. Después acompaña a la persona."
        ),
    }


def _avisar_emergencias(caso: dict[str, Any], *, caso_id: str, motivo: str) -> bool:
    ajustes = config()
    if not ajustes.correo_emergencias:
        return False

    cuerpo = "\n".join(
        [
            "Se activó la ruta de emergencia de CareSync.",
            "",
            f"Caso: {caso_id}",
            f"Persona: {caso.get('paciente_nombre')} <{caso.get('paciente_email')}>",
            f"Centro: {caso.get('centro') or 'sin asignar'}",
            f"Detectado: {reloj.humano(reloj.ahora())} (hora de Bogotá)",
            f"Motivo: {motivo}",
            "",
            "Entra a CareSync para ver la conversación completa. Este correo no la "
            "incluye a propósito.",
        ]
    )
    return correo.enviar(
        para=ajustes.correo_emergencias,
        asunto=f"[CareSync] Urgencia escalada · caso {caso_id}",
        cuerpo=cuerpo,
    )
