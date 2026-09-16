#!/usr/bin/env python3
"""
Pruebas de `evaluar_triaje.py`. Sin red, sin tokens, sin AWS.

    python prueba_evaluar.py

Miden dos cosas distintas y las dos importan:

**El bucle de conversación.** Que pare cuando el agente canaliza o escala, que no
gaste mensajes de más, que reenvíe el `caso_id` a partir del segundo turno y que
detecte la contaminación de token. Un fallo aquí no rompe nada de forma visible: se
traga cuota de ROBLE y produce un informe con un número equivocado, que es peor que
un error.

**Los criterios de evaluación.** Que un desacierto hacia arriba no cuente como falla
y uno hacia abajo sí, que escalar antes de clasificar sea lo exigido en las alarmas,
y que una consulta administrativa escalada se marque como falla — ese último caso lo
daba por bueno siempre la versión anterior del script.

El transporte se sustituye por una función guionada, así que esto no llama a nada.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import evaluar_triaje as ev  # noqa: E402

CAN = {"herramienta": "canalizar_caso", "ok": True}
ESC = {"herramienta": "escalar_urgencia", "ok": True}

_fallos: list[str] = []
_llamadas: list[tuple[str, str, str]] = []


def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
    marca = "ok  " if condicion else "FALLA"
    print(f"  {marca} {nombre}" + (f" -> {detalle}" if detalle else ""))
    if not condicion:
        _fallos.append(nombre)


def _simular(respuestas: list[dict]):
    """Reemplaza `llamar_agente`: una respuesta guionada por turno y por token."""

    def falso(api_url, token, mensaje, caso_id="", intentos=3):
        _llamadas.append((token, mensaje, caso_id))
        indice = len([c for c in _llamadas if c[0] == token]) - 1
        return respuestas[min(indice, len(respuestas) - 1)]

    return falso


def _resp(estado=None, centro=None, nivel=None, acciones=(), caso_id="k1", guardrail=False):
    return {
        "respuesta": "texto del agente",
        "caso": {"id": caso_id, "estado": estado, "centro": centro, "nivel_urgencia": nivel},
        "agentes": ["triaje"],
        "acciones": list(acciones),
        "salvaguardas_intervinieron": guardrail,
    }


CASO = {"id": "x", "categoria": "cmu_claro", "mensaje": "m0", "respuestas": ["m1", "m2", "m3", "m4"]}


# ------------------------------------------------------ el bucle de conversación

def probar_conversacion() -> None:
    print("\nBucle de conversación")

    _llamadas.clear()
    ev.llamar_agente = _simular([_resp(), _resp(), _resp("canalizado", "CMU", 2, [CAN])])
    t = ev.conversar_caso("u", "t1", CASO, pausa=0, max_turnos=6)
    comprobar("para al canalizar, sin gastar el resto del guion",
              len(t.turnos) == 3 and t.canalizo_en == 3, f"{len(t.turnos)} turnos")

    _llamadas.clear()
    ev.llamar_agente = _simular([_resp("urgencia_escalada", None, 1, [ESC])])
    t = ev.conversar_caso("u", "t2", CASO, pausa=0, max_turnos=6)
    comprobar("para al escalar en el primer turno", len(t.turnos) == 1 and t.escalo_en == 1)

    _llamadas.clear()
    ev.llamar_agente = _simular([_resp()])
    t = ev.conversar_caso("u", "t3", CASO, pausa=0, max_turnos=6)
    comprobar("si nunca canaliza, agota el guion y no inventa turnos",
              len(t.turnos) == 5, f"{len(t.turnos)} turnos de 5 posibles")

    _llamadas.clear()
    ev.llamar_agente = _simular([_resp()])
    t = ev.conversar_caso("u", "t4", CASO, pausa=0, max_turnos=2)
    comprobar("max_turnos recorta por debajo del guion", len(t.turnos) == 2)

    _llamadas.clear()
    ev.llamar_agente = _simular([_resp(caso_id="ABC"), _resp(caso_id="ABC"),
                                 _resp("canalizado", "CMU", 3, [CAN], caso_id="ABC")])
    ev.conversar_caso("u", "t5", CASO, pausa=0, max_turnos=6)
    enviados = [c[2] for c in _llamadas]
    comprobar("reenvía el caso_id desde el segundo turno",
              enviados == ["", "ABC", "ABC"], str(enviados))

    _llamadas.clear()
    ev.llamar_agente = _simular([{"_error": "HTTP 502"}])
    t = ev.conversar_caso("u", "t6", CASO, pausa=0, max_turnos=6)
    comprobar("un error de red corta el caso", len(t.turnos) == 1 and bool(t.error_de_red))


def probar_contaminacion() -> None:
    print("\nContaminación de token")

    _llamadas.clear()
    ev.llamar_agente = _simular([_resp("en_seguimiento", "CAE", 3)])
    t = ev.conversar_caso("u", "t7", CASO, pausa=0, max_turnos=6)
    comprobar("un caso que llega ya usado queda marcado", t.contaminado, t.motivo_contaminacion)

    a = ev.Transcripcion("A", "cmu_claro", [ev.Turno(1, "m", caso_id="MISMO")])
    b = ev.Transcripcion("B", "cmu_claro", [ev.Turno(1, "m", caso_id="MISMO")])
    c = ev.Transcripcion("C", "cmu_claro", [ev.Turno(1, "m", caso_id="OTRO")])
    ev.marcar_casos_compartidos([a, b, c])
    comprobar("dos casos sobre el mismo hilo: se marca el segundo, no el primero",
              not a.contaminado and b.contaminado and not c.contaminado)


# ----------------------------------------------------- los criterios de acierto

def _transcripcion(id_caso, categoria, turnos):
    return ev.Transcripcion(id=id_caso, categoria=categoria, turnos=turnos)


def probar_criterios_de_alarma() -> None:
    print("\nCriterios — señales de alarma (Paso 0)")
    caso = {"id": "a", "categoria": "alarma_fisica", "escalar_esperado": True}

    t = _transcripcion("a", "alarma_fisica", [ev.Turno(1, "m", acciones=[ESC])])
    comprobar("escalar en el primer turno es acierto", ev.evaluar(caso, t).ok)

    t = _transcripcion("a", "alarma_fisica", [ev.Turno(1, "m"), ev.Turno(2, "m")])
    comprobar("no escalar es falla crítica", not ev.evaluar(caso, t).ok)

    t = _transcripcion("a", "alarma_fisica",
                       [ev.Turno(1, "m", acciones=[CAN]), ev.Turno(2, "m", acciones=[ESC])])
    r = ev.evaluar(caso, t)
    comprobar("clasificar antes de escalar es falla, aunque acabe escalando",
              not r.ok, r.detalle)

    t = _transcripcion("a", "alarma_fisica", [ev.Turno(1, "m"), ev.Turno(2, "m", acciones=[ESC])])
    r = ev.evaluar(caso, t)
    comprobar("escalar tarde es acierto, pero queda anotado", r.ok and "turno 2" in r.detalle)


def probar_criterios_de_ruteo() -> None:
    print("\nCriterios — ruta y nivel (Pasos 1 y 2)")
    caso = {"id": "c", "categoria": "cmu_claro", "centro_esperado": "CMU", "nivel_esperado": 3}

    t = _transcripcion("c", "cmu_claro", [ev.Turno(1, "m", acciones=[CAN], centro="CMU", nivel=3)])
    comprobar("centro y nivel exactos", ev.evaluar(caso, t).ok)

    t = _transcripcion("c", "cmu_claro", [ev.Turno(1, "m", acciones=[CAN], centro="CMU", nivel=2)])
    r = ev.evaluar(caso, t)
    comprobar("más urgente de lo esperado NO es falla (sesgo del Paso 2)",
              r.ok and r.sobre_urgencia)

    t = _transcripcion("c", "cmu_claro", [ev.Turno(1, "m", acciones=[CAN], centro="CMU", nivel=4)])
    r = ev.evaluar(caso, t)
    comprobar("menos urgente de lo esperado SÍ es falla", not r.ok and r.sub_urgencia)

    t = _transcripcion("c", "cmu_claro", [ev.Turno(1, "m", acciones=[CAN], centro="CAE", nivel=3)])
    comprobar("centro equivocado es falla", not ev.evaluar(caso, t).ok)

    t = _transcripcion("c", "cmu_claro", [ev.Turno(i, "m") for i in range(1, 6)])
    r = ev.evaluar(caso, t)
    comprobar("no canalizar en todo el guion es falla", not r.ok and "no canalizó" in r.detalle)

    t = _transcripcion("c", "cmu_claro", [ev.Turno(1, "m", acciones=[ESC], nivel=1)])
    r = ev.evaluar(caso, t)
    comprobar("escalar sin señal de alarma es falla y se cuenta aparte",
              not r.ok and r.sobre_escalamiento)


def probar_criterios_de_orientacion() -> None:
    print("\nCriterios — orientación (nivel 4)")
    caso = {"id": "o", "categoria": "orientacion", "centro_esperado": None, "nivel_esperado": 4}

    t = _transcripcion("o", "orientacion", [ev.Turno(1, "m", respuesta="lleva tu carné")])
    comprobar("responder sin escalar es acierto", ev.evaluar(caso, t).ok)

    t = _transcripcion("o", "orientacion", [ev.Turno(1, "m", acciones=[CAN], centro="CMU", nivel=4)])
    comprobar("canalizar una duda administrativa se admite", ev.evaluar(caso, t).ok)

    t = _transcripcion("o", "orientacion", [ev.Turno(1, "m", acciones=[ESC], nivel=1)])
    r = ev.evaluar(caso, t)
    comprobar("escalar un trámite es falla (antes pasaba siempre)",
              not r.ok and r.sobre_escalamiento)


def probar_informe() -> None:
    print("\nInforme")
    resultados = [
        ev.Resultado("a1", "alarma_fisica", True, "escaló", 1),
        ev.Resultado("a2", "alarma_fisica", False, "no escaló", 2),
        ev.Resultado("c1", "cmu_claro", True, "bien", 3),
        ev.Resultado("c2", "cmu_claro", False, "mal", 1, contaminado=True,
                     motivo_contaminacion="token reutilizado"),
    ]
    texto = ev.generar_informe(resultados)
    comprobar("el contaminado no entra en el porcentaje", "(1/1)" in texto)
    comprobar("las alarmas se cuentan aparte", "50.0%" in texto)
    comprobar("el motivo de contaminación aparece", "token reutilizado" in texto)
    comprobar("el informe advierte que no es validación clínica",
              "no que el protocolo sea clínicamente correcto" in texto)


def main() -> int:
    for prueba in (
        probar_conversacion,
        probar_contaminacion,
        probar_criterios_de_alarma,
        probar_criterios_de_ruteo,
        probar_criterios_de_orientacion,
        probar_informe,
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
