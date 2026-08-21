"""Orquestador de agentes: el único punto de entrada del sistema.

Lo que hace, en orden:

1. Autoriza al llamante contra ROBLE con su propio token, y de ahí saca su rol.
2. Resuelve el caso: continúa el que esté abierto o abre uno nuevo.
3. Elige el agente por rol y por estado del caso, no por lo que diga el cliente.
4. Corre el bucle de herramientas contra Bedrock.
5. Traspasa al siguiente agente si el anterior cerró su parte.
6. Deja la conversación escrita en ROBLE y responde.

Lo que NO hace: acceder a datos. Cualquier lectura o escritura del dominio pasa
por el módulo de acceso, y cualquier acción con efecto por la función de
herramientas. Este archivo coordina.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

import boto3
import requests

from caresync_comun import respuesta
from caresync_comun.catalogo_herramientas import especificaciones, permitida
from caresync_comun.config import config
from caresync_comun.errores import (
    ErrorDeCareSync,
    ErrorDeDatos,
    NoAutorizado,
    SinPermiso,
    SolicitudInvalida,
)
from caresync_comun.registro import evento, registro
from caresync_comun.roble_acceso import AccesoRoble, fila_id

import agentes
import bedrock_conversa

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
        return _conversar(acceso, token=token, mensaje=mensaje, cuerpo=cuerpo)
    finally:
        acceso.cerrar()


# ------------------------------------------------------------- conversación

def _conversar(
    acceso: AccesoRoble, *, token: str, mensaje: str, cuerpo: dict[str, Any]
) -> dict[str, Any]:
    actor = acceso.actor
    caso = _resolver_caso(acceso, cuerpo=cuerpo, mensaje=mensaje)
    caso_id = str(fila_id(caso))

    solicitado = str(cuerpo.get("agente") or "").strip().lower()
    clave = solicitado if solicitado in agentes.AGENTES else agentes.agente_por_defecto(caso)
    agente = agentes.AGENTES[clave]

    if actor.rol not in agente.roles:
        raise SinPermiso(f"El rol «{actor.rol}» no puede usar el {agente.nombre}")

    acceso.anotar_mensaje(caso_id=caso_id, agente=agente.clave, autor="paciente", contenido=mensaje)

    # El hilo que se le pasa al modelo es sólo texto: turnos de la persona y del
    # agente. Los bloques `toolUse`/`toolResult` de la vuelta anterior se quedan
    # dentro del bucle y no se arrastran al traspaso, porque el segundo agente
    # declara otras herramientas y la API rechaza un historial que referencia
    # herramientas que ya no existen.
    hilo = _historial(acceso, caso_id)
    hilo.append({"role": "user", "content": [{"text": mensaje}]})

    participantes: list[str] = []
    usos_totales: list[bedrock_conversa.Uso] = []
    texto_final = ""
    tokens = {"entrada": 0, "salida": 0, "cacheados": 0}
    intervino = False

    # Como máximo dos agentes por petición: el que atiende y el que recibe el
    # traspaso. Un tercero sería una cadena que la persona no puede seguir.
    for salto in range(2):
        participantes.append(agente.clave)
        contexto_extra = _contexto_del_traspaso(caso) if salto else ""

        resultado = bedrock_conversa.conversar(
            sistema=agentes.instrucciones(
                agente, actor=actor, caso=caso, contexto=contexto_extra
            ),
            mensajes=hilo,
            herramientas=_herramientas_de(agente, actor.rol),
            ejecutar=_ejecutor(token=token, caso_id=caso_id, agente=agente.clave),
        )

        usos_totales.extend(resultado.usos)
        tokens["entrada"] += resultado.tokens_entrada
        tokens["salida"] += resultado.tokens_salida
        tokens["cacheados"] += resultado.tokens_cacheados
        intervino = intervino or resultado.intervino_guardrail
        texto_final = "\n\n".join(t for t in (texto_final, resultado.texto) if t)

        siguiente = _traspaso(agente, resultado)
        if not siguiente:
            break

        # El caso cambió de estado dentro de la herramienta: hay que releerlo
        # para que el siguiente agente vea el centro y el nivel de urgencia.
        caso = acceso.caso(caso_id)
        agente = agentes.AGENTES[siguiente]
        if actor.rol not in agente.roles:
            break

        if resultado.texto:
            hilo.append({"role": "assistant", "content": [{"text": resultado.texto}]})
        hilo.append({"role": "user", "content": [{"text": _nota_de_traspaso(caso)}]})

    if texto_final:
        acceso.anotar_mensaje(
            caso_id=caso_id, agente=participantes[-1], autor="agente", contenido=texto_final
        )

    caso = acceso.caso(caso_id)
    evento(
        log,
        "conversacion_atendida",
        caso_id=caso_id,
        agentes=participantes,
        herramientas=[u.nombre for u in usos_totales],
        tokens_entrada=tokens["entrada"],
        tokens_salida=tokens["salida"],
        tokens_cacheados=tokens["cacheados"],
        guardrail=intervino,
    )

    return respuesta.ok(
        {
            "respuesta": texto_final,
            "caso": {
                "id": caso_id,
                "estado": caso.get("estado"),
                "centro": caso.get("centro"),
                "nivel_urgencia": caso.get("nivel_urgencia"),
            },
            "agentes": participantes,
            "acciones": [
                {"herramienta": u.nombre, "ok": u.ok, "resultado": u.resultado}
                for u in usos_totales
            ],
            "salvaguardas_intervinieron": intervino,
        },
        cabeceras={"x-caresync-caso": caso_id},
    )


def _resolver_caso(
    acceso: AccesoRoble, *, cuerpo: dict[str, Any], mensaje: str
) -> dict[str, Any]:
    pedido = cuerpo.get("caso_id")
    if pedido:
        return acceso.caso_visible(str(pedido))

    if not acceso.actor.es_paciente:
        # Un profesional o un administrativo siempre habla *sobre* un caso
        # concreto; no tiene uno propio que continuar.
        raise SolicitudInvalida("Falta «caso_id»: tu rol siempre actúa sobre un caso concreto")

    abierto = acceso.caso_abierto_de(acceso.actor.user_id)
    return abierto or acceso.abrir_caso(motivo=mensaje)


def _historial(acceso: AccesoRoble, caso_id: str) -> list[dict[str, Any]]:
    """Convierte lo escrito en ROBLE al formato de mensajes de Converse.

    Los resultados de herramientas no se rehidratan: se guardan como texto en la
    bitácora del caso, pero al modelo se le da la conversación con la persona.
    Reconstruir bloques `toolUse`/`toolResult` de turnos viejos obligaría a
    guardar identificadores de la API en la base y no aporta nada al hilo.
    """
    mensajes: list[dict[str, Any]] = []
    for fila in acceso.mensajes(caso_id, maximo=20):
        contenido = str(fila.get("contenido") or "").strip()
        if not contenido:
            continue
        papel = "assistant" if fila.get("autor") == "agente" else "user"
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


def _herramientas_de(agente: agentes.Agente, rol: str) -> list[dict[str, Any]]:
    """Sólo se declaran las herramientas que el rol puede usar de verdad.

    Filtrar aquí, y no al ejecutar, evita que el modelo prometa a la persona algo
    que después le va a ser negado.
    """
    disponibles = tuple(n for n in agente.herramientas if permitida(n, rol))
    return especificaciones(disponibles)


def _traspaso(agente: agentes.Agente, resultado: bedrock_conversa.Resultado) -> str | None:
    if not agente.traspaso:
        return None
    disparador, destino = agente.traspaso
    for uso in resultado.usos:
        if uso.nombre == disparador and uso.ok:
            return destino
    return None


def _contexto_del_traspaso(caso: dict[str, Any]) -> str:
    return (
        f"El agente anterior acaba de canalizar este caso al {caso.get('centro')} "
        f"con nivel de urgencia {caso.get('nivel_urgencia')}. Continúas tú, en la misma "
        "conversación: no te presentes de nuevo ni repitas lo que ya se dijo."
    )


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
