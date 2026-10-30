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

from caresync_comun import correo, plazos, reloj
from caresync_comun.config import config
from caresync_comun.errores import Conflicto, SolicitudInvalida
from caresync_comun.registro import evento, registro
from caresync_comun.roble_acceso import (
    CASO_ABIERTO,
    CASO_AGENDADO,
    CASO_CANALIZADO,
    CASO_CERRADO,
    CASO_URGENTE,
    AccesoRoble,
    cita_por_delante,
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
            # Lo que piden `cancelar_cita` y `reprogramar_cita` en `cita_actual` cuando
            # hay más de una cita por delante.
            "inicio": reloj.iso_local(c.get("inicio")),
            "centro": c.get("centro"),
            "profesional": c.get("profesional_nombre"),
            "estado": c.get("estado"),
            "ya_paso": not cita_por_delante(c) and c.get("estado") in (None, "", "confirmada"),
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
    # Una duda que el agente ya resolvió con la información de los centros no deja
    # nada pendiente, así que el caso se cierra aquí. Abierto, se quedaba en
    # `canalizado` para siempre —nadie cierra un nivel 4, porque no hay cita ni
    # profesional— y el siguiente problema de esa persona caía en agenda sin triaje.
    resuelta = nivel == 4 and bool(argumentos.get("orientacion_resuelta"))

    # Sin `canalizado_en`: esa columna no existe en `casos` y ROBLE rechaza la
    # actualización entera con un 400 si se envía. Cuándo se canalizó ya está en dos
    # sitios —`actualizado_en`, que pone `actualizar_caso`, y el evento
    # `caso_canalizado` de aquí abajo—, así que no hace falta una tercera.
    acceso.actualizar_caso(
        caso_id,
        {
            "estado": CASO_CERRADO if resuelta else CASO_CANALIZADO,
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
    if resuelta:
        acceso.registrar_evento(
            caso_id=caso_id, tipo="orientacion_entregada", detalle={"centro": centro}
        )
    # `nivel_urgencia` y no `nivel`: `evento()` tiene un parámetro propio llamado
    # `nivel`, que es el nivel de log. Pasarle el del protocolo mandaba la línea con
    # nivel 1 a 4 —por debajo de DEBUG— y el evento `caso_canalizado` desaparecía
    # entero del log: ni la línea, ni el caso, ni el centro. Nada fallaba, así que no
    # se notó hasta que alguien fue a buscar en CloudWatch una canalización que sí
    # había ocurrido.
    evento(log, "caso_canalizado", caso_id=caso_id, centro=centro, nivel_urgencia=nivel)

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

    # Nivel 4 es «sin cita» en el protocolo (E2E-7: orientar sin reservar). Antes
    # pasaba igual al agente de agenda, que se ponía a buscar espacios para una
    # duda de información. Sin traspaso, el de triaje cierra el turno; si después la
    # persona pide una cita, el caso ya está canalizado y la atiende agenda.
    if nivel == 4:
        return {
            "ok": True,
            "centro": centro,
            "nivel_urgencia": nivel,
            "agendar": False,
            "plazo": plazos.texto_de(nivel),
            "cerrado": resuelta,
            "siguiente": _SIGUIENTE_ORIENTACION_RESUELTA
            if resuelta
            else _siguiente_orientacion_registrada(centro),
        }

    return {
        "ok": True,
        "centro": centro,
        "nivel_urgencia": nivel,
        "agendar": True,
        "plazo": plazos.texto_de(nivel),
        "siguiente": (
            "El caso pasa al agente de agenda, que continúa en esta misma "
            "conversación. No te despidas de la persona."
        ),
    }


# El modo simulación del orquestador devuelve estos mismos textos: lo que se evalúa
# ahí es cómo cierra el triaje una duda de información, y con otra instrucción
# cerraría de otra forma. Si cambian aquí, cambian allá.
_SIGUIENTE_ORIENTACION_RESUELTA = (
    "La duda quedó resuelta con la información de los centros y el caso se cerró: no "
    "queda nada pendiente. Si la persona necesita algo más, lo cuenta aquí y se le "
    "atiende desde el principio. No le prometas ningún seguimiento."
)


def _siguiente_orientacion_registrada(centro: str) -> str:
    # Decía «no le prometas cuándo ni cómo le van a responder», que daba a entender
    # que alguien iba a responder. Nadie puede: el centro ve el caso en su panel, pero
    # lo que escribe el personal no le llega a la persona y el correo no sale.
    return (
        f"Es una orientación sin cita que no se resolvió con la información de los "
        f"centros. Dile a la persona que su consulta quedó registrada en el {centro} "
        "con lo que te contó, y que si quiere hablarlo con alguien del centro le buscas "
        "una cita aquí mismo. No le digas que le van a responder por otra vía: el "
        "centro ve el caso, pero no tiene cómo escribirle."
    )


# ----------------------------------------------------------- subir la urgencia

def subir_urgencia(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    """Sube el nivel de un caso que espera su cita, cuando la persona cuenta que empeoró.

    Sólo sube y nunca baja: el protocolo resuelve toda duda hacia lo más urgente, y
    bajar un nivel es justo el error que mide M3. Al nivel 1 tampoco se llega por
    aquí, porque una emergencia no espera una cita: eso es `escalar_urgencia`.

    Antes no había cómo. Agenda podía escalar una urgencia y nada más, así que un
    «ya no puedo apoyar el pie» tres días antes de una cita de nivel 3 dejaba la cita
    donde estaba: un sub-triaje que aparecía después del triaje.
    """
    caso_id = str(fila_id(caso))
    nuevo = int(argumentos["nivel_urgencia"])
    motivo = str(argumentos.get("motivo") or "")[:500]

    if nuevo <= 1:
        raise SolicitudInvalida(
            "subir_urgencia no lleva a nivel 1",
            publico=(
                "Un nivel 1 es una emergencia: no se sube con esta herramienta, se "
                "escala con escalar_urgencia."
            ),
        )
    if caso.get("estado") not in (CASO_CANALIZADO, CASO_AGENDADO):
        raise Conflicto(
            "Sólo se sube la urgencia de un caso que espera su cita",
            publico=(
                "La urgencia sólo se sube en un caso canalizado que todavía espera su "
                "cita. Si hay una señal de alarma, usa escalar_urgencia."
            ),
        )

    anterior = plazos.nivel_de(caso)
    if anterior and nuevo >= anterior:
        return {
            "ok": True,
            "sin_cambio": True,
            "nivel_urgencia": anterior,
            "instruccion": (
                "El caso ya tiene ese nivel o uno más urgente, así que no cambia: la "
                "urgencia sólo sube. Sigue con lo que la persona necesita."
            ),
        }

    acceso.actualizar_caso(caso_id, {"nivel_urgencia": nuevo})
    acceso.registrar_evento(
        caso_id=caso_id,
        tipo="urgencia_subida",
        severidad="alta" if nuevo == 2 else "info",
        detalle={"anterior": anterior, "nuevo": nuevo, "motivo": motivo},
    )
    # `nivel_urgencia`, nunca `nivel`: ver la nota de `caso_canalizado` más arriba.
    evento(log, "urgencia_subida", caso_id=caso_id, anterior=anterior, nivel_urgencia=nuevo)

    limite = reloj.ahora() + (plazos.plazo_de(nuevo) or plazos.PLAZOS[3])
    proximas = sorted(
        (c for c in acceso.citas_del_caso(caso_id) if cita_por_delante(c)),
        key=lambda c: str(c.get("inicio") or ""),
    )
    tarde = bool(proximas) and (reloj.desde_iso(proximas[0].get("inicio")) or limite) > limite

    return {
        "ok": True,
        "nivel_urgencia": nuevo,
        "plazo": plazos.texto_de(nuevo),
        "cita_fuera_de_plazo": tarde,
        "instruccion": (
            f"Su cita del {reloj.humano(proximas[0].get('inicio'))} queda después del "
            f"nuevo plazo ({plazos.texto_de(nuevo)}). Ofrécele adelantarla: consulta la "
            "disponibilidad y, si elige otra, usa reprogramar_cita."
            if tarde
            else (
                "Sigue con la cita: con el nuevo nivel, consulta la disponibilidad y "
                "ofrécele un espacio dentro del plazo."
                if not proximas
                else "Su cita ya está dentro del nuevo plazo. Díselo y no la muevas."
            )
        ),
    }


# --------------------------------------------------------------- nuevo motivo

def nuevo_motivo(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    """Abre un caso aparte para un problema distinto del que lleva este caso.

    Una persona tenía un solo caso vivo, y un problema nuevo caía en el agente del caso
    viejo: un dolor de rodilla de alguien en seguimiento por ansiedad lo atendía
    Seguimiento, que no puede canalizar, y si el caso estaba canalizado Agenda le
    buscaba cita en el centro del caso viejo con el resumen viejo. Ahora el caso viejo
    sigue su curso y lo nuevo empieza su propio triaje; el orquestador hace el traspaso
    y cambia de caso en el mismo turno.

    Abre el caso con el token de la persona, como cuando escribe por primera vez, así
    que no hay forma de abrírselo a otra.
    """
    if caso.get("estado") in (None, "", CASO_ABIERTO):
        raise Conflicto(
            "El caso todavía está en triaje",
            publico=(
                "Este caso todavía está en triaje: lo nuevo se cuenta aquí mismo y el "
                "triaje lo tiene en cuenta."
            ),
        )

    motivo = str(argumentos.get("motivo") or "").strip()[:500]
    if not motivo:
        raise SolicitudInvalida("nuevo_motivo sin motivo")

    caso_id = str(fila_id(caso))
    nuevo = acceso.abrir_caso(motivo=motivo)
    nuevo_id = str(fila_id(nuevo))
    acceso.registrar_evento(
        caso_id=caso_id, tipo="nuevo_motivo", detalle={"caso_nuevo": nuevo_id, "motivo": motivo}
    )

    return {
        "ok": True,
        "caso_nuevo": nuevo_id,
        "siguiente": (
            "Lo nuevo sigue en un caso aparte, con su propio triaje, y este caso sigue "
            "igual. El agente de triaje continúa en esta misma conversación: dile en una "
            "frase que lo van a ver por separado y no le hagas tú las preguntas."
        ),
    }

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
