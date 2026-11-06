#!/usr/bin/env python3
"""
Pruebas de `evaluar_concurrencia.py` (M4) y `evaluar_seguimiento.py` (M5). Sin red,
sin tokens, sin AWS.

    python prueba_metricas.py

Lo que importa es que ninguno de los dos informes **diga que se cumple cuando no**.
En M4, una cita confirmada sobre un cupo que quedó libre no es una doble reserva
todavía, pero lo será en cuanto un tercero tome el cupo: tiene que salir aparte, no
como un par sano. En M5, un retroceso sin alerta y una alerta sin retroceso son los
dos fallos, y el banco tiene que esperar alerta exactamente donde la regla de
`seguimiento.registrar_evolucion` la produce, o la métrica mediría el banco y no el
sistema.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ.parent / "lambdas" / "pruebas"))

from entorno import comprobar, fallos, preparar  # noqa: E402

preparar()
sys.path.insert(0, str(RAIZ.parent / "lambdas" / "herramientas"))

import evaluar_concurrencia as m4  # noqa: E402
import evaluar_seguimiento as m5  # noqa: E402
import seguimiento  # noqa: E402

CASO_A, CASO_B, OTRO = "caso-a", "caso-b", "caso-de-otra-persona"
CUPO = "5eed0000-0000-4000-8000-000000000001"


class _Agenda:
    """Lo que `_revisar` lee de ROBLE: las citas de un cupo y el cupo."""

    def __init__(self, citas: list[dict], cupo: dict) -> None:
        self.citas, self.fila = citas, cupo

    def _leer(self, tabla: str, filtro: dict) -> list[dict]:
        assert tabla == "citas" and filtro == {"cupo_id": CUPO}
        return self.citas

    def cupo(self, cupo_id: str) -> dict:
        return self.fila


def _par(a: str = "cita", b: str = "tomado", alternativas: int = 3) -> m4.Par:
    return m4.Par(
        numero=1, cupo_id=CUPO, inicio="2026-11-13T14:00:00",
        a=m4.Lado(caso=CASO_A, resultado=a), b=m4.Lado(caso=CASO_B, resultado=b, alternativas=alternativas),
    )


def _cita(caso: str, estado: str = "confirmada") -> dict:
    return {"_id": f"cita-{caso}", "caso_id": caso, "cupo_id": CUPO, "estado": estado}


def probar_concurrencia() -> None:
    print("\nM4: lo que quedó sobre el cupo")
    par = _par()
    m4._revisar(_Agenda([_cita(CASO_A), _cita(CASO_B, "cancelada")], {"estado": "confirmado"}), par)
    comprobar("una cita y el cupo confirmado: en firme", par.en_firme and not par.doble and not par.latente)
    comprobar("el perdedor con alternativas cuenta", par.con_alternativas)

    par = _par(a="cita", b="cita")
    m4._revisar(_Agenda([_cita(CASO_A), _cita(CASO_B)], {"estado": "confirmado"}), par)
    comprobar("dos citas confirmadas: doble reserva", par.doble and not par.en_firme)

    par = _par()
    m4._revisar(_Agenda([_cita(CASO_A)], {"estado": "libre"}), par)
    comprobar("cita sobre un cupo libre: latente, no en firme", par.latente and not par.en_firme)

    par = _par(a="error", b="error", alternativas=0)
    m4._revisar(_Agenda([], {"estado": "libre"}), par)
    comprobar("los dos cedieron: ni doble ni en firme", par.confirmadas == 0 and not par.doble and not par.en_firme)

    par = _par()
    m4._revisar(_Agenda([_cita(CASO_A), _cita(OTRO)], {"estado": "confirmado"}), par)
    comprobar("la cita de otra persona en ese cupo no es de la prueba", par.confirmadas == 1)

    par = _par(b="tomado", alternativas=0)
    m4._revisar(_Agenda([_cita(CASO_A)], {"estado": "confirmado"}), par)
    comprobar("un perdedor sin alternativas no cuenta como atendido", not par.con_alternativas)

    print("\nM4: el informe")
    doble = _par(a="cita", b="cita")
    m4._revisar(_Agenda([_cita(CASO_A), _cita(CASO_B)], {"estado": "confirmado"}), doble)
    sano = _par()
    m4._revisar(_Agenda([_cita(CASO_A)], {"estado": "confirmado"}), sano)
    informe = m4.generar_informe([doble, sano], centro="CMU", desfase_ms=0)
    comprobar("cuenta la doble reserva", "Dobles reservas: 1 de 2" in informe, informe.splitlines()[4])
    comprobar("y la marca en su fila", "❌ doble reserva" in informe)


def _turno(escala: int, alerta: bool, *, registrada: int | None = None, nuevas: int = 0,
           segundos: float | None = None, herramientas: tuple = ("registrar_evolucion",)) -> m5.Turno:
    return m5.Turno(
        mensaje="m", escala_esperada=escala, alerta_esperada=alerta, herramientas=list(herramientas),
        escala_registrada=escala if registrada is None else registrada,
        alertas_nuevas=nuevas, segundos_hasta_alerta=segundos,
    )


def _guion(*turnos: m5.Turno) -> m5.Guion:
    return m5.Guion(id="g", grupo="caida", objetivo="o", turnos=list(turnos))


def probar_seguimiento() -> None:
    print("\nM5: el veredicto de un guion")
    bien, _ = m5.veredicto(_guion(_turno(8, False), _turno(4, True, nuevas=1, segundos=9.5)))
    comprobar("retroceso con alerta a tiempo: cumple", bien)

    bien, motivo = m5.veredicto(_guion(_turno(8, False), _turno(4, True)))
    comprobar("retroceso sin alerta: no cumple", not bien and "no dejó alerta" in motivo, motivo)

    bien, motivo = m5.veredicto(_guion(_turno(7, False, nuevas=1, segundos=4.0)))
    comprobar("alerta sin retroceso: no cumple", not bien and "sin retroceso" in motivo, motivo)

    bien, motivo = m5.veredicto(_guion(_turno(3, True, nuevas=1, segundos=m5.LIMITE_SEGUNDOS + 1)))
    comprobar("alerta después de 5 min: no cumple", not bien and "tardó" in motivo, motivo)

    bien, motivo = m5.veredicto(_guion(_turno(4, True, registrada=6, nuevas=1, segundos=5.0)))
    comprobar("escala registrada distinta de la dicha: no cumple", not bien and "registró 6" in motivo, motivo)

    bien, motivo = m5.veredicto(
        _guion(_turno(3, True, nuevas=1, segundos=5.0, herramientas=("registrar_evolucion", "escalar_urgencia")))
    )
    comprobar("escalar sin señal de alarma: no cumple", not bien and "escaló" in motivo, motivo)

    print("\nM5: el informe")
    tarde = _guion(_turno(8, False), _turno(4, True))
    a_tiempo = _guion(_turno(3, True, nuevas=1, segundos=7.0))
    estable = m5.Guion(id="e", grupo="estable", objetivo="o", turnos=[_turno(6, False), _turno(7, False)])
    informe = m5.generar_informe([tarde, a_tiempo, estable])
    comprobar("M5 cuenta sólo los guiones con retroceso", "menos de 5 min: 1 de 2" in informe)
    comprobar("las alertas falsas en cero", "Alertas sin retroceso (falsas): 0" in informe)


def probar_banco() -> None:
    print("\nM5: el banco")
    casos = json.loads(m5.CASOS_PATH.read_text(encoding="utf-8"))
    grupos = {g: sum(c["grupo"] == g for c in casos) for g in ("estable", "caida", "escala")}
    comprobar("6 guiones: 2 estables, 2 con caída, 2 con escala baja",
              len(casos) == 6 and grupos == {"estable": 2, "caida": 2, "escala": 2}, str(grupos))

    # La alerta esperada tiene que ser la que produce la regla del sistema, con sus
    # mismos umbrales: si alguien los cambia, el banco tiene que avisar, no mentir.
    distintos = []
    for caso in casos:
        anterior = None
        for n, turno in enumerate(caso["turnos"], start=1):
            escala = turno["escala"]
            regla = (anterior is not None and anterior - escala >= seguimiento.CAIDA_RELEVANTE) or (
                escala <= seguimiento.ESCALA_PREOCUPANTE
            )
            if regla != turno["alerta"]:
                distintos.append(f"{caso['id']} turno {n}")
            anterior = escala
    comprobar("la alerta esperada es la de registrar_evolucion", not distintos, str(distintos))

    sin_alerta = [c["id"] for c in casos if c["grupo"] != "estable" and not any(t["alerta"] for t in c["turnos"])]
    comprobar("todo guion de retroceso espera al menos una alerta", not sin_alerta, str(sin_alerta))
    con_numero = [c["id"] for c in casos for t in c["turnos"] if str(t["escala"]) not in t["mensaje"]]
    comprobar("cada mensaje dice su escala con el número", not con_numero, str(con_numero))


def main() -> int:
    for prueba in (probar_concurrencia, probar_seguimiento, probar_banco):
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
