"""Herramientas de agenda: ver espacios, tomar uno, cambiarlo o soltarlo, y avisar.

Aquí vive la única concurrencia real del prototipo. Dos personas pueden pedir el
mismo espacio en el mismo segundo, y ROBLE no tiene escritura condicional con la
que impedirlo. El patrón está en `roble_acceso.reservar_cupo`; lo que este módulo
añade es lo que la persona percibe: **quien pierde la carrera no ve un error, ve
las siguientes tres opciones libres**. Sin eso, un conflicto de reserva sería un
callejón sin salida en medio de una conversación.

Cancelar y reprogramar existen desde el 29/10. Antes no había forma de hacer ninguna
de las dos, y aun así el sistema las prometía: `agendar_cita` decía que «el personal
del centro» reprogramaba —el centro no tenía con qué— y el correo de confirmación
pedía a la persona que «avisara» si no podía ir. Las dos piden que la persona
confirme antes del efecto: la herramienta devuelve la cita para preguntárselo y sólo
actúa cuando se la llama otra vez con `confirmado`.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from caresync_comun import correo, plazos, reloj
from caresync_comun.errores import Conflicto, NoEncontrado, SolicitudInvalida
from caresync_comun.registro import evento, registro
from caresync_comun.roble_acceso import (
    CASO_AGENDADO,
    CASO_CANALIZADO,
    CITA_CANCELADA,
    AccesoRoble,
    cita_por_delante,
    fila_id,
)

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

# Un espacio que empieza en cinco minutos no le sirve a nadie que está escribiendo en
# el chat: no alcanza a llegar. Se ofrece a partir de esta anticipación.
ANTICIPACION = timedelta(minutes=int(os.environ.get("MINUTOS_ANTICIPACION", "60")))

# 0 = lunes … 6 = domingo, la convención de la columna `dia_semana`.
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

# --------------------------------------------------------------- disponibilidad

def consultar_disponibilidad(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    """Los espacios libres del centro, dentro del plazo que pide el nivel del caso.

    Con nivel 2 o 3 la ventana la pone el protocolo y no el modelo: 72 horas o 7 días.
    Antes era `dias_adelante`, 7 si el modelo no decía nada, y un caso de nivel 2 podía
    salir con cita a seis días sin que nada lo marcara. Si dentro del plazo no hay
    nada, se ofrece lo primero que haya después, dicho como tal, y queda anotado en el
    caso para que se vea que el centro no tuvo espacio a tiempo.
    """
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

    nivel = plazos.nivel_de(caso)
    plazo = plazos.plazo_de(nivel)

    if not plazo:
        # Sin plazo: el personal del centro preguntando por su agenda, o un nivel 4
        # que pidió cita. Ahí sí vale la ventana que pida el modelo.
        cupos = _libres(acceso, centro=centro, hasta=reloj.mas(dias=dias), maximo=MAX_OPCIONES)
        return {
            "centro": centro,
            "ventana_dias": dias,
            "opciones": [_opcion(acceso, cupo) for cupo in cupos],
            "instruccion": _OFRECER
            if cupos
            else (
                "No hay espacios en esa ventana. Amplía los días una vez; si sigue "
                "vacío, dilo con claridad: el caso queda registrado y el centro lo ve "
                "en su panel, así que puede volver a intentarlo más tarde. No inventes "
                "un espacio y no prometas que alguien la va a contactar."
            ),
        }

    texto_plazo = plazos.texto_de(nivel)
    en_plazo = _libres(acceso, centro=centro, hasta=reloj.ahora() + plazo, maximo=MAX_OPCIONES)
    if en_plazo:
        return {
            "centro": centro,
            "plazo": texto_plazo,
            "dentro_del_plazo": True,
            "opciones": [_opcion(acceso, cupo) for cupo in en_plazo],
            "instruccion": _OFRECER,
        }

    despues = _libres(acceso, centro=centro, hasta=reloj.mas(dias=VENTANA_MAXIMA_DIAS), maximo=3)
    _anotar_sin_cupo_en_plazo(acceso, caso, nivel=nivel, primero=despues[0] if despues else None)
    return {
        "centro": centro,
        "plazo": texto_plazo,
        "dentro_del_plazo": False,
        "opciones": [_opcion(acceso, cupo) for cupo in despues],
        "instruccion": (
            f"No hay espacios dentro del plazo que corresponde a su nivel ({texto_plazo}). "
            "Díselo así a la persona y ofrécele estas opciones con su fecha: son más "
            "tarde de lo que pide el protocolo. Queda anotado en el caso que no hubo "
            "espacio a tiempo. No prometas que se va a abrir otro espacio ni que alguien "
            "la va a contactar."
            if despues
            else (
                "No queda ningún espacio libre en el centro en los próximos 30 días. Dilo "
                "con claridad: el caso queda registrado y puede volver a intentarlo más "
                "tarde. No inventes un espacio y no prometas que alguien la va a contactar."
            )
        ),
    }


_OFRECER = (
    "Ofrece dos o tres opciones como máximo, con el texto de «cuando». "
    "Cuando la persona elija, llama a agendar_cita con el «inicio» de esa "
    "opción, copiado tal cual. Si ya no lo tienes delante, vuelve a llamar "
    "a esta herramienta: no reconstruyas la fecha de memoria."
)


def _libres(
    acceso: AccesoRoble, *, centro: str, hasta: Any, maximo: int
) -> list[dict[str, Any]]:
    """Los cupos libres del centro desde dentro de una hora, ordenados por cercanía."""
    return acceso.cupos_libres(
        centro=centro, desde=reloj.ahora() + ANTICIPACION, hasta=hasta, maximo=maximo
    )


def _anotar_sin_cupo_en_plazo(
    acceso: AccesoRoble, caso: dict[str, Any], *, nivel: int | None, primero: dict[str, Any] | None
) -> None:
    """Deja en la bitácora que el centro no tuvo espacio a tiempo, una vez al día.

    Una vez al día y no una por consulta: el agente puede consultar la disponibilidad
    tres veces en la misma conversación, y tres eventos iguales dirían que faltó cupo
    tres veces. Si la anotación falla, la persona igual recibe sus opciones.
    """
    caso_id = str(fila_id(caso) or "")
    if not caso_id:
        return
    try:
        hace_un_dia = reloj.mas(dias=-1)
        for previo in acceso.eventos_del_caso(caso_id):
            momento = reloj.desde_iso(previo.get("creado_en"))
            if previo.get("tipo") == "sin_cupo_en_plazo" and momento and momento > hace_un_dia:
                return
        acceso.registrar_evento(
            caso_id=caso_id,
            tipo="sin_cupo_en_plazo",
            severidad="alta" if nivel == 2 else "info",
            detalle={
                "nivel_urgencia": nivel,
                "plazo": plazos.texto_de(nivel),
                "primer_espacio": primero.get("inicio") if primero else None,
            },
        )
        evento(log, "sin_cupo_en_plazo", caso_id=caso_id, nivel_urgencia=nivel)
    except Exception as exc:  # noqa: BLE001 - las opciones son lo importante
        evento(log, "sin_cupo_no_anotado", caso_id=caso_id, detalle=type(exc).__name__)


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

    Lo usan las herramientas que escriben sobre una cita: ahí el centro del actor no
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
    libres = _libres(
        acceso, centro=centro, hasta=reloj.mas(dias=VENTANA_MAXIMA_DIAS), maximo=MAX_CANDIDATOS
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


def _resolver_espacio(
    acceso: AccesoRoble, *, caso: dict[str, Any], centro: str, argumentos: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """El cupo que pidió el modelo, o lo que hay que devolverle si no resolvió a uno."""
    coincidencias = _coincidencias(acceso, centro=centro, argumentos=argumentos)
    if len(coincidencias) == 1:
        return coincidencias[0], None
    return None, _hay_que_reconsultar(acceso, caso=caso, centro=centro, coincidencias=coincidencias)


def _hay_que_reconsultar(
    acceso: AccesoRoble,
    *,
    caso: dict[str, Any],
    centro: str,
    coincidencias: list[dict[str, Any]],
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
                "llamar con el mismo «inicio» y el nombre elegido."
            ),
        }

    alternativas = _alternativas(acceso, caso=caso, centro=centro)
    return {
        "error": "Ese espacio ya no está libre en la agenda.",
        "motivo": "espacio_no_encontrado",
        "alternativas": [_opcion(acceso, c) for c in alternativas],
        "instruccion": (
            "Ofrécele las alternativas con el texto de «cuando» y usa el «inicio» de la "
            "que elija."
            if alternativas
            else (
                "No queda ningún espacio libre en el centro. Dilo con claridad, sin "
                "prometer que alguien la contactará, y ofrécele volver a intentarlo."
            )
        ),
    }


def _alternativas(acceso: AccesoRoble, *, caso: dict[str, Any], centro: str) -> list[dict[str, Any]]:
    """Tres espacios para ofrecer en lugar del que no se pudo: en plazo si los hay."""
    plazo = plazos.plazo_de(plazos.nivel_de(caso))
    if plazo:
        en_plazo = _libres(acceso, centro=centro, hasta=reloj.ahora() + plazo, maximo=3)
        if en_plazo:
            return en_plazo
    return _libres(acceso, centro=centro, hasta=reloj.mas(dias=DIAS_ALTERNATIVAS), maximo=3)


def _nombre_del_profesional(acceso: AccesoRoble, cupo: dict[str, Any]) -> str:
    try:
        return str(acceso.profesional(str(cupo.get("profesional_id"))).get("nombre") or "")
    except NoEncontrado:
        # Un cupo huérfano no debería existir, pero si existe es mejor ofrecerlo
        # sin nombre que ocultar el único espacio libre de la semana.
        evento(log, "cupo_sin_profesional", cupo_id=fila_id(cupo))
        return ""


def _reservar_y_confirmar(
    acceso: AccesoRoble, *, caso: dict[str, Any], centro: str, cupo: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Toma el espacio: lo reserva, lo confirma como cita y devuelve la cita.

    Si otra persona lo tomó primero, devuelve en su lugar lo que hay que decirle al
    modelo. Lo comparten agendar y reprogramar, que toman un espacio de la misma forma.
    """
    caso_id = str(fila_id(caso))
    cupo_id = str(fila_id(cupo))

    try:
        acceso.reservar_cupo(cupo_id=cupo_id, caso_id=caso_id)
    except Conflicto as exc:
        # Perder la carrera no es un error para la persona: es «ese ya lo
        # tomaron, mira estos». Se devuelve como resultado y no como excepción
        # para que el modelo tenga las alternativas en la misma vuelta.
        evento(log, "reserva_en_conflicto", caso_id=caso_id, cupo_id=cupo_id)
        return None, {
            "error": exc.publico,
            "motivo": "espacio_tomado",
            "alternativas": [_opcion(acceso, c) for c in _alternativas(acceso, caso=caso, centro=centro)],
            "instruccion": "Ofrece las alternativas. No vuelvas a intentar el mismo espacio.",
        }

    try:
        return acceso.confirmar_cita(cupo_id=cupo_id, caso_id=caso_id), None
    except Exception:
        # Si la confirmación falla, el cupo queda reservado y bloqueado. Se
        # libera aquí en lugar de esperar el barrido de los 15 minutos.
        try:
            acceso.liberar_cupo(cupo_id)
        except Exception:  # noqa: BLE001
            evento(log, "cupo_no_liberado", cupo_id=cupo_id)
        raise


