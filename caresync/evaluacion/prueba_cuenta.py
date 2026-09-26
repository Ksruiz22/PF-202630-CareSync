#!/usr/bin/env python3
"""
Pruebas de `cuenta_roble.py` y de cómo lo usan los evaluadores. Sin red ni tokens.

    python prueba_cuenta.py

Lo que se protege es lo que hace que una sola cuenta sirva para todo el banco:

- que el caso se cierre con la petición que ROBLE espera (`PUT /update` sobre
  `casos`, por `_id`), porque si el cierre no llega, cada caso del banco continúa
  el anterior y el informe sale lleno de contaminados;
- que un 401 a media corrida se resuelva renovando una sola vez y no pare la
  evaluación a los diez minutos, cuando vence el token de acceso;
- que el archivo `.env` no pise lo que ya esté exportado, para poder cambiar de
  cuenta sin editarlo.

El transporte se sustituye por un falso que anota cada petición.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cuenta_roble as cr  # noqa: E402
import evaluar_triaje as ev  # noqa: E402

_fallos: list[str] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    marca = "ok  " if condicion else "FALLA"
    print(f"  {marca} {nombre}" + (f" -> {detalle}" if detalle else ""))
    if not condicion:
        _fallos.append(nombre)


class _Respuesta:
    def __init__(self, estado: int, cuerpo=None) -> None:
        self.status_code = estado
        self._cuerpo = cuerpo if cuerpo is not None else {}
        self.text = str(self._cuerpo)

    def json(self):
        return self._cuerpo


class _RequestsFalso:
    """Imita lo que los evaluadores usan de `requests`, con respuestas guionadas."""

    class RequestException(Exception):
        pass

    def __init__(self, guion) -> None:
        # guion(metodo, url, cuerpo, cabeceras) -> _Respuesta
        self._guion = guion
        self.peticiones: list[tuple[str, str, dict, dict]] = []

    def request(self, metodo, url, headers=None, json=None, params=None, timeout=None):
        self.peticiones.append((metodo, url, json or params or {}, headers or {}))
        return self._guion(metodo, url, json or params or {}, headers or {})

    def post(self, url, json=None, headers=None, timeout=None):
        return self.request("POST", url, headers=headers, json=json, timeout=timeout)


def _instalar(falso: _RequestsFalso) -> None:
    cr.requests = falso
    ev.requests = falso


# ------------------------------------------------------------------- el cierre

def probar_cierre() -> None:
    print("\nCierre del caso")

    falso = _RequestsFalso(lambda *_: _Respuesta(200, {}))
    _instalar(falso)
    credencial = cr.Credencial.desde_token("tk")
    ok = credencial.cerrar_caso("c-123")

    metodo, url, cuerpo, cabeceras = falso.peticiones[-1]
    comprobar("devuelve que se cerró", ok)
    comprobar("es un PUT a /database/<contrato>/update",
              metodo == "PUT" and url.endswith(f"/database/{cr.ROBLE_CONTRATO}/update"), url)
    comprobar("actualiza casos por _id",
              cuerpo.get("tableName") == "casos" and cuerpo.get("idColumn") == "_id"
              and cuerpo.get("idValue") == "c-123", str(cuerpo))
    comprobar("sólo cambia el estado a cerrado",
              cuerpo.get("updates") == {"estado": "cerrado"}, str(cuerpo.get("updates")))
    comprobar("con el token del paciente", cabeceras.get("Authorization") == "Bearer tk")

    comprobar("sin caso no llama a nada", not cr.Credencial.desde_token("tk").cerrar_caso(""))

    _instalar(_RequestsFalso(lambda *_: _Respuesta(500, {})))
    comprobar("un 500 se informa como no cerrado, sin lanzar",
              cr.Credencial.desde_token("tk").cerrar_caso("c-1") is False)

    def caido(*_):
        raise _RequestsFalso.RequestException("sin red")

    _instalar(_RequestsFalso(caido))
    comprobar("sin red tampoco lanza", cr.Credencial.desde_token("tk").cerrar_caso("c-1") is False)


def probar_limpieza_inicial() -> None:
    print("\nLimpieza antes de la corrida")

    def guion(metodo, url, cuerpo, _cabeceras):
        if url.endswith("/me"):
            return _Respuesta(200, {"userId": "u-9", "id": "otro"})
        if url.endswith("/read"):
            return _Respuesta(200, [
                {"_id": "a", "estado": "canalizado"},
                {"_id": "b", "estado": "cerrado"},
                {"_id": "c", "estado": "urgencia_escalada"},
            ])
        return _Respuesta(200, {})

    falso = _RequestsFalso(guion)
    _instalar(falso)
    cerrados = cr.Credencial.desde_token("tk").cerrar_casos_abiertos()

    lectura = next(p for p in falso.peticiones if p[1].endswith("/read"))
    cerrados_ids = [p[2].get("idValue") for p in falso.peticiones if p[0] == "PUT"]
    comprobar("filtra por el userId de /me, el mismo que usa el orquestador",
              lectura[2].get("paciente_user_id") == "u-9", str(lectura[2]))
    comprobar("cierra sólo los que no estaban cerrados",
              cerrados == 2 and cerrados_ids == ["a", "c"], str(cerrados_ids))


# ----------------------------------------------------------------- la sesión

def probar_renovacion() -> None:
    print("\nRenovación del token")

    estado = {"llamadas_agente": 0}

    def guion(metodo, url, cuerpo, cabeceras):
        if url.endswith("/login"):
            return _Respuesta(201, {"accessToken": "acc-1", "refreshToken": "ref-1"})
        if url.endswith("/refresh-token"):
            ok = cuerpo.get("refreshToken") == "ref-1"
            return _Respuesta(201 if ok else 401, {"accessToken": "acc-2"} if ok else {})
        if url.endswith("/agente"):
            estado["llamadas_agente"] += 1
            if cabeceras.get("Authorization") == "Bearer acc-1":
                return _Respuesta(401, {"error": "vencido"})
            return _Respuesta(200, {"respuesta": "hola", "caso": {"id": "k"}})
        return _Respuesta(404, {})

    falso = _RequestsFalso(guion)
    _instalar(falso)
    cuenta = cr.Credencial.desde_contrasena("p@x.co", "secreta")
    comprobar("el inicio de sesión guarda el token de acceso", cuenta.actual() == "acc-1")

    datos = ev.llamar_agente("https://api", cuenta, "hola", intentos=3)
    comprobar("un 401 se resuelve renovando y reintentando",
              datos.get("respuesta") == "hola" and estado["llamadas_agente"] == 2,
              f"{estado['llamadas_agente']} llamadas")
    comprobar("renueva con refresh-token y no gasta un inicio de sesión",
              sum(1 for p in falso.peticiones if p[1].endswith("/login")) == 1)
    comprobar("se queda con el token nuevo", cuenta.actual() == "acc-2")

    # Un token fijo, sin contraseña, no se puede renovar: tiene que parar con un
    # mensaje que diga qué hacer, no reintentar a ciegas.
    _instalar(_RequestsFalso(lambda *_: _Respuesta(401, {})))
    try:
        ev.llamar_agente("https://api", cr.Credencial.desde_token("viejo"), "hola")
        paro = False
    except SystemExit as salida:
        paro = "CARESYNC_EMAIL" in str(salida)
    comprobar("un token fijo vencido para y dice cómo arreglarlo", paro)


def probar_inicio_fallido() -> None:
    print("\nInicio de sesión")

    _instalar(_RequestsFalso(lambda *_: _Respuesta(401, {"message": "no"})))
    try:
        cr.Credencial.desde_contrasena("p@x.co", "mala")
        lanzo = ""
    except cr.ErrorDeCuenta as exc:
        lanzo = str(exc)
    comprobar("credenciales malas dan un error que nombra la cuenta", "p@x.co" in lanzo, lanzo)

    _instalar(_RequestsFalso(lambda *_: _Respuesta(429, {})))
    try:
        cr.Credencial.desde_contrasena("p@x.co", "x")
        lanzo = ""
    except cr.ErrorDeCuenta as exc:
        lanzo = str(exc)
    comprobar("un 429 explica el cubo de 10 inicios cada 15 minutos", "15 minutos" in lanzo, lanzo)


# ------------------------------------------------------------ configuración

def probar_entorno() -> None:
    print("\nArchivo .env")

    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / ".env"
        ruta.write_text(
            "# comentario\nCARESYNC_PRUEBA_A=desde_archivo\nexport CARESYNC_PRUEBA_B=\"con comillas\"\n"
            "CARESYNC_PRUEBA_C=no_pisa\nlinea sin igual\n",
            encoding="utf-8",
        )
        os.environ.pop("CARESYNC_PRUEBA_A", None)
        os.environ.pop("CARESYNC_PRUEBA_B", None)
        os.environ["CARESYNC_PRUEBA_C"] = "exportado"
        cr.cargar_entorno(ruta)

        comprobar("lee CLAVE=valor", os.environ.get("CARESYNC_PRUEBA_A") == "desde_archivo")
        comprobar("admite export y comillas", os.environ.get("CARESYNC_PRUEBA_B") == "con comillas")
        comprobar("lo exportado manda sobre el archivo",
                  os.environ.get("CARESYNC_PRUEBA_C") == "exportado")
        for clave in ("CARESYNC_PRUEBA_A", "CARESYNC_PRUEBA_B", "CARESYNC_PRUEBA_C"):
            os.environ.pop(clave, None)

    comprobar("sin archivo no hace nada", cr.cargar_entorno(Path("no-existe/.env")) is None)


def probar_una_cuenta_para_todos() -> None:
    print("\nUna cuenta para todo el banco")

    lista = [cr.Credencial.desde_token("a")] * 3 + [cr.Credencial.desde_token("b")]
    comprobar("distintas() limpia cada cuenta una sola vez", len(cr.distintas(lista)) == 2)

    cerrados: list[str] = []

    class _Falsa:
        def cerrar_caso(self, caso_id: str) -> bool:
            cerrados.append(caso_id)
            return True

    t = ev.Transcripcion(id="x", categoria="cmu_claro", turnos=[
        ev.Turno(numero=1, enviado="m0", caso_id="k-1"),
        ev.Turno(numero=2, enviado="m1", caso_id="k-1"),
    ])
    ev.cerrar_al_terminar(_Falsa(), t)
    comprobar("al terminar cierra el caso de la conversación", cerrados == ["k-1"], str(cerrados))

    cerrados.clear()
    ev.cerrar_al_terminar(_Falsa(), ev.Transcripcion(id="y", categoria="cmu_claro", turnos=[
        ev.Turno(numero=1, enviado="m0", error="HTTP 502")
    ]))
    comprobar("sin caso abierto no intenta cerrar nada", cerrados == [])


def main() -> int:
    for prueba in (
        probar_cierre,
        probar_limpieza_inicial,
        probar_renovacion,
        probar_inicio_fallido,
        probar_entorno,
        probar_una_cuenta_para_todos,
    ):
        prueba()

    print()
    if _fallos:
        print(f"{len(_fallos)} pruebas fallaron:")
        for nombre in _fallos:
            print(f"  - {nombre}")
        return 1
    print("Todas las pruebas pasan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
