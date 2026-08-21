"""Registro en una línea de JSON por evento.

Un log de conversaciones clínicas no puede llevar el contenido de la
conversación: por eso `evento()` recibe campos nombrados y no texto libre, y hay
una lista de claves que se recortan siempre.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

# Nunca se registran completos, aunque alguien los pase por descuido.
_RECORTAR = {
    "mensaje",
    "texto",
    "contenido",
    "nota",
    "resumen",
    "sintomas",
    "respuesta",
    "password",
    "token",
    "access_token",
    "authorization",
}


class _FormatoJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        cuerpo: dict[str, Any] = {
            "nivel": record.levelname,
            "evento": record.getMessage(),
        }
        extra = getattr(record, "datos", None)
        if isinstance(extra, dict):
            cuerpo.update(extra)
        if record.exc_info:
            cuerpo["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(cuerpo, ensure_ascii=False, default=str)


def registro(nombre: str) -> logging.Logger:
    """Logger listo para CloudWatch, con formato JSON y sin duplicar handlers."""
    log = logging.getLogger(nombre)
    if not log.handlers:
        manejador = logging.StreamHandler()
        manejador.setFormatter(_FormatoJson())
        log.addHandler(manejador)
        log.propagate = False
    log.setLevel(os.environ.get("NIVEL_LOG", "INFO").upper())
    return log


def _saneado(datos: dict[str, Any]) -> dict[str, Any]:
    limpio: dict[str, Any] = {}
    for clave, valor in datos.items():
        if clave.lower() in _RECORTAR:
            limpio[f"{clave}_long"] = len(str(valor)) if valor is not None else 0
        else:
            limpio[clave] = valor
    return limpio


def evento(log: logging.Logger, nombre: str, *, nivel: int = logging.INFO, **datos: Any) -> None:
    """Registra un evento con nombre y campos, recortando lo que no debe salir.

    El nombre es el que buscan los filtros de métricas de CloudWatch, así que
    cambiarlo rompe una alarma: `ESCALAMIENTO` alimenta la de urgencias.
    """
    log.log(nivel, nombre, extra={"datos": _saneado(datos)})
