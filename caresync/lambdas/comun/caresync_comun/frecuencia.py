"""Cada cuánto: la frecuencia de una indicación, de texto a intervalo.

Vive aquí y no en la función de recordatorios porque la leen dos sitios que tienen
que estar de acuerdo. Recordatorios la usa para programar los correos; el
orquestador, para avisarle al profesional —antes de guardar el plan— de que una
frecuencia no se va a convertir en ningún recordatorio. Si cada uno tuviera su
copia, la propuesta podría dar por buena una frase que después recordatorios no
entiende, y el plan se guardaría sin que saliera un solo aviso.

La vista del profesional tiene un espejo en `app/src/frecuencia.ts` para validar
mientras se escribe. Si cambian las frases que se aceptan, cambian las dos.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

# «cada 24 horas», «cada 2 días», «cada 3 semanas». Con y sin tilde, porque el
# profesional escribe rápido.
_CADA_N = re.compile(r"cada\s+(\d+)\s*(horas?|h|d[ií]as?|semanas?)")
_VECES_AL_DIA = re.compile(r"(\d+|una|dos|tres|cuatro)\s+ve(?:z|ces)\s+al\s+d[ií]a")
_NUMEROS = {"una": 1, "dos": 2, "tres": 3, "cuatro": 4}

# Por debajo de esto no se programa más seguido. Un recordatorio cada hora entre
# las 7:00 y las 20:00 son trece correos al día, y lo que enseñan es a ignorarlos.
# Se recorta en vez de omitir: avisar menos de lo pedido es mejor que no avisar.
INTERVALO_MINIMO = timedelta(hours=4)


def intervalo(frecuencia: Any) -> timedelta | None:
    """Traduce la frecuencia que escribió el profesional a un intervalo.

    Es texto libre a propósito: el profesional escribe en su interfaz, no elige
    de una lista. Lo que no se entiende no se convierte en una serie de correos,
    se omite y queda contado en el resumen de la corrida.

    Antes sólo se reconocía una lista cerrada de frases, y en ella no estaban ni
    «cada 24 horas» —el valor que la vista del profesional propone por omisión— ni
    «cada 2 días», que su ayuda da como ejemplo. Un plan guardado sin tocar ese
    campo no programaba ni un recordatorio y la corrida lo contaba como «de una
    sola vez», así que nadie lo notaba.
    """
    texto = str(frecuencia or "").strip().lower()
    if not texto:
        return None

    cada = _CADA_N.search(texto)
    if cada:
        cantidad = int(cada.group(1))
        if cantidad <= 0:
            return None
        unidad = cada.group(2)
        if unidad.startswith("h"):
            delta = timedelta(hours=cantidad)
        elif unidad.startswith("d"):
            delta = timedelta(days=cantidad)
        else:
            delta = timedelta(weeks=cantidad)
        return max(delta, INTERVALO_MINIMO)

    veces = _VECES_AL_DIA.search(texto)
    if veces:
        crudo = veces.group(1)
        cuantas = int(crudo) if crudo.isdigit() else _NUMEROS[crudo]
        if cuantas <= 0:
            return None
        return max(timedelta(hours=24) / cuantas, INTERVALO_MINIMO)

    for palabra, delta in (
        ("cada hora", INTERVALO_MINIMO),
        ("diari", timedelta(days=1)),
        ("cada día", timedelta(days=1)),
        ("cada dia", timedelta(days=1)),
        ("semanal", timedelta(days=7)),
        ("cada semana", timedelta(days=7)),
    ):
        if palabra in texto:
            return delta
    return None
