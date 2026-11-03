"""Orquestador de agentes: el único punto de entrada del sistema.

Lo que hace, en orden:

1. Autoriza al llamante contra ROBLE con su propio token, y de ahí saca su rol.
2. Resuelve el caso: continúa el que esté abierto, abre uno nuevo, o ninguno —el
   personal de un centro pregunta también por su operación, sin hablar de nadie.
3. Elige el agente por rol y por estado del caso, no por lo que diga el cliente.
4. Corre el bucle de herramientas contra Bedrock.
5. Traspasa al siguiente agente si el anterior cerró su parte.
6. Deja la conversación escrita en ROBLE y responde.

Lo que NO hace: acceder a datos. Cualquier lectura o escritura del dominio pasa
por el módulo de acceso, y cualquier acción con efecto por la función de
herramientas. Este archivo coordina.

Hay un segundo camino, el **modo simulación** (`simulacion: true` en el cuerpo):
un profesional se pone en los zapatos de un paciente para evaluar al modelo, y
nada de lo que pase ahí tiene efecto real. Vive al final del archivo, separado del
camino real a propósito; ver la sección «simulación».

Y dos rutas que no son de ningún agente, para la consulta del profesional:
`POST /plan/propuesta` ordena en un plan lo que el profesional dictó o escribió, sin
guardarlo, y `POST /dictado/sesion` le firma la conexión a Amazon Transcribe para que
pueda dictar. Están en la sección «consulta del profesional».
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any

import boto3
import requests

from caresync_comun import plazos, reloj, respuesta
from caresync_comun.catalogo_herramientas import (
    CATALOGO,
    especificaciones,
    necesita_caso,
    permitida,
)
from caresync_comun.config import config
from caresync_comun.errores import (
    ErrorDeCareSync,
    ErrorDeDatos,
    NoAutorizado,
    SinPermiso,
    SolicitudInvalida,
)
from caresync_comun.registro import evento, registro
from caresync_comun.roble_acceso import (
    ADMIN_CAE,
    ADMIN_CMU,
    CASO_ABIERTO,
    CASO_CERRADO,
    PACIENTE,
    PROFESIONAL,
    AccesoRoble,
    Actor,
    cita_por_delante,
    fila_id,
)

import agentes
import bedrock_conversa
import dictado
import plan_propuesta

log = registro("orquestador")

FUNCION_HERRAMIENTAS = os.environ.get("FUNCION_HERRAMIENTAS", "")
LIMITE_MENSAJE = 2000


@lru_cache(maxsize=1)
def _lambda():
    return boto3.client("lambda")


# ------------------------------------------------------------------ entrada

def manejar(evento_entrada: dict[str, Any], contexto: Any = None) -> dict[str, Any]:
    ruta = (evento_entrada.get("routeKey") or "").strip()

    try:
        if ruta.endswith("/salud") or evento_entrada.get("accion") == "salud":
            return respuesta.ok(_salud())
        if ruta == "POST /plan/propuesta":
            return _proponer_plan(evento_entrada)
        if ruta == "POST /dictado/sesion":
            return _sesion_de_dictado(evento_entrada)
        return _atender(evento_entrada)
    except ErrorDeCareSync as exc:
        evento(
            log,
            "peticion_rechazada",
            tipo=type(exc).__name__,
            estado=exc.http,
            detalle=exc.mensaje,
        )
        return respuesta.de_excepcion(exc)
    except Exception:  # noqa: BLE001 - nada sale sin registrarse
        log.exception("fallo_no_previsto")
        return respuesta.error(500, "Algo falló de nuestro lado. Vuelve a intentarlo.")


def _salud() -> dict[str, Any]:
    """Comprobación sin token: ¿arrancó, leyó su configuración y ve a ROBLE?

    No consulta datos. Pide `/me` sin token justamente porque un 401 es la
    prueba de que el host correcto está respondiendo: un 404 o un fallo de red
    significan que la URL o el contrato están mal.
    """
    ajustes = config()
    estado: dict[str, Any] = {
        "entorno": ajustes.entorno,
        "modelo": bedrock_conversa.MODELO,
        "guardrail": bool(os.environ.get("GUARDRAIL_ID")),
        "correo": ajustes.envia_correo,
        "herramientas": bool(FUNCION_HERRAMIENTAS),
    }

    try:
        sonda = requests.get(
            f"{ajustes.roble_base_url.rstrip('/')}/auth/{ajustes.roble_contract_id}/me",
            timeout=5,
        )
        estado["roble"] = {
            "alcanzable": True,
            "estado_http": sonda.status_code,
            "contrato_valido": sonda.status_code == 401,
        }
    except requests.RequestException as exc:
        estado["roble"] = {"alcanzable": False, "detalle": type(exc).__name__}

    estado["ok"] = bool(estado["roble"].get("contrato_valido")) and estado["herramientas"]
    return estado


def _atender(entrada: dict[str, Any]) -> dict[str, Any]:
    token = respuesta.token_del_evento(entrada)
    if not token:
        raise NoAutorizado("La petición no trae cabecera Authorization")

    cuerpo = respuesta.cuerpo_del_evento(entrada)
    mensaje = str(cuerpo.get("mensaje") or "").strip()
    if not mensaje:
        raise SolicitudInvalida("Falta el campo «mensaje»")
    if len(mensaje) > LIMITE_MENSAJE:
        raise SolicitudInvalida(f"El mensaje excede {LIMITE_MENSAJE} caracteres")

    acceso = AccesoRoble.desde_token(token)
    try:
        # Dos caminos que no se cruzan, y la bifurcación está aquí arriba a
        # propósito: así se puede comprobar leyendo que la simulación no pasa por
        # `_conversar`. El token no se le pasa porque no tiene a quién invocar —sin
        # token no hay forma de llegar a la función de herramientas—, y eso es lo
        # que hace que «nada de la simulación tiene efecto real» sea verificable y
        # no una promesa.
        if _pide_simulacion(cuerpo):
            return _simular(acceso, mensaje=mensaje, cuerpo=cuerpo)
        return _conversar(acceso, token=token, mensaje=mensaje, cuerpo=cuerpo)
    finally:
        acceso.cerrar()


# ------------------------------------------------------ consulta del profesional
#
# Dos ayudas para escribir el plan, y ninguna escribe nada: la propuesta devuelve el
# texto ordenado para que el profesional lo corrija y lo guarde él desde la PWA, con su
# token, y el dictado sólo firma una conexión. Por eso ninguna de las dos pasa por la
# función de herramientas ni toca ROBLE más allá de validar quién llama.


def _proponer_plan(entrada: dict[str, Any]) -> dict[str, Any]:
    acceso = _solo_profesional(entrada)
    try:
        cuerpo = respuesta.cuerpo_del_evento(entrada)
        propuesta = plan_propuesta.proponer(str(cuerpo.get("texto") or ""))
        # Sin el texto ni la propuesta: lo dictado es un plan de tratamiento, y el log
        # técnico no es sitio para datos de salud. Las cuentas bastan para saber si la
        # ruta se usa y si el modelo deja dudas.
        evento(
            log,
            "plan_propuesto",
            profesional=acceso.actor.user_id,
            indicaciones=len(propuesta["indicaciones"]),
            dudas=len(propuesta["dudas"]),
        )
        return respuesta.ok(propuesta)
    finally:
        acceso.cerrar()


def _sesion_de_dictado(entrada: dict[str, Any]) -> dict[str, Any]:
    acceso = _solo_profesional(entrada)
    try:
        sesion = dictado.url_firmada()
        evento(log, "dictado_firmado", profesional=acceso.actor.user_id)
        return respuesta.ok(sesion)
    finally:
        acceso.cerrar()


def _solo_profesional(entrada: dict[str, Any]) -> AccesoRoble:
    """Quien llama, si es un profesional. El rol lo dice ROBLE, no el cuerpo.

    Las dos rutas son del profesional y de nadie más: la propuesta corre sin la
    salvaguarda de los agentes —quien prescribe ahí es él— y el dictado abre Transcribe
    con el rol de la Lambda. Un paciente que las llamara recibiría un 403 aunque la
    vista nunca le muestre el botón: el permiso se comprueba en el lado del efecto.
    """
    token = respuesta.token_del_evento(entrada)
    if not token:
        raise NoAutorizado("La petición no trae cabecera Authorization")
    acceso = AccesoRoble.desde_token(token)
    if acceso.actor.rol != PROFESIONAL:
        rol = acceso.actor.rol
        acceso.cerrar()
        raise SinPermiso(
            f"El rol «{rol}» no puede usar las ayudas de la consulta",
            publico="Esto es sólo para profesionales que atienden.",
        )
    return acceso


# ------------------------------------------------------------- conversación

def _conversar(
    acceso: AccesoRoble, *, token: str, mensaje: str, cuerpo: dict[str, Any]
) -> dict[str, Any]:
    actor = acceso.actor
    caso = _resolver_caso(acceso, cuerpo=cuerpo, mensaje=mensaje)
    caso_id = str(fila_id(caso)) if caso else ""

    # Dónde se guarda este hilo. Con caso, en el caso. Sin caso —el personal de un
    # centro preguntando por sus horarios— en un hilo propio de quien pregunta, para
    # que la conversación tenga memoria de un turno a otro igual que las demás.
    # `conversaciones.caso_id` es texto libre, así que el prefijo no colisiona con
    # ningún `_id`; una columna nueva no era opción, ROBLE no admite `alter`.
    hilo_id = caso_id or f"consulta:{actor.user_id}"

    solicitado = str(cuerpo.get("agente") or "").strip().lower()
    clave = (
        solicitado
        if solicitado in agentes.AGENTES
        else agentes.agente_por_defecto(caso, rol=actor.rol)
    )
    agente = agentes.AGENTES[clave]

    if actor.rol not in agente.roles:
        raise SinPermiso(f"El rol «{actor.rol}» no puede usar el {agente.nombre}")

    acceso.anotar_mensaje(
        caso_id=hilo_id, agente=agente.clave, autor=actor.rol, contenido=mensaje
    )

    # El hilo que se le pasa al modelo es sólo texto: turnos de la persona y del
    # agente. Los bloques `toolUse`/`toolResult` de la vuelta anterior se quedan
    # dentro del bucle y no se arrastran al traspaso, porque el segundo agente
    # declara otras herramientas y la API rechaza un historial que referencia
    # herramientas que ya no existen.
    filas = acceso.mensajes(hilo_id, maximo=20)
    hilo = _historial_de_filas(filas)
    hilo.append({"role": "user", "content": _turno_de_la_persona(mensaje, agente)})
    pausa = _pausa(filas)

    participantes: list[str] = []
    usos_totales: list[bedrock_conversa.Uso] = []
    texto_final = ""
    # Lo que se guarda en el hilo de este caso. Es lo mismo que `texto_final` salvo
    # cuando la conversación cambia de caso a mitad del turno (`nuevo_motivo`): lo
    # que dijo el primer agente se queda en el hilo del caso viejo, y la persona
    # recibe las dos cosas en una sola respuesta.
    texto_del_hilo = ""
    usos_del_hilo: list[bedrock_conversa.Uso] = []
    caso_anterior = ""
    tokens = {"entrada": 0, "salida": 0, "cacheados": 0}
    intervino = False
    salvaguardas: set[str] = set()

    # Como máximo dos agentes por petición: el que atiende y el que recibe el
    # traspaso. Un tercero sería una cadena que la persona no puede seguir.
    for salto in range(2):
        participantes.append(agente.clave)
        if not salto:
            contexto_extra = pausa
        elif caso_anterior:
            contexto_extra = _contexto_del_caso_nuevo()
        else:
            contexto_extra = _contexto_del_traspaso(caso or {})

        # Se guarda para poder volver a llamar al mismo agente si su respuesta da por
        # hecha una cita que ninguna herramienta hizo (`_sin_citas_inventadas`).
        llamada = {
            "sistema": agentes.instrucciones_partidas(
                agente, actor=actor, caso=caso, contexto=contexto_extra
            ),
            "herramientas": _herramientas_de(agente, actor.rol, con_caso=bool(caso_id)),
            "ejecutar": _ejecutor(token=token, caso_id=caso_id, agente=agente.clave),
            # Agenda no contesta de memoria: antes de responder mira algo de verdad.
            # Con sólo el recordatorio, en la prueba del 2/11 siguió dando por
            # cancelada una cita sin llamar a `cancelar_cita` y ofreciendo cupos sin
            # consultarlos. Cuesta una lectura por turno. Seguimiento igual: también
            # agenda (el control del plan) y registra lo que la persona cuenta, y un
            # «quedó registrado» sin `registrar_adherencia` es el mismo fallo.
            "exigir_herramienta": agente.clave in _NO_CONTESTAN_DE_MEMORIA,
        }
        resultado = bedrock_conversa.conversar(mensajes=hilo, **llamada)

        usos_totales.extend(resultado.usos)
        usos_del_hilo.extend(resultado.usos)
        tokens["entrada"] += resultado.tokens_entrada
        tokens["salida"] += resultado.tokens_salida
        tokens["cacheados"] += resultado.tokens_cacheados
        intervino = intervino or resultado.intervino_guardrail
        salvaguardas.update(resultado.salvaguardas)
        texto_final = "\n\n".join(t for t in (texto_final, resultado.texto) if t)
        texto_del_hilo = "\n\n".join(t for t in (texto_del_hilo, resultado.texto) if t)

        siguiente = _traspaso(agente, resultado)
        if not siguiente:
            break

        nuevo = _caso_nuevo(resultado)
        if nuevo:
            # El problema nuevo sigue en su propio caso. Lo dicho hasta aquí se queda
            # en el hilo del caso viejo, y el nuevo empieza con el mensaje de la
            # persona, que es lo que su triaje tiene que leer.
            if texto_del_hilo:
                acceso.anotar_mensaje(
                    caso_id=hilo_id, agente=agente.clave, autor="agente", contenido=texto_del_hilo
                )
            _dejar_constancia_de_los_fallos(
                acceso, hilo_id=hilo_id, agente=agente.clave, usos=usos_del_hilo
            )
            _dejar_constancia_de_la_agenda(
                acceso, hilo_id=hilo_id, agente=agente.clave, usos=usos_del_hilo
            )
            texto_del_hilo, usos_del_hilo = "", []
            caso_anterior, caso_id, hilo_id = caso_id, nuevo, nuevo
            caso = acceso.caso(caso_id)
            agente = agentes.AGENTES[siguiente]
            if actor.rol not in agente.roles:
                break
            acceso.anotar_mensaje(
                caso_id=hilo_id, agente=agente.clave, autor=actor.rol, contenido=mensaje
            )
            hilo = [{"role": "user", "content": [_lo_que_escribio(mensaje)]}]
            continue

        # El caso cambió de estado dentro de la herramienta: hay que releerlo
        # para que el siguiente agente vea el centro y el nivel de urgencia. Aquí
        # hay caso con seguridad: el traspaso lo dispara `canalizar_caso`, que sin
        # caso no se le llega a declarar al modelo.
        caso = acceso.caso(caso_id)
        agente = agentes.AGENTES[siguiente]
        if actor.rol not in agente.roles:
            break

        if resultado.texto:
            hilo.append({"role": "assistant", "content": [{"text": resultado.texto}]})
        hilo.append({"role": "user", "content": [{"text": _nota_de_traspaso(caso)}]})

    if caso_id and not resultado.intervino_guardrail and _DA_POR_HECHA.search(resultado.texto or ""):
        corregido, extra = _sin_citas_inventadas(
            acceso, caso_id=caso_id, resultado=resultado, usos=usos_del_hilo, llamada=llamada
        )
        if corregido != resultado.texto:
            texto_final = _cambiar_el_final(texto_final, resultado.texto, corregido)
            texto_del_hilo = _cambiar_el_final(texto_del_hilo, resultado.texto, corregido)
        if extra:
            usos_totales.extend(extra.usos)
            usos_del_hilo.extend(extra.usos)
            tokens["entrada"] += extra.tokens_entrada
            tokens["salida"] += extra.tokens_salida
            tokens["cacheados"] += extra.tokens_cacheados

    texto_final = _con_la_ruta_de_emergencia(texto_final, usos_totales, intervino=intervino)
    texto_del_hilo = _con_la_ruta_de_emergencia(texto_del_hilo, usos_del_hilo, intervino=intervino)

    if texto_del_hilo:
        acceso.anotar_mensaje(
            caso_id=hilo_id, agente=participantes[-1], autor="agente", contenido=texto_del_hilo
        )

    # La constancia de los fallos va fuera de ese `if`: un turno puede salir sin
    # texto —el modelo se queda callado— y es precisamente cuando más falta hace
    # que la bitácora diga qué no se hizo. Colgada del texto, el turno siguiente
    # arrancaba sin saber que la herramienta había fallado.
    _dejar_constancia_de_los_fallos(
        acceso, hilo_id=hilo_id, agente=participantes[-1], usos=usos_del_hilo
    )
    _dejar_constancia_de_la_agenda(
        acceso, hilo_id=hilo_id, agente=participantes[-1], usos=usos_del_hilo
    )

    if caso_id:
        caso = acceso.caso(caso_id)
    evento(
        log,
        "conversacion_atendida",
        caso_id=hilo_id,
        caso_anterior=caso_anterior or None,
        agentes=participantes,
        herramientas=[u.nombre for u in usos_totales],
        tokens_entrada=tokens["entrada"],
        tokens_salida=tokens["salida"],
        tokens_cacheados=tokens["cacheados"],
        guardrail=intervino,
        salvaguardas=sorted(salvaguardas),
    )

    # `caso` va en null cuando no hay ninguno: la vista lo usa para saber si el hilo
    # tiene sujeto, y un objeto con el id a medias la haría creer que sí.
    return respuesta.ok(
        {
            "respuesta": texto_final,
            "caso": (
                {
                    "id": caso_id,
                    "estado": caso.get("estado"),
                    "centro": caso.get("centro"),
                    "nivel_urgencia": caso.get("nivel_urgencia"),
                }
                if caso
                else None
            ),
            "agentes": participantes,
            "acciones": [
                {"herramienta": u.nombre, "ok": u.ok, "resultado": u.resultado}
                for u in usos_totales
            ],
            "salvaguardas_intervinieron": intervino,
            # Qué política actuó, sin el contenido. Sirve a los evaluadores para
            # distinguir la salvaguarda cortando una dosis —su trabajo— de la
            # salvaguarda cortando una urgencia, que es el peor fallo posible.
            "salvaguardas_detalle": sorted(salvaguardas),
        },
        cabeceras={"x-caresync-caso": caso_id} if caso_id else None,
    )


def _resolver_caso(
    acceso: AccesoRoble, *, cuerpo: dict[str, Any], mensaje: str
) -> dict[str, Any] | None:
    """El caso de esta petición, si hay uno.

    Devuelve `None` cuando quien escribe no es un paciente y no dijo sobre qué caso
    trabaja. No es un error: el personal de un centro también pregunta por su
    agenda, por quién atiende y a qué horas, y eso no es de nadie en concreto. Lo
    que se le exigía antes era un `caso_id` que la vista no tenía, y el 400 se leía
    en pantalla como «No entendí la solicitud».

    Lo que no se hace es deducir el caso de lo que diga el mensaje: la identidad la
    pone el orquestador desde la sesión, no el modelo leyendo un nombre.

    Un paciente que pide un caso cerrado no lo reabre: se le atiende en su caso
    vigente, o en uno nuevo. La vista guarda el `caso_id` del primer turno y lo
    reenvía en los siguientes, así que una pestaña abierta mientras el profesional
    cerraba el caso seguiría escribiendo en él; el triaje no podría canalizarlo
    —`canalizar_caso` no acepta un caso cerrado— y la persona se quedaría hablando
    con un agente que no puede hacer nada.
    """
    pedido = cuerpo.get("caso_id")
    if pedido:
        caso = acceso.caso_visible(str(pedido))
        if not (acceso.actor.es_paciente and caso.get("estado") == CASO_CERRADO):
            return caso

    if not acceso.actor.es_paciente:
        return None

    abierto = acceso.caso_abierto_de(acceso.actor.user_id)
    return abierto or acceso.abrir_caso(motivo=mensaje)


# Cómo se le presenta al modelo un turno que escribió alguien del equipo de atención
# y no la persona que consulta. La marca sigue la convención de `[sistema]`, que el
# prompt común declara: algo entre corchetes al principio del turno no lo dijo la
# persona.
_MARCA_DE_AUTOR = {
    ADMIN_CMU: "[personal del CMU]",
    ADMIN_CAE: "[personal del CAE]",
    PROFESIONAL: "[profesional que atiende]",
}


def _historial(acceso: AccesoRoble, hilo_id: str) -> list[dict[str, Any]]:
    """Convierte lo escrito en ROBLE al formato de mensajes de Converse.

    Los resultados de herramientas no se rehidratan: se guardan como texto en la
    bitácora del caso, pero al modelo se le da la conversación con la persona.
    Reconstruir bloques `toolUse`/`toolResult` de turnos viejos obligaría a
    guardar identificadores de la API en la base y no aporta nada al hilo.
    """
    return _historial_de_filas(acceso.mensajes(hilo_id, maximo=20))


def _pausa(filas: list[dict[str, Any]]) -> str:
    """Una línea para la situación actual si la conversación estuvo detenida un día o más.

    El historial le llega al modelo sin fechas, así que un «desde hace dos días»
    escrito hace una semana se leía como de hoy y el triaje decidía el nivel con un
    dato viejo. La última fila es el mensaje que se acaba de anotar: la pausa es la
    que hay entre él y la anterior. Sale de la misma lectura del historial, sin otra
    operación contra la cuota de ROBLE.
    """
    if len(filas) < 2:
        return ""
    actual = reloj.desde_iso(filas[-1].get("creado_en"))
    anterior = reloj.desde_iso(filas[-2].get("creado_en"))
    if not actual or not anterior:
        return ""
    dias = int((actual - anterior).total_seconds() // 86400)
    if dias < 1:
        return ""
    return (
        f"La conversación estuvo detenida {dias} {'día' if dias == 1 else 'días'}: el "
        f"mensaje anterior a este es del {reloj.humano(anterior)}."
    )


def _historial_de_filas(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mensajes: list[dict[str, Any]] = []
    for fila in filas:
        contenido = str(fila.get("contenido") or "").strip()
        if not contenido:
            continue
        autor = str(fila.get("autor") or PACIENTE)
        # Habla como `user` cualquier persona: el paciente y también quien atiende el
        # caso desde un centro, que sobre el mismo caso conversa con el agente de
        # agenda. Las notas `[sistema]` van del lado del agente a propósito: son lo
        # último que se escribe en el turno, y un turno de usuario al final lo
        # descarta el recorte de más abajo.
        papel = "assistant" if autor in ("agente", "sistema") else "user"
        # Y se dice de quién es el turno, porque si no el modelo le atribuye al
        # paciente el «¿por qué no se ha asignado cita?» que escribió el centro y le
        # responde a la persona equivocada en el turno siguiente.
        marca = _MARCA_DE_AUTOR.get(autor)
        if marca:
            contenido = f"{marca} {contenido}"
        if mensajes and mensajes[-1]["role"] == papel:
            # Converse exige alternancia estricta de papeles.
            mensajes[-1]["content"].append({"text": contenido})
            continue
        mensajes.append({"role": papel, "content": [{"text": contenido}]})

    # El primer mensaje tiene que ser del usuario.
    while mensajes and mensajes[0]["role"] != "user":
        mensajes.pop(0)
    # El último lo añade quien llama, así que aquí no puede quedar uno de usuario.
    if mensajes and mensajes[-1]["role"] == "user":
        mensajes.pop()
    return mensajes


# El historial que ve el modelo es sólo texto: los bloques de herramientas no se
# rehidratan. En una conversación larga, todas «sus» respuestas anteriores son prosa,
# y el modelo la imita. En la prueba del 2/11 el agente de agenda pasó cuatro turnos
# seguidos sin llamar a nada: escribió «te busco espacios para el jueves» y ofreció
# un cupo a las 10:00 que no existe, y dio por cancelada una cita que seguía en pie.
# En el primer turno de un caso casi nunca pasa. El recordatorio va junto al
# mensaje, que es lo último que lee, y no se guarda en el hilo.
_RECORDATORIO = {
    agentes.AGENDA: (
        "[sistema] Para este turno: buscar espacios, agendar, cambiar o cancelar sólo "
        "pasa si llamas ahora a la herramienta. Escribir que lo vas a hacer no lo hace, y "
        "sin la respuesta de la herramienta no hay días ni horas que ofrecer."
    ),
    agentes.SEGUIMIENTO: (
        "[sistema] Para este turno: registrar cómo se siente o si cumplió una indicación, "
        "y buscar, agendar, cambiar o cancelar una cita, sólo pasa si llamas ahora a la "
        "herramienta. Escribir que lo hiciste no lo hace."
    ),
}
_NO_CONTESTAN_DE_MEMORIA = frozenset(_RECORDATORIO)


def _lo_que_escribio(mensaje: str) -> dict[str, Any]:
    """El mensaje de la persona, marcado para que la salvaguarda de entrada mire sólo eso.

    Sin la marca, Bedrock evalúa como entrada todo el historial en cada turno. En la
    prueba de seguimiento del 2/11, «hoy me tomé el ibuprofeno de la mañana y me puse
    hielo» se bloqueó como `MISCONDUCT`, y el mismo mensaje, evaluado solo, pasa: lo
    que disparó el filtro fue el resto de la conversación —medicamentos, el plan, las
    notas del sistema—. Los mensajes anteriores ya se evaluaron en su turno, y lo que
    responde el agente lo sigue evaluando la salvaguarda de salida, así que no se pierde
    nada. Sin salvaguarda configurada, `bedrock_conversa` lo vuelve texto normal.
    """
    return {"guardContent": {"text": {"text": mensaje}}}


def _turno_de_la_persona(mensaje: str, agente: agentes.Agente) -> list[dict[str, Any]]:
    contenido = [_lo_que_escribio(mensaje)]
    if agente.clave in _RECORDATORIO:
        contenido.append({"text": _RECORDATORIO[agente.clave]})
    return contenido


def _herramientas_de(
    agente: agentes.Agente, rol: str, *, con_caso: bool
) -> list[dict[str, Any]]:
    """Sólo se declaran las herramientas que se pueden usar de verdad ahora mismo.

    Dos filtros. El rol, porque filtrar aquí y no al ejecutar evita que el modelo
    prometa a la persona algo que después le va a ser negado. Y el caso: en una
    consulta general no hay sobre quién agendar, así que esas herramientas no se
    declaran —si se declararan, el modelo pediría un nombre para buscar el caso, que
    es justo lo que el sistema no hace.

    Ninguno de los dos es la última defensa: la función de herramientas vuelve a
    comprobar el rol y a exigir el caso antes del efecto.
    """
    disponibles = tuple(
        n
        for n in agente.herramientas
        if permitida(n, rol) and (con_caso or not necesita_caso(n))
    )
    return especificaciones(disponibles)


def _con_la_ruta_de_emergencia(
    texto: str, usos: list[bedrock_conversa.Uso], *, intervino: bool
) -> str:
    """Garantiza que quien escaló una urgencia reciba la ruta de emergencia.

    `escalar_urgencia` —y `canalizar_caso` con nivel 1— devuelven en
    `decir_a_la_persona` el texto que no puede faltar. Hasta ahora decirlo dependía
    del modelo, y el 24/09 eso falló de la peor forma: el agente escalaba, iba a
    decir la ruta y la salvaguarda de salida le cambiaba la respuesta por «Prefiero
    no responder eso». La urgencia quedaba registrada y la persona, sin saber a quién
    llamar.

    Si la salvaguarda intervino en un turno con escalamiento, lo que se dice es la
    ruta y nada más: la negativa no aporta nada y la contradice. Si no intervino pero
    el modelo no dijo la ruta, se antepone. Si ya la dijo, no se toca.
    """
    ruta = next(
        (
            str(u.resultado["decir_a_la_persona"])
            for u in usos
            if u.ok
            and isinstance(u.resultado, dict)
            and u.resultado.get("decir_a_la_persona")
        ),
        "",
    )
    if not ruta:
        return texto
    if intervino or not texto:
        return ruta
    if " ".join(ruta.split()) in " ".join(texto.split()):
        return texto
    return f"{ruta}\n\n{texto}"


def _traspaso(agente: agentes.Agente, resultado: bedrock_conversa.Resultado) -> str | None:
    """A quién pasa la conversación, si pasa.

    La herramienta decide si hay cita que buscar (`agendar`), no este bucle: con
    nivel 1 ya se escaló y con nivel 4 no hay cita. Pasarle esos casos a agenda era
    ponerla a buscar espacios que el protocolo dice que no tocan.
    """
    if not agente.traspaso:
        return None
    disparador, destino = agente.traspaso
    for uso in resultado.usos:
        if uso.nombre == disparador and uso.ok and uso.resultado.get("agendar", True):
            return destino
    return None


def _contexto_del_traspaso(caso: dict[str, Any]) -> str:
    nivel = plazos.nivel_de(caso)
    plazo = f" (cita dentro de {plazos.texto_de(nivel)})" if plazos.plazo_de(nivel) else ""
    return (
        f"El agente anterior acaba de canalizar este caso al {caso.get('centro')} "
        f"con nivel de urgencia {caso.get('nivel_urgencia')}{plazo}. Continúas tú, en la "
        "misma conversación: no te presentes de nuevo ni repitas lo que ya se dijo."
    )


def _contexto_del_caso_nuevo() -> str:
    return (
        "La persona trajo un problema distinto del de su otro caso, y este caso se abrió "
        "para él. Empiezas su triaje en la misma conversación: no te presentes de nuevo "
        "ni le preguntes por el otro caso, que sigue su curso."
    )


def _caso_nuevo(resultado: bedrock_conversa.Resultado) -> str:
    """El caso que abrió `nuevo_motivo` en esta vuelta, si abrió uno."""
    for uso in resultado.usos:
        if uso.nombre == "nuevo_motivo" and uso.ok and isinstance(uso.resultado, dict):
            return str(uso.resultado.get("caso_nuevo") or "")
    return ""


def _dejar_constancia_de_los_fallos(
    acceso: AccesoRoble, *, hilo_id: str, agente: str, usos: list[bedrock_conversa.Uso]
) -> None:
    """Escribe en el caso qué herramientas fallaron, junto a lo que dijo el agente.

    El texto del agente se guarda tal cual y vuelve como historial en la petición
    siguiente. Si en esa respuesta prometió algo que la herramienta no hizo, el
    modelo se lo encuentra después como un hecho suyo y lo defiende: fue así como
    una cita que nunca se agendó pasó a estar «pendiente de que el centro llame».
    La nota va al lado para que el historial diga también lo que no ocurrió. Si el
    agente no dijo nada, la nota va sola: el fallo se registra igual.

    Se anota como `sistema` y no como una fila más de la conversación: la persona
    no la ve —la vista del paciente descarta esas filas al pintar el historial—, y
    en la bitácora del caso queda distinguible de lo que sí se le dijo.
    """
    fallidas = sorted({u.nombre for u in usos if not u.ok})
    if not fallidas:
        return

    acceso.anotar_mensaje(
        caso_id=hilo_id,
        agente=agente,
        autor="sistema",
        contenido=(
            "[sistema] En el turno anterior no se completó: "
            + ", ".join(fallidas)
            + ". Nada de lo que dependía de esas herramientas quedó hecho, por mucho "
            "que la respuesta anterior lo diera por hecho. Si hace falta, vuelve a "
            "intentarlo ahora; no lo presentes como algo ya resuelto ni pendiente de "
            "que alguien lo confirme por fuera."
        ),
    )


_HACEN_LA_CITA = ("agendar_cita", "reprogramar_cita", "cancelar_cita")
_MUESTRAN_ESPACIOS = ("consultar_disponibilidad", "agendar_cita", "reprogramar_cita")


def _hizo_la_cita(usos: list[bedrock_conversa.Uso]) -> bool:
    """¿Agendó, cambió o canceló de verdad alguna herramienta en este turno?"""
    return any(
        u.nombre in _HACEN_LA_CITA and u.ok and isinstance(u.resultado, dict) and u.resultado.get("ok")
        for u in usos
    )


def _opciones_mostradas(usos: list[bedrock_conversa.Uso]) -> list[dict[str, Any]]:
    """Los últimos espacios que vio el modelo en el turno, con su «inicio» literal."""
    for uso in reversed(usos):
        if uso.nombre not in _MUESTRAN_ESPACIOS or not isinstance(uso.resultado, dict):
            continue
        for clave in ("opciones", "alternativas"):
            lista = uso.resultado.get(clave)
            if isinstance(lista, list) and lista and all(isinstance(o, dict) and o.get("inicio") for o in lista):
                return lista[:4]
    return []


def _dejar_constancia_de_la_agenda(
    acceso: AccesoRoble, *, hilo_id: str, agente: str, usos: list[bedrock_conversa.Uso]
) -> None:
    """Escribe en el caso los espacios que se ofrecieron y lo que quedó por confirmar.

    Lo que devuelven las herramientas no vuelve como historial —no se rehidratan los
    bloques de herramientas—, así que en el turno siguiente el modelo sólo tiene lo
    que le dijo a la persona: «martes 03/11 a las 08:30», no el «inicio» exacto. En la
    prueba del 2/11 lo reconstruyó mal y `agendar_cita` no encontró un espacio que
    estaba libre; y al «sí, confirmo» de un cambio contestó «listo, tu cita está
    reprogramada» sin llamar a nada, con la cita en el mismo sitio. La nota deja
    escrito con qué se cumple lo que la persona elija o confirme.

    Cancelar y cambiar van en dos turnos: la herramienta devuelve lo que haría, la
    persona confirma y en el siguiente se la llama con `confirmado`.
    """
    pendientes: dict[str, bedrock_conversa.Uso] = {}
    for uso in usos:
        resultado = uso.resultado if isinstance(uso.resultado, dict) else {}
        if uso.nombre not in ("reprogramar_cita", "cancelar_cita"):
            continue
        if uso.ok and resultado.get("confirmar_primero"):
            pendientes[uso.nombre] = uso
        elif uso.ok and resultado.get("ok"):
            # Preguntó y la persona ya había dicho que sí en el mismo turno.
            pendientes.pop(uso.nombre, None)
    # Con la cita ya hecha, los espacios que se vieron antes no sirven para nada.
    opciones = [] if _hizo_la_cita(usos) else _opciones_mostradas(usos)
    if not pendientes and not opciones:
        return

    partes = []
    if opciones:
        partes.append(
            "Espacios que se le mostraron, con el «inicio» que hay que copiar tal cual "
            "si elige uno: "
            + "; ".join(f"{o.get('cuando')} = «{o.get('inicio')}»" for o in opciones)
            + "."
        )
    if pendientes:
        partes.append(_lo_pendiente(pendientes))
    acceso.anotar_mensaje(
        caso_id=hilo_id, agente=agente, autor="sistema", contenido="[sistema] " + " ".join(partes)
    )


def _lo_pendiente(pendientes: dict[str, bedrock_conversa.Uso]) -> str:
    llamadas = []
    for nombre, uso in pendientes.items():
        cita_actual = str(uso.argumentos.get("cita_actual") or "")
        con_cita = f", cita_actual «{cita_actual}»" if cita_actual else ""
        if nombre == "reprogramar_cita":
            llamadas.append(
                f"cambiar la cita del {uso.resultado.get('de')} a la del "
                f"{uso.resultado.get('a')}, que se cumple llamando a reprogramar_cita con "
                f"inicio «{uso.argumentos.get('inicio')}»{con_cita} y confirmado en true"
            )
        else:
            cita = uso.resultado.get("cita") or {}
            llamadas.append(
                f"cancelar la cita del {cita.get('cuando')}, que se cumple llamando a "
                f"cancelar_cita{con_cita} con confirmado en true"
            )
    return (
        "Quedó esperando la respuesta de la persona y todavía no se cambió nada: "
        + "; ".join(llamadas)
        + ". Si dice que sí, haz esa llamada en este turno, y sólo cuando la "
        "herramienta responda ok le dices que quedó hecho. Si dice que no o pide otra "
        "cosa, no la hagas."
    )


# Lo que delata que una respuesta da una cita por hecha. «Agendada» o «confirmada»
# también se dice al repetir una cita que existe, así que se contrasta con la agenda.
_DA_POR_HECHA = re.compile(
    r"\b(?:qued[oóa]|est[aá]|fue)\s+(agendada|confirmada|reprogramada|cambiada|cancelada|anulada)\b"
    r"|\b(reprogram[eé]|cancel[eé]|cambi[eé]|agend[eé])\b",
    re.IGNORECASE,
)
_DIA_Y_MES = re.compile(r"\b(\d{1,2})/(\d{1,2})\b")
_FRASES = re.compile(r"(?<=[.!?])\s+|\n+")


def _cita_inventada(
    texto: str, usos: list[bedrock_conversa.Uso], reales: list[dict[str, Any]]
) -> bool:
    """¿Da la respuesta por hecha una cita que ninguna herramienta hizo en el turno?

    Se mira frase por frase: la fecha que cuenta es la de la frase que afirma, no la
    de una opción que se ofrece dos líneas más abajo. Con una herramienta que agendó,
    cambió o canceló en el turno, lo que diga se da por bueno.
    """
    if _hizo_la_cita(usos):
        return False
    reales_dia = {
        f"{local.day:02d}/{local.month:02d}"
        for local in (reloj.en_bogota(c.get("inicio")) for c in reales)
        if local
    }
    for frase in _FRASES.split(texto or ""):
        afirmaciones = [
            m.group(1) or m.group(2)
            for m in _DA_POR_HECHA.finditer(frase)
            if not re.search(r"\bno\s*$|\bno\s+\w+\s*$", frase[: m.start()].lower())
        ]
        dichas = {f"{int(d):02d}/{int(m):02d}" for d, m in _DIA_Y_MES.findall(frase)}
        for afirmacion in afirmaciones:
            if afirmacion.lower().startswith(("cancel", "anul")):
                # Cancelada es cierto si esa cita ya no está por delante.
                if reales_dia and (not dichas or dichas & reales_dia):
                    return True
            elif not reales_dia or dichas - reales_dia:
                return True
    return False


def _citas_reales(acceso: AccesoRoble, caso_id: str) -> list[dict[str, Any]]:
    return [c for c in acceso.citas_del_caso(caso_id) if cita_por_delante(c)]


def _sin_citas_inventadas(
    acceso: AccesoRoble,
    *,
    caso_id: str,
    resultado: bedrock_conversa.Resultado,
    usos: list[bedrock_conversa.Uso],
    llamada: dict[str, Any],
) -> tuple[str, bedrock_conversa.Resultado | None]:
    """La respuesta del turno, sin una cita que ninguna herramienta hizo.

    En la prueba del 2/11 el agente de agenda, sin llamar a nada, le dijo a la persona
    «listo, tu cita quedó agendada para el miércoles» y el caso no tenía ninguna cita.
    El prompt ya lo prohibía, y después de reforzarlo volvió a pasar: no basta con
    pedírselo al modelo. Si la respuesta afirma una cita que la agenda no tiene, no
    sale. El mismo agente responde otra vez con la agenda real delante, y si vuelve a
    inventarla la persona recibe un texto fijo con lo que de verdad hay.
    """
    try:
        reales = _citas_reales(acceso, caso_id)
    except ErrorDeCareSync as exc:
        # Sin poder leer la agenda no se puede contrastar. Se entrega lo que hay.
        evento(log, "agenda_no_contrastada", caso_id=caso_id, detalle=type(exc).__name__)
        return resultado.texto, None
    if not _cita_inventada(resultado.texto, usos, reales):
        return resultado.texto, None

    evento(log, "cita_sin_respaldo", caso_id=caso_id)
    if reales:
        agenda = "Lo que el caso de verdad tiene por delante: " + "; ".join(
            reloj.humano(c.get("inicio")) for c in reales
        ) + "."
    else:
        agenda = "El caso no tiene ninguna cita por delante."
    # «Para ella es tu primera respuesta» no sobra: sin eso, en la prueba del 2/11 el
    # modelo arrancó con «Tienes razón, disculpa», como si la persona le hubiera
    # reclamado algo que nunca leyó.
    nota = (
        "[sistema] Esa respuesta no le llegó a la persona: da por hecha una cita que "
        f"ninguna herramienta hizo en este turno. {agenda} Si la persona eligió o "
        "confirmó algo, haz ahora la llamada que corresponde; si no, respóndele sin "
        "darlo por hecho. La persona no leyó tu respuesta anterior ni lee este aviso: "
        "para ella lo que digas ahora es tu primera respuesta, así que no te disculpes, "
        "no le des la razón ni digas que corriges algo."
    )
    try:
        extra = bedrock_conversa.conversar(
            mensajes=[*resultado.mensajes, {"role": "user", "content": [{"text": nota}]}],
            **llamada,
        )
    except Exception as exc:  # noqa: BLE001 - lo que se le dice no depende del modelo
        evento(log, "correccion_fallida", caso_id=caso_id, detalle=type(exc).__name__)
        return _lo_que_de_verdad_hay(reales), None

    if any(u.nombre in _HACEN_LA_CITA for u in extra.usos):
        try:
            reales = _citas_reales(acceso, caso_id)
        except ErrorDeCareSync:
            pass
    if (
        extra.intervino_guardrail
        or not extra.texto
        or _cita_inventada(extra.texto, [*usos, *extra.usos], reales)
    ):
        evento(log, "cita_sin_respaldo_otra_vez", caso_id=caso_id)
        return _lo_que_de_verdad_hay(reales), extra
    return extra.texto, extra


def _lo_que_de_verdad_hay(reales: list[dict[str, Any]]) -> str:
    if reales:
        return (
            "Perdona, me adelanté: ese cambio no quedó hecho. Tu cita sigue siendo el "
            f"{reloj.humano(reales[0].get('inicio'))}. ¿Quieres que lo intentemos de nuevo?"
        )
    return (
        "Perdona, me adelanté: todavía no tienes ninguna cita agendada. ¿Quieres que "
        "busque los espacios disponibles para agendarla?"
    )


def _cambiar_el_final(texto: str, viejo: str, nuevo: str) -> str:
    """Cambia la última respuesta dentro del texto del turno, que puede traer otra antes."""
    antes, encontrado, despues = texto.rpartition(viejo)
    return f"{antes}{nuevo}{despues}" if encontrado else nuevo


def _nota_de_traspaso(caso: dict[str, Any]) -> str:
    """El turno sintético que abre la vuelta del segundo agente.

    Converse necesita que el último mensaje sea del usuario para responder, y la
    persona no escribió nada nuevo: el traspaso lo disparó una herramienta. Así
    que se inserta un turno con la marca `[sistema]`, que el prompt común declara
    como algo que el agente no debe atribuir a la persona ni citar.
    """
    return (
        "[sistema] El caso quedó canalizado al "
        f"{caso.get('centro')} con nivel de urgencia {caso.get('nivel_urgencia')}. "
        "Sigue tú desde aquí, sin saludar de nuevo."
    )


# --------------------------------------------------- ejecución de herramientas

def _ejecutor(*, token: str, caso_id: str, agente: str):
    """Devuelve la función que el bucle usa para ejecutar una herramienta.

    Los argumentos de identidad —token, caso, rol— los pone el orquestador, no el
    modelo. El modelo sólo controla los argumentos del catálogo. Esa frontera es
    lo que impide que una respuesta del modelo pida el caso de otra persona.
    """

    def ejecutar(nombre: str, argumentos: dict[str, Any]) -> dict[str, Any]:
        if not FUNCION_HERRAMIENTAS:
            raise ErrorDeDatos("No está configurada la función de herramientas")

        carga = {
            "herramienta": nombre,
            "argumentos": argumentos,
            "contexto": {
                # El token viaja por la API de Lambda, cifrada en tránsito, y no
                # queda en ningún log: las cargas de invocación no se registran.
                "access_token": token,
                "caso_id": caso_id,
                "agente": agente,
            },
        }

        respuesta_lambda = _lambda().invoke(
            FunctionName=FUNCION_HERRAMIENTAS,
            InvocationType="RequestResponse",
            Payload=json.dumps(carga).encode("utf-8"),
        )

        crudo = respuesta_lambda["Payload"].read().decode("utf-8") or "{}"
        if respuesta_lambda.get("FunctionError"):
            evento(log, "herramienta_reventada", herramienta=nombre, detalle=crudo[:400])
            raise ErrorDeDatos(f"La herramienta {nombre} falló")

        try:
            datos = json.loads(crudo)
        except ValueError as exc:
            raise ErrorDeDatos(f"La herramienta {nombre} devolvió algo ilegible") from exc

        if isinstance(datos, dict) and datos.get("error"):
            # Error de dominio: se le devuelve al modelo tal cual para que lo
            # explique, en vez de romper la conversación.
            return datos
        return datos if isinstance(datos, dict) else {"resultado": datos}

    return ejecutar


# ------------------------------------------------------------------ simulación
#
# Un profesional se pone en los zapatos de un paciente y corre un triaje de
# prueba, para ver qué decide el modelo y compararlo con su propio criterio. Todo
# este bloque es un camino de código aparte, y la separación es la garantía:
# ninguna función de aquí abajo llama a `_ejecutor`, a `_lambda().invoke`, a
# `acceso.abrir_caso`, a `acceso.caso_visible`, a `caso_abierto_de` ni a
# `actualizar_caso`. Lo único que escribe son los turnos de la conversación y los
# eventos de la bitácora, las dos cosas que el rol `user` de ROBLE puede crear.
#
# Lo que sí sigue vivo es lo que se está evaluando: el prompt, el protocolo, el
# guardarrail de Bedrock y las salvaguardas. Una simulación que los esquivara no
# mediría nada.

# Quién puede simular. Un **paciente nunca**, y no es una cuestión de jerarquía:
# si un paciente pudiera pedir `simulacion: true`, una urgencia real —un dolor de
# pecho escrito en la vista del paciente— quedaría atendida por un sandbox que no
# marca el caso, no escribe el evento `urgencia_escalada` y, sobre todo, no emite
# `ESCALAMIENTO`, así que no dispara la alarma de CloudWatch y nadie se entera. La
# persona recibiría el texto de la ruta de emergencia y el sistema no habría hecho
# nada. El modo existe para evaluar, y quien evalúa es el equipo de atención.
ROLES_QUE_SIMULAN = frozenset({PROFESIONAL, ADMIN_CMU, ADMIN_CAE})

# Hoy sólo se simula el triaje: es el agente que se está evaluando y el único cuyas
# herramientas se pueden ejecutar en seco sin inventarle datos a nadie. Simular al
# de agenda obligaría a fabricar cupos y profesionales, y ofrecerle a la persona una
# hora que no existe no mide nada. Pedir otro agente es un 400 explícito y no un
# cambio silencioso: si la vista cree que evalúa agenda y se le responde con triaje,
# la medición queda contaminada sin que nadie lo note.
AGENTES_SIMULABLES = frozenset({agentes.TRIAJE})

LIMITE_SLUG = 40
_ALFABETO_SLUG = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")

# El paciente que se le presenta al modelo. Sin esto el prompt diría «hablas con
# Ana Gómez, cuyo rol es profesional» y el triaje no se comportaría como el que
# atiende a un paciente: preguntaría por el caso de otra persona en vez de por
# cómo se siente quien escribe, y lo que se mediría sería otro agente.
#
# Es sintético y sirve **sólo** para `agentes.instrucciones(...)`. Las escrituras
# siguen yendo por `acceso`, cuyo `actor` es el profesional de verdad, así que en
# `eventos` queda su `actor_user_id` y su `actor_rol`. Invariante 1 intacto: la
# identidad la pone el orquestador, no el modelo, y aquí tampoco la pone el modelo
# —la pone esta constante.
_PACIENTE_SIMULADO = Actor(
    user_id="",
    email="",
    nombre="una persona de la comunidad universitaria",
    rol=PACIENTE,
)

# Copia de `triaje._plazo`, que vive en el otro paquete de despliegue. Importarlo
# significaría que el orquestador puede ejecutar las herramientas de verdad, que es
# exactamente lo que esta separación impide. Si cambian los plazos del protocolo, este
# diccionario hay que tocarlo a mano.
# Los mismos plazos que usa la herramienta real, del mismo sitio: con una copia aparte
# aquí, un cambio del protocolo dejaría al simulador evaluando otro plazo.
_PLAZO_SIMULADO = plazos.TEXTO


def _pide_simulacion(cuerpo: dict[str, Any]) -> bool:
    """¿Esta petición es una simulación?

    Se admite el booleano de JSON y también el texto, con la misma lista de
    verdaderos que usa la validación de argumentos de la función de herramientas:
    un cliente que serializa `true` como cadena no debería acabar corriendo una
    conversación real por accidente.
    """
    valor = cuerpo.get("simulacion")
    if isinstance(valor, bool):
        return valor
    return str(valor or "").strip().lower() in ("true", "1", "si", "sí", "yes")


def _slug_de_simulacion(valor: Any) -> str:
    """Saneado del `simulacion_id` que manda la vista.

    El slug acaba dentro de `conversaciones.caso_id`, que es la clave por la que se
    lee el hilo, así que no puede llevar nada raro: minúsculas, `[a-z0-9-]` y 40
    caracteres. Lo que no encaja se convierte en guion en vez de descartarse, para
    que «Dolor de pecho» siga siendo legible como `dolor-de-pecho` en la bitácora.

    Si no viene o queda vacío se genera uno del reloj: la alternativa —fallar con un
    400— obligaría a la vista a inventar identificadores para algo que es de usar y
    tirar.
    """
    crudo = str(valor or "").strip().lower()
    limpio = "".join(c if c in _ALFABETO_SLUG else "-" for c in crudo)
    while "--" in limpio:
        limpio = limpio.replace("--", "-")
    limpio = limpio.strip("-")[:LIMITE_SLUG].strip("-")
    return limpio or reloj.ahora().strftime("s-%Y%m%d-%H%M%S")


def _simular(
    acceso: AccesoRoble, *, mensaje: str, cuerpo: dict[str, Any]
) -> dict[str, Any]:
    """Corre un triaje de prueba sin efecto real, para evaluar al modelo.

    **Sólo simula el equipo de atención** (`ROLES_QUE_SIMULAN`). Un paciente nunca:
    si pudiera pedir `simulacion: true`, una urgencia real escrita en la vista del
    paciente quedaría atendida por este sandbox, que no marca el caso, no escribe el
    evento `urgencia_escalada` y no emite `ESCALAMIENTO`, así que no dispara la alarma
    de CloudWatch y nadie se entera. La persona leería la ruta de emergencia y el
    sistema no habría hecho nada. Rol no autorizado, `SinPermiso`.

    Lo que cambia respecto a `_conversar`, y por qué:

    * **No hay caso.** `caso_id` queda vacío, nada se escribe en `casos` y el hilo
      se guarda bajo `simulacion:<user_id>:<slug>`. El truco ya estaba en el camino
      real (`hilo_id = caso_id or f"consulta:{actor.user_id}"`): `caso_id` es texto
      libre en `conversaciones`, y una columna nueva no era opción porque ROBLE no
      admite `alter`. El prefijo además deja dicho quién simuló.
    * **Un solo agente y una sola vuelta de `conversar`.** No hay traspaso: el
      agente de agenda consultaría disponibilidad de cupos reales y ofrecería horas
      que sí existen. La respuesta lo dice en `agentes`.
    * **Las herramientas se declaran pero se ejecutan en seco.** Ver
      `_ejecutor_simulado`.
    * **El prompt recibe un paciente sintético y un caso sintético**, porque sin
      ellos no se está midiendo al agente de triaje sino a otra cosa.

    Lo que no cambia: el guardarrail, las salvaguardas, la garantía de la ruta de
    emergencia, la constancia de los fallos y la memoria del hilo entre turnos.
    """
    actor = acceso.actor
    if actor.rol not in ROLES_QUE_SIMULAN:
        raise SinPermiso(f"El rol «{actor.rol}» no puede correr una simulación")

    solicitado = str(cuerpo.get("agente") or "").strip().lower() or agentes.TRIAJE
    if solicitado not in AGENTES_SIMULABLES:
        raise SolicitudInvalida(
            f"Todavía no se puede simular el agente «{solicitado}»",
            publico="Por ahora sólo se puede simular el triaje.",
        )
    agente = agentes.AGENTES[solicitado]

    slug = _slug_de_simulacion(cuerpo.get("simulacion_id"))
    hilo_id = f"simulacion:{actor.user_id}:{slug}"

    # El turno de la persona se anota como `paciente` y no con el rol real de quien
    # escribe. Es el papel que se está interpretando: con `autor="profesional"`,
    # `_historial` le pondría delante la marca `[profesional que atiende]`, el modelo
    # dejaría de hablarle a un paciente y lo que se mediría sería el triaje
    # atendiendo a un profesional —otro comportamiento, otra medición. De quién es la
    # simulación queda constancia en dos sitios que no dependen de esto: el prefijo
    # `simulacion:<user_id>` del hilo y el `actor_user_id` de cada evento
    # `simulacion_triaje`.
    acceso.anotar_mensaje(
        caso_id=hilo_id, agente=agente.clave, autor=PACIENTE, contenido=mensaje
    )

    # Mismo historial que el camino real: la simulación tiene memoria de un turno a
    # otro, que es justo lo que hace falta para evaluar una conversación de cinco
    # preguntas y no cinco primeros turnos.
    hilo = _historial(acceso, hilo_id)
    hilo.append({"role": "user", "content": [_lo_que_escribio(mensaje)]})

    decisiones: list[dict[str, Any]] = []
    resultado = bedrock_conversa.conversar(
        sistema=agentes.instrucciones_partidas(
            agente,
            actor=_PACIENTE_SIMULADO,
            # Un caso sintético que no se escribe en ninguna parte. Con `caso=None`,
            # `instrucciones` le dice al modelo que «las herramientas que necesitan un
            # caso no están disponibles aquí», y entonces no llamaría a
            # `canalizar_caso` ni a `escalar_urgencia`: no habría nada que evaluar.
            caso={"_id": hilo_id, "estado": CASO_ABIERTO},
        ),
        mensajes=hilo,
        herramientas=_herramientas_simuladas(agente),
        ejecutar=_ejecutor_simulado(acceso, hilo_id=hilo_id, slug=slug, decisiones=decisiones),
    )

    texto = _con_la_ruta_de_emergencia(
        resultado.texto, resultado.usos, intervino=resultado.intervino_guardrail
    )

    if texto:
        acceso.anotar_mensaje(
            caso_id=hilo_id, agente=agente.clave, autor="agente", contenido=texto
        )
    # Invariante 8 también aquí: si una herramienta simulada devolvió error, el turno
    # siguiente tiene que encontrarlo escrito. Sin esa nota el modelo defiende en el
    # turno siguiente una canalización que no ocurrió, y el profesional estaría
    # evaluando una conversación que no se corresponde con lo que decidió el modelo.
    _dejar_constancia_de_los_fallos(
        acceso, hilo_id=hilo_id, agente=agente.clave, usos=resultado.usos
    )

    # Nombres de evento en minúsculas, y ni uno con el literal `ESCALAMIENTO`. De ese
    # literal cuelga el filtro de métrica de CloudWatch (`infra/observabilidad.tf`,
    # `pattern = "ESCALAMIENTO"`, texto plano y sensible a mayúsculas) y de ahí la
    # alarma que avisa a una persona. Que el filtro mire hoy el grupo de la función de
    # herramientas y esto corra en el orquestador no es la garantía: ampliar el filtro
    # a todos los grupos de CareSync es una línea de Terraform, y entonces cada
    # simulación levantaría a alguien de la cama.
    evento(
        log,
        "simulacion_atendida",
        caso_id=hilo_id,
        simulacion_id=slug,
        agentes=[agente.clave],
        herramientas=[u.nombre for u in resultado.usos],
        tokens_entrada=resultado.tokens_entrada,
        tokens_salida=resultado.tokens_salida,
        tokens_cacheados=resultado.tokens_cacheados,
        guardrail=resultado.intervino_guardrail,
        salvaguardas=sorted(set(resultado.salvaguardas)),
    )

    return respuesta.ok(
        {
            "respuesta": texto,
            # Siempre `null`: no hay caso y no lo habrá. Si aquí fuera un objeto, la
            # vista creería que el hilo tiene sujeto y lo reenviaría como `caso_id`
            # en el turno siguiente.
            "caso": None,
            "agentes": [agente.clave],
            "acciones": [
                {"herramienta": u.nombre, "ok": u.ok, "resultado": u.resultado}
                for u in resultado.usos
            ],
            "salvaguardas_intervinieron": resultado.intervino_guardrail,
            "salvaguardas_detalle": sorted(set(resultado.salvaguardas)),
            "simulacion": True,
            # El slug ya saneado, no el que llegó: la vista lo necesita para volver a
            # escribir en el mismo hilo en el turno siguiente.
            "simulacion_id": slug,
            # Sólo existe en simulación. Es lo que el profesional juzga: qué centro
            # eligió el modelo, con qué nivel, con qué resumen y si escaló. `acciones`
            # no sirve para eso porque no lleva los argumentos.
            "decisiones": decisiones,
        }
    )


def _herramientas_simuladas(agente: agentes.Agente) -> list[dict[str, Any]]:
    """Las herramientas del agente, todas, sin filtrar por rol ni por caso.

    Al contrario que `_herramientas_de`, aquí no se llama a `permitida(nombre, rol)`:
    el rol real es `profesional` y `canalizar_caso` es sólo de pacientes, así que el
    filtro dejaría al modelo sin la decisión que se le quiere medir. Tampoco se filtra
    por `necesita_caso`, porque el caso sintético existe para el prompt.

    No se toca `permitida()` ni el catálogo, y la autorización de verdad sigue
    intacta: lo que hace que esto sea seguro no es un filtro, es que **ninguna llamada
    sale de este proceso**. El ejecutor de abajo no habla con la función de
    herramientas, que de todos modos volvería a comprobar el rol antes del efecto.
    """
    return especificaciones(agente.herramientas)


def _ejecutor_simulado(
    acceso: AccesoRoble, *, hilo_id: str, slug: str, decisiones: list[dict[str, Any]]
):
    """Devuelve el ejecutor en seco: valida igual, responde igual, no hace nada.

    Lo que el modelo recibe tiene la **misma forma** que el resultado real
    (`lambdas/herramientas/triaje.py`), con un `simulado: True` añadido para que ni
    el modelo ni la vista confundan esto con un efecto. La forma importa: si
    `canalizar_caso` no devolviera `agendar` y `plazo`, el modelo cerraría de otra
    manera y lo que se mediría no sería lo que pasa en producción.

    Los argumentos se validan antes, porque un error de validación es parte de lo que
    se evalúa: si el modelo llama a `canalizar_caso` sin `resumen`, en producción
    recibe un error y tiene que reintentar, y eso es exactamente lo que el
    profesional tiene que ver.
    """

    def ejecutar(nombre: str, argumentos: dict[str, Any]) -> dict[str, Any]:
        herramienta = CATALOGO.get(nombre)
        simulador = _SIMULADORES.get(nombre)
        if not herramienta or not simulador:
            salida = _error_simulado(nombre, f"No existe la herramienta «{nombre}»")
        else:
            try:
                limpios = _argumentos_simulados(nombre, herramienta, argumentos)
                salida = simulador(limpios)
            except SolicitudInvalida as exc:
                # Igual que en la función de herramientas: el error de dominio sale
                # dentro del resultado y no como excepción, para que el modelo lo
                # explique en vez de romper la conversación.
                salida = _error_simulado(nombre, exc.mensaje, publico=exc.publico)

        ok = not salida.get("error")
        decisiones.append(
            {
                "herramienta": nombre,
                "argumentos": dict(argumentos) if isinstance(argumentos, dict) else {},
                "resultado": salida,
                "ok": ok,
            }
        )

        # La bitácora recoge sólo las herramientas que en producción escribirían algo:
        # consultar el estado no decide nada y cada fila en ROBLE gasta de la cuota de
        # 100 operaciones por minuto y por IP, que una tanda de simulaciones agota.
        if herramienta and herramienta.escribe:
            _anotar_decision_simulada(
                acceso,
                hilo_id=hilo_id,
                slug=slug,
                nombre=nombre,
                argumentos=argumentos,
                ok=ok,
            )
        return salida

    return ejecutar


def _error_simulado(nombre: str, detalle: str, publico: str = "") -> dict[str, Any]:
    """Un error con la misma forma que devuelve la función de herramientas."""
    evento(log, "simulacion_herramienta_rechazada", herramienta=nombre, detalle=detalle)
    return {
        "error": publico or SolicitudInvalida.publico,
        "herramienta": nombre,
        "simulado": True,
    }


def _argumentos_simulados(
    nombre: str, herramienta: Any, crudos: dict[str, Any]
) -> dict[str, Any]:
    """Lo mínimo de `_argumentos()` que hace falta para que el modelo vea lo mismo.

    Es una copia reducida de la validación que vive en `herramientas/handler.py`, y la
    copia es el precio de no tener aquí ningún camino que pueda producir un efecto:
    ese módulo es otro paquete de despliegue y traerlo implicaría poder llamarlo.
    Se comprueban las tres cosas que cambian lo que el modelo recibe —claves no
    declaradas, argumentos requeridos y `enum`— y se recortan los enteros a su rango,
    igual que allí. El esquema completo ya lo valida Bedrock.
    """
    if not isinstance(crudos, dict):
        raise SolicitudInvalida(f"Los argumentos de {nombre} no son un objeto")

    limpios: dict[str, Any] = {}
    for clave, esquema in herramienta.propiedades.items():
        if clave not in crudos or crudos[clave] is None:
            continue
        valor = crudos[clave]
        if esquema.get("type") == "integer":
            try:
                numero = int(float(str(valor).strip()))
            except (TypeError, ValueError) as exc:
                raise SolicitudInvalida(f"{nombre}.{clave} debe ser un entero") from exc
            minimo, maximo = esquema.get("minimum"), esquema.get("maximum")
            if minimo is not None:
                numero = max(int(minimo), numero)
            if maximo is not None:
                numero = min(int(maximo), numero)
            limpios[clave] = numero
            continue
        if esquema.get("type") == "boolean":
            # Como en la función de herramientas. Sin esto, un `false` llegaba como el
            # texto «False», que es verdadero, y `orientacion_resuelta` en false cerraba
            # el caso simulado.
            limpios[clave] = (
                valor
                if isinstance(valor, bool)
                else str(valor).strip().lower() in ("true", "1", "si", "sí", "yes")
            )
            continue
        texto = str(valor).strip()
        opciones = esquema.get("enum")
        if opciones and texto not in opciones:
            raise SolicitudInvalida(
                f"{nombre}.{clave} debe ser uno de: {', '.join(map(str, opciones))}"
            )
        limpios[clave] = texto

    faltan = [c for c in herramienta.requeridos if c not in limpios]
    if faltan:
        raise SolicitudInvalida(f"A {nombre} le faltan argumentos: {', '.join(faltan)}")
    return limpios


def _anotar_decision_simulada(
    acceso: AccesoRoble,
    *,
    hilo_id: str,
    slug: str,
    nombre: str,
    argumentos: dict[str, Any],
    ok: bool,
) -> None:
    """Deja la decisión en la bitácora, para poder contarlas después.

    La vista del profesional lista estos eventos para llevar la cuenta de cuánto
    coincidió el modelo con su criterio, así que el `detalle` lleva el centro y el
    nivel cuando los haya: sin ellos el evento no sirve para comparar nada.

    La severidad es `info` siempre, incluso en un nivel 1. Un escalamiento simulado
    con severidad `critica` aparecería en la bitácora igual que uno de verdad, y
    quien revise los casos urgentes perdería el tiempo en uno que nunca existió.

    Si la escritura falla, la simulación no se cae: el profesional pierde el registro
    de la decisión, pero no la conversación que estaba evaluando.
    """
    detalle: dict[str, Any] = {
        "simulacion_id": slug,
        "herramienta": nombre,
        "ok": ok,
        "simulado": True,
    }
    if isinstance(argumentos, dict):
        for clave in ("centro", "nivel_urgencia", "motivo", "resumen"):
            if argumentos.get(clave) not in (None, ""):
                detalle[clave] = argumentos[clave]

    try:
        acceso.registrar_evento(
            caso_id=hilo_id, tipo="simulacion_triaje", severidad="info", detalle=detalle
        )
    except Exception as exc:  # noqa: BLE001 - la simulación sigue sin su bitácora
        evento(
            log,
            "simulacion_sin_bitacora",
            caso_id=hilo_id,
            herramienta=nombre,
            detalle=type(exc).__name__,
        )

    # El campo se llama `nivel_urgencia` y no `nivel`: `evento()` tiene un parámetro
    # propio llamado `nivel` —el nivel de log— y pasarle un 1 como campo del evento no
    # falla, registra la línea con nivel 1, por debajo de DEBUG, y la línea desaparece
    # del log entera.
    evento(
        log,
        "simulacion_decision",
        caso_id=hilo_id,
        simulacion_id=slug,
        herramienta=nombre,
        centro=detalle.get("centro"),
        nivel_urgencia=detalle.get("nivel_urgencia"),
        ok=ok,
    )


# ------------------------------------------- resultados en seco, por herramienta

def _simular_canalizar_caso(argumentos: dict[str, Any]) -> dict[str, Any]:
    """Misma forma que `triaje.canalizar_caso`, sin tocar el caso.

    El nivel 1 se trata igual que en el real: ahí `canalizar_caso` llama a
    `escalar_urgencia` y devuelve `agendar: False` con la ruta de emergencia en
    `decir_a_la_persona`. Si aquí no se reprodujera, el nivel 1 —la decisión más
    importante que puede tomar el triaje— sería lo único que la simulación no
    permitiría evaluar.
    """
    centro = argumentos["centro"]
    nivel = int(argumentos["nivel_urgencia"])

    if nivel == 1:
        return {
            "ok": True,
            "simulado": True,
            "centro": centro,
            "nivel_urgencia": nivel,
            "agendar": False,
            "decir_a_la_persona": agentes.RUTA_EMERGENCIA,
        }

    # El nivel 4 es «sin cita» también en el real, y su `siguiente` no habla de
    # traspaso, así que aquí va el mismo texto: lo que se evalúa es cómo cierra el
    # triaje una duda de información, y con otra instrucción cerraría de otra forma.
    # Los textos son copia de los de `herramientas/triaje.py`, que es otro paquete de
    # despliegue y no se puede importar desde aquí.
    if nivel == 4:
        resuelta = bool(argumentos.get("orientacion_resuelta"))
        return {
            "ok": True,
            "simulado": True,
            "centro": centro,
            "nivel_urgencia": nivel,
            "agendar": False,
            "plazo": _PLAZO_SIMULADO[4],
            "cerrado": resuelta,
            "siguiente": (
                "La duda quedó resuelta con la información de los centros y el caso se "
                "cerró: no queda nada pendiente. Si la persona necesita algo más, lo "
                "cuenta aquí y se le atiende desde el principio. No le prometas ningún "
                "seguimiento."
            )
            if resuelta
            else (
                f"Es una orientación sin cita que no se resolvió con la información de los "
                f"centros. Dile a la persona que su consulta quedó registrada en el {centro} "
                "con lo que te contó, y que si quiere hablarlo con alguien del centro le "
                "buscas una cita aquí mismo. No le digas que le van a responder por otra "
                "vía: el centro ve el caso, pero no tiene cómo escribirle."
            ),
        }

    return {
        "ok": True,
        "simulado": True,
        "centro": centro,
        "nivel_urgencia": nivel,
        "agendar": True,
        "plazo": _PLAZO_SIMULADO.get(nivel, "7 días"),
        # El real dice aquí que el caso pasa al agente de agenda. En la simulación no
        # hay traspaso, y dejar esa frase haría que el modelo se despidiera prometiendo
        # una cita que nadie va a buscar.
        "siguiente": (
            "Cierra tú aquí: dile a la persona a qué centro queda canalizada y en qué "
            "plazo. No agendes ni prometas una hora."
        ),
    }


def _simular_escalar_urgencia(argumentos: dict[str, Any]) -> dict[str, Any]:
    """Misma forma que `triaje.escalar_urgencia`, sin ninguna de sus cuatro escrituras.

    `avisado_el_equipo` va en `False` por la misma razón por la que no se emite
    `ESCALAMIENTO`: no se avisó a nadie, y decirle al modelo que sí le haría
    prometerle a la persona un contacto humano que no existe (invariante 7).
    """
    return {
        "ok": True,
        "simulado": True,
        "decir_a_la_persona": agentes.RUTA_EMERGENCIA,
        "avisado_el_equipo": False,
        "agendar": False,
        "instruccion": (
            "Di ese texto tal cual, antes de cualquier otra cosa. No agendes ni "
            "sigas preguntando por síntomas. Después acompaña a la persona."
        ),
    }


def _simular_consultar_estado_caso(_argumentos: dict[str, Any]) -> dict[str, Any]:
    """Un caso recién abierto, sin leer ROBLE.

    Plausible y vacío a propósito: es el estado en el que de verdad está un caso
    cuando el triaje lo consulta en su primer turno, y así el modelo no se ahorra
    ninguna pregunta que en producción tendría que hacer.
    """
    return {
        "simulado": True,
        "estado": CASO_ABIERTO,
        "centro": None,
        "nivel_urgencia": None,
        "motivo": "Caso de prueba abierto en esta simulación",
        "resumen_triaje": None,
        "abierto_desde": reloj.humano(reloj.ahora()),
        "citas": [],
        "tiene_plan": False,
        "indicaciones_activas": 0,
    }


# Qué se puede ejecutar en seco. Una herramienta del agente que no esté aquí devuelve
# error de dominio en vez de inventarse un resultado: un resultado improvisado se
# evaluaría como si fuera el del sistema.
_SIMULADORES = {
    "canalizar_caso": _simular_canalizar_caso,
    "escalar_urgencia": _simular_escalar_urgencia,
    "consultar_estado_caso": _simular_consultar_estado_caso,
}
