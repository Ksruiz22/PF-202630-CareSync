"""Envío de correo por SES.

Si no hay remitente verificado, `enviar` registra el correo y devuelve `False`
en lugar de fallar. Es deliberado: mientras SES no esté listo, el agendamiento
y el seguimiento tienen que seguir funcionando de extremo a extremo, y el
mensaje queda visible en el log para poder comprobar la prueba de aceptación.

Ningún correo lleva el contenido de la conversación ni el detalle clínico: sólo
el mínimo para que la persona entre a la aplicación y lo lea ahí, donde los
permisos de ROBLE sí se aplican.
"""

from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

from .config import config
from .registro import evento, registro

log = registro(__name__)

PIE = (
    "\n\n—\nCareSync · prototipo académico de la Universidad del Norte.\n"
    "Este mensaje no reemplaza una consulta con personal de salud. "
    "Si es una urgencia, llama a la línea de emergencias del campus o al 123."
)


@lru_cache(maxsize=1)
def _ses():
    return boto3.client("sesv2")


def enviar(*, para: str, asunto: str, cuerpo: str) -> bool:
    """Envía un correo. Devuelve si salió de verdad."""
    ajustes = config()

    if not ajustes.envia_correo or not para:
        evento(log, "correo_no_enviado", motivo="sin_remitente_o_destinatario", asunto=asunto, para=para)
        return False

    peticion = {
        "FromEmailAddress": ajustes.correo_remitente,
        "Destination": {"ToAddresses": [para]},
        "Content": {
            "Simple": {
                "Subject": {"Data": asunto, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": cuerpo + PIE, "Charset": "UTF-8"}},
            }
        },
    }
    if ajustes.ses_conjunto:
        peticion["ConfigurationSetName"] = ajustes.ses_conjunto

    try:
        respuesta = _ses().send_email(**peticion)
    except ClientError as exc:
        codigo = exc.response.get("Error", {}).get("Code", "desconocido")
        # En sandbox, el destinatario también tiene que estar verificado. Es el
        # fallo más habitual en una demo, así que se nombra explícitamente.
        evento(
            log,
            "correo_fallido",
            codigo=codigo,
            para=para,
            asunto=asunto,
            pista="en sandbox de SES el destinatario también debe estar verificado"
            if codigo == "MessageRejected"
            else "",
        )
        return False

    evento(log, "correo_enviado", para=para, asunto=asunto, id=respuesta.get("MessageId"))
    return True
