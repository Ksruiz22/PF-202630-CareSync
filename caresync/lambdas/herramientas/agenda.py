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
DIAS_ALTERNATIVAS = 30

# La ventana en la que se busca el espacio que pide el modelo es la misma en la
# que se ofrecen alternativas, y la misma cota que el catálogo admite en
# `dias_adelante`: así no se puede ofrecer un espacio que después no se encuentre.
VENTANA_MAXIMA_DIAS = DIAS_ALTERNATIVAS
MAX_CANDIDATOS = 200

# Tope de la lectura con la que se cuentan los cupos libres por profesional. No es
# una página que se pueda pedir de nuevo: es cuántos se cuentan como máximo, y el
# número va en la respuesta para que el agente no diga «tiene 300» cuando lo que
# sabe es «al menos 300».
MAX_CUPOS_CONTADOS = 300

# 0 = lunes … 6 = domingo, la convención de la columna `dia_semana`.
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

# --------------------------------------------------------------- disponibilidad

def consultar_disponibilidad(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    centro = _centro(acceso, caso)
    # El `maximum` del esquema es una indicación para el modelo, no una validación:
    # se recorta aquí para no ofrecer un espacio que después `_coincidencias` no
    # alcanzaría a encontrar.
    dias = max(1, min(int(argumentos.get("dias_adelante") or 7), VENTANA_MAXIMA_DIAS))

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
            "Cuando la persona elija, llama a agendar_cita con el «inicio» de esa "
            "opción, copiado tal cual. Si ya no lo tienes delante, vuelve a llamar "
            "a esta herramienta: no reconstruyas la fecha de memoria."
        )
        if cupos
        else (
            "No hay espacios en esa ventana. Amplía los días una vez; si sigue "
            "vacío, dilo con claridad: el caso queda registrado y el centro lo ve "
            "en su panel, así que puede volver a intentarlo más tarde. No inventes "
            "un espacio y no prometas que alguien la va a contactar."
        ),
    }


def _opcion(acceso: AccesoRoble, cupo: dict[str, Any]) -> dict[str, Any]:
    return {
        # `inicio` y no el `_id` de la fila: el identificador sólo vive dentro de
        # esta vuelta, la hora sobrevive en la conversación. Ver `_coincidencias`.
        "inicio": reloj.iso_local(cupo.get("inicio")),
        "cuando": reloj.humano(cupo.get("inicio")),
        "profesional": _nombre_del_profesional(acceso, cupo),
        "modalidad": cupo.get("modalidad") or "presencial",
    }


def _centro(acceso: AccesoRoble, caso: dict[str, Any]) -> str:
    """Sobre qué centro se mira la agenda.

    El del caso cuando hay caso. Cuando no lo hay —el personal de un centro
    preguntando por su propia agenda— el del actor, que sale de su perfil en ROBLE
    y no de nada que haya dicho el modelo: así una consulta general no puede
    terminar leyendo los cupos del otro centro.
    """
    centro = caso.get("centro") or (acceso.actor.centro if not acceso.actor.es_paciente else "")
    if not centro:
        raise SolicitudInvalida(
            "El caso todavía no tiene centro asignado: hay que canalizarlo antes de agendar",
            publico=(
                "Este caso todavía no está canalizado a un centro, así que no se puede "
                "agendar. Completa el triaje primero."
            ),
        )
    return str(centro)


def _centro_del_caso(caso: dict[str, Any]) -> str:
    """El centro del caso, y sólo el del caso.

    Lo usan `agendar_cita` y `notificar_profesional`: ahí el centro del actor no
    vale como respaldo, porque lo que se va a escribir cuelga del caso.
    """
    centro = caso.get("centro")
    if not centro:
        raise SolicitudInvalida(
            "El caso todavía no tiene centro asignado: hay que canalizarlo antes de agendar",
            publico=(
                "Este caso todavía no está canalizado a un centro, así que no se puede "
                "agendar. Completa el triaje primero."
            ),
        )
    return str(centro)


# ------------------------------------------------------------- profesionales