def _citas_por_delante(acceso: AccesoRoble, caso_id: str) -> list[dict[str, Any]]:
    """Las citas confirmadas del caso que todavía no terminan, la más próxima primero."""
    return sorted(
        (c for c in acceso.citas_del_caso(caso_id) if cita_por_delante(c)),
        key=lambda c: str(c.get("inicio") or ""),
    )


def _ficha(cita: dict[str, Any]) -> dict[str, Any]:
    return {
        "inicio": reloj.iso_local(cita.get("inicio")),
        "cuando": reloj.humano(cita.get("inicio")),
        "profesional": cita.get("profesional_nombre"),
        "centro": cita.get("centro"),
    }


def _cita_elegida(
    acceso: AccesoRoble, caso_id: str, argumentos: dict[str, Any], *, accion: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """La cita sobre la que se cancela o se cambia: la que el caso tiene por delante.

    Lo normal es una sola. Dos sólo pasan si una reprogramación no alcanzó a cancelar
    la anterior, y entonces decide `cita_actual`, la hora de la que se quiere tocar.
    """
    por_delante = _citas_por_delante(acceso, caso_id)
    if not por_delante:
        raise SolicitudInvalida(
            "El caso no tiene una cita por delante",
            publico=(
                f"Este caso no tiene ninguna cita por delante que {accion}. Si la persona "
                "quiere una, búscala con consultar_disponibilidad y agéndala con agendar_cita."
            ),
        )
    if len(por_delante) == 1:
        return por_delante[0], None

    buscada = reloj.desde_local(argumentos.get("cita_actual"))
    if buscada:
        for cita in por_delante:
            inicio = reloj.desde_iso(cita.get("inicio"))
            if inicio and inicio.replace(second=0, microsecond=0) == buscada.replace(second=0, microsecond=0):
                return cita, None
    return None, {
        "error": "El caso tiene más de una cita por delante.",
        "motivo": "varias_citas",
        "citas": [_ficha(c) for c in por_delante],
        "instruccion": (
            f"Pregúntale a la persona cuál quiere {accion} y vuelve a llamar con "
            "cita_actual igual al «inicio» de esa."
        ),
    }


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

    # Sólo bloquea una cita que todavía no ha pasado. Hasta el 29/10 bloqueaba toda
    # cita no cancelada, también las pasadas: quien no llegaba a la suya ya no podía
    # pedir otra y el caso se quedaba en `agendado` sin salida.
    por_delante = _citas_por_delante(acceso, caso_id)
    if por_delante:
        cuando = reloj.humano(por_delante[0].get("inicio"))
        raise Conflicto(
            "Este caso ya tiene una cita por delante",
            publico=(
                f"Este caso ya tiene una cita el {cuando}. Si la persona quiere cambiarla, "
                "usa reprogramar_cita; si quiere anularla, cancelar_cita."
            ),
        )

    # La búsqueda ya es por centro, así que un espacio de otro centro no puede
    # colarse: no hay identificador ajeno que arrastrar.
    cupo, salida = _resolver_espacio(acceso, caso=caso, centro=centro, argumentos=argumentos)
    if salida:
        return salida
    cita, salida = _reservar_y_confirmar(acceso, caso=caso, centro=centro, cupo=cupo)
    if salida:
        return salida

    # La hora sale del cupo y no de la cita recién creada. Lo que ROBLE devuelve al
    # insertar trae las fechas reinterpretadas en la zona de su servidor —Colombia—
    # y corridas cinco horas: «08:30» volvía como «13:30», el agente se lo confirmaba
    # así a la persona y la cita guardada seguía siendo a las 08:30. Al releer la
    # fila la hora sale bien; la respuesta del `insert` es la única que miente.
    cuando = reloj.humano(cupo.get("inicio"))
    acceso.registrar_evento(
        caso_id=caso_id,
        tipo="cita_agendada",
        detalle={
            "cita_id": fila_id(cita),
            "centro": centro,
            "inicio": cupo.get("inicio"),
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
            # Decía «entra a CareSync y avísanos», cuando no había a quién avisar ni
            # con qué cancelar. Desde el 29/10 la conversación cancela y cambia citas.
            "Si no puedes asistir, entra a CareSync y escríbelo en la conversación: "
            "ahí mismo puedes cancelarla o cambiarla de hora.",
        ]
    )
    return correo.enviar(para=destino, asunto="[CareSync] Tu cita quedó agendada", cuerpo=cuerpo)


# ------------------------------------------------------- cancelar y reprogramar

def cancelar_cita(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    """Anula la cita que el caso tiene por delante y devuelve su espacio a la agenda.

    El caso vuelve a `canalizado`: sigue siendo de agenda, sin cita, y puede pedir otra
    cuando quiera. El profesional recibe el aviso, porque si no seguiría esperando a
    alguien que no va a llegar.
    """
    caso_id = str(fila_id(caso))
    cita, salida = _cita_elegida(acceso, caso_id, argumentos, accion="cancelar")
    if salida:
        return salida

    cuando = reloj.humano(cita.get("inicio"))
    if not argumentos.get("confirmado"):
        return {
            "confirmar_primero": True,
            "cita": _ficha(cita),
            "instruccion": (
                f"Todavía no se canceló nada. Pregúntale a la persona si confirma que "
                f"cancela la cita del {cuando}. Si te dice que sí, vuelve a llamar a "
                "cancelar_cita con confirmado en true."
            ),
        }

    motivo = str(argumentos.get("motivo") or "").strip()[:300]
    cupo_liberado = acceso.cancelar_cita(cita)
    if caso.get("estado") == CASO_AGENDADO:
        acceso.actualizar_caso(caso_id, {"estado": CASO_CANALIZADO})

    acceso.registrar_evento(
        caso_id=caso_id,
        tipo="cita_cancelada",
        detalle={
            "cita_id": fila_id(cita),
            "inicio": cita.get("inicio"),
            "motivo": motivo,
            "por": acceso.actor.rol,
            "cupo_liberado": cupo_liberado,
        },
    )
    avisado = _avisar_cancelacion(acceso, caso, cita=cita, cuando=cuando, motivo=motivo)
    _avisar_cancelacion_a_la_persona(caso, cuando=cuando)

    return {
        "ok": True,
        "cancelada": cuando,
        "profesional_avisado": avisado,
        "instruccion": (
            f"Confírmale que la cita del {cuando} quedó cancelada. Si quiere otra, "
            "consulta la disponibilidad y agéndala; si no, no insistas."
        ),
    }


def reprogramar_cita(
    acceso: AccesoRoble, caso: dict[str, Any], argumentos: dict[str, Any]
) -> dict[str, Any]:
    """Cambia la cita que el caso tiene por delante por otro espacio.

    **Primero se toma el espacio nuevo y sólo después se suelta el viejo.** Sin
    transacciones, si algo falla en medio la persona conserva una cita. Al revés, un
    fallo entre los dos pasos la dejaba sin ninguna, y el espacio viejo ya podía ser
    de otra persona.
    """
    caso_id = str(fila_id(caso))
    centro = _centro_del_caso(caso)

    anterior, salida = _cita_elegida(acceso, caso_id, argumentos, accion="cambiar")
    if salida:
        return salida
    cupo, salida = _resolver_espacio(acceso, caso=caso, centro=centro, argumentos=argumentos)
    if salida:
        return salida

    de = reloj.humano(anterior.get("inicio"))
    a = reloj.humano(cupo.get("inicio"))
    if not argumentos.get("confirmado"):
        return {
            "confirmar_primero": True,
            "de": de,
            "a": a,
            "profesional": _nombre_del_profesional(acceso, cupo),
            "instruccion": (
                f"Todavía no se cambió nada. Pregúntale a la persona si confirma el "
                f"cambio de la cita del {de} a la del {a}. Si te dice que sí, vuelve a "
                "llamar a reprogramar_cita con el mismo «inicio» y confirmado en true."
            ),
        }

    nueva, salida = _reservar_y_confirmar(acceso, caso=caso, centro=centro, cupo=cupo)
    if salida:
        # Otra persona tomó el espacio nuevo. La cita anterior sigue intacta.
        return salida

    try:
        acceso.cancelar_cita(anterior)
        anterior_cancelada = True
    except Exception as exc:  # noqa: BLE001 - la persona ya tiene la cita nueva
        anterior_cancelada = False
        evento(log, "reprogramacion_incompleta", caso_id=caso_id, detalle=type(exc).__name__)

    acceso.registrar_evento(
        caso_id=caso_id,
        tipo="cita_reprogramada",
        detalle={
            "cita_anterior": fila_id(anterior),
            "de": anterior.get("inicio"),
            "cita_nueva": fila_id(nueva),
            "a": cupo.get("inicio"),
            "anterior_cancelada": anterior_cancelada,
            "por": acceso.actor.rol,
        },
    )
    _avisar_a_la_persona(caso, cita=nueva, cuando=a)
    if anterior_cancelada:
        _avisar_cancelacion(acceso, caso, cita=anterior, cuando=de, motivo="la cita se cambió de hora")
    profesional_avisado = _enviar_resumen(acceso, caso, nueva)

    if not anterior_cancelada:
        return {
            "ok": True,
            "cuando": a,
            "centro": centro,
            "profesional": nueva.get("profesional_nombre"),
            "anterior_cancelada": False,
            "cita_anterior_inicio": reloj.iso_local(anterior.get("inicio")),
            "instruccion": (
                f"La cita nueva quedó el {a}, pero la del {de} no se pudo cancelar. "
                "Díselo así y vuelve a llamar ahora a cancelar_cita, con cita_actual "
                "igual a «cita_anterior_inicio» y confirmado en true."
            ),
        }
    return {
        "ok": True,
        "cuando": a,
        "centro": centro,
        "profesional": nueva.get("profesional_nombre"),
        "anterior_cancelada": True,
        "profesional_avisado": profesional_avisado,
        "instruccion": (
            "Confírmale el día, la hora y el centro de la cita nueva. El profesional ya "
            "recibió el resumen del caso: no llames a notificar_profesional."
        ),
    }


def _avisar_cancelacion(
    acceso: AccesoRoble, caso: dict[str, Any], *, cita: dict[str, Any], cuando: str, motivo: str
) -> bool:
    """Le dice al profesional que esa cita ya no va. Sin correo registrado, no avisa."""
    try:
        destino = _correo_del_profesional(acceso, cita)
    except NoEncontrado:
        return False
    return correo.enviar(
        para=destino,
        asunto=f"[CareSync] Cita cancelada · {cuando}",
        cuerpo="\n".join(
            [
                f"La cita del {cuando} (hora de Bogotá) en {cita.get('centro')} quedó cancelada.",
                "",
                f"Persona: {caso.get('paciente_nombre')}",
                f"Motivo: {motivo or 'no lo dijo'}",
                "",
                "El espacio volvió a quedar libre en la agenda.",
            ]
        ),
    )


def _avisar_cancelacion_a_la_persona(caso: dict[str, Any], *, cuando: str) -> bool:
    return correo.enviar(
        para=str(caso.get("paciente_email") or ""),
        asunto="[CareSync] Tu cita quedó cancelada",
        cuerpo="\n".join(
            [
                f"Hola {caso.get('paciente_nombre') or ''}".strip() + ",",
                "",
                f"Tu cita del {cuando} (hora de Bogotá) quedó cancelada.",
                "Si necesitas otra, pídela en la conversación de CareSync.",
            ]
        ),
    )


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

    # La cita de la que se avisa es la próxima que tiene el caso. Antes era la última
    # por fecha, y desde que hay reprogramación esa puede ser una cancelada.
    por_delante = _citas_por_delante(acceso, caso_id)
    if por_delante:
        cita = por_delante[0]
    else:
        vigentes = sorted(
            (c for c in acceso.citas_del_caso(caso_id) if c.get("estado") != CITA_CANCELADA),
            key=lambda c: str(c.get("inicio") or ""),
        )
        if not vigentes:
            raise SolicitudInvalida(
                "Todavía no hay cita: agenda primero y después notifica",
                publico="Este caso todavía no tiene cita. Agéndala antes de notificar.",
            )
        cita = vigentes[-1]

    if _ya_notificada(acceso, caso_id, cita):
        return {
            "ok": True,
            "repetido": True,
            "instruccion": "Ya estaba avisado. No se lo digas a la persona, sigue con la conversación.",
        }

    enviado = _enviar_resumen(acceso, caso, cita, exigir_correo=True)

    return {
        "ok": True,
        "enviado": enviado,
        "profesional": cita.get("profesional_nombre"),
        "instruccion": (
            "Dile a la persona que el profesional ya tiene su información."
            if enviado
            # Decía «dile que el centro la contactará»: una promesa de contacto
            # humano que nadie va a cumplir (invariante 7), y mientras SES no tenga
            # remitente salía en cada cita agendada. Lo cierto es lo que sigue.
            else (
                "El correo no salió, pero la cita quedó en la agenda del profesional en "
                "CareSync, con el resumen del caso. Díselo así, y no prometas que alguien "
                "la va a llamar, escribir o contactar."
            )
        ),
    }


def _enviar_resumen(
    acceso: AccesoRoble, caso: dict[str, Any], cita: dict[str, Any], *, exigir_correo: bool = False
) -> bool:
    """Envía el resumen del caso al profesional de esa cita y lo deja en la bitácora.

    `notificar_profesional` exige que el profesional tenga correo y, si no, devuelve el
    error al modelo para que lo explique. `reprogramar_cita` no: a esas alturas la cita
    nueva ya existe, y un correo que falta no puede deshacerla.
    """
    caso_id = str(fila_id(caso))
    try:
        destino = _correo_del_profesional(acceso, cita)
    except NoEncontrado:
        if exigir_correo:
            raise
        return False

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
    return enviado


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
