"""Bucle de herramientas sobre la API Converse de Bedrock.

Converse es lo que permite usar un solo formato de mensajes y de herramientas
para cualquier modelo: si mañana el prototipo cambia Claude Haiku por otro
modelo, esto no se toca.

Dos cosas que aquí se hacen a propósito:

**El punto de caché va al final del prompt de sistema.** El prefijo estable es
lo que se cachea: instrucciones y protocolo, que son varios miles de tokens y
son idénticos en cada turno. Si el modelo o la región no admiten el punto de
caché, la llamada se repite sin él en lugar de fallar.

**El bucle tiene tope.** Un modelo puede quedarse pidiendo herramientas en
círculo, y cada vuelta es una llamada facturada. Al agotar las vueltas se
devuelve lo que haya, no un error: la persona recibe una respuesta.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable

import boto3
from botocore.config import Config as ConfigBoto
from botocore.exceptions import ClientError

from caresync_comun.errores import ErrorDeCareSync
from caresync_comun.registro import evento, registro

log = registro(__name__)

MODELO = os.environ.get("MODELO_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
MAX_VUELTAS = int(os.environ.get("MAX_VUELTAS", "5"))


class ErrorDelModelo(ErrorDeCareSync):
    http = 502
    publico = "El asistente no está disponible en este momento. Inténtalo de nuevo."


@lru_cache(maxsize=1)
def _bedrock():
    return boto3.client(
        "bedrock-runtime",
        config=ConfigBoto(
            # El reintento estándar de botocore ya cubre el throttling de
            # Bedrock, que es el error transitorio habitual.
            retries={"max_attempts": 3, "mode": "standard"},
            read_timeout=30,
            connect_timeout=5,
        ),
    )


@dataclass
class Uso:
    """Una llamada a herramienta, con lo que devolvió."""

    nombre: str
    argumentos: dict[str, Any]
    resultado: dict[str, Any]
    ok: bool


@dataclass
class Resultado:
    texto: str
    usos: list[Uso] = field(default_factory=list)
    mensajes: list[dict[str, Any]] = field(default_factory=list)
    parada: str = ""
    vueltas: int = 0
    tokens_entrada: int = 0
    tokens_salida: int = 0
    tokens_cacheados: int = 0
    intervino_guardrail: bool = False


def _guardrail() -> dict[str, Any] | None:
    identificador = os.environ.get("GUARDRAIL_ID", "")
    version = os.environ.get("GUARDRAIL_VERSION", "")
    if not identificador or not version:
        return None
    return {
        "guardrailIdentifier": identificador,
        "guardrailVersion": version,
        "trace": "enabled",
    }


def _texto_de(mensaje: dict[str, Any]) -> str:
    partes = [
        bloque["text"]
        for bloque in mensaje.get("content", [])
        if isinstance(bloque, dict) and "text" in bloque
    ]
    return "\n".join(p.strip() for p in partes if p and p.strip())


def conversar(
    *,
    sistema: str,
    mensajes: list[dict[str, Any]],
    herramientas: list[dict[str, Any]],
    ejecutar: Callable[[str, dict[str, Any]], dict[str, Any]],
    max_vueltas: int = MAX_VUELTAS,
    temperatura: float = 0.2,
    max_tokens: int = 800,
) -> Resultado:
    """Conversa hasta que el modelo deje de pedir herramientas.

    `ejecutar` recibe (nombre, argumentos) y devuelve el resultado ya en forma
    de diccionario. Si lanza una excepción, el bucle no se rompe: el error se le
    devuelve al modelo como resultado de la herramienta, que es lo que le
    permite explicárselo a la persona o intentar otra cosa.
    """
    historial = list(mensajes)
    resultado = Resultado(texto="", mensajes=historial)
    usar_cache = os.environ.get("CACHE_PROMPT", "1") == "1"

    for vuelta in range(1, max_vueltas + 1):
        resultado.vueltas = vuelta
        respuesta = _llamar(
            sistema=sistema,
            mensajes=historial,
            herramientas=herramientas,
            temperatura=temperatura,
            max_tokens=max_tokens,
            usar_cache=usar_cache,
        )

        uso_tokens = respuesta.get("usage") or {}
        resultado.tokens_entrada += int(uso_tokens.get("inputTokens", 0))
        resultado.tokens_salida += int(uso_tokens.get("outputTokens", 0))
        resultado.tokens_cacheados += int(uso_tokens.get("cacheReadInputTokens", 0) or 0)

        parada = respuesta.get("stopReason", "")
        resultado.parada = parada
        mensaje = (respuesta.get("output") or {}).get("message") or {}
        historial.append(mensaje)

        if parada == "guardrail_intervened":
            resultado.intervino_guardrail = True
            resultado.texto = _texto_de(mensaje) or (
                "Prefiero no responder eso. Si es una urgencia, llama a la línea "
                "de emergencias del campus o al 123."
            )
            evento(log, "guardrail_intervino", vuelta=vuelta)
            return resultado

        if parada != "tool_use":
            resultado.texto = _texto_de(mensaje)
            return resultado

        peticiones = [
            bloque["toolUse"]
            for bloque in mensaje.get("content", [])
            if isinstance(bloque, dict) and "toolUse" in bloque
        ]

        bloques_resultado = []
        for peticion in peticiones:
            nombre = peticion.get("name", "")
            argumentos = peticion.get("input") or {}
            try:
                salida = ejecutar(nombre, argumentos)
                correcto = True
            except Exception as exc:  # noqa: BLE001 - se le devuelve al modelo
                salida = {"error": _mensaje_para_el_modelo(exc)}
                correcto = False
                evento(log, "herramienta_fallida", herramienta=nombre, detalle=str(exc))

            resultado.usos.append(Uso(nombre, argumentos, salida, correcto))
            bloques_resultado.append(
                {
                    "toolResult": {
                        "toolUseId": peticion.get("toolUseId"),
                        "content": [{"json": salida}],
                        "status": "success" if correcto else "error",
                    }
                }
            )

        historial.append({"role": "user", "content": bloques_resultado})

    # Se agotaron las vueltas. Se pide una respuesta final sin herramientas para
    # no dejar a la persona con la conversación colgada.
    evento(log, "vueltas_agotadas", vueltas=max_vueltas)
    cierre = _llamar(
        sistema=sistema
        + "\n\nCierra ahora: resume en dos frases lo que lograste y qué falta. No pidas más herramientas.",
        mensajes=historial,
        herramientas=[],
        temperatura=temperatura,
        max_tokens=300,
        usar_cache=False,
    )
    mensaje = (cierre.get("output") or {}).get("message") or {}
    historial.append(mensaje)
    resultado.texto = _texto_de(mensaje)
    resultado.parada = "vueltas_agotadas"
    return resultado


def _llamar(
    *,
    sistema: str,
    mensajes: list[dict[str, Any]],
    herramientas: list[dict[str, Any]],
    temperatura: float,
    max_tokens: int,
    usar_cache: bool,
) -> dict[str, Any]:
    bloques_sistema: list[dict[str, Any]] = [{"text": sistema}]
    if usar_cache:
        bloques_sistema.append({"cachePoint": {"type": "default"}})

    peticion: dict[str, Any] = {
        "modelId": MODELO,
        "system": bloques_sistema,
        "messages": mensajes,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperatura},
    }
    if herramientas:
        peticion["toolConfig"] = {"tools": herramientas}
    salvaguardas = _guardrail()
    if salvaguardas:
        peticion["guardrailConfig"] = salvaguardas

    try:
        return _bedrock().converse(**peticion)
    except ClientError as exc:
        codigo = exc.response.get("Error", {}).get("Code", "")
        detalle = exc.response.get("Error", {}).get("Message", "")

        # El punto de caché exige un mínimo de tokens y no lo admiten todas las
        # combinaciones de modelo y región. Si es eso, se reintenta sin él: el
        # caché es una optimización de coste, no un requisito.
        if usar_cache and codigo == "ValidationException" and "cache" in detalle.lower():
            evento(log, "cache_prompt_no_admitido", detalle=detalle)
            return _llamar(
                sistema=sistema,
                mensajes=mensajes,
                herramientas=herramientas,
                temperatura=temperatura,
                max_tokens=max_tokens,
                usar_cache=False,
            )

        if codigo == "AccessDeniedException":
            raise ErrorDelModelo(
                f"Sin acceso al modelo {MODELO}. Revisa el acceso al modelo en la consola de "
                f"Bedrock y que el identificador lleve el prefijo de perfil de inferencia: {detalle}"
            ) from exc
        if codigo in ("ThrottlingException", "ServiceQuotaExceededException"):
            raise ErrorDelModelo(f"Bedrock está limitando las llamadas: {detalle}") from exc
        raise ErrorDelModelo(f"Bedrock respondió {codigo}: {detalle}") from exc


def _mensaje_para_el_modelo(exc: Exception) -> str:
    """Qué se le cuenta al modelo cuando una herramienta falla.

    Se le da el mensaje público del error de dominio, no la traza: el modelo va a
    parafrasear esto a la persona, así que tiene que ser algo decible.
    """
    if isinstance(exc, ErrorDeCareSync):
        return exc.publico
    return "La operación no se pudo completar por un problema técnico."


def como_texto(contenido: Any) -> str:
    """Serializa lo que sea a algo que quepa en un bloque de texto."""
    if isinstance(contenido, str):
        return contenido
    return json.dumps(contenido, ensure_ascii=False, default=str)
