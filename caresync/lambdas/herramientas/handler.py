"""Función de herramientas: lo único del sistema que produce efectos.

El orquestador decide *qué* hacer; esta función lo hace. Están separadas a
propósito, y la separación es de seguridad, no de estilo:

* El orquestador puede tener el bucle del modelo, que es la parte impredecible.
  Aquí no entra nada que el modelo haya inventado sin pasar por una validación.
* La identidad no la aporta el modelo. El `caso_id` y el token llegan en el
  bloque `contexto` que arma el orquestador desde la sesión. Si el modelo
  incluyera un `caso_id` entre sus argumentos, se ignora: no está en el catálogo.
* El rol se vuelve a comprobar aquí. El orquestador ya filtra qué herramientas
  declara, pero una segunda comprobación en el punto donde ocurre el efecto es
  lo que hace que el filtro del prompt no sea la única defensa.

El valor de retorno no es una respuesta HTTP: es el diccionario que el
orquestador mete en el bloque `toolResult`. Un error de dominio sale como
`{"error": "..."}` y el modelo lo explica a la persona, en lugar de romper la
conversación.
"""

from __future__ import annotations

from typing import Any, Callable

from caresync_comun.catalogo_herramientas import CATALOGO, Herramienta, permitida
from caresync_comun.errores import (
    ErrorDeCareSync,
    NoAutorizado,
    SinPermiso,
    SolicitudInvalida,
)
from caresync_comun.registro import evento, registro
from caresync_comun.roble_acceso import AccesoRoble, fila_id

import agenda
import seguimiento
import triaje

log = registro("herramientas")

# Nombre del catálogo -> función que lo ejecuta. Que las claves sean las mismas
# del catálogo no es casual: `_comprobar_cobertura` falla al importar si alguien
# añade una herramienta al catálogo y olvida implementarla.
EJECUTORES: dict[str, Callable[[AccesoRoble, dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "consultar_estado_caso": triaje.consultar_estado_caso,
    "canalizar_caso": triaje.canalizar_caso,
    "escalar_urgencia": triaje.escalar_urgencia,
    "consultar_disponibilidad": agenda.consultar_disponibilidad,
    "agendar_cita": agenda.agendar_cita,
    "notificar_profesional": agenda.notificar_profesional,
    "consultar_plan": seguimiento.consultar_plan,
    "registrar_evolucion": seguimiento.registrar_evolucion,
    "registrar_adherencia": seguimiento.registrar_adherencia,
}


def _comprobar_cobertura() -> None:
    faltan = set(CATALOGO) - set(EJECUTORES)
    sobran = set(EJECUTORES) - set(CATALOGO)
    if faltan or sobran:
        raise RuntimeError(
            f"Catálogo y ejecutores desalineados. Sin implementar: {sorted(faltan)}. "
            f"Sin declarar: {sorted(sobran)}."
        )


_comprobar_cobertura()


def manejar(entrada: dict[str, Any], contexto_lambda: Any = None) -> dict[str, Any]:
    nombre = str(entrada.get("herramienta") or "").strip()
    crudos = entrada.get("argumentos") or {}
    contexto = entrada.get("contexto") or {}

    try:
        return _ejecutar(nombre, crudos, contexto)
    except ErrorDeCareSync as exc:
        evento(
            log,
            "herramienta_rechazada",
            herramienta=nombre,
            tipo=type(exc).__name__,
            detalle=exc.mensaje,
        )
        # Lo que va al modelo es el mensaje público, nunca el de ROBLE.
        return {"error": exc.publico, "herramienta": nombre}
    except Exception:  # noqa: BLE001
        log.exception("herramienta_reventada", extra={"caresync": {"herramienta": nombre}})
        return {
            "error": "La operación no se pudo completar por un problema técnico.",
            "herramienta": nombre,
        }


def _ejecutar(nombre: str, crudos: dict[str, Any], contexto: dict[str, Any]) -> dict[str, Any]:
    herramienta = CATALOGO.get(nombre)
    if not herramienta:
        raise SolicitudInvalida(f"No existe la herramienta «{nombre}»")

    token = str(contexto.get("access_token") or "")
    caso_id = str(contexto.get("caso_id") or "")
    if not token:
        raise NoAutorizado("La invocación no trae el token del llamante")
    if not caso_id:
        raise SolicitudInvalida("La invocación no trae el caso sobre el que actuar")

    argumentos = _argumentos(herramienta, crudos)

    acceso = AccesoRoble.desde_token(token)
    try:
        if not permitida(nombre, acceso.actor.rol):
            raise SinPermiso(f"El rol «{acceso.actor.rol}» no puede usar {nombre}")

        # Autorización de fila: que el caso exista no basta, tiene que ser un
        # caso que este actor tenga por qué tocar.
        caso = acceso.caso_visible(caso_id)

        salida = EJECUTORES[nombre](acceso, caso, argumentos)

        evento(
            log,
            "herramienta_ejecutada",
            herramienta=nombre,
            caso_id=fila_id(caso),
            rol=acceso.actor.rol,
            agente=contexto.get("agente"),
            escribe=herramienta.escribe,
        )
        return salida
    finally:
        acceso.cerrar()


# ------------------------------------------------------ validación de argumentos

def _argumentos(herramienta: Herramienta, crudos: dict[str, Any]) -> dict[str, Any]:
    """Filtra y comprueba lo que mandó el modelo contra el catálogo.

    Bedrock valida el esquema de entrada, pero no es la única fuente posible de
    una invocación y validar dos veces cuesta microsegundos. Lo importante es lo
    que hace la primera línea: **descarta cualquier clave que no esté declarada**,
    así que un `caso_id` o un `user_id` colados por el modelo no llegan al
    dominio.
    """
    if not isinstance(crudos, dict):
        raise SolicitudInvalida(f"Los argumentos de {herramienta.nombre} no son un objeto")

    limpios: dict[str, Any] = {}
    for clave, esquema in herramienta.propiedades.items():
        if clave not in crudos or crudos[clave] is None:
            continue
        limpios[clave] = _valor(herramienta.nombre, clave, esquema, crudos[clave])

    faltan = [c for c in herramienta.requeridos if c not in limpios]
    if faltan:
        raise SolicitudInvalida(
            f"A {herramienta.nombre} le faltan argumentos: {', '.join(faltan)}"
        )
    return limpios


def _valor(herramienta: str, clave: str, esquema: dict[str, Any], valor: Any) -> Any:
    tipo = esquema.get("type")

    if tipo == "integer":
        try:
            # El modelo manda enteros como texto con más frecuencia de la que
            # debería; convertir es más útil que rechazar.
            numero = int(float(str(valor).strip()))
        except (TypeError, ValueError) as exc:
            raise SolicitudInvalida(f"{herramienta}.{clave} debe ser un número entero") from exc
        minimo, maximo = esquema.get("minimum"), esquema.get("maximum")
        if minimo is not None:
            numero = max(int(minimo), numero)
        if maximo is not None:
            numero = min(int(maximo), numero)
        return numero

    if tipo == "boolean":
        if isinstance(valor, bool):
            return valor
        return str(valor).strip().lower() in ("true", "1", "si", "sí", "yes")

    texto = str(valor).strip()
    opciones = esquema.get("enum")
    if opciones and texto not in opciones:
        # Un enum equivocado no se corrige adivinando: el agente tiene que
        # volver a decidir con la lista delante.
        raise SolicitudInvalida(
            f"{herramienta}.{clave} debe ser uno de: {', '.join(map(str, opciones))}"
        )
    return texto
