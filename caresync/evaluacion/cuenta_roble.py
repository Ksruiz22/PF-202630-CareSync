"""
La cuenta de paciente con la que conversan los evaluadores.

Existe para que medir el triaje no dependa de un favor de ocho horas. Hasta ahora
cada caso del banco necesitaba su propio token: un caso canalizado no queda
cerrado, `caso_abierto_de` sólo excluye los cerrados, y el segundo caso de un token
continuaba el hilo del primero. Cuarenta cuentas, con `signup` limitado a cinco por
hora y por IP, eran ocho horas de reloj desde una sola máquina.

Pero cerrar el caso no necesita ninguna ruta nueva del sistema. El rol `user` de
ROBLE —el de toda cuenta que se registra— tiene `casos:update` (ver
`docs/runbook-roble.md`), porque el propio paciente actualiza su caso cuando el
agente lo canaliza. Así que el evaluador, con el mismo token con el que conversa,
marca su caso como `cerrado` al terminar, y la siguiente conversación abre uno
limpio. Una cuenta alcanza para todo el banco.

Tres decisiones que el código lleva tal cual:

- **Se inicia sesión con correo y contraseña, no con un token pegado.** El token de
  acceso de ROBLE es de vida corta y una corrida completa dura un cuarto de hora.
  Con la contraseña, un 401 se resuelve renovando —`refresh-token` está en el cubo
  de 100 por minuto, no en el de 10 inicios de sesión cada 15 minutos— y, si eso
  falla, volviendo a entrar.
- **Las credenciales se leen de `evaluacion/.env`**, que el `.gitignore` excluye.
  Las variables de entorno mandan sobre el archivo, para poder cambiar de cuenta
  sin editarlo.
- **Antes de empezar se cierran los casos que la cuenta tenga abiertos.** Si no, el
  primer caso del banco continuaría la última conversación de quien usó la cuenta
  a mano, y quedaría marcado como contaminado sin que nadie hubiera hecho nada mal.

Sigue funcionando el modo anterior —`CARESYNC_TOKEN` o `CARESYNC_TOKENS_FILE`—
para quien ya tenga tokens: sin contraseña no se puede renovar, pero cerrar el caso
sí, porque sólo necesita el token.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

RAIZ = Path(__file__).parent
ARCHIVO_ENTORNO = RAIZ / ".env"

# Los mismos valores de `infra/dev.tfvars`. No son secretos: el contrato viaja en
# cada URL que pide la PWA. Se pueden cambiar por entorno para otro despliegue.
ROBLE_URL = "https://roble-api.test-openlab.uninorte.edu.co"
ROBLE_CONTRATO = "caresync_cab021ce03"

TIEMPO_ESPERA = 20
CASO_CERRADO = "cerrado"


def cargar_entorno(ruta: Path = ARCHIVO_ENTORNO) -> None:
    """Lee `CLAVE=valor` de `evaluacion/.env` sin pisar lo que ya esté exportado.

    Un lector de diez líneas y no `python-dotenv`: el evaluador sólo pide
    `requests`, y una dependencia más es una instalación más en la máquina de
    quien vaya a correrlo.
    """
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip().removeprefix("export ").strip()
        valor = valor.strip().strip('"').strip("'")
        if clave and clave not in os.environ:
            os.environ[clave] = valor


class ErrorDeCuenta(Exception):
    """Algo que impide seguir conversando con esta cuenta."""


class Credencial:
    """Un token de paciente que sabe renovarse y cerrar su propio caso.

    Se construye con `desde_contrasena` (lo normal) o `desde_token` (compatibilidad
    con los archivos de tokens). Los evaluadores sólo usan `actual()`, `renovar()` y
    `cerrar_caso()`.
    """

    def __init__(
        self,
        *,
        token: str = "",
        email: str = "",
        contrasena: str = "",
        base_url: str = "",
        contrato: str = "",
    ) -> None:
        self._acceso = token
        self._refresco = ""
        self._email = email
        self._contrasena = contrasena
        self._user_id = ""
        base = (base_url or os.environ.get("CARESYNC_ROBLE_URL") or ROBLE_URL).rstrip("/")
        contrato = contrato or os.environ.get("CARESYNC_ROBLE_CONTRATO") or ROBLE_CONTRATO
        self._auth = f"{base}/auth/{contrato}"
        self._datos = f"{base}/database/{contrato}"

    # ---------------------------------------------------------- construcción

    @classmethod
    def desde_contrasena(cls, email: str, contrasena: str) -> Credencial:
        credencial = cls(email=email, contrasena=contrasena)
        credencial._entrar()
        return credencial

    @classmethod
    def desde_token(cls, token: str) -> Credencial:
        return cls(token=token)

    @property
    def renovable(self) -> bool:
        return bool(self._email and self._contrasena)

    def __repr__(self) -> str:  # nunca el token en un log
        return f"Credencial({self._email or 'token fijo'})"

    # --------------------------------------------------------------- sesión

    def actual(self) -> str:
        return self._acceso

    def renovar(self) -> str:
        """Consigue un token de acceso nuevo, o explica por qué no se puede.

        Primero `refresh-token`, que no gasta del cubo de inicios de sesión. Si el
        refresco también está vencido, se vuelve a entrar con la contraseña.
        """
        if not self.renovable:
            raise ErrorDeCuenta(
                "401: ROBLE rechazó el token y no hay contraseña para renovarlo. Pon "
                "CARESYNC_EMAIL y CARESYNC_PASSWORD en evaluacion/.env, o genera tokens nuevos."
            )
        if self._refresco:
            respuesta = self._post(f"{self._auth}/refresh-token", {"refreshToken": self._refresco})
            datos = _json(respuesta)
            if respuesta.status_code in (200, 201) and datos.get("accessToken"):
                self._acceso = str(datos["accessToken"])
                self._refresco = str(datos.get("refreshToken") or self._refresco)
                return self._acceso
        self._entrar()
        return self._acceso

    def _entrar(self) -> None:
        respuesta = self._post(
            f"{self._auth}/login", {"email": self._email, "password": self._contrasena}
        )
        if respuesta.status_code == 429:
            raise ErrorDeCuenta(
                "429 al iniciar sesión: el cubo es de 10 inicios cada 15 minutos por IP. "
                "Espera un cuarto de hora."
            )
        datos = _json(respuesta)
        if respuesta.status_code not in (200, 201) or not datos.get("accessToken"):
            raise ErrorDeCuenta(
                f"ROBLE no aceptó el inicio de sesión de {self._email} "
                f"(HTTP {respuesta.status_code}). Revisa CARESYNC_EMAIL y CARESYNC_PASSWORD."
            )
        self._acceso = str(datos["accessToken"])
        self._refresco = str(datos.get("refreshToken") or "")

    # ---------------------------------------------------------------- datos

    def user_id(self) -> str:
        if not self._user_id:
            datos = _json(self._pedir("GET", f"{self._auth}/me"))
            # El orquestador usa `user_id or id` (`AccesoRoble._resolver_actor`); aquí
            # tiene que salir el mismo valor o no se encontraría ningún caso.
            self._user_id = str(datos.get("userId") or datos.get("id") or "")
        return self._user_id

    def cerrar_caso(self, caso_id: str) -> bool:
        """Marca el caso como cerrado. Devuelve si ROBLE lo aceptó.

        No lanza: si el cierre falla, la conversación siguiente continúa este caso y
        el evaluador la marca como contaminada, que es la red de seguridad que ya
        existía.
        """
        if not caso_id:
            return False
        try:
            respuesta = self._pedir(
                "PUT",
                f"{self._datos}/update",
                json={
                    "tableName": "casos",
                    "idColumn": "_id",
                    "idValue": caso_id,
                    "updates": {"estado": CASO_CERRADO},
                },
            )
        except ErrorDeCuenta:
            return False
        return respuesta.status_code in (200, 201, 204)

    def cerrar_casos_abiertos(self) -> int:
        """Cierra lo que la cuenta tenga abierto antes de la corrida. Devuelve cuántos."""
        user_id = self.user_id()
        if not user_id:
            return 0
        respuesta = self._pedir(
            "GET",
            f"{self._datos}/read",
            params={"tableName": "casos", "paciente_user_id": user_id},
        )
        filas = _json(respuesta, lista=True)
        abiertos = [
            str(f.get("_id") or f.get("id"))
            for f in filas
            if isinstance(f, dict) and f.get("estado") != CASO_CERRADO
        ]
        return sum(self.cerrar_caso(caso_id) for caso_id in abiertos)

    # ------------------------------------------------------------ transporte

    def _pedir(self, metodo: str, url: str, **kwargs: Any) -> Any:
        """Una petición autenticada a ROBLE, renovando una vez si vence el token."""
        _requiere_requests()
        for intento in (1, 2):
            try:
                respuesta = requests.request(
                    metodo,
                    url,
                    headers={"Authorization": f"Bearer {self._acceso}"},
                    timeout=TIEMPO_ESPERA,
                    **kwargs,
                )
            except requests.RequestException as exc:
                raise ErrorDeCuenta(f"No se pudo alcanzar ROBLE: {type(exc).__name__}") from exc
            if respuesta.status_code != 401 or intento == 2:
                return respuesta
            self.renovar()
        return respuesta  # pragma: no cover - el bucle siempre devuelve

    @staticmethod
    def _post(url: str, cuerpo: dict[str, Any]) -> Any:
        _requiere_requests()
        try:
            return requests.post(url, json=cuerpo, timeout=TIEMPO_ESPERA)
        except requests.RequestException as exc:
            raise ErrorDeCuenta(f"No se pudo alcanzar ROBLE: {type(exc).__name__}") from exc


def credenciales(n_casos: int) -> list[Credencial]:
    """Una credencial por caso, a partir de lo que haya configurado.

    Con correo y contraseña es la misma cuenta para todos: el evaluador cierra el
    caso entre uno y otro. Con un archivo de tokens se respeta un token por caso
    como antes, y los que falten reutilizan el último —ya sin contaminar, porque el
    caso se cierra igual—.
    """
    cargar_entorno()

    email = os.environ.get("CARESYNC_EMAIL", "").strip()
    contrasena = os.environ.get("CARESYNC_PASSWORD", "")
    if email and contrasena:
        try:
            cuenta = Credencial.desde_contrasena(email, contrasena)
        except ErrorDeCuenta as exc:
            sys.exit(str(exc))
        return [cuenta] * n_casos

    ruta = os.environ.get("CARESYNC_TOKENS_FILE", "")
    if ruta and Path(ruta).exists():
        tokens = [l.strip() for l in Path(ruta).read_text(encoding="utf-8").splitlines() if l.strip()]
        if not tokens:
            sys.exit(f"{ruta} está vacío.")
        fijas = [Credencial.desde_token(t) for t in tokens]
        fijas += [fijas[-1]] * max(0, n_casos - len(fijas))
        return fijas[:n_casos]

    token = os.environ.get("CARESYNC_TOKEN", "").strip()
    if token:
        return [Credencial.desde_token(token)] * n_casos

    sys.exit(
        "Falta la cuenta de prueba. Crea evaluacion/.env con CARESYNC_EMAIL y "
        "CARESYNC_PASSWORD de una cuenta de paciente que no se use para la demo."
    )


def distintas(lista: list[Credencial]) -> list[Credencial]:
    """Las credenciales sin repetir, en orden: para limpiar cada cuenta una vez."""
    vistas: list[Credencial] = []
    for credencial in lista:
        if not any(credencial is v for v in vistas):
            vistas.append(credencial)
    return vistas


def _json(respuesta: Any, *, lista: bool = False) -> Any:
    try:
        datos = respuesta.json()
    except ValueError:
        return [] if lista else {}
    if lista:
        return datos if isinstance(datos, list) else []
    return datos if isinstance(datos, dict) else {}


def _requiere_requests() -> None:
    if requests is None:
        sys.exit("Falta la dependencia «requests» para hablar con ROBLE: pip install requests")
