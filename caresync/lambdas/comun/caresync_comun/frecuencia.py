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
from datetime import date, datetime, timedelta
from typing import Any

from caresync_comun import reloj

# «cada 24 horas», «cada 2 días», «cada 3 semanas». Con y sin tilde, porque el
# profesional escribe rápido.
_CADA_N = re.compile(r"cada\s+(\d+)\s*(horas?|h|d[ií]as?|semanas?)")
_VECES_AL_DIA = re.compile(r"(\d+|una|dos|tres|cuatro)\s+ve(?:z|ces)\s+al\s+d[ií]a")
_NUMEROS = {"una": 1, "dos": 2, "tres": 3, "cuatro": 4}

# Por debajo de esto no se programa más seguido. Un recordatorio cada hora durante el
# día son una decena de avisos, y lo que enseñan es a ignorarlos. Se recorta en vez de
# omitir: avisar menos de lo pedido es mejor que no avisar.
INTERVALO_MINIMO = timedelta(hours=4)

# La ventana de los avisos, en hora de Bogotá (propuesta de Kevin, 2/11): por defecto
# nada antes de las 8:00 ni después de las 19:00, para no ser intrusivo. Antes eran
# las 7:00 y las 20:00 en los correos, y las 7:00 y las 22:00 en la app: el mismo plan
# avisaba a horas distintas en cada sitio. Las horas que fije el profesional
# (`indicaciones.horas`) mandan sobre la ventana: lo clínico decide cuando él lo dice.
# El espejo está en `app/src/frecuencia.ts` y en `movil/src/agenda.ts`.
HORA_PRIMERA = 8
HORA_ULTIMA = 19

_HORA = re.compile(r"^(\d{1,2})(?:[:.h](\d{2}))?$")


def horas_fijas(horas: Any) -> list[tuple[int, int]]:
    """Las horas que fijó el profesional: «6:00, 18:30» es [(6, 0), (18, 30)].

    Ordenadas y sin repetir. Lo que no es una hora del día se descarta; si no queda
    ninguna, la indicación usa la ventana.
    """
    resultado = set()
    for trozo in re.split(r"[,;y ]+", str(horas or "").strip().lower()):
        encontrada = _HORA.match(trozo.strip())
        if not encontrada:
            continue
        hora, minuto = int(encontrada.group(1)), int(encontrada.group(2) or 0)
        if 0 <= hora <= 23 and 0 <= minuto <= 59:
            resultado.add((hora, minuto))
    return sorted(resultado)


def horas_en_texto(horas: Any) -> str:
    """La forma en que se guarda `indicaciones.horas`: «06:00,18:30», o vacío."""
    return ",".join(f"{hora:02d}:{minuto:02d}" for hora, minuto in horas_fijas(horas))


def veces_al_dia(frecuencia: Any) -> int | None:
    """«3 veces al día» es 3. Esas se reparten en la ventana, no cada 8 horas."""
    veces = _VECES_AL_DIA.search(str(frecuencia or "").strip().lower())
    if not veces:
        return None
    crudo = veces.group(1)
    cuantas = int(crudo) if crudo.isdigit() else _NUMEROS[crudo]
    return cuantas if cuantas > 0 else None


def momentos_del_dia(
    frecuencia: Any, horas: Any, creada: datetime | None, dia: date
) -> list[datetime]:
    """A qué horas se avisa esta indicación el día `dia` (de Bogotá), en UTC.

    - Con horas del profesional, esas, todos los días que le toquen.
    - «N veces al día», repartidas entre las 8:00 y las 19:00: tres son 8:00, 13:30 y
      19:00. No cada ocho horas: no es una pauta, es cuántas veces.
    - «Cada N horas» es una pauta: desde las 8:00, cada N horas, y lo que cae después
      de las 19:00 no se avisa. «Cada 8 horas» son las 8:00 y las 16:00; la toma de la
      medianoche no suena, salvo que el profesional fije las horas.
    - Cada varios días, a las 8:00 de los días que tocan, contados desde que se escribió.

    Nada anterior a que existiera la indicación: no se le puede reclamar a nadie.
    """
    paso = intervalo(frecuencia)
    fijas = horas_fijas(horas)
    if not paso and not fijas:
        return []

    creada_local = reloj.en_bogota(creada) if creada else None
    if creada_local and dia < creada_local.date():
        return []

    if paso and paso >= timedelta(days=1):
        cada_dias = max(1, round(paso / timedelta(days=1)))
        if creada_local and (dia - creada_local.date()).days % cada_dias:
            return []
        del_dia = fijas or [(HORA_PRIMERA, 0)]
    elif fijas:
        del_dia = fijas
    elif veces_al_dia(frecuencia):
        cuantas = veces_al_dia(frecuencia) or 1
        ventana = (HORA_ULTIMA - HORA_PRIMERA) * 60
        minutos = [HORA_PRIMERA * 60] if cuantas == 1 else [
            HORA_PRIMERA * 60 + round(k * ventana / (cuantas - 1)) for k in range(cuantas)
        ]
        del_dia = [(m // 60, m % 60) for m in minutos]
    else:
        pasos = int((HORA_ULTIMA - HORA_PRIMERA) * 60 // (paso.total_seconds() // 60)) + 1
        minutos = [HORA_PRIMERA * 60 + k * int(paso.total_seconds() // 60) for k in range(pasos)]
        del_dia = [(m // 60, m % 60) for m in minutos if m <= HORA_ULTIMA * 60]

    momentos = [
        datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=reloj.BOGOTA).astimezone(
            reloj.ahora().tzinfo
        )
        for hora, minuto in del_dia
    ]
    return [m for m in momentos if not creada or m > creada]


def siguiente_momento(
    frecuencia: Any, horas: Any, creada: datetime | None, despues_de: datetime, *, dias: int = 35
) -> datetime | None:
    """El primer momento de aviso posterior a `despues_de`, mirando hasta `dias` adelante.

    35 días alcanza para «cada 4 semanas», la frecuencia más espaciada que se entiende.
    """
    primero = reloj.en_bogota(despues_de).date()
    for desfase in range(dias + 1):
        for momento in momentos_del_dia(frecuencia, horas, creada, primero + timedelta(days=desfase)):
            if momento > despues_de:
                return momento
    return None


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
