"""Módulo compartido por las tres funciones de CareSync.

Va en una capa de Lambda junto a `requests` y al SDK de ROBLE. Contiene lo que
no debe duplicarse entre funciones: la configuración, el reloj, el registro, los
errores del dominio, el catálogo de herramientas y —sobre todo—
`roble_acceso`, la única puerta a los datos.

El catálogo de herramientas está aquí, y no dentro del orquestador, porque lo
comparten dos funciones distintas: el orquestador declara las herramientas al
modelo y la función de herramientas las ejecuta. Si cada una tuviera su copia,
la primera divergencia sería silenciosa —el modelo llamaría con un argumento que
la otra parte ya no lee— y sólo se vería como una respuesta rara del agente.
"""

from .errores import (
    Conflicto,
    ErrorDeCareSync,
    ErrorDeConfiguracion,
    ErrorDeDatos,
    NoAutorizado,
    NoEncontrado,
    SinPermiso,
    SolicitudInvalida,
)

__all__ = [
    "Conflicto",
    "ErrorDeCareSync",
    "ErrorDeConfiguracion",
    "ErrorDeDatos",
    "NoAutorizado",
    "NoEncontrado",
    "SinPermiso",
    "SolicitudInvalida",
]
