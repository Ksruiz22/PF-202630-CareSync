"""Respuestas HTTP para API Gateway (payload 2.0).

El detalle técnico del error va al log; al cliente sólo le llega el mensaje
público del error de dominio. La razón no es estética: un mensaje de ROBLE
reenviado tal cual puede revelar nombres de tablas o de columnas.
"""

from __future__ import annotations

import json
from typing import Any

from .errores import ErrorDeCareSync

CABECERAS = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
}


def ok(cuerpo: dict[str, Any], *, estado: int = 200, cabeceras: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "statusCode": estado,
        "headers": {**CABECERAS, **(cabeceras or {})},
        "body": json.dumps(cuerpo, ensure_ascii=False, default=str),
    }


def error(estado: int, mensaje: str, *, codigo: str | None = None) -> dict[str, Any]:
    return ok({"error": mensaje, "codigo": codigo or f"http_{estado}"}, estado=estado)


def de_excepcion(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ErrorDeCareSync):
        return error(exc.http, exc.publico, codigo=type(exc).__name__)
    return error(500, "Algo falló de nuestro lado. Vuelve a intentarlo.", codigo="ErrorInesperado")


def token_del_evento(evento: dict[str, Any]) -> str | None:
    """Extrae el Bearer de la cabecera Authorization.

    API Gateway normaliza los nombres de cabecera a minúsculas en el payload
    2.0, pero se comprueban las dos formas para que la función se pueda invocar
    también con un evento escrito a mano en las pruebas.
    """
    cabeceras = evento.get("headers") or {}
    crudo = cabeceras.get("authorization") or cabeceras.get("Authorization") or ""
    partes = str(crudo).split()
    if len(partes) == 2 and partes[0].lower() == "bearer":
        return partes[1]
    return None


def cuerpo_del_evento(evento: dict[str, Any]) -> dict[str, Any]:
    crudo = evento.get("body")
    if not crudo:
        return {}
    if evento.get("isBase64Encoded"):
        import base64

        crudo = base64.b64decode(crudo).decode("utf-8")
    try:
        datos = json.loads(crudo)
    except (ValueError, TypeError):
        return {}
    return datos if isinstance(datos, dict) else {}
