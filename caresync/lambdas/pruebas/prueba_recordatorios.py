#!/usr/bin/env python3
"""
Pruebas de la función de recordatorios: cada cuánto y a qué hora.

    python pruebas/prueba_recordatorios.py

`_intervalo` convierte en una serie de correos lo que el profesional escribió a
mano. Esta prueba existe porque la versión anterior no entendía «cada 24 horas»,
que es justo el valor que la vista del profesional propone por omisión, ni «cada 2
días», que su ayuda pone de ejemplo: un plan guardado sin tocar ese campo no
programaba ni un recordatorio, y la corrida lo contaba como una indicación «de una
sola vez», así que nadie lo veía.

La primera fila de la tabla, entonces, no es un ejemplo cualquiera: es el valor
por omisión de `Profesional.tsx`. Si alguien lo cambia allí, que lo añada aquí.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from entorno import cargar, comprobar, fallos, preparar  # noqa: E402

preparar()

from caresync_comun import reloj  # noqa: E402

recordatorios = cargar("recordatorios", "handler")

H = timedelta(hours=1)
D = timedelta(days=1)


def probar_intervalo() -> None:
    print("\nCada cuánto")

    for texto, esperado in (
        ("cada 24 horas", D),  # el valor por omisión de la vista del profesional
        ("cada 12 horas", 12 * H),
        ("Cada 8 horas", 8 * H),
        ("cada 48 h", 2 * D),
        ("cada 2 días", 2 * D),
        ("cada 3 dias", 3 * D),
        ("cada 2 semanas", 14 * D),
        ("semanal", 7 * D),
        ("una vez a la semana, semanal", 7 * D),
        ("diaria", D),
        ("diario, en la mañana", D),
        ("cada día", D),
        ("cada dia", D),
        ("dos veces al día", 12 * H),
        ("3 veces al dia", 8 * H),
        # Menos de cuatro horas se recorta: trece correos al día enseñan a ignorarlos.
        ("cada hora", 4 * H),
        ("cada 1 hora", 4 * H),
        ("cada 2 horas", 4 * H),
        # Lo que no es una frecuencia no se convierte en una serie de correos.
        ("acude al control del viernes", None),
        ("cada 0 días", None),
        ("", None),
        (None, None),
    ):
        real = recordatorios._intervalo(texto)
        comprobar(f"«{texto}» -> {esperado}", real == esperado, str(real))


def probar_hora_decente() -> None:
    print("\nA qué hora")

    def bogota(hora: int, minuto: int = 0, dia: int = 1) -> datetime:
        return datetime(2026, 10, dia, hora, minuto, tzinfo=reloj.BOGOTA)

    def hora_local(momento: datetime) -> tuple[int, int, int]:
        local = reloj.en_bogota(momento)
        return (local.day, local.hour, local.minute)

    comprobar("de madrugada se corre a las 7:00 del mismo día",
              hora_local(recordatorios._hora_decente(bogota(3, 20))) == (1, 7, 0))
    comprobar("a media mañana se deja como está",
              hora_local(recordatorios._hora_decente(bogota(10, 15))) == (1, 10, 15))
    comprobar("a las 20:00 ya es tarde: pasa a las 7:00 del día siguiente",
              hora_local(recordatorios._hora_decente(bogota(20, 0))) == (2, 7, 0))
    comprobar("las 19:59 todavía valen",
              hora_local(recordatorios._hora_decente(bogota(19, 59))) == (1, 19, 59))


def main() -> int:
    for prueba in (probar_intervalo, probar_hora_decente):
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
