"""Herramientas de agenda: ver espacios, tomar uno y avisar al profesional.

Aquí vive la única concurrencia real del prototipo. Dos personas pueden pedir el
mismo espacio en el mismo segundo, y ROBLE no tiene escritura condicional con la
que impedirlo. El patrón está en `roble_acceso.reservar_cupo`; lo que este módulo
añade es lo que la persona percibe: **quien pierde la carrera no ve un error, ve
las siguientes tres opciones libres**. Sin eso, un conflicto de reserva sería un
callejón sin salida en medio de una conversación.
"""

from __future__ import annotations

import os
from typing import Any

from caresync_comun import correo, reloj
from caresync_comun.errores import Conflicto, NoEncontrado, SolicitudInvalida
from caresync_comun.registro import evento, registro
from caresync_comun.roble_acceso import AccesoRoble, fila_id

log = registro(__name__)

MINUTOS_RESERVA = int(os.environ.get("MINUTOS_RESERVA", "2"))
MAX_OPCIONES = 6


# --------------------------------------------------------------- disponibilidad

def consultar_disponibilidad(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    centro = _centro_del_caso(caso)
    dias = int(argumentos.get("dias_adelante") or 7)

    # Barrido oportunista: un cupo que quedó reservado y sin confirmar no
    # aparecería como libre, así que se recupera antes de listar. La función de
    # recordatorios hace lo mismo cada 15 minutos; hacerlo también aquí es lo que
    # evita que un espacio se pierda justo cuando alguien lo está buscando.
    try:
        acceso.liberar_reservas_vencidas(minutos=MINUTOS_RESERVA)
    except Exception as exc:  # noqa: BLE001 - listar es lo importante
        evento(log, "barrido_omitido", detalle=type(exc).__name__)

    cupos = acceso.cupos_libres(
        centro=centro, hasta=reloj.mas(dias=dias), maximo=MAX_OPCIONES
    )

    return {
        "centro": centro,
        "ventana_dias": dias,
        "opciones": [_opcion(acceso, cupo) for cupo in cupos],
        "instruccion": (
            "Ofrece dos o tres opciones como máximo, con el texto de «cuando». "
            "Nunca le muestres a la persona el cupo_id."
        )
        if cupos
        else (
            "No hay espacios en esa ventana. Amplía los días una vez; si sigue "
            "vacío, dilo con claridad y explica que el personal del centro la "
            "contactará. No inventes un espacio."
        ),
    }


def _opcion(acceso: AccesoRoble, cupo: dict[str, Any]) -> dict[str, Any]:
    profesional = ""
    try:
        profesional = str(acceso.profesional(str(cupo.get("profesional_id"))).get("nombre") or "")
    except NoEncontrado:
        # Un cupo huérfano no debería existir, pero si existe es mejor ofrecerlo
        # sin nombre que ocultar el único espacio libre de la semana.
        evento(log, "cupo_sin_profesional", cupo_id=fila_id(cupo))

    return {
        "cupo_id": fila_id(cupo),
        "cuando": reloj.humano(cupo.get("inicio")),
        "profesional": profesional,
        "modalidad": cupo.get("modalidad") or "presencial",
    }


def _centro_del_caso(caso: dict[str, Any]) -> str:
    centro = caso.get("centro")
    if not centro:
        raise SolicitudInvalida(
            "El caso todavía no tiene centro asignado: hay que canalizarlo antes de agendar"
        )
    return str(centro)


# -------------------------------------------------------------------- agendar

def agendar_cita(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    caso_id = str(fila_id(caso))
    centro = _centro_del_caso(caso)
    cupo_id = str(argumentos["cupo_id"])

    if str(caso.get("nivel_urgencia") or "") == "1":
        raise Conflicto(
            "Este caso es una emergencia: no se agenda una cita, se sigue la ruta de urgencias"
        )

    if acceso.citas_del_caso(caso_id):
        raise Conflicto(
            "Este caso ya tiene una cita confirmada. Si la persona quiere cambiarla, "
            "el personal del centro es quien la reprograma."
        )

    cupo = acceso.cupo(cupo_id)
    if cupo.get("centro") != centro:
        # El modelo pudo tomar un identificador de una vuelta anterior, de otro
        # centro. Es un caso real y no vale reservarlo para descubrirlo después.
        raise SolicitudInvalida(
            f"Ese espacio no pertenece al {centro}. Vuelve a consultar la disponibilidad."
        )

    try:
        acceso.reservar_cupo(cupo_id=cupo_id, caso_id=caso_id)
    except Conflicto as exc:
        # Perder la carrera no es un error para la persona: es «ese ya lo
        # tomaron, mira estos». Se devuelve como resultado y no como excepción
        # para que el modelo tenga las alternativas en la misma vuelta.
        evento(log, "reserva_en_conflicto", caso_id=caso_id, cupo_id=cupo_id)
        return {
            "error": exc.publico,
            "motivo": "espacio_tomado",
            "alternativas": [
                _opcion(acceso, c)
                for c in acceso.cupos_libres(centro=centro, hasta=reloj.mas(dias=7), maximo=3)
            ],
            "instruccion": "Ofrece las alternativas. No vuelvas a intentar el mismo espacio.",
        }

    try:
        cita = acceso.confirmar_cita(cupo_id=cupo_id, caso_id=caso_id)
    except Exception:
        # Si la confirmación falla, el cupo queda reservado y bloqueado. Se
        # libera aquí en lugar de esperar el barrido de los 15 minutos.
        try:
            acceso.liberar_cupo(cupo_id)
        except Exception:  # noqa: BLE001
            evento(log, "cupo_no_liberado", cupo_id=cupo_id)
        raise

    cuando = reloj.humano(cita.get("inicio"))
    acceso.registrar_evento(
        caso_id=caso_id,
        tipo="cita_agendada",
        detalle={
            "cita_id": fila_id(cita),
            "centro": centro,
            "inicio": cita.get("inicio"),
            "profesional": cita.get("profesional_nombre"),
        },
    )
    _avisar_a_la_persona(caso, cita=cita, cuando=cuando)

    return {
        "ok": True,
        "cuando": cuando,
        "centro": centro,
        "profesional": cita.get("profesional_nombre"),
        "modalidad": cupo.get("modalidad") or "presencial",
        "siguiente": (
            "Confirma a la persona el día, la hora y el centro, y llama a "
            "notificar_profesional una sola vez."
        ),
    }


def _avisar_a_la_persona(caso: dict[str, Any], *, cita: dict[str, Any], cuando: str) -> bool:
    destino = str(caso.get("paciente_email") or "")
    cuerpo = "\n".join(
        [
            f"Hola {caso.get('paciente_nombre') or ''}".strip() + ",",
            "",
            "Tu cita quedó agendada:",
            f"  Cuándo: {cuando} (hora de Bogotá)",
            f"  Dónde: {cita.get('centro')}",
            f"  Con: {cita.get('profesional_nombre') or 'el profesional asignado'}",
            "",
            "Si no puedes asistir, entra a CareSync y avísanos.",
        ]
    )
    return correo.enviar(para=destino, asunto="[CareSync] Tu cita quedó agendada", cuerpo=cuerpo)


# ----------------------------------------------------------------- notificar

def notificar_profesional(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    """Manda al profesional el resumen del triaje, no la conversación.

    La conversación se queda en ROBLE, donde los permisos por rol sí se aplican.
    Un correo se reenvía, se imprime y termina en una bandeja compartida; el
    resumen del triaje es lo mínimo que el profesional necesita para llegar con
    contexto.
    """
    caso_id = str(fila_id(caso))

    citas = sorted(acceso.citas_del_caso(caso_id), key=lambda c: str(c.get("inicio") or ""))
    if not citas:
        raise SolicitudInvalida("Todavía no hay cita: agenda primero y después notifica")
    cita = citas[-1]

    if _ya_notificada(acceso, caso_id, cita):
        return {
            "ok": True,
            "repetido": True,
            "instruccion": "Ya estaba avisado. No se lo digas a la persona, sigue con la conversación.",
        }

    destino = _correo_del_profesional(acceso, cita)
    cuando = reloj.humano(cita.get("inicio"))
    enviado = correo.enviar(
        para=destino,
        asunto=f"[CareSync] Caso asignado · {cuando}",
        cuerpo="\n".join(
            [
                f"Tienes una cita asignada el {cuando} (hora de Bogotá) en {cita.get('centro')}.",
                "",
                f"Persona: {caso.get('paciente_nombre')}",
                f"Nivel de urgencia asignado en triaje: {caso.get('nivel_urgencia')}",
                "",
                "Resumen del triaje:",
                str(caso.get("resumen_triaje") or caso.get("motivo") or "sin resumen"),
                "",
                "El triaje lo hizo un agente automático siguiendo un protocolo sin "
                "validación clínica. Verifícalo en la consulta.",
                "",
                f"Caso en CareSync: {caso_id}",
            ]
        ),
    )

    acceso.registrar_evento(
        caso_id=caso_id,
        tipo="profesional_notificado",
        detalle={"para": destino, "enviado": enviado, "cita_id": fila_id(cita)},
    )

    return {
        "ok": True,
        "enviado": enviado,
        "profesional": cita.get("profesional_nombre"),
        "instruccion": (
            "Dile a la persona que el profesional ya tiene su información."
            if enviado
            else "El correo no salió. Dile que el centro la contactará y no prometas un aviso."
        ),
    }


def _ya_notificada(acceso: AccesoRoble, caso_id: str, cita: dict[str, Any]) -> bool:
    """Evita el segundo correo si el modelo llama dos veces a la herramienta."""
    cita_id = fila_id(cita)
    return any(
        e.get("tipo") == "profesional_notificado"
        and (e.get("detalle") or {}).get("cita_id") == cita_id
        for e in acceso.eventos_del_caso(caso_id)
    )


def _correo_del_profesional(acceso: AccesoRoble, cita: dict[str, Any]) -> str:
    ficha = acceso.profesional(str(cita.get("profesional_id")))
    destino = str(ficha.get("email") or "")
    if not destino:
        raise NoEncontrado(
            f"El profesional {ficha.get('nombre')} no tiene correo registrado en ROBLE"
        )
    return destino
