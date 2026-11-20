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
from datetime import date, datetime, timedelta
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


def probar_horario() -> None:
    """La regla compartida con la app: ventana de 8:00 a 19:00, salvo horas del profesional."""
    print("\nA qué hora")
    frecuencia = recordatorios.frecuencia
    creada = datetime(2026, 11, 3, 10, 0, tzinfo=reloj.BOGOTA)

    def horas(frec: str, fijas: str = "", dia: int = 5) -> list[str]:
        momentos = frecuencia.momentos_del_dia(frec, fijas, creada, date(2026, 11, dia))
        return [reloj.en_bogota(m).strftime("%H:%M") for m in momentos]

    comprobar("cada 8 horas: desde las 8:00, y lo que cae después de las 19:00 no se avisa",
              horas("cada 8 horas") == ["08:00", "16:00"], str(horas("cada 8 horas")))
    comprobar("3 veces al día se reparten en la ventana, no cada 8 horas",
              horas("3 veces al día") == ["08:00", "13:30", "19:00"], str(horas("3 veces al día")))
    comprobar("diario, a las 8:00", horas("diario") == ["08:00"])
    comprobar("las horas del profesional mandan sobre la ventana",
              horas("cada 8 horas", "06:00,14:00,22:00") == ["06:00", "14:00", "22:00"])
    comprobar("y bastan solas, sin frecuencia", horas("", "7 y 19") == ["07:00", "19:00"])
    comprobar("cada 2 días: los días que tocan, contados desde que se escribió",
              horas("cada 2 días", dia=5) == ["08:00"] and horas("cada 2 días", dia=4) == [])
    comprobar("el día en que se escribió, sólo lo que viene después",
              horas("cada 4 horas", dia=3) == ["12:00", "16:00"], str(horas("cada 4 horas", dia=3)))
    comprobar("una de una sola vez no tiene horario", horas("acude al control del viernes") == [])
    comprobar("las horas se guardan ordenadas y sin lo que no es una hora",
              frecuencia.horas_en_texto("18:30, 6, 6:00; 25:00, x") == "06:00,18:30")

    tarde = datetime(2026, 11, 5, 17, 0, tzinfo=reloj.BOGOTA)
    siguiente = frecuencia.siguiente_momento("cada 8 horas", "", creada, tarde)
    comprobar("después de la última toma del día, la siguiente es mañana a las 8:00",
              reloj.en_bogota(siguiente).strftime("%d %H:%M") == "06 08:00", str(siguiente))


def probar_se_recuerda() -> None:
    print("\nQué se sigue recordando")

    ahora = reloj.ahora()

    def creada_hace(dias: int) -> str:
        return reloj.iso(ahora - timedelta(days=dias))

    comprobar("una fila de antes, sin columnas nuevas, se recuerda",
              recordatorios._se_recuerda({"creado_en": creada_hace(90)}))
    comprobar("una vigilancia nunca se recuerda",
              not recordatorios._se_recuerda({"tipo": "vigilancia", "creado_en": creada_hace(0)}))
    comprobar("dentro de su duración se recuerda",
              recordatorios._se_recuerda({"duracion_dias": 3, "creado_en": creada_hace(2)}))
    comprobar("pasada su duración ya no",
              not recordatorios._se_recuerda({"duracion_dias": 3, "creado_en": creada_hace(4)}))
    comprobar("ROBLE puede devolver el entero como texto",
              not recordatorios._se_recuerda({"duracion_dias": "3", "creado_en": creada_hace(4)}))


def main() -> int:
    for prueba in (probar_intervalo, probar_horario, probar_se_recuerda):
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
