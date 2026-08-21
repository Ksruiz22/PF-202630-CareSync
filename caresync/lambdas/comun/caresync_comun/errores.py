"""Errores del dominio, cada uno con el código HTTP que le corresponde.

La traducción a HTTP vive aquí y en un solo sitio: ni los servicios ni el
handler deciden códigos de estado a mano.
"""

from __future__ import annotations


class ErrorDeCareSync(Exception):
    """Base de todo lo que este sistema sabe que puede fallar."""

    http = 500
    publico = "Algo falló de nuestro lado. Vuelve a intentarlo."

    def __init__(self, mensaje: str, *, publico: str | None = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        if publico is not None:
            self.publico = publico


class ErrorDeConfiguracion(ErrorDeCareSync):
    """Falta un parámetro o tiene todavía el valor de relleno.

    Es 500 a propósito: no es culpa de quien llama.
    """

    http = 500
    publico = "El servicio no está configurado por completo."


class SolicitudInvalida(ErrorDeCareSync):
    http = 400
    publico = "No entendí la solicitud."


class NoAutorizado(ErrorDeCareSync):
    http = 401
    publico = "Tu sesión no es válida o expiró. Vuelve a iniciar sesión."


class SinPermiso(ErrorDeCareSync):
    http = 403
    publico = "Tu rol no permite esta acción."


class NoEncontrado(ErrorDeCareSync):
    http = 404
    publico = "No encontré eso."


class Conflicto(ErrorDeCareSync):
    """Alguien llegó primero. El caso típico es un cupo ya reservado."""

    http = 409
    publico = "Ese espacio ya no está disponible."


class ErrorDeDatos(ErrorDeCareSync):
    """ROBLE no respondió, o respondió algo que no se puede usar."""

    http = 502
    publico = "La base de datos del proyecto no respondió. Inténtalo en un momento."
