"""Cómo se cargan las Lambdas en una prueba, sin AWS ni ROBLE.

Las pruebas de esta carpeta ejercitan las funciones puras que sostienen la
seguridad y la lógica del sistema —permisos, argumentos, selección de agente,
historial, frecuencias— y ninguna abre una conexión. Pero los módulos que las
contienen importan `boto3`, `requests` y el SDK de ROBLE al cargarse, y CI corre
las pruebas sin instalar nada.

Por eso cada dependencia externa se sustituye **sólo si falta**: en una máquina
con el entorno montado se importan las de verdad, y en CI un módulo vacío con los
nombres que el código pide. Si alguien añade un `from roble import Algo` nuevo, la
prueba falla al importar y dice qué nombre falta aquí; es el aviso correcto.

Las dos funciones tienen un `handler.py` y cada una importa a sus hermanos por
nombre (`import agentes`, `import agenda`), así que no se pueden cargar las dos con
`import handler`. `cargar()` les da un nombre propio a cada una.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Any

LAMBDAS = Path(__file__).resolve().parent.parent

_fallos: list[str] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    """Lo mismo que usan las pruebas de los evaluadores: una línea por comprobación."""
    marca = "ok  " if condicion else "FALLA"
    print(f"  {marca} {nombre}" + (f" -> {detalle}" if detalle else ""))
    if not condicion:
        _fallos.append(nombre)


def lanza(tipo: type[BaseException], funcion, *args: Any, **kwargs: Any) -> BaseException | None:
    """La excepción de ese tipo que lanzó `funcion`, o `None` si no lanzó ninguna."""
    try:
        funcion(*args, **kwargs)
    except tipo as exc:
        return exc
    return None


def fallos() -> list[str]:
    return list(_fallos)


# ------------------------------------------------------------ dependencias

class _ErrorRoble(Exception):
    pass


class _ErrorHttpRoble(_ErrorRoble):
    def __init__(self, mensaje: str = "", status_code: int = 500) -> None:
        super().__init__(mensaje)
        self.status_code = status_code


def _sustituto(nombre: str, **atributos: Any) -> None:
    modulo = types.ModuleType(nombre)
    for clave, valor in atributos.items():
        setattr(modulo, clave, valor)
    sys.modules[nombre] = modulo


def _falta(nombre: str) -> bool:
    try:
        importlib.import_module(nombre)
    except ModuleNotFoundError:
        return True
    return False


def _cliente_inutilizable(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("Una prueba intentó hablar con AWS: sólo se prueban funciones puras")


def preparar() -> None:
    """Deja importables `caresync_comun` y las tres funciones. Se puede llamar varias veces."""
    comun = str(LAMBDAS / "comun")
    if comun not in sys.path:
        sys.path.insert(0, comun)

    # Nada de lo que se prueba lee Parameter Store, pero `config()` lo intentaría si
    # alguna rama lo alcanzara; con el prefijo puesto falla en el cliente, no antes.
    os.environ.setdefault("SSM_PREFIJO", "/caresync/pruebas")
    os.environ.setdefault("NIVEL_LOG", "CRITICAL")

    if _falta("boto3"):
        _sustituto("boto3", client=_cliente_inutilizable)
    if _falta("botocore"):
        _sustituto("botocore")
        _sustituto("botocore.config", Config=lambda **_kw: None)

        class ClientError(Exception):
            def __init__(self, response: dict | None = None, operation_name: str = "") -> None:
                super().__init__(operation_name)
                self.response = response or {}

        _sustituto("botocore.exceptions", ClientError=ClientError)
    if _falta("requests"):

        class RequestException(Exception):
            pass

        _sustituto("requests", RequestException=RequestException, get=_cliente_inutilizable)
    if _falta("roble"):
        _sustituto(
            "roble",
            MemoryStorage=object,
            RobleClient=object,
            User=object,
            RobleError=_ErrorRoble,
            RobleAuthError=_ErrorRoble,
            RobleHttpError=_ErrorHttpRoble,
            RobleNetworkError=_ErrorRoble,
            RobleTimeoutError=_ErrorRoble,
        )


def cargar(funcion: str, modulo: str) -> types.ModuleType:
    """Importa `lambdas/<funcion>/<modulo>.py` con un nombre que no choque.

    La carpeta de la función va al principio de `sys.path` para que sus
    `import agentes` o `import agenda` resuelvan contra sus hermanos.
    """
    preparar()
    carpeta = LAMBDAS / funcion
    if str(carpeta) not in sys.path:
        sys.path.insert(0, str(carpeta))

    nombre = f"{funcion}__{modulo}"
    if nombre in sys.modules:
        return sys.modules[nombre]
    especificacion = importlib.util.spec_from_file_location(nombre, carpeta / f"{modulo}.py")
    assert especificacion and especificacion.loader
    cargado = importlib.util.module_from_spec(especificacion)
    sys.modules[nombre] = cargado
    especificacion.loader.exec_module(cargado)
    return cargado


# ------------------------------------------------------------- dobles de datos

class ActorFalso:
    """Lo que el código lee de `Actor`, sin pasar por ROBLE."""

    def __init__(self, rol: str, *, user_id: str = "u-1", centro: str | None = None) -> None:
        self.rol = rol
        self.user_id = user_id
        self.centro = centro
        self.nombre = "Persona de prueba"
        self.email = "prueba@uninorte.edu.co"

    @property
    def es_paciente(self) -> bool:
        return self.rol == "paciente"

    @property
    def es_administrativo(self) -> bool:
        return self.rol in ("admin_cmu", "admin_cae")


class AccesoFalso:
    """Un `AccesoRoble` en memoria: anota lo que se escribe y devuelve lo que se le dé."""

    def __init__(
        self,
        actor: ActorFalso,
        *,
        casos: dict[str, dict[str, Any]] | None = None,
        mensajes: list[dict[str, Any]] | None = None,
        abierto: dict[str, Any] | None = None,
        falla_al_escribir: bool = False,
    ) -> None:
        self.actor = actor
        self._casos = casos or {}
        self._mensajes = mensajes or []
        self._abierto = abierto
        self._falla = falla_al_escribir
        self.escrito: list[tuple[str, dict[str, Any]]] = []

    def _escribir(self, que: str, datos: dict[str, Any]) -> dict[str, Any]:
        if self._falla:
            raise RuntimeError(f"ROBLE no responde ({que})")
        self.escrito.append((que, datos))
        return {"_id": f"nuevo-{len(self.escrito)}", **datos}

    # Lo que usa el orquestador
    def caso_visible(self, caso_id: str) -> dict[str, Any]:
        return self._casos[caso_id]

    def caso_abierto_de(self, user_id: str) -> dict[str, Any] | None:
        return self._abierto

    def abrir_caso(self, *, motivo: str) -> dict[str, Any]:
        return self._escribir("abrir_caso", {"motivo": motivo, "estado": "abierto"})

    def mensajes(self, caso_id: str, *, maximo: int = 30) -> list[dict[str, Any]]:
        return list(self._mensajes)[-maximo:]

    def anotar_mensaje(self, **datos: Any) -> None:
        self._escribir("mensaje", datos)

    # Lo que usan las herramientas
    def actualizar_caso(self, caso_id: str, cambios: dict[str, Any]) -> dict[str, Any]:
        return self._escribir("caso", {"caso_id": caso_id, **cambios})

    def registrar_evento(self, **datos: Any) -> dict[str, Any]:
        return self._escribir("evento", datos)
