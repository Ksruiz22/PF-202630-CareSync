"""Configuración del entorno, leída una vez por contenedor.

Nada sensible viaja en variables de entorno de Lambda: sólo el prefijo del que
leer. Lo demás está en Parameter Store, cifrado cuando toca.

La lectura de las credenciales de servicio va en su propia función y su propia
llamada porque los permisos también están separados: sólo el rol de
`recordatorios` puede leerlas, y una llamada conjunta fallaría entera para las
otras dos funciones.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import boto3

from .errores import ErrorDeConfiguracion

RELLENO = "PENDIENTE-DE-CARGAR"


@dataclass(frozen=True)
class Config:
    entorno: str
    roble_base_url: str
    roble_contract_id: str
    correo_remitente: str
    correo_emergencias: str
    ses_conjunto: str

    @property
    def envia_correo(self) -> bool:
        """Si no hay remitente verificado, los envíos se registran en el log.

        Es lo que permite desplegar y probar el flujo completo antes de que SES
        esté listo, en lugar de dejar el agendamiento roto esperando un correo.
        """
        return bool(self.correo_remitente) and self.correo_remitente != RELLENO


@lru_cache(maxsize=1)
def _ssm():
    return boto3.client("ssm")


def _prefijo() -> str:
    prefijo = os.environ.get("SSM_PREFIJO", "").rstrip("/")
    if not prefijo:
        raise ErrorDeConfiguracion("Falta la variable de entorno SSM_PREFIJO")
    return prefijo


def _leer(nombres: dict[str, str], *, descifrar: bool) -> dict[str, str]:
    """Lee varios parámetros de una vez y devuelve {clave: valor}."""
    rutas = {ruta: clave for clave, ruta in nombres.items()}
    respuesta = _ssm().get_parameters(Names=list(rutas), WithDecryption=descifrar)

    faltantes = list(respuesta.get("InvalidParameters") or [])
    if faltantes:
        raise ErrorDeConfiguracion(
            "Parámetros ausentes o sin permiso de lectura: " + ", ".join(sorted(faltantes))
        )

    return {rutas[p["Name"]]: p["Value"] for p in respuesta["Parameters"]}


@lru_cache(maxsize=1)
def config() -> Config:
    """Configuración común. Se cachea por contenedor, no por invocación."""
    prefijo = _prefijo()
    valores = _leer(
        {
            "base_url": f"{prefijo}/roble/base_url",
            "contract_id": f"{prefijo}/roble/contract_id",
            "remitente": f"{prefijo}/correo/remitente",
            "emergencias": f"{prefijo}/correo/emergencias",
        },
        descifrar=False,
    )

    for clave in ("base_url", "contract_id"):
        if valores[clave] in ("", RELLENO):
            raise ErrorDeConfiguracion(
                f"El parámetro {prefijo}/roble/{clave} sigue sin cargar"
            )

    def real(valor: str) -> str:
        return "" if valor == RELLENO else valor

    return Config(
        entorno=os.environ.get("ENTORNO", "dev"),
        roble_base_url=valores["base_url"],
        roble_contract_id=valores["contract_id"],
        correo_remitente=real(valores["remitente"]),
        correo_emergencias=real(valores["emergencias"]),
        ses_conjunto=os.environ.get("SES_CONJUNTO", ""),
    )


@lru_cache(maxsize=1)
def credenciales_servicio() -> tuple[str, str]:
    """Cuenta de ROBLE con la que corre la función de recordatorios.

    Existe sólo porque esa función la despierta el reloj y no hay un usuario que
    la autorice. El resto del sistema actúa con el token del propio llamante.
    """
    prefijo = _prefijo()
    valores = _leer(
        {
            "email": f"{prefijo}/roble/servicio/email",
            "password": f"{prefijo}/roble/servicio/password",
        },
        descifrar=True,
    )

    if RELLENO in (valores["email"], valores["password"]):
        raise ErrorDeConfiguracion(
            "Las credenciales de la cuenta de servicio de ROBLE siguen sin cargar. "
            f"Cárgalas en {prefijo}/roble/servicio/email y /password."
        )

    return valores["email"], valores["password"]
