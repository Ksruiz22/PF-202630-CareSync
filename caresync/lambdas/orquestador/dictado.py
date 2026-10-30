"""La sesión de dictado: una URL firmada para hablarle a Amazon Transcribe.

El dictado del plan (RF-11) va del micrófono del navegador a Amazon Transcribe en
tiempo real, por un WebSocket. El navegador no tiene credenciales de AWS —la sesión
de la PWA es de ROBLE—, así que no puede firmar esa conexión. La firma este módulo, y
la vista abre el WebSocket con la URL que recibe.

Por qué Transcribe y no el reconocimiento de voz del navegador: en Chrome, la Web
Speech API manda el audio a los servidores de Google. Lo que se dicta aquí es un plan
de tratamiento, y el proyecto se comprometió a no sacar datos de salud de la
infraestructura que ya usa. Transcribe está en la misma cuenta de AWS que Bedrock, y
en tiempo real **no guarda el audio**: no hay bucket ni archivo que borrar después.

Lo que expone la URL: la firma es de un solo uso —vale para esa ruta y esos
parámetros, y caduca a los `VIGENCIA` segundos— y lleva el identificador de la clave
y el token de sesión del rol de la Lambda, **no** el secreto. Con ella no se puede
firmar otra petición. Aun así, sólo la pide un `profesional`: el rol de la Lambda
tiene permiso de Transcribe, y nadie más necesita dictar.

`es-US` y no `es-CO`, que Transcribe no tiene: es la variante latinoamericana, con
vocabulario personalizado y modelos de lenguaje propios si un día hacen falta.
"""

from __future__ import annotations

import hashlib
import os
from urllib.parse import urlencode

import boto3

from caresync_comun.errores import ErrorDeConfiguracion

IDIOMA = os.environ.get("DICTADO_IDIOMA", "es-US")
# 16 kHz es lo que Transcribe recomienda para voz; la vista remuestrea el micrófono
# (que suele ir a 44,1 o 48 kHz) antes de mandar el audio.
TASA_DE_MUESTREO = 16000
# El máximo que admite Transcribe para una URL firmada. Basta con que sea válida al
# abrir el WebSocket: una vez abierto, el dictado puede durar lo que haga falta.
VIGENCIA = 300


def _region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def url_firmada() -> dict[str, object]:
    credenciales = boto3.Session().get_credentials()
    if credenciales is None:
        raise ErrorDeConfiguracion("La Lambda no tiene credenciales para firmar el dictado")

    region = _region()
    parametros = {
        "language-code": IDIOMA,
        "media-encoding": "pcm",
        "sample-rate": str(TASA_DE_MUESTREO),
        # Sin estabilización, los resultados parciales cambian palabras ya mostradas
        # mientras la persona sigue hablando, y el texto en pantalla «baila».
        "enable-partial-results-stabilization": "true",
        "partial-results-stability": "medium",
    }
    url = firmar(
        f"https://transcribestreaming.{region}.amazonaws.com:8443"
        f"/stream-transcription-websocket?{urlencode(parametros)}",
        credenciales.get_frozen_credentials(),
        region,
    )

    return {
        "url": "wss://" + url.removeprefix("https://"),
        "idioma": IDIOMA,
        "tasa_de_muestreo": TASA_DE_MUESTREO,
        "vigencia_segundos": VIGENCIA,
    }


def firmar(url: str, credenciales, region: str) -> str:
    """Firma SigV4 en la URL, con el hash del cuerpo vacío y no `UNSIGNED-PAYLOAD`.

    `SigV4QueryAuth` firma como S3, que acepta la constante `UNSIGNED-PAYLOAD` en la
    petición canónica. La guía de Transcribe para WebSocket pide el SHA-256 de un
    cuerpo vacío, y una firma calculada con otra petición canónica sale `403` al abrir
    la conexión, sin decir por qué.

    botocore se importa aquí y no arriba: el orquestador carga este módulo al
    arrancar, y las pruebas de CI corren sin botocore —lo trae el runtime de Lambda—.
    """
    from botocore.auth import SigV4QueryAuth
    from botocore.awsrequest import AWSRequest

    class _Firma(SigV4QueryAuth):
        def payload(self, request):
            return hashlib.sha256(b"").hexdigest()

    peticion = AWSRequest(method="GET", url=url)
    _Firma(credenciales, "transcribe", region, expires=VIGENCIA).add_auth(peticion)
    return peticion.url
