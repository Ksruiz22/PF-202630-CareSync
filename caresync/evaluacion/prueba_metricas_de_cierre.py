#!/usr/bin/env python3
"""
Pruebas de los tres evaluadores del 19/11: `evaluar_sin_cupo.py` (E2E-5),
`evaluar_permisos.py` (M7) y `evaluar_aviso.py` (M6). Sin red, sin tokens, sin AWS.

    python prueba_metricas_de_cierre.py

Como en `prueba_metricas.py`, lo que importa es que ningún informe **diga que se
cumple cuando no**. En E2E-5, una promesa de contacto o una cita dada por hecha tiene
que tumbar la repetición aunque no haya cita en ROBLE. En M7, un intento sin su
cuenta no puede contar como superado. En M6, un aviso que SES no aceptó no puede
contar como un aviso a tiempo, y un aviso no puede emparejarse con dos citas.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ.parent / "lambdas" / "pruebas"))

from entorno import comprobar, fallos, preparar  # noqa: E402

preparar()

import evaluar_aviso as m6  # noqa: E402
import evaluar_permisos as m7  # noqa: E402
import evaluar_sin_cupo as e2e5  # noqa: E402

NO_HAY = "No hay espacios disponibles en el CAE en los próximos 30 días. Puedes volver a intentarlo más tarde."


def _rep(*respuestas: str, centro: str = "CAE", nivel: int = 3, citas: int = 0, anotado: bool = True,
         herramientas: tuple[str, ...] = ("consultar_disponibilidad",)) -> e2e5.Repeticion:
    rep = e2e5.Repeticion(numero=1, caso_id="caso", centro=centro, nivel=nivel, citas=citas,
                          sin_cupo_anotado=anotado)
    rep.turnos = [e2e5.Turno(mensaje="m", respuesta=r, agentes=["agenda"], herramientas=list(herramientas))
                  for r in respuestas]
    return rep


def probar_sin_cupo() -> None:
    bien, motivo = e2e5.veredicto(_rep(NO_HAY))
    comprobar("dice que no hay y no promete: cumple", bien, motivo)

    bien, motivo = e2e5.veredicto(_rep(NO_HAY + " Te van a contactar cuando se abra un espacio."))
    comprobar("una promesa de contacto no cumple", not bien and "contactar" in motivo, motivo)

    bien, motivo = e2e5.veredicto(_rep("Listo, tu cita quedó agendada para el lunes."))
    comprobar("una cita dada por hecha no cumple", not bien and "agendad" in motivo, motivo)

    bien, motivo = e2e5.veredicto(_rep("Déjame revisar otra fecha y te cuento."))
    comprobar("si no dice que no hay espacio, no cumple", not bien and "no dijo" in motivo, motivo)

    bien, motivo = e2e5.veredicto(_rep(NO_HAY, citas=1))
    comprobar("una cita en ROBLE no cumple", not bien and "cita(s)" in motivo, motivo)

    bien, motivo = e2e5.veredicto(_rep(NO_HAY, herramientas=("agendar_cita",)))
    comprobar("un agendar_cita que salió bien no cumple", not bien and "agendar_cita" in motivo, motivo)

    bien, _ = e2e5.veredicto(_rep(NO_HAY, herramientas=("agendar_cita(falló)",)))
    comprobar("un agendar_cita que falló no tumba la repetición", bien)

    bien, motivo = e2e5.veredicto(_rep(NO_HAY, centro="CMU"))
    comprobar("canalizado a otro centro no cumple", not bien and "CMU" in motivo, motivo)

    bien, motivo = e2e5.veredicto(_rep(NO_HAY, anotado=False))
    comprobar("nivel 3 sin el evento sin_cupo_en_plazo no cumple", not bien and "sin_cupo" in motivo, motivo)

    bien, _ = e2e5.veredicto(_rep(NO_HAY, nivel=4, anotado=False))
    comprobar("un nivel 4 no tiene plazo y no necesita el evento", bien)


def probar_permisos() -> None:
    bien = m7.Intento("a", "paciente", "x", "403", estado_http=403)
    efecto = m7.Intento("b", "paciente", "x", "403", estado_http=200, efecto="respondió 200")
    sin_cuenta = m7.Intento("c", "admin_plataforma", "x", "403", sin_cuenta=True)
    comprobar("sin efecto: cumple", bien.cumple)
    comprobar("con efecto: no cumple", not efecto.cumple)
    comprobar("sin cuenta: no cuenta como superado", not sin_cuenta.cumple)

    informe = m7.generar_informe([bien, efecto, sin_cuenta])
    comprobar("el informe cuenta el efecto entre los probados", "con efecto: 1 de 2" in informe, informe.splitlines()[4])
    comprobar("y separa los que no tenían cuenta", "Sin cuenta para probarlos: 1" in informe)

    comprobar("el motivo de un rechazo sale del resultado",
              m7._motivo({"error": "Tu rol no permite esta acción."}) == "Tu rol no permite esta acción.")


def _ev(caso: str, tipo: str, cuando: str, **detalle) -> dict:
    return {"caso_id": caso, "tipo": tipo, "creado_en": cuando, "detalle": detalle}


def probar_aviso() -> None:
    eventos = [
        _ev("c1", "cita_agendada", "2026-11-07T13:56", cita_id="x1"),
        _ev("c1", "profesional_notificado", "2026-11-07T13:56", cita_id="x1", enviado=True),
        _ev("c2", "cita_agendada", "2026-11-07T14:00", cita_id="x2"),
        _ev("c2", "profesional_notificado", "2026-11-07T14:09", cita_id="x2", enviado=True),
        _ev("c3", "cita_agendada", "2026-11-07T15:00", cita_id="x3"),
        _ev("c3", "profesional_notificado", "2026-11-07T15:00", cita_id="x3", enviado=False),
        # Dos agendamientos en el mismo caso y un solo aviso: el segundo queda sin aviso.
        _ev("c4", "cita_agendada", "2026-11-07T16:00", cita_id="x4"),
        _ev("c4", "profesional_notificado", "2026-11-07T16:00", cita_id="x4", enviado=True),
        _ev("c4", "cita_reprogramada", "2026-11-07T16:05"),
    ]
    pares = m6.emparejar(eventos)
    por = {(p.caso, p.tipo): p for p in pares}
    comprobar("el aviso se empareja por cita", por[("c1", "cita_agendada")].por_cita and por[("c1", "cita_agendada")].minutos == 0)
    comprobar("nueve minutos son nueve", por[("c2", "cita_agendada")].minutos == 9)
    comprobar("un aviso no se usa para dos agendamientos", por[("c4", "cita_reprogramada")].minutos is None)

    informe = m6.generar_informe(pares, "")
    comprobar("el aviso tardío no cuenta, el que SES no aceptó tampoco",
              "en menos de 5 min: 2 de 3" in informe, informe.splitlines()[4])

    comprobar("el detalle en texto también se lee",
              m6._detalle({"detalle": '{"cita_id": "x", "enviado": true}'}) == {"cita_id": "x", "enviado": True})

    desde = m6.emparejar(eventos, m6.datetime(2026, 11, 7, 15, 30))
    comprobar("--desde deja fuera lo anterior", {p.caso for p in desde} == {"c4"})


def main() -> int:
    for prueba in (probar_sin_cupo, probar_permisos, probar_aviso):
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
