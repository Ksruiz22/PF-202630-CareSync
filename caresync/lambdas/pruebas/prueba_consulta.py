#!/usr/bin/env python3
"""
Pruebas de las dos ayudas de la consulta del profesional. Sin red, sin AWS.

    python lambdas/pruebas/prueba_consulta.py

Lo que se cuida aquí:

- **Que la propuesta de plan no escriba nada.** El invariante 3 —el plan lo escribe el
  profesional— sigue en pie sólo si `POST /plan/propuesta` devuelve texto y no toca
  ROBLE. Se comprueba sobre el acceso doblado: después de una propuesta, nada escrito.
- **Que sólo la use un profesional.** Corre sin la salvaguarda de los agentes —quien
  prescribe ahí es él— y eso sólo es aceptable si un paciente no puede llamarla.
- **Que la frecuencia se juzgue con la regla de los recordatorios**, la misma función,
  para que el aviso de «esta no va a recordarse» no mienta.
- **Que la firma del dictado sea la que pide Transcribe**: el hash del cuerpo vacío y
  no `UNSIGNED-PAYLOAD`. Esa comprobación necesita botocore de verdad; en CI, que no lo
  instala, se omite y lo dice.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlsplit

sys.path.insert(0, str(Path(__file__).parent))

from entorno import AccesoFalso, ActorFalso, cargar, comprobar, fallos, lanza, preparar  # noqa: E402

preparar()

from caresync_comun import frecuencia  # noqa: E402
from caresync_comun.errores import NoAutorizado, SinPermiso, SolicitudInvalida  # noqa: E402

orquestador = cargar("orquestador", "handler")
recordatorios = cargar("recordatorios", "handler")
# Los módulos hermanos son los que importó el handler, no copias nuevas.
plan_propuesta = sys.modules["plan_propuesta"]
dictado = sys.modules["dictado"]
bedrock_conversa = sys.modules["bedrock_conversa"]


class BedrockFalso:
    """Un cliente de Bedrock que devuelve lo que se le diga y anota lo que se le pidió."""

    def __init__(self, entrada=None, *, sin_herramienta=False):
        self.entrada = entrada
        self.sin_herramienta = sin_herramienta
        self.pedidos: list[dict] = []

    def converse(self, **pedido):
        self.pedidos.append(pedido)
        if self.sin_herramienta:
            contenido = [{"text": "Aquí tienes el plan ordenado."}]
        else:
            contenido = [{"toolUse": {"toolUseId": "t1", "name": "proponer_plan", "input": self.entrada}}]
        return {"output": {"message": {"role": "assistant", "content": contenido}}, "stopReason": "tool_use"}


def con_bedrock(cliente, funcion, *args, **kwargs):
    original = bedrock_conversa._bedrock
    bedrock_conversa._bedrock = lambda: cliente
    try:
        return funcion(*args, **kwargs)
    finally:
        bedrock_conversa._bedrock = original


PROPUESTA = {
    "resumen": "Faringitis viral sin signos de alarma. Manejo sintomático.",
    "indicaciones": [
        {"texto": "Tomar acetaminofén 500 mg durante tres días", "frecuencia": "cada 8 horas"},
        {"texto": "Caminar 20 minutos", "frecuencia": "diario"},
        {"texto": "Hacer control en dos semanas", "frecuencia": ""},
        {"texto": "   ", "frecuencia": "cada 8 horas"},
    ],
    "dudas": ["No se dijo cada cuánto hacer las gárgaras."],
}


def probar_depurar() -> None:
    print("\nLo que devuelve el modelo, recortado a lo que se puede guardar")
    limpia = plan_propuesta.depurar(PROPUESTA)
    comprobar("descarta indicaciones vacías", len(limpia["indicaciones"]) == 3, str(limpia["indicaciones"]))
    comprobar("conserva el texto tal como llegó, dosis incluida",
              limpia["indicaciones"][0]["texto"] == "Tomar acetaminofén 500 mg durante tres días")
    comprobar("«cada 8 horas» programa recordatorios",
              limpia["indicaciones"][0]["programa_recordatorios"] is True)
    comprobar("una indicación de una sola vez no programa ninguno",
              limpia["indicaciones"][2]["programa_recordatorios"] is False)
    comprobar("las dudas pasan", limpia["dudas"] == ["No se dijo cada cuánto hacer las gárgaras."])

    rara = plan_propuesta.depurar({"resumen": ["no", "es", "texto"], "indicaciones": "tampoco", "dudas": None})
    comprobar("tipos equivocados del modelo no revientan: quedan vacíos",
              rara == {"resumen": "", "indicaciones": [], "dudas": []}, str(rara))

    muchas = plan_propuesta.depurar(
        {"resumen": "x", "indicaciones": [{"texto": f"Paso {i}", "frecuencia": ""} for i in range(40)], "dudas": []}
    )
    comprobar("no más de 15 indicaciones", len(muchas["indicaciones"]) == plan_propuesta.MAX_INDICACIONES)

    larga = plan_propuesta.depurar({"resumen": "a" * 5000, "indicaciones": [], "dudas": []})
    comprobar("el resumen cabe en lo que deja guardar el formulario",
              len(larga["resumen"]) == plan_propuesta.LIMITE_RESUMEN)

    # La regla es la de recordatorios, no una copia: si cambia allá, cambia aquí.
    for texto in ("cada 12 horas", "3 veces al día", "semanal", "cuando haga falta", "una vez"):
        esperado = frecuencia.intervalo(texto) is not None
        real = plan_propuesta.depurar(
            {"resumen": "", "indicaciones": [{"texto": "x", "frecuencia": texto}], "dudas": []}
        )["indicaciones"][0]["programa_recordatorios"]
        comprobar(f"«{texto}»: el aviso coincide con lo que hará recordatorios", real == esperado)


def probar_proponer() -> None:
    print("\nLa llamada al modelo")
    cliente = BedrockFalso(PROPUESTA)
    resultado = con_bedrock(cliente, plan_propuesta.proponer, "Le dejo acetaminofén cada 8 horas...")
    pedido = cliente.pedidos[0]
    comprobar("una sola llamada", len(cliente.pedidos) == 1)
    comprobar("la herramienta va forzada: sin prosa que no se pueda revisar",
              pedido["toolConfig"]["toolChoice"] == {"tool": {"name": "proponer_plan"}})
    comprobar("sin la salvaguarda de los agentes (bloquearía la prescripción del profesional)",
              "guardrailConfig" not in pedido)
    comprobar("temperatura cero: el mismo dictado, la misma propuesta",
              pedido["inferenceConfig"]["temperature"] == 0)
    instrucciones = pedido["system"][0]["text"]
    comprobar("las instrucciones prohíben completar o corregir lo dictado",
              "no completarlo" in instrucciones and "no lo corriges tú" in instrucciones)
    comprobar("las frecuencias que pide son las que entiende recordatorios",
              all(f in instrucciones for f in ("cada N horas", "veces al día", "diario", "semanal")))
    comprobar("devuelve la propuesta depurada", resultado == plan_propuesta.depurar(PROPUESTA))

    comprobar("texto vacío: 400 antes de llamar al modelo",
              lanza(SolicitudInvalida, plan_propuesta.proponer, "   ") is not None)
    comprobar("texto enorme: 400 antes de llamar al modelo",
              lanza(SolicitudInvalida, plan_propuesta.proponer, "a" * 7000) is not None)

    sin_herramienta = BedrockFalso(sin_herramienta=True)
    error = lanza(bedrock_conversa.ErrorDelModelo, con_bedrock, sin_herramienta,
                  plan_propuesta.proponer, "Caminar diario")
    comprobar("si el modelo contesta en prosa, error claro y no una propuesta vacía", error is not None)


def _evento(ruta: str, cuerpo: dict | None = None, token: str | None = "tok") -> dict:
    return {
        "routeKey": ruta,
        "headers": {"authorization": f"Bearer {token}"} if token else {},
        "body": json.dumps(cuerpo or {}),
    }


def _con_acceso(acceso, funcion, *args):
    original = orquestador.AccesoRoble.desde_token
    orquestador.AccesoRoble.desde_token = classmethod(lambda cls, token: acceso)
    try:
        return funcion(*args)
    finally:
        orquestador.AccesoRoble.desde_token = original


def probar_rutas() -> None:
    print("\nLas rutas del profesional")
    profesional = AccesoFalso(ActorFalso("profesional", user_id="u-prof"))
    cliente = BedrockFalso(PROPUESTA)

    respuesta = con_bedrock(
        cliente, _con_acceso, profesional, orquestador.manejar,
        _evento("POST /plan/propuesta", {"texto": "Le dejo acetaminofén cada 8 horas"}),
    )
    cuerpo = json.loads(respuesta["body"])
    comprobar("un profesional recibe la propuesta", respuesta["statusCode"] == 200 and len(cuerpo["indicaciones"]) == 3,
              str(respuesta["statusCode"]))
    comprobar("y nada quedó escrito en ROBLE (invariante 3)", profesional.escrito == [], str(profesional.escrito))
    comprobar("el acceso se cerró", getattr(profesional, "cerrado", False))

    for rol in ("paciente", "admin_cmu", "admin_plataforma"):
        acceso = AccesoFalso(ActorFalso(rol))
        otro = BedrockFalso(PROPUESTA)
        respuesta = con_bedrock(otro, _con_acceso, acceso, orquestador.manejar,
                                _evento("POST /plan/propuesta", {"texto": "x"}))
        comprobar(f"{rol}: 403 y el modelo ni se llama",
                  respuesta["statusCode"] == 403 and otro.pedidos == [], str(respuesta["statusCode"]))
        comprobar(f"{rol}: el acceso se cierra también al rechazar", getattr(acceso, "cerrado", False))

        respuesta = _con_acceso(acceso, orquestador.manejar, _evento("POST /dictado/sesion"))
        comprobar(f"{rol}: tampoco puede abrir un dictado", respuesta["statusCode"] == 403)

    sin_token = orquestador.manejar(_evento("POST /plan/propuesta", {"texto": "x"}, token=None))
    comprobar("sin token: 401", sin_token["statusCode"] == 401)

    comprobar("las dos rutas exigen profesional en el código, no en la vista",
              lanza(SinPermiso, _con_acceso, AccesoFalso(ActorFalso("paciente")),
                    orquestador._solo_profesional, _evento("POST /dictado/sesion")) is not None)
    comprobar("y sin token no llegan ni a ROBLE",
              lanza(NoAutorizado, orquestador._solo_profesional, _evento("POST /dictado/sesion", token=None))
              is not None)


def probar_dictado() -> None:
    print("\nLa firma del dictado")
    try:
        import botocore.auth  # noqa: F401
        from botocore.credentials import ReadOnlyCredentials
    except ImportError:
        # En CI `botocore` es el sustituto de `entorno.py`, sin submódulos.
        print("  (omitida: sin botocore instalado, como en CI; la firma se prueba en local)")
        return

    credenciales = ReadOnlyCredentials("AKIDEXAMPLE", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "token-de-sesion")
    url = dictado.firmar(
        "https://transcribestreaming.us-east-1.amazonaws.com:8443/stream-transcription-websocket"
        "?language-code=es-US&media-encoding=pcm&sample-rate=16000",
        credenciales,
        "us-east-1",
    )
    partes = urlsplit(url)
    parametros = dict(parse_qsl(partes.query))
    comprobar("firma en la URL, con el token de sesión", "X-Amz-Signature" in parametros
              and parametros.get("X-Amz-Security-Token") == "token-de-sesion")
    comprobar("caduca a los 300 s", parametros.get("X-Amz-Expires") == "300")

    # La firma, recalculada a mano con el algoritmo de la guía de Transcribe para
    # WebSocket: si botocore hubiera usado UNSIGNED-PAYLOAD, no coincidiría.
    fecha = parametros["X-Amz-Date"]
    firmados = {k: v for k, v in parametros.items() if k != "X-Amz-Signature"}
    consulta = "&".join(
        f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(firmados.items())
    )
    canonica = "\n".join([
        "GET", partes.path, consulta,
        f"host:{partes.netloc}\n", "host", hashlib.sha256(b"").hexdigest(),
    ])
    ambito = f"{fecha[:8]}/us-east-1/transcribe/aws4_request"
    a_firmar = "\n".join([
        "AWS4-HMAC-SHA256", fecha, ambito, hashlib.sha256(canonica.encode()).hexdigest()
    ])

    def h(clave: bytes, texto: str) -> bytes:
        return hmac.new(clave, texto.encode(), hashlib.sha256).digest()

    clave = h(h(h(h(("AWS4" + credenciales.secret_key).encode(), fecha[:8]), "us-east-1"), "transcribe"),
              "aws4_request")
    esperada = hmac.new(clave, a_firmar.encode(), hashlib.sha256).hexdigest()
    comprobar("la firma es la de la guía de Transcribe (hash del cuerpo vacío)",
              parametros["X-Amz-Signature"] == esperada)


def probar_frecuencia_compartida() -> None:
    print("\nUna sola regla de frecuencias")
    comprobar("recordatorios usa la de caresync_comun, no una copia",
              recordatorios._intervalo is frecuencia.intervalo)


def main() -> int:
    for prueba in (probar_depurar, probar_proponer, probar_rutas, probar_dictado, probar_frecuencia_compartida):
        prueba()
    print()
    if fallos():
        print(f"{len(fallos())} pruebas fallaron:")
        for nombre in fallos():
            print(f"  - {nombre}")
        return 1
    print("Todas las pruebas pasan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