def consultar_profesionales(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    """Quién atiende en el centro, con qué horario y cuánto le queda libre.

    Existe porque el personal del centro preguntaba esto y el agente no tenía de
    dónde sacarlo: sin herramienta, lo único correcto que podía hacer era decir que
    no lo sabe —y lo incorrecto, inventárselo—.

    Los cupos libres se cuentan a partir de una sola lectura del centro y no una
    por profesional: la cuota de ROBLE es de 100 operaciones por minuto y por IP, y
    los horarios ya gastan una lectura por profesional.
    """
    centro = _centro(acceso, caso)
    dias = max(1, min(int(argumentos.get("dias_adelante") or 7), VENTANA_MAXIMA_DIAS))

    cupos = acceso.cupos_libres(
        centro=centro, hasta=reloj.mas(dias=dias), maximo=MAX_CUPOS_CONTADOS
    )
    libres_por_profesional: dict[str, int] = {}
    for cupo in cupos:
        clave = str(cupo.get("profesional_id") or "")
        libres_por_profesional[clave] = libres_por_profesional.get(clave, 0) + 1

    profesionales = acceso.profesionales_de(centro)
    fichas = [
        {
            "nombre": str(p.get("nombre") or ""),
            "especialidad": str(p.get("especialidad") or "sin especialidad registrada"),
            "atiende": _horario_legible(acceso, fila_id(p)),
            "espacios_libres": libres_por_profesional.get(str(fila_id(p) or ""), 0),
        }
        for p in profesionales
    ]

    salida: dict[str, Any] = {
        "centro": centro,
        "ventana_dias": dias,
        "profesionales": fichas,
        "instruccion": (
            "Responde en prosa corta sólo lo que te preguntaron: no recites los cuatro "
            "campos de cada profesional. «espacios_libres» son cupos publicados y sin "
            "reservar en esa ventana; un cero no dice que el profesional no atienda, "
            "dice que no hay cupos publicados, y esos los publica el centro desde su "
            "panel."
        )
        if fichas
        else (
            "Este centro no tiene profesionales activos registrados. Dilo tal cual: no "
            "es un fallo del sistema, es que faltan por dar de alta."
        ),
    }

    if len(cupos) >= MAX_CUPOS_CONTADOS:
        # El conteo se quedó en el tope, así que los números son un mínimo. Decirlo
        # es la diferencia entre «tiene 300 libres» y «tiene al menos 300».
        salida["conteo_recortado_en"] = MAX_CUPOS_CONTADOS

    return salida


def _horario_legible(acceso: AccesoRoble, profesional_id: str | None) -> str:
    """Los horarios de un profesional en una frase, agrupando días de igual horario.

    Se agrupa porque lo normal es «lunes a viernes de 8:00 a 12:00» y enumerar cinco
    veces el mismo rango hace que el agente lo lea en voz alta entero.
    """
    if not profesional_id:
        return "sin horario registrado"

    por_rango: dict[tuple[str, str], list[int]] = {}
    for horario in acceso.horarios_de(profesional_id):
        if not _activo(horario):
            continue
        dia = horario.get("dia_semana")
        if dia is None:
            continue
        rango = (str(horario.get("hora_inicio") or ""), str(horario.get("hora_fin") or ""))
        por_rango.setdefault(rango, []).append(int(dia) % 7)

    if not por_rango:
        return "sin horario registrado"

    partes = [
        f"{_dias_legibles(sorted(set(dias)))} de {desde} a {hasta}"
        for (desde, hasta), dias in sorted(por_rango.items(), key=lambda par: par[0])
    ]
    return "; ".join(partes)


def _dias_legibles(dias: list[int]) -> str:
    nombres = [DIAS[d] for d in dias if 0 <= d < len(DIAS)]
    if not nombres:
        return "sin días registrados"
    # Un tramo corrido se dice como tramo. `dias` viene ordenado y sin repetidos.
    if len(nombres) > 2 and dias[-1] - dias[0] == len(dias) - 1:
        return f"{nombres[0]} a {nombres[-1]}"
    if len(nombres) == 1:
        return nombres[0]
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _activo(horario: dict[str, Any]) -> bool:
    """ROBLE devuelve los booleanos de cuatro formas, y `None` en las filas viejas."""
    return horario.get("activo") in (True, "true", "t", 1, "1", None)


# --------------------------------------------------------- resolver el espacio

def _coincidencias(
    acceso: AccesoRoble, *, centro: str, argumentos: dict[str, Any]
) -> list[dict[str, Any]]:
    """Los cupos libres que encajan con lo que el modelo pidió, por hora de inicio.

    Por qué la hora y no un identificador: el `_id` del cupo sólo existe dentro
    de la vuelta en que se pidió la disponibilidad. Al modelo se le da como
    historial la conversación con la persona, sin resultados de herramientas
    (ver `_historial` en el orquestador), así que cuando alguien contesta «sí, la
    de las nueve» en la petición siguiente el identificador no está en ninguna
    parte —y el modelo, obligado a rellenar el argumento, se lo inventaba: un
    texto que no es un uuid hacía fallar a PostgreSQL y la persona acababa
    oyendo que la base de datos no responde. La hora sí sobrevive, porque es
    exactamente lo que el agente le dijo.

    Es el patrón de `registrar_adherencia`: resolver lo que dice el modelo contra
    una lectura fresca y, si no cuadra, devolverle las opciones de verdad.
    """
    momento = reloj.desde_local(argumentos.get("inicio"))
    if not momento:
        raise SolicitudInvalida(
            f"«inicio» no es una fecha reconocible: {argumentos.get('inicio')!r}",
            publico=(
                "No reconozco esa fecha y hora. Vuelve a llamar a "
                "consultar_disponibilidad y copia el campo «inicio» de la opción que "
                "eligió la persona, sin cambiarlo."
            ),
        )

    buscado = momento.replace(second=0, microsecond=0)
    libres = acceso.cupos_libres(
        centro=centro, hasta=reloj.mas(dias=VENTANA_MAXIMA_DIAS), maximo=MAX_CANDIDATOS
    )
    mismos = [
        cupo
        for cupo in libres
        if (inicio := reloj.desde_iso(cupo.get("inicio")))
        and inicio.replace(second=0, microsecond=0) == buscado
    ]

    # Un mismo horario puede tener cupo con dos profesionales distintos. Si la
    # persona ya eligió, el nombre desempata; si no, se le pregunta.
    nombre = str(argumentos.get("profesional") or "").strip().casefold()
    if len(mismos) > 1 and nombre:
        filtrados = [c for c in mismos if nombre in _nombre_del_profesional(acceso, c).casefold()]
        if filtrados:
            return filtrados
    return mismos


def _hay_que_reconsultar(
    acceso: AccesoRoble, *, centro: str, coincidencias: list[dict[str, Any]]
) -> dict[str, Any]:
    """Lo que se le devuelve al modelo cuando la hora pedida no resuelve a un cupo.

    Va como resultado y no como excepción por lo mismo que el conflicto de
    reserva: así el modelo tiene las opciones reales en la misma vuelta y puede
    seguir la conversación en vez de disculparse.
    """
    if len(coincidencias) > 1:
        return {
            "error": "Hay más de un espacio libre a esa hora.",
            "motivo": "varios_profesionales",
            "opciones": [_opcion(acceso, c) for c in coincidencias],
            "instruccion": (
                "Pregúntale a la persona con cuál profesional prefiere, y vuelve a "
                "llamar a agendar_cita con el mismo «inicio» y el nombre elegido."
            ),
        }

    alternativas = acceso.cupos_libres(
        centro=centro, hasta=reloj.mas(dias=DIAS_ALTERNATIVAS), maximo=3
    )
    return {
        "error": "Ese espacio ya no está libre en la agenda.",
        "motivo": "espacio_no_encontrado",
        "alternativas": [_opcion(acceso, c) for c in alternativas],
        "instruccion": (
            "Ofrécele las alternativas con el texto de «cuando» y agenda con el "
            "«inicio» de la que elija."
            if alternativas
            else (
                "No queda ningún espacio libre en el centro. Dilo con claridad, sin "
                "prometer que alguien la contactará, y ofrécele volver a intentarlo."
            )
        ),
    }


def _nombre_del_profesional(acceso: AccesoRoble, cupo: dict[str, Any]) -> str:
    try:
        return str(acceso.profesional(str(cupo.get("profesional_id"))).get("nombre") or "")
    except NoEncontrado:
        # Un cupo huérfano no debería existir, pero si existe es mejor ofrecerlo
        # sin nombre que ocultar el único espacio libre de la semana.
        evento(log, "cupo_sin_profesional", cupo_id=fila_id(cupo))
        return ""


# -------------------------------------------------------------------- agendar

def agendar_cita(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    caso_id = str(fila_id(caso))
    centro = _centro_del_caso(caso)

    if str(caso.get("nivel_urgencia") or "") == "1":
        raise Conflicto(
            "Este caso es una emergencia: no se agenda una cita, se sigue la ruta de urgencias",
            publico=(
                "Este caso está marcado como emergencia: no se agenda una cita, se sigue "
                "la ruta de urgencias del campus."
            ),
        )

    vigentes = [
        c for c in acceso.citas_del_caso(caso_id) if c.get("estado") != "cancelada"
    ]
    if vigentes:
        raise Conflicto(
            "Este caso ya tiene una cita confirmada",
            publico=(
                "Este caso ya tiene una cita confirmada. Si la persona quiere cambiarla, "
                "el personal del centro es quien la reprograma."
            ),
        )

    # La búsqueda ya es por centro, así que un espacio de otro centro no puede
    # colarse: no hay identificador ajeno que arrastrar.
    coincidencias = _coincidencias(acceso, centro=centro, argumentos=argumentos)
    if len(coincidencias) != 1:
        return _hay_que_reconsultar(acceso, centro=centro, coincidencias=coincidencias)

    cupo = coincidencias[0]
    cupo_id = str(fila_id(cupo))

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
                for c in acceso.cupos_libres(
                    centro=centro, hasta=reloj.mas(dias=DIAS_ALTERNATIVAS), maximo=3
                )
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
        raise SolicitudInvalida(
            "Todavía no hay cita: agenda primero y después notifica",
            publico="Este caso todavía no tiene cita. Agéndala antes de notificar.",
        )
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
            f"El profesional {ficha.get('nombre')} no tiene correo registrado en ROBLE",
            publico=(
                "No pude avisar al profesional porque no tiene correo registrado. La cita "
                "sigue agendada; dilo así, sin prometer otro aviso."
            ),
        )
    return destino
