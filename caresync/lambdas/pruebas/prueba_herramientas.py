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
- **La cita respeta el plazo del nivel** y no se ofrece un espacio que empieza ya.
- **Cancelar y cambiar una cita piden confirmación**, y cambiarla toma el espacio
  nuevo antes de soltar el viejo.
- **Una cita que ya pasó no deja a la persona sin salida.**
- **La urgencia sólo sube**, y un problema nuevo abre un caso aparte.
"""

from __future__ import annotations

import logging
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from entorno import AccesoFalso, ActorFalso, cargar, comprobar, fallos, lanza, preparar  # noqa: E402

preparar()

from caresync_comun import roble_acceso  # noqa: E402
from caresync_comun.errores import (  # noqa: E402
    Conflicto,
    ErrorDeConfiguracion,
    NoAutorizado,
    SolicitudInvalida,
)
from caresync_comun.roble_acceso import cita_por_delante  # noqa: E402

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

    orientacion = AccesoFalso(ActorFalso("paciente"))
    salida = triaje.canalizar_caso(orientacion, {"_id": "k", "estado": "abierto"},
                                   {"centro": "CMU", "nivel_urgencia": 4, "resumen": "Anticonceptivos"})
    comprobar("nivel 4: queda canalizado, pero sin cita (E2E-7)",
              salida.get("agendar") is False and salida.get("plazo") == "sin cita"
              and any(d.get("estado") == "canalizado" for que, d in orientacion.escrito if que == "caso"))
    # Decía «no le prometas cuándo ni cómo le van a responder», que daba a entender
    # que alguien iba a responder: el centro no tiene cómo escribirle a la persona.
    comprobar("nivel 4: le dice al agente qué decir, sin prometer respuesta",
              "CMU" in salida.get("siguiente", "")
              and "No le digas que le van a responder" in salida.get("siguiente", ""))
    comprobar("nivel 4: no escala",
              not any(d.get("estado") == "urgencia_escalada" for que, d in orientacion.escrito if que == "caso"))
    comprobar("nivel 4 sin resolver: el caso sigue abierto para el centro",
              salida.get("cerrado") is False
              and not any(d.get("tipo") == "orientacion_entregada" for que, d in orientacion.escrito if que == "evento"))

    resuelta = AccesoFalso(ActorFalso("paciente"))
    salida = triaje.canalizar_caso(resuelta, {"_id": "k", "estado": "abierto"},
                                   {"centro": "CMU", "nivel_urgencia": 4, "resumen": "Certificado",
                                    "orientacion_resuelta": True})
    cambios = [d for que, d in resuelta.escrito if que == "caso"]
    comprobar("nivel 4 resuelto con la información de los centros: el caso se cierra (T2)",
              salida.get("cerrado") is True and cambios and cambios[0].get("estado") == "cerrado"
              and cambios[0].get("centro") == "CMU" and cambios[0].get("nivel_urgencia") == 4)
    comprobar("y deja la orientación entregada en la bitácora",
              any(d.get("tipo") == "orientacion_entregada" for que, d in resuelta.escrito if que == "evento"))

    tres = AccesoFalso(ActorFalso("paciente"))
    triaje.canalizar_caso(tres, {"_id": "k", "estado": "abierto"},
                          {"centro": "CMU", "nivel_urgencia": 3, "resumen": "x", "orientacion_resuelta": True})
    comprobar("orientacion_resuelta no cierra nada que no sea nivel 4",
              any(d.get("estado") == "canalizado" for que, d in tres.escrito if que == "caso"))

    comprobar("una cita para un caso de nivel 1 se rechaza antes de leer la agenda",
              lanza(Conflicto, agenda.agendar_cita, AccesoFalso(ActorFalso("paciente")),
                    {"_id": "k", "centro": "CMU", "nivel_urgencia": 1},
                    {"inicio": "2026-10-01T09:00:00-05:00"}) is not None)


class _AccesoConAgenda(AccesoFalso):
    """Un cupo libre a las 08:30 de Bogotá, y un `insert` que miente como el de ROBLE.

    ROBLE guarda las fechas sin zona y, al releerlas, las devuelve en UTC sin sufijo
    («2026-10-14T13:30»). Pero la fila que devuelve al **insertar** viene con la hora
    reinterpretada en la zona de su servidor, Colombia: «2026-10-14T18:30:00.000Z».
    Así lo mostró una cita real del 14/10 que el agente confirmó a las 13:30.
    """

    CUPO = {"_id": "cupo-1", "centro": "CMU", "profesional_id": "p-1", "inicio": "2026-10-14T13:30",
            "fin": "2026-10-14T14:00", "estado": "libre", "modalidad": "presencial"}

    def citas_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
        return []

    def cupos_libres(self, **_filtros: Any) -> list[dict[str, Any]]:
        return [dict(self.CUPO)]

    def reservar_cupo(self, *, cupo_id: str, caso_id: str) -> dict[str, Any]:
        return {**self.CUPO, "estado": "reservado", "caso_id": caso_id}

    def confirmar_cita(self, *, cupo_id: str, caso_id: str) -> dict[str, Any]:
        return self._escribir("cita", {"caso_id": caso_id, "centro": "CMU", "profesional_nombre": "Dra. Prueba",
                                       "inicio": "2026-10-14T18:30:00.000Z"})


def probar_agendar() -> None:
    print("\nAgendar una cita")
    agenda.correo.config = lambda: type("Sin", (), {"envia_correo": False, "correo_remitente": ""})()
    acceso = _AccesoConAgenda(ActorFalso("paciente"))
    salida = agenda.agendar_cita(acceso, {"_id": "k", "centro": "CMU", "nivel_urgencia": 2},
                                 {"inicio": "2026-10-14T08:30:00-05:00"})
    comprobar("la hora que se le confirma a la persona es la del cupo: 08:30 de Bogotá",
              "08:30" in str(salida.get("cuando")), str(salida.get("cuando")))
    evento_cita = [d for que, d in acceso.escrito if que == "evento" and d.get("tipo") == "cita_agendada"]
    comprobar("y la bitácora guarda la del cupo, no la que devolvió el insert",
              evento_cita and evento_cita[0]["detalle"]["inicio"] == "2026-10-14T13:30")


def probar_notificar_sin_correo() -> None:
    print("\nAvisar al profesional cuando el correo no sale")

    class _ConCita(AccesoFalso):
        def citas_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
            return [{"_id": "c-1", "inicio": "2026-10-14T13:30", "centro": "CMU", "profesional_id": "p-1",
                     "profesional_nombre": "Dra. Prueba"}]

        def eventos_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
            return []

        def profesional(self, profesional_id: str) -> dict[str, Any]:
            return {"email": "dra.prueba@ejemplo.edu.co"}

    agenda.correo.config = lambda: type("Sin", (), {"envia_correo": False, "correo_remitente": ""})()
    salida = agenda.notificar_profesional(_ConCita(ActorFalso("paciente")),
                                          {"_id": "k", "paciente_nombre": "X", "nivel_urgencia": 2}, {})
    instruccion = str(salida.get("instruccion", ""))
    comprobar("sin correo, no le pide al agente prometer contacto (invariante 7)",
              salida.get("enviado") is False and "contactará" not in instruccion
              and "no prometas" in instruccion, instruccion)


def probar_adherencia() -> None:
    print("\nAdherencia con un identificador que no es del plan")

    class _ConPlan(AccesoFalso):
        def indicaciones_activas(self, caso_id: str) -> list[dict[str, Any]]:
            return [{"_id": "ind-1", "texto": "Tomar acetaminofén"}, {"_id": "ind-2", "texto": "Hacer gárgaras"}]

        def registrar_adherencia(self, **datos: Any) -> None:
            self._escribir("adherencia", datos)

    acceso = _ConPlan(ActorFalso("paciente"))
    salida = seguimiento.registrar_adherencia(acceso, {"_id": "k"}, {"indicacion_id": "de-otro-turno", "cumplida": False})
    comprobar("no escribe nada sobre un identificador ajeno", acceso.escrito == [])
    comprobar("y le devuelve al agente las indicaciones de verdad para corregir en la misma vuelta",
              salida.get("error") and [i["indicacion_id"] for i in salida.get("indicaciones_activas", [])] == ["ind-1", "ind-2"],
              str(salida))

    salida = seguimiento.registrar_adherencia(acceso, {"_id": "k"}, {"indicacion_id": "ind-2", "cumplida": False, "nota": "duele"})
    comprobar("con el identificador correcto registra, y el incumplimiento deja evento",
              salida.get("ok") is True and [que for que, _ in acceso.escrito] == ["adherencia", "evento"])


def probar_plan_con_reportes_de_la_app() -> None:
    print("\nLo que el agente ve de los reportes de la app móvil")

    class _ConReportes(AccesoFalso):
        def plan_del_caso(self, caso_id: str) -> dict[str, Any]:
            return {"resumen": "Plan", "creado_en": "2026-10-28T15:00"}

        def indicaciones_activas(self, caso_id: str) -> list[dict[str, Any]]:
            return [
                {"_id": "ind-1", "texto": "Hacer gárgaras", "tipo": "autocuidado", "duracion_dias": 7},
                {"_id": "ind-2", "texto": "Si empeora, ve a urgencias"},
            ]

        def adherencia_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
            # Como las devuelve ROBLE: sin zona ni segundos.
            return [
                {"indicacion_id": "ind-1", "cumplida": True, "reportado_en": f"2026-10-2{dia}T13:00",
                 "programado_para": f"2026-10-2{dia}T12:00", "origen": "app"}
                for dia in range(5, 9)
            ] + [
                {"indicacion_id": "ind-1", "cumplida": False, "nota": "Se me olvidó",
                 "reportado_en": "2026-10-30T13:28", "programado_para": "2026-10-30T12:00", "origen": "app"},
            ]

        def evolucion_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
            return []

    salida = seguimiento.consultar_plan(_ConReportes(ActorFalso("paciente")), {"_id": "k"}, {})
    con_reportes, sin_reportes = salida["indicaciones"]
    recientes = con_reportes["ultimos_reportes"]

    comprobar("el total sigue contando todos", con_reportes["reportes"] == 5)
    comprobar("pero sólo viajan los últimos", len(recientes) == seguimiento.REPORTES_RECIENTES, str(recientes))
    comprobar("el último trae la nota, para no volver a preguntarla", recientes[-1]["nota"] == "Se me olvidó")
    comprobar("y su toma en hora de Bogotá: las 12:00 de ROBLE son las 7:00, no «anoche»",
              "30/10 a las 07:00" in recientes[-1]["toma_de_las"], recientes[-1]["toma_de_las"])
    comprobar("un reporte sin nota no inventa una cadena vacía", recientes[0]["nota"] is None)
    comprobar("sin toma queda nula, como lo que registra el agente",
              seguimiento._reporte({"reportado_en": "2026-10-30T13:28", "cumplida": True})["toma_de_las"] is None)
    comprobar("una indicación sin reportes no trae ninguno", sin_reportes["ultimos_reportes"] == [])
    comprobar("el tipo nulo se le presenta como otro", sin_reportes["tipo"] == "otro")


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

    # El mismo número hace un momento es el mismo reporte (prueba de punta a punta del
    # 14/10: el agente registró dos veces el 3 y dejó dos alertas por una caída).
    hace_un_rato = _AccesoConEvolucion([6, 3])
    hace_un_rato._previas[-1]["reportado_en"] = seguimiento.reloj.iso(seguimiento.reloj.mas(minutos=-10))
    salida = seguimiento.registrar_evolucion(hace_un_rato, {"_id": "k", "estado": "en_seguimiento"}, {"escala": 3})
    comprobar("repetir la escala de hace 10 minutos no escribe ni alerta otra vez",
              salida.get("repetido") is True and hace_un_rato.escrito == [], str(hace_un_rato.escrito))
    comprobar("y le recuerda al agente que la adherencia va aparte",
              "registrar_adherencia" in str(salida.get("instruccion")))

    otro_numero = _AccesoConEvolucion([6])
    otro_numero._previas[-1]["reportado_en"] = seguimiento.reloj.iso(seguimiento.reloj.mas(minutos=-10))
    seguimiento.registrar_evolucion(otro_numero, {"_id": "k", "estado": "en_seguimiento"}, {"escala": 3})
    comprobar("un número distinto hace un momento sí es un reporte nuevo",
              any(que == "evolucion" for que, _ in otro_numero.escrito))

    al_dia_siguiente = _AccesoConEvolucion([3])
    seguimiento.registrar_evolucion(al_dia_siguiente, {"_id": "k", "estado": "en_seguimiento"}, {"escala": 3})
    comprobar("el mismo número otro día también es un dato",
              any(que == "evolucion" for que, _ in al_dia_siguiente.escrito))

    primera = _AccesoConEvolucion([])
    seguimiento.registrar_evolucion(primera, {"_id": "k", "estado": "agendado"}, {"escala": 6})
    comprobar("el primer reporte pasa el caso a seguimiento",
              any(d.get("estado") == "en_seguimiento" for que, d in primera.escrito if que == "caso"))

    cerrado = _AccesoConEvolucion([])
    seguimiento.registrar_evolucion(cerrado, {"_id": "k", "estado": "cerrado"}, {"escala": 6})
    comprobar("pero no reabre un caso cerrado",
              not any(que == "caso" for que, _ in cerrado.escrito))


def _sin_correo() -> Any:
    return type("Sin", (), {"envia_correo": False, "correo_remitente": ""})()


def _iso(momento: Any) -> str:
    """Una fecha como las guarda ROBLE: en UTC y sin sufijo."""
    return momento.strftime("%Y-%m-%dT%H:%M:00")


def _iso_utc(**delta: Any) -> str:
    return _iso(agenda.reloj.ahora() + timedelta(**delta))


def _franja(**delta: Any) -> dict[str, str]:
    """Inicio y fin de un espacio de 30 minutos que empieza a `delta` de ahora."""
    inicio = agenda.reloj.ahora() + timedelta(**delta)
    return {"inicio": _iso(inicio), "fin": _iso(inicio + timedelta(minutes=30))}


def _cupo(cupo_id: str, **delta: Any) -> dict[str, Any]:
    return {"_id": cupo_id, "centro": "CMU", "profesional_id": "p-1", "estado": "libre",
            **_franja(**delta)}


def _cita(cita_id: str, cupo_id: str, **delta: Any) -> dict[str, Any]:
    return {"_id": cita_id, "cupo_id": cupo_id, "centro": "CMU", "profesional_id": "p-1",
            "profesional_nombre": "Dra. Prueba", "estado": "confirmada", **_franja(**delta)}


def _caso(**datos: Any) -> dict[str, Any]:
    return {"_id": "k", "centro": "CMU", "nivel_urgencia": 3, "estado": "agendado",
            "paciente_nombre": "Ana", "paciente_email": "", **datos}


class _AgendaViva(AccesoFalso):
    """Una agenda en memoria que filtra por fechas como la de verdad.

    `cupos_libres` aplica `desde` y `hasta` igual que `roble_acceso`, así que lo que
    se prueba es qué ventana pide cada herramienta, y no lo que devuelve un doble que
    ignora las fechas.
    """

    def __init__(self, *, cupos: list[dict[str, Any]] = (), citas: list[dict[str, Any]] = (),
                 reserva_falla: bool = False) -> None:
        super().__init__(ActorFalso("paciente"))
        self.cupos = [dict(c) for c in cupos]
        self.citas = [dict(c) for c in citas]
        self.eventos: list[dict[str, Any]] = []
        self.reserva_falla = reserva_falla

    def liberar_reservas_vencidas(self, *, minutos: int) -> int:
        return 0

    def cupos_libres(self, *, centro: str, desde: Any = None, hasta: Any = None,
                     maximo: int = 10) -> list[dict[str, Any]]:
        inicio = desde or agenda.reloj.ahora()
        libres = []
        for cupo in self.cupos:
            momento = agenda.reloj.desde_iso(cupo["inicio"])
            if momento and momento >= inicio and (hasta is None or momento <= hasta):
                libres.append((momento, cupo))
        libres.sort(key=lambda par: par[0])
        return [cupo for _, cupo in libres[:maximo]]

    def profesional(self, profesional_id: str) -> dict[str, Any]:
        return {"nombre": "Dra. Prueba", "email": "dra.prueba@ejemplo.edu.co"}

    def citas_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
        return list(self.citas)

    def eventos_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
        return list(self.eventos)

    def registrar_evento(self, **datos: Any) -> dict[str, Any]:
        self.eventos.append({**datos, "creado_en": agenda.reloj.iso()})
        return self._escribir("evento", datos)

    def reservar_cupo(self, *, cupo_id: str, caso_id: str) -> dict[str, Any]:
        if self.reserva_falla:
            raise Conflicto("Otra persona tomó ese espacio mientras lo reservábamos")
        return self._escribir("reserva", {"cupo_id": cupo_id})

    def confirmar_cita(self, *, cupo_id: str, caso_id: str) -> dict[str, Any]:
        cupo = next(c for c in self.cupos if c["_id"] == cupo_id)
        cita = _cita(f"cita-{cupo_id}", cupo_id)
        cita.update(inicio=cupo["inicio"], fin=cupo["fin"])
        self.citas.append(cita)
        return self._escribir("cita", cita)

    def cancelar_cita(self, cita: dict[str, Any]) -> bool:
        self._escribir("cancelada", {"cita_id": cita["_id"]})
        return True

    def liberar_cupo(self, cupo_id: str) -> None:
        self._escribir("cupo_liberado", {"cupo_id": cupo_id})


def probar_plazo_del_nivel() -> None:
    print("\nLa ventana de la cita la pone el nivel (A1 y A8)")
    agenda.correo.config = _sin_correo
    iso_local = agenda.reloj.iso_local

    en_dos_dias, en_cinco_dias = _cupo("c2", days=2), _cupo("c5", days=5)
    acceso = _AgendaViva(cupos=[en_cinco_dias, en_dos_dias])
    salida = agenda.consultar_disponibilidad(acceso, _caso(nivel_urgencia=2), {"dias_adelante": 30})
    comprobar("nivel 2: sólo ofrece lo que cabe en 72 horas, aunque el modelo pida 30 días",
              [o["inicio"] for o in salida["opciones"]] == [iso_local(en_dos_dias["inicio"])]
              and salida["dentro_del_plazo"] is True, str(salida.get("opciones")))

    acceso = _AgendaViva(cupos=[en_cinco_dias])
    salida = agenda.consultar_disponibilidad(acceso, _caso(nivel_urgencia=2), {})
    comprobar("sin espacio en el plazo, lo dice y ofrece lo primero que hay después",
              salida["dentro_del_plazo"] is False and len(salida["opciones"]) == 1
              and "72 horas" in salida["instruccion"], salida.get("instruccion"))
    comprobar("y le prohíbe al agente prometer un espacio o un contacto",
              "No prometas" in salida["instruccion"])
    comprobar("queda anotado en la bitácora del caso",
              [e["tipo"] for e in acceso.eventos] == ["sin_cupo_en_plazo"])
    agenda.consultar_disponibilidad(acceso, _caso(nivel_urgencia=2), {})
    comprobar("una segunda consulta el mismo día no lo anota otra vez",
              [e["tipo"] for e in acceso.eventos] == ["sin_cupo_en_plazo"])

    acceso = _AgendaViva(cupos=[en_cinco_dias])
    salida = agenda.consultar_disponibilidad(acceso, _caso(nivel_urgencia=3), {})
    comprobar("nivel 3: cinco días caben en su plazo de 7", salida["dentro_del_plazo"] is True)

    ya = _cupo("c0", minutes=10)
    acceso = _AgendaViva(cupos=[ya, en_dos_dias])
    salida = agenda.consultar_disponibilidad(acceso, _caso(nivel_urgencia=3), {})
    comprobar("un espacio que empieza en 10 minutos no se ofrece: no alcanza a llegar",
              iso_local(ya["inicio"]) not in [o["inicio"] for o in salida["opciones"]])

    acceso = _AgendaViva(cupos=[en_cinco_dias])
    salida = agenda.consultar_disponibilidad(acceso, _caso(nivel_urgencia=4), {"dias_adelante": 7})
    comprobar("nivel 4 que pidió cita: sin plazo, la ventana la pide el modelo",
              "dentro_del_plazo" not in salida and len(salida["opciones"]) == 1)


def probar_cancelar() -> None:
    print("\nCancelar una cita (A2)")
    agenda.correo.config = _sin_correo

    acceso = _AgendaViva(citas=[_cita("cita-1", "cupo-1", days=2)])
    salida = agenda.cancelar_cita(acceso, _caso(), {"confirmado": False})
    comprobar("sin confirmar no escribe nada y devuelve la cita para preguntar",
              salida.get("confirmar_primero") is True and acceso.escrito == []
              and bool(salida["cita"]["cuando"]))

    salida = agenda.cancelar_cita(acceso, _caso(), {"confirmado": True, "motivo": "un viaje"})
    comprobar("confirmado: cancela la cita", salida.get("ok") is True
              and any(que == "cancelada" for que, _ in acceso.escrito))
    comprobar("y el caso vuelve a canalizado, para poder pedir otra",
              any(d.get("estado") == "canalizado" for que, d in acceso.escrito if que == "caso"))
    comprobar("con el motivo en la bitácora",
              any(e["tipo"] == "cita_cancelada" and e["detalle"]["motivo"] == "un viaje"
                  for e in acceso.eventos))

    pasada = _AgendaViva(citas=[_cita("cita-1", "cupo-1", days=-3)])
    comprobar("una cita que ya pasó no se cancela",
              lanza(SolicitudInvalida, agenda.cancelar_cita, pasada, _caso(), {"confirmado": True})
              is not None)

    dos = _AgendaViva(citas=[_cita("a", "cupo-a", days=2), _cita("b", "cupo-b", days=4)])
    salida = agenda.cancelar_cita(dos, _caso(), {"confirmado": True})
    comprobar("con dos citas por delante pregunta cuál, sin cancelar ninguna",
              salida.get("motivo") == "varias_citas" and len(salida["citas"]) == 2
              and not any(que == "cancelada" for que, _ in dos.escrito))
    elegida = salida["citas"][1]["inicio"]
    agenda.cancelar_cita(dos, _caso(), {"confirmado": True, "cita_actual": elegida})
    comprobar("y con cita_actual cancela la elegida",
              [d["cita_id"] for que, d in dos.escrito if que == "cancelada"] == ["b"])


def probar_reprogramar() -> None:
    print("\nCambiar una cita (A3)")
    agenda.correo.config = _sin_correo

    nuevo = _cupo("cupo-nuevo", days=2)
    inicio = agenda.reloj.iso_local(nuevo["inicio"])

    acceso = _AgendaViva(cupos=[nuevo], citas=[_cita("cita-vieja", "cupo-viejo", days=5)])
    salida = agenda.reprogramar_cita(acceso, _caso(), {"inicio": inicio, "confirmado": False})
    comprobar("sin confirmar no toca nada y le da las dos fechas para preguntar",
              salida.get("confirmar_primero") is True and acceso.escrito == []
              and salida.get("de") and salida.get("a"))

    salida = agenda.reprogramar_cita(acceso, _caso(), {"inicio": inicio, "confirmado": True})
    orden = [que for que, _ in acceso.escrito]
    comprobar("toma el espacio nuevo antes de soltar el viejo",
              "cita" in orden and "cancelada" in orden and orden.index("cita") < orden.index("cancelada"),
              str(orden))
    comprobar("confirma la nueva y avisa que no hace falta notificar otra vez",
              salida.get("ok") is True and salida.get("anterior_cancelada") is True
              and "no llames a notificar_profesional" in salida.get("instruccion", ""))
    comprobar("y le manda el resumen al profesional de la cita nueva",
              any(e["tipo"] == "profesional_notificado" and e["detalle"]["cita_id"] == "cita-cupo-nuevo"
                  for e in acceso.eventos))

    perdida = _AgendaViva(cupos=[nuevo], citas=[_cita("cita-vieja", "cupo-viejo", days=5)],
                          reserva_falla=True)
    salida = agenda.reprogramar_cita(perdida, _caso(), {"inicio": inicio, "confirmado": True})
    comprobar("si otra persona toma el espacio nuevo, la cita de antes sigue intacta",
              salida.get("motivo") == "espacio_tomado"
              and not any(que == "cancelada" for que, _ in perdida.escrito))


def probar_cita_pasada() -> None:
    print("\nUna cita que ya pasó no deja a la persona sin salida (A4)")
    agenda.correo.config = _sin_correo

    libre = _cupo("cupo-nuevo", days=2)
    inicio = agenda.reloj.iso_local(libre["inicio"])

    acceso = _AgendaViva(cupos=[libre], citas=[_cita("pasada", "cupo-viejo", days=-2)])
    salida = agenda.agendar_cita(acceso, _caso(), {"inicio": inicio})
    comprobar("con una cita pasada que nadie marcó, se puede pedir otra", salida.get("ok") is True)

    acceso = _AgendaViva(cupos=[libre], citas=[_cita("futura", "cupo-viejo", days=1)])
    error = lanza(Conflicto, agenda.agendar_cita, acceso, _caso(), {"inicio": inicio})
    comprobar("con una cita por delante no, y le dice cómo cambiarla",
              error is not None and "reprogramar_cita" in error.publico)

    futura = _cita("x", "y", days=1)
    comprobar("una cita cancelada no está por delante", not cita_por_delante({**futura, "estado": "cancelada"}))
    comprobar("una marcada como no asistió tampoco", not cita_por_delante({**futura, "estado": "no_asistio"}))
    comprobar("una en curso sí: no se pide otra durante la consulta",
              cita_por_delante({**futura, "inicio": _iso_utc(minutes=-10), "fin": _iso_utc(minutes=20)}))
    comprobar("sin `fin`, se supone de una hora",
              cita_por_delante({"estado": "confirmada", "inicio": _iso_utc(minutes=-30)})
              and not cita_por_delante({"estado": "confirmada", "inicio": _iso_utc(minutes=-90)}))

    reprogramada = _AgendaViva(citas=[{**_cita("vieja", "c-v", days=5), "estado": "cancelada"},
                                      _cita("nueva", "c-n", days=2)])
    agenda.notificar_profesional(reprogramada, _caso(), {})
    comprobar("el aviso al profesional es de la próxima cita, no de la última por fecha",
              [e["detalle"]["cita_id"] for e in reprogramada.eventos if e["tipo"] == "profesional_notificado"]
              == ["nueva"])


def probar_subir_urgencia() -> None:
    print("\nEmpeora antes de la cita, sin señal de alarma (T6)")
    _capturar(triaje)

    acceso = _AgendaViva(citas=[_cita("cita-1", "cupo-1", days=5)])
    salida = triaje.subir_urgencia(acceso, _caso(nivel_urgencia=3),
                                   {"nivel_urgencia": 2, "motivo": "Ya no puede apoyar el pie"})
    comprobar("de 3 a 2: cambia el nivel y deja el evento",
              any(d.get("nivel_urgencia") == 2 for que, d in acceso.escrito if que == "caso")
              and any(e["tipo"] == "urgencia_subida" for e in acceso.eventos))
    comprobar("y avisa que su cita de dentro de cinco días queda fuera de las 72 horas",
              salida.get("cita_fuera_de_plazo") is True and "reprogramar_cita" in salida["instruccion"])

    acceso = _AgendaViva()
    salida = triaje.subir_urgencia(acceso, _caso(nivel_urgencia=2), {"nivel_urgencia": 3, "motivo": "x"})
    comprobar("nunca baja", salida.get("sin_cambio") is True and acceso.escrito == [])
    comprobar("al nivel 1 no se llega por aquí: eso es escalar_urgencia",
              lanza(SolicitudInvalida, triaje.subir_urgencia, acceso, _caso(), {"nivel_urgencia": 1, "motivo": "x"})
              is not None)
    comprobar("y no se sube en un caso que ya fue atendido",
              lanza(Conflicto, triaje.subir_urgencia, acceso, _caso(estado="en_seguimiento"),
                    {"nivel_urgencia": 2, "motivo": "x"}) is not None)


def probar_nuevo_motivo() -> None:
    print("\nUn problema nuevo con un caso abierto (T1)")

    acceso = AccesoFalso(ActorFalso("paciente"))
    salida = triaje.nuevo_motivo(acceso, {"_id": "viejo", "estado": "en_seguimiento"},
                                 {"motivo": "Me duele la rodilla"})
    abiertos = [d for que, d in acceso.escrito if que == "abrir_caso"]
    comprobar("abre un caso aparte con el problema nuevo como motivo",
              abiertos and abiertos[0]["motivo"] == "Me duele la rodilla" and salida.get("caso_nuevo"))
    comprobar("y lo anota en la bitácora del caso viejo",
              any(d.get("tipo") == "nuevo_motivo" and d.get("caso_id") == "viejo"
                  for que, d in acceso.escrito if que == "evento"))
    comprobar("en pleno triaje no abre otro: lo nuevo se cuenta ahí mismo",
              lanza(Conflicto, triaje.nuevo_motivo, AccesoFalso(ActorFalso("paciente")),
                    {"_id": "k", "estado": "abierto"}, {"motivo": "x"}) is not None)


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


def probar_sesion_vencida() -> None:
    print("\nEl token vence a mitad de la petición")

    class _Vencido:
        """El SDK cuando el token vence y no lo puede refrescar."""

        def read(self, *_args: Any) -> Any:
            raise roble_acceso.RobleAuthError("Token expirado y no se pudo refrescar")

        create = update = read

    acceso = roble_acceso.AccesoRoble(_Vencido(), ActorFalso("paciente"))
    comprobar("leer sale como 401 y no como 500",
              lanza(NoAutorizado, acceso._leer, "casos") is not None)
    comprobar("escribir también", lanza(NoAutorizado, acceso._crear, "mensajes", {}) is not None)
    comprobar("y actualizar", lanza(NoAutorizado, acceso._actualizar, "casos", "c-1", {}) is not None)


def main() -> int:
    for prueba in (
        probar_escalar_urgencia,
        probar_canalizar,
        probar_agendar,
        probar_notificar_sin_correo,
        probar_retroceso,
        probar_adherencia,
        probar_plan_con_reportes_de_la_app,
        probar_horarios_legibles,
        probar_plazo_del_nivel,
        probar_cancelar,
        probar_reprogramar,
        probar_cita_pasada,
        probar_subir_urgencia,
        probar_nuevo_motivo,
        probar_sesion_vencida,
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
