#!/usr/bin/env python3
"""
Pruebas de las herramientas que no pueden fallar en silencio.

    python pruebas/prueba_herramientas.py

- **`escalar_urgencia` nunca lanza** y siempre devuelve el texto de la ruta de
  emergencia, aunque fallen las cuatro escrituras (invariante 6). Y emite el evento
  con el nombre literal `ESCALAMIENTO`, del que cuelga la alarma de CloudWatch
  (invariante 5): renombrarlo la deja muda sin que nada falle.
- **Un nivel 1 no se agenda**, ni al canalizar ni al intentar la cita.
- **El retroceso en el seguimiento se detecta** con los umbrales del E2E-2: una
  caída de 3 puntos o una escala de 3 o menos dejan el evento que ve el profesional.
- **El horario de un profesional se lee como lo diría una persona.**
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from entorno import AccesoFalso, ActorFalso, cargar, comprobar, fallos, lanza, preparar  # noqa: E402

preparar()

from caresync_comun.errores import Conflicto, ErrorDeConfiguracion  # noqa: E402

triaje = cargar("herramientas", "triaje")
agenda = cargar("herramientas", "agenda")
seguimiento = cargar("herramientas", "seguimiento")


class _Capturador(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.eventos: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.eventos.append(record.getMessage())


def _capturar(modulo: Any) -> _Capturador:
    """Sustituye los manejadores del log del módulo por uno que anota los eventos."""
    capturador = _Capturador()
    modulo.log.handlers = [capturador]
    modulo.log.setLevel(logging.INFO)
    return capturador


def _sin_configuracion() -> Any:
    raise ErrorDeConfiguracion("Parameter Store no está en una prueba")


def probar_escalar_urgencia() -> None:
    print("\nEscalar una urgencia")

    triaje.config = _sin_configuracion
    capturador = _capturar(triaje)

    todo_falla = AccesoFalso(ActorFalso("paciente"), falla_al_escribir=True)
    caso = {"_id": "k-1", "centro": "CAE", "paciente_nombre": "Ana"}
    try:
        salida = triaje.escalar_urgencia(todo_falla, caso, {"motivo": "ideación suicida"})
        lanzo = False
    except Exception:  # noqa: BLE001 - es justo lo que se comprueba
        salida, lanzo = {}, True

    comprobar("no lanza aunque fallen el caso, la bitácora y el correo (invariante 6)", not lanzo)
    comprobar("devuelve siempre el texto de la ruta de emergencia",
              salida.get("decir_a_la_persona") == triaje.RUTA_EMERGENCIA and bool(triaje.RUTA_EMERGENCIA))
    comprobar("y le prohíbe agendar", salida.get("agendar") is False)
    comprobar("emite el evento con el literal ESCALAMIENTO (invariante 5)",
              "ESCALAMIENTO" in capturador.eventos, str(capturador.eventos))
    comprobar("y deja constancia de que el escalamiento fue parcial",
              "escalamiento_parcial" in capturador.eventos)

    bien = AccesoFalso(ActorFalso("paciente"))
    triaje.escalar_urgencia(bien, caso, {"motivo": "dolor de pecho"})
    cambios = [d for que, d in bien.escrito if que == "caso"]
    eventos = [d for que, d in bien.escrito if que == "evento"]
    comprobar("marca el caso como urgencia de nivel 1",
              cambios and cambios[0].get("estado") == "urgencia_escalada" and cambios[0].get("nivel_urgencia") == 1)
    comprobar("sin escribir columnas que `casos` no tiene",
              cambios and not ({"escalado_en", "canalizado_en"} & set(cambios[0])))
    comprobar("deja el evento crítico en la bitácora",
              eventos and eventos[0].get("tipo") == "urgencia_escalada" and eventos[0].get("severidad") == "critica")


def probar_canalizar() -> None:
    print("\nCanalizar")

    triaje.config = _sin_configuracion
    _capturar(triaje)

    ya = AccesoFalso(ActorFalso("paciente"))
    comprobar("un caso ya canalizado no se vuelve a canalizar",
              lanza(Conflicto, triaje.canalizar_caso, ya, {"_id": "k", "estado": "canalizado", "centro": "CMU"},
                    {"centro": "CAE", "nivel_urgencia": 3, "resumen": "x"}) is not None)
    comprobar("un caso cerrado tampoco",
              lanza(Conflicto, triaje.canalizar_caso, ya, {"_id": "k", "estado": "cerrado"},
                    {"centro": "CAE", "nivel_urgencia": 3, "resumen": "x"}) is not None)

    normal = AccesoFalso(ActorFalso("paciente"))
    salida = triaje.canalizar_caso(normal, {"_id": "k", "estado": "abierto"},
                                   {"centro": "CMU", "nivel_urgencia": 3, "resumen": "Fiebre"})
    comprobar("nivel 3: se agenda, en 7 días", salida.get("agendar") is True and salida.get("plazo") == "7 días")
    cambios = [d for que, d in normal.escrito if que == "caso"]
    comprobar("escribe sólo columnas que existen en `casos`",
              cambios and set(cambios[0]) <= {"caso_id", "estado", "centro", "nivel_urgencia", "resumen_triaje"},
              str(cambios[0] if cambios else {}))

    emergencia = AccesoFalso(ActorFalso("paciente"))
    salida = triaje.canalizar_caso(emergencia, {"_id": "k", "estado": "abierto"},
                                   {"centro": "CAE", "nivel_urgencia": 1, "resumen": "Ideación"})
    comprobar("nivel 1: no se agenda y se da la ruta de emergencia",
              salida.get("agendar") is False and salida.get("decir_a_la_persona") == triaje.RUTA_EMERGENCIA)
    comprobar("nivel 1: además queda escalado",
              any(d.get("estado") == "urgencia_escalada" for que, d in emergencia.escrito if que == "caso"))

    comprobar("una cita para un caso de nivel 1 se rechaza antes de leer la agenda",
              lanza(Conflicto, agenda.agendar_cita, AccesoFalso(ActorFalso("paciente")),
                    {"_id": "k", "centro": "CMU", "nivel_urgencia": 1},
                    {"inicio": "2026-10-01T09:00:00-05:00"}) is not None)


class _AccesoConEvolucion(AccesoFalso):
    def __init__(self, previas: list[int]) -> None:
        super().__init__(ActorFalso("paciente"))
        self._previas = [{"escala": e, "reportado_en": f"2026-09-0{i + 1}T10:00:00Z"} for i, e in enumerate(previas)]

    def evolucion_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
        return list(self._previas)

    def registrar_evolucion(self, **datos: Any) -> None:
        self._escribir("evolucion", datos)


def probar_retroceso() -> None:
    print("\nRetroceso en el seguimiento (E2E-2)")

    _capturar(seguimiento)

    def reportar(previas: list[int], escala: int) -> tuple[dict, list]:
        acceso = _AccesoConEvolucion(previas)
        salida = seguimiento.registrar_evolucion(acceso, {"_id": "k", "estado": "en_seguimiento"},
                                                 {"escala": escala, "nota": "así voy"})
        eventos = [d for que, d in acceso.escrito if que == "evento"]
        return salida, eventos

    salida, eventos = reportar([7], 4)
    comprobar("caer 3 puntos es empeorar y deja el evento",
              salida.get("empeoro") is True and eventos and eventos[0].get("tipo") == "evolucion_desfavorable")

    salida, eventos = reportar([], 3)
    comprobar("una escala de 3 alerta aunque sea el primer reporte",
              salida.get("empeoro") is False and eventos and eventos[0].get("severidad") == "alta")

    salida, eventos = reportar([7], 5)
    comprobar("caer 2 puntos es la variación de un día, no una alerta", not eventos and salida.get("empeoro") is False)

    salida, eventos = reportar([4], 8)
    comprobar("mejorar no alerta", not eventos)
    comprobar("y al agente no se le pide que interprete",
              "no lo interpretes" in str(salida.get("instruccion")))

    primera = _AccesoConEvolucion([])
    seguimiento.registrar_evolucion(primera, {"_id": "k", "estado": "agendado"}, {"escala": 6})
    comprobar("el primer reporte pasa el caso a seguimiento",
              any(d.get("estado") == "en_seguimiento" for que, d in primera.escrito if que == "caso"))

    cerrado = _AccesoConEvolucion([])
    seguimiento.registrar_evolucion(cerrado, {"_id": "k", "estado": "cerrado"}, {"escala": 6})
    comprobar("pero no reabre un caso cerrado",
              not any(que == "caso" for que, _ in cerrado.escrito))


def probar_horarios_legibles() -> None:
    print("\nHorarios dichos como una persona")

    legibles = agenda._dias_legibles
    for dias, esperado in (
        ([0, 1, 2, 3, 4], "lunes a viernes"),
        ([0, 2, 4], "lunes, miércoles y viernes"),
        ([0, 1], "lunes y martes"),
        ([5], "sábado"),
        ([], "sin días registrados"),
    ):
        comprobar(f"{dias} -> «{esperado}»", legibles(dias) == esperado, legibles(dias))

    for valor, esperado in ((True, True), ("true", True), ("t", True), (1, True), (None, True),
                            (False, False), ("false", False), (0, False)):
        comprobar(f"activo={valor!r} se lee como {esperado}", agenda._activo({"activo": valor}) is esperado)


def main() -> int:
    for prueba in (
        probar_escalar_urgencia,
        probar_canalizar,
        probar_retroceso,
        probar_horarios_legibles,
    ):
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
