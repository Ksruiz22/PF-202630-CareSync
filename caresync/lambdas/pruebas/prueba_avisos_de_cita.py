#!/usr/bin/env python3
"""
Pruebas de los avisos de cita de la función de recordatorios (A6).

    python pruebas/prueba_avisos_de_cita.py

Hasta el 6/11, a quien no tenía la app móvil nada le recordaba la cita después del
correo de confirmación. Lo que se prueba aquí es lo que no puede fallar en silencio:
que cada cita en firme reciba sus dos avisos una sola vez aunque la función corra cada
15 minutos, que una cita cancelada o cambiada de hora no le llegue a la persona, y que
un aviso de cita no salga con el texto de los recordatorios del plan.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from entorno import cargar, comprobar, fallos, preparar  # noqa: E402

preparar()

from caresync_comun import reloj  # noqa: E402

recordatorios = cargar("recordatorios", "handler")

H = timedelta(hours=1)
CASO = "11111111-1111-4111-8111-111111111111"
CITA = "22222222-2222-4222-8222-222222222222"
OTRA = "33333333-3333-4333-8333-333333333333"


class _Acceso:
    """ROBLE en memoria con sólo lo que tocan los avisos de cita."""

    def __init__(self, citas: list[dict[str, Any]]) -> None:
        self.citas = citas
        self.filas: list[dict[str, Any]] = []
        self.marcas: dict[str, str] = {}

    def citas_confirmadas(self) -> list[dict[str, Any]]:
        return [c for c in self.citas if c.get("estado") == "confirmada"]

    def cita(self, cita_id: str) -> dict[str, Any] | None:
        return next((c for c in self.citas if c["_id"] == cita_id), None)

    def recordatorios_de_cita(self, cita_id: str) -> list[dict[str, Any]]:
        return [f for f in self.filas if f.get("cita_id") == cita_id]

    def programar_recordatorio(self, *, caso_id, indicacion_id, cuando, texto, cita_id=None):
        fila = {
            "_id": f"r{len(self.filas)}",
            "caso_id": caso_id,
            "indicacion_id": indicacion_id,
            "cita_id": cita_id,
            "programado_para": reloj.iso(cuando),
            "estado": "pendiente",
            "texto": texto,
        }
        self.filas.append(fila)
        return fila

    def recordatorios_pendientes(self, *, hasta):
        return [
            f for f in self.filas
            if f["estado"] == "pendiente" and reloj.desde_iso(f["programado_para"]) <= hasta
        ]

    def caso(self, caso_id: str) -> dict[str, Any]:
        return {"_id": caso_id, "estado": "agendado", "paciente_email": "p@x.co", "paciente_nombre": "Ana"}

    def marcar_recordatorio(self, recordatorio_id: str, *, estado: str, detalle: str = "") -> None:
        self.marcas[recordatorio_id] = estado
        for f in self.filas:
            if f["_id"] == recordatorio_id:
                f["estado"] = estado


def _cita(cita_id: str = CITA, *, en: timedelta, estado: str = "confirmada") -> dict[str, Any]:
    # ROBLE devuelve los momentos sin zona y en UTC.
    inicio = (reloj.ahora() + en).replace(microsecond=0, tzinfo=None).isoformat()
    return {
        "_id": cita_id,
        "caso_id": CASO,
        "estado": estado,
        "inicio": inicio,
        "centro": "CMU",
        "profesional_nombre": "Dra. Prueba",
    }


def _horas_antes(acceso: _Acceso, cita: dict[str, Any]) -> list[int]:
    inicio = reloj.desde_iso(cita["inicio"])
    return sorted(
        round((inicio - reloj.desde_iso(f["programado_para"])) / H)
        for f in acceso.recordatorios_de_cita(cita["_id"])
    )


def probar_materializar() -> None:
    print("\nQué avisos se escriben")

    cita = _cita(en=30 * H)
    acceso = _Acceso([cita])
    recordatorios._materializar_citas(acceso)
    comprobar("una cita dentro de 30 horas recibe el aviso de 24 y el de 2",
              _horas_antes(acceso, cita) == [2, 24], str(_horas_antes(acceso, cita)))
    comprobar("el aviso va con indicacion_id vacío, no nulo: la columna no lo admite",
              all(f["indicacion_id"] == "" for f in acceso.filas))

    recordatorios._materializar_citas(acceso)
    comprobar("la corrida de 15 minutos después no los duplica", len(acceso.filas) == 2, str(len(acceso.filas)))

    cerca = _cita(en=3 * H)
    acceso = _Acceso([cerca])
    recordatorios._materializar_citas(acceso)
    comprobar("una cita dentro de 3 horas sólo recibe el de 2: el de 24 ya pasó",
              _horas_antes(acceso, cerca) == [2], str(_horas_antes(acceso, cerca)))

    lejos = _cita(en=5 * 24 * H)
    acceso = _Acceso([lejos])
    recordatorios._materializar_citas(acceso)
    comprobar("una cita dentro de cinco días todavía no recibe nada", not acceso.filas)

    for nombre, cita in (
        ("cancelada", _cita(en=30 * H, estado="cancelada")),
        ("ya pasada", _cita(en=-1 * H)),
    ):
        acceso = _Acceso([cita])
        recordatorios._materializar_citas(acceso)
        comprobar(f"una cita {nombre} no recibe avisos", not acceso.filas)


def probar_enviar() -> None:
    print("\nQué avisos salen")

    enviados: list[dict[str, str]] = []
    original = recordatorios.correo.enviar
    recordatorios.correo.enviar = lambda **kw: enviados.append(kw) or True
    try:
        cita = _cita(en=2 * H + 10 * timedelta(minutes=1))
        acceso = _Acceso([cita])
        recordatorios._materializar_citas(acceso)
        recordatorios._enviar(acceso)
        comprobar("el aviso de 2 horas sale en la corrida que le toca", len(enviados) == 1, str(len(enviados)))
        if enviados:
            correo = enviados[0]
            comprobar("con el asunto de la cita, no el del plan", correo["asunto"] == "[CareSync] Recordatorio de tu cita",
                      correo["asunto"])
            comprobar("dice cuándo, dónde y con quién",
                      reloj.humano(cita["inicio"]) in correo["cuerpo"] and "CMU" in correo["cuerpo"]
                      and "Dra. Prueba" in correo["cuerpo"])
            comprobar("y cómo cancelarla o cambiarla", "cancelarla o cambiarla" in correo["cuerpo"])

        # Cambiar la hora cancela la cita anterior y crea otra: el aviso de la vieja no
        # puede llegar con la hora vieja.
        enviados.clear()
        vieja = _cita(en=2 * H + 10 * timedelta(minutes=1))
        acceso = _Acceso([vieja])
        recordatorios._materializar_citas(acceso)
        vieja["estado"] = "cancelada"
        acceso.citas.append(_cita(OTRA, en=3 * 24 * H))
        recordatorios._enviar(acceso)
        comprobar("el aviso de una cita cancelada no sale", not enviados, str(enviados))
        comprobar("y queda marcado como cancelado, para no revisarlo cada 15 minutos",
                  list(acceso.marcas.values()) == ["cancelado"], str(acceso.marcas))
    finally:
        recordatorios.correo.enviar = original


def main() -> int:
    for prueba in (probar_materializar, probar_enviar):
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
