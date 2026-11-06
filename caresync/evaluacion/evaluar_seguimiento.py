"""
Evaluación del seguimiento (M5) — CareSync
==========================================

Mide la métrica M5 del segundo informe: **todo retroceso de los guiones de
seguimiento genera un evento `evolucion_desfavorable` visible para el profesional en
menos de 5 minutos**. El banco (`casos_seguimiento.json`) tiene los 6 guiones
comprometidos: 2 estables, 2 con una caída de 3 puntos o más y 2 que llegan a una
escala de 3 o menos.

Cada guion conversa con el agente de seguimiento por `POST /agente`, el mismo camino
que la PWA y la app móvil, y después de cada turno lee `eventos` y `evolucion` en
ROBLE con la misma cuenta. Lo que se mide:

- **Retroceso detectado a tiempo** (la métrica): en cada turno marcado con
  `"alerta": true`, que aparezca un `evolucion_desfavorable` nuevo y en cuánto. El
  tiempo se toma con un solo reloj, el de esta máquina: desde que se envió el mensaje
  hasta la lectura que lo encontró. Es una cota superior, sin el desfase entre el
  reloj local y el de la Lambda.
- **Ninguna alerta falsa**: en los turnos sin `"alerta"`, que no aparezca ninguna.
- **Lo que hizo el agente**: si llamó a `registrar_evolucion` con la escala que dijo
  la persona, y que no llamó a `escalar_urgencia`, porque ningún guion trae una
  señal de alarma.

**Cómo se prepara cada guion.** El agente de seguimiento atiende un caso en
`en_seguimiento` con un plan, y llegar ahí por el camino real exige triaje, cita,
consulta y un plan dictado por un profesional. El evaluador lo siembra directo en
ROBLE con la cuenta de prueba: un caso en seguimiento y un plan de una indicación,
firmado como «Profesional de prueba (evaluación M5)». La indicación va **sin
frecuencia**, para que la función de recordatorios no le programe avisos a nadie. Es
la misma escritura que hace la PWA del profesional: ROBLE no distingue a un paciente
de un profesional —los dos son su rol `user`—, la regla de que el plan lo escribe el
profesional vive en la aplicación (ver `docs/runbook-roble.md`). Al terminar, la
indicación se desactiva y el caso se cierra.

Requisitos: las dependencias de las Lambdas (`requests`, `boto3`, el SDK de ROBLE).

Uso (la cuenta de `evaluacion/.env`; `CARESYNC_API_URL` apunta a lo desplegado):
    python evaluar_seguimiento.py --solo caida-01     # una prueba barata primero
    python evaluar_seguimiento.py                     # los 6 guiones, ~4 min
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from cuenta_roble import ErrorDeCuenta, Credencial, cargar_entorno
from evaluar_concurrencia import _preparar_lambdas

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

RAIZ = Path(__file__).parent
CASOS_PATH = RAIZ / "casos_seguimiento.json"
INFORME_PATH = RAIZ / "informe_seguimiento.md"
CRUDO_PATH = RAIZ / "resultados_seguimiento.json"

# La cuota de ROBLE (100 operaciones por minuto y por IP): cada turno del agente gasta
# una docena entre el hilo, el plan y los registros, y el evaluador lee dos tablas más.
PAUSA_ENTRE_TURNOS = 6.0
LIMITE_SEGUNDOS = 5 * 60
SONDEO_SEGUNDOS = 20
TIEMPO_ESPERA = 60
PROFESIONAL = "Profesional de prueba (evaluación M5)"
DESFAVORABLE = "evolucion_desfavorable"


@dataclass
class Turno:
    mensaje: str
    escala_esperada: int
    alerta_esperada: bool
    herramientas: list[str] = field(default_factory=list)
    respuesta: str = ""
    error: str = ""
    escala_registrada: int | None = None
    alertas_nuevas: int = 0
    segundos_hasta_alerta: float | None = None
    segundos_respuesta: float = 0.0


@dataclass
class Guion:
    id: str
    grupo: str
    objetivo: str
    caso_id: str = ""
    turnos: list[Turno] = field(default_factory=list)
    limpieza: list[str] = field(default_factory=list)


def _turno(api_url: str, cuenta: Credencial, mensaje: str, caso_id: str) -> dict[str, Any]:
    """Un mensaje a `/agente` sin pedir agente: lo elige el estado del caso, como en la app."""
    if requests is None:
        sys.exit("Falta la dependencia «requests»: pip install requests")
    for intento in range(1, 4):
        try:
            r = requests.post(
                f"{api_url.rstrip('/')}/agente",
                headers={"Authorization": f"Bearer {cuenta.actual()}"},
                json={"mensaje": mensaje, "caso_id": caso_id},
                timeout=TIEMPO_ESPERA,
            )
        except requests.RequestException as exc:
            fallo = f"red: {type(exc).__name__}"
        else:
            if r.status_code == 200:
                return r.json()
            if r.status_code == 401 and intento == 1:
                cuenta.renovar()
                continue
            fallo = f"HTTP {r.status_code}: {r.text[:160]}"
            if r.status_code not in (429, 502, 503):
                return {"error": fallo}
        time.sleep(10 * intento)
    return {"error": fallo}


def _sembrar(acceso, caso_def: dict[str, Any]) -> tuple[str, str]:
    """Un caso en seguimiento con su plan, como lo dejaría la consulta del profesional."""
    from caresync_comun import reloj
    from caresync_comun.roble_acceso import fila_id

    caso = acceso.abrir_caso(motivo=f"{caso_def['motivo']} [evaluación M5: {caso_def['id']}]")
    caso_id = str(fila_id(caso))
    acceso.actualizar_caso(
        caso_id,
        {
            "estado": "en_seguimiento",
            "centro": caso_def["centro"],
            "nivel_urgencia": 3,
            "resumen_triaje": caso_def["motivo"],
        },
    )
    plan = acceso._crear(
        "planes",
        {
            "caso_id": caso_id,
            "profesional_user_id": "evaluacion-m5",
            "profesional_nombre": PROFESIONAL,
            "resumen": caso_def["plan"],
            "creado_en": reloj.iso(),
        },
    )
    indicacion = acceso._crear(
        "indicaciones",
        {
            "caso_id": caso_id,
            "plan_id": str(fila_id(plan)),
            "texto": caso_def["indicacion"],
            "frecuencia": None,
            "activa": True,
            "creado_en": reloj.iso(),
        },
    )
    return caso_id, str(fila_id(indicacion))


def _desfavorables(acceso, caso_id: str) -> list[dict[str, Any]]:
    return [e for e in acceso.eventos_del_caso(caso_id) if e.get("tipo") == DESFAVORABLE]


def _correr(api_url: str, cuenta: Credencial, acceso, caso_def: dict[str, Any], pausa: float) -> Guion:
    guion = Guion(id=caso_def["id"], grupo=caso_def["grupo"], objetivo=caso_def["objetivo"])
    caso_id, indicacion_id = _sembrar(acceso, caso_def)
    guion.caso_id = caso_id
    try:
        vistas = 0
        for numero, definicion in enumerate(caso_def["turnos"], start=1):
            turno = Turno(
                mensaje=definicion["mensaje"],
                escala_esperada=int(definicion["escala"]),
                alerta_esperada=bool(definicion["alerta"]),
            )
            enviado = time.monotonic()
            datos = _turno(api_url, cuenta, turno.mensaje, caso_id)
            turno.segundos_respuesta = round(time.monotonic() - enviado, 1)
            turno.error = str(datos.get("error") or "")
            turno.respuesta = str(datos.get("respuesta") or "")
            turno.herramientas = [
                f"{a.get('herramienta')}{'' if a.get('ok', True) else '(falló)'}"
                for a in datos.get("acciones") or []
            ]

            # Se sondea hasta el límite sólo si se espera una alerta; si no, basta una
            # lectura, y otra al final del guion por si alguna llegó tarde.
            while True:
                nuevas = _desfavorables(acceso, caso_id)[vistas:]
                if nuevas or not turno.alerta_esperada or time.monotonic() - enviado > LIMITE_SEGUNDOS + 30:
                    break
                time.sleep(SONDEO_SEGUNDOS)
            if nuevas:
                turno.segundos_hasta_alerta = round(time.monotonic() - enviado, 1)
            turno.alertas_nuevas = len(nuevas)
            vistas += len(nuevas)

            evolucion = acceso.evolucion_del_caso(caso_id)
            if evolucion:
                turno.escala_registrada = int(evolucion[-1].get("escala"))
            guion.turnos.append(turno)
            print(
                f"    [{numero}] herramientas={turno.herramientas or 'ninguna'} "
                f"escala={turno.escala_registrada} alertas={turno.alertas_nuevas}"
                + (f" en {turno.segundos_hasta_alerta}s" if turno.segundos_hasta_alerta else "")
                + (f" ERROR {turno.error}" if turno.error else "")
            )
            time.sleep(pausa)

        tardias = len(_desfavorables(acceso, caso_id)) - vistas
        if tardias:
            guion.limpieza.append(f"{tardias} alerta(s) que aparecieron después de su turno")
    finally:
        acceso._actualizar("indicaciones", indicacion_id, {"activa": False})
        guion.limpieza.append("indicación desactivada")
        if cuenta.cerrar_caso(caso_id):
            guion.limpieza.append("caso cerrado")
    return guion


def veredicto(guion: Guion) -> tuple[bool, str]:
    """Si el guion cumple, y por qué no cuando no cumple."""
    problemas = []
    for n, t in enumerate(guion.turnos, start=1):
        if t.error:
            problemas.append(f"turno {n}: error del API")
            continue
        if t.alerta_esperada:
            if not t.alertas_nuevas:
                problemas.append(f"turno {n}: el retroceso no dejó alerta")
            elif (t.segundos_hasta_alerta or 0) > LIMITE_SEGUNDOS:
                problemas.append(f"turno {n}: la alerta tardó {t.segundos_hasta_alerta} s")
        elif t.alertas_nuevas:
            problemas.append(f"turno {n}: alerta sin retroceso")
        if t.escala_registrada != t.escala_esperada:
            problemas.append(f"turno {n}: registró {t.escala_registrada}, la persona dijo {t.escala_esperada}")
        if any(h.startswith("escalar_urgencia") for h in t.herramientas):
            problemas.append(f"turno {n}: escaló a urgencias sin señal de alarma")
    if any("después de su turno" in l for l in guion.limpieza):
        problemas.append("alerta tardía")
    return (not problemas, "; ".join(problemas) or "cumple")


def generar_informe(guiones: list[Guion]) -> str:
    con_retroceso = [g for g in guiones if any(t.alerta_esperada for t in g.turnos)]
    estables = [g for g in guiones if not any(t.alerta_esperada for t in g.turnos)]
    a_tiempo = sum(
        all(t.alertas_nuevas and (t.segundos_hasta_alerta or 0) <= LIMITE_SEGUNDOS
            for t in g.turnos if t.alerta_esperada)
        for g in con_retroceso
    )
    falsas = sum(t.alertas_nuevas for g in guiones for t in g.turnos if not t.alerta_esperada)
    tiempos = [t.segundos_hasta_alerta for g in guiones for t in g.turnos if t.segundos_hasta_alerta]
    cumplen = sum(veredicto(g)[0] for g in guiones)

    lineas = [
        "# Informe de seguimiento (M5) — CareSync",
        "",
        f"Generado el {datetime.now().strftime('%Y-%m-%d %H:%M')}.",
        "",
        f"- **M5 — retrocesos con alerta visible en menos de 5 min: {a_tiempo} de {len(con_retroceso)}** "
        "guiones (meta: todos).",
        f"- Alertas sin retroceso (falsas): {falsas}, en {len(estables)} guiones estables y en los turnos "
        "previos al retroceso.",
        f"- Tiempo hasta la alerta: {', '.join(f'{s:g} s' for s in tiempos) or '—'} "
        "(desde el envío hasta la lectura que la encontró, con el reloj de esta máquina).",
        f"- Guiones que cumplen en todo (alerta, escala registrada y sin escalar): {cumplen} de {len(guiones)}.",
        "",
        "Cada guion es un caso sembrado en seguimiento con un plan de prueba; la conversación",
        "va por `POST /agente` y lo demás se lee en ROBLE. Ver el docstring de",
        "`evaluar_seguimiento.py`.",
        "",
        "| Guion | Grupo | Turnos | Escalas (dicha → registrada) | Alertas por turno | Resultado |",
        "|---|---|:-:|---|---|---|",
    ]
    for g in guiones:
        bien, motivo = veredicto(g)
        escalas = ", ".join(f"{t.escala_esperada}→{t.escala_registrada}" for t in g.turnos)
        alertas = ", ".join(
            f"{t.alertas_nuevas}" + (f" ({t.segundos_hasta_alerta:g} s)" if t.segundos_hasta_alerta else "")
            for t in g.turnos
        )
        lineas.append(
            f"| {g.id} | {g.grupo} | {len(g.turnos)} | {escalas} | {alertas} | "
            f"{'✅' if bien else '❌ ' + motivo} |"
        )

    lineas += ["", "## Conversaciones", ""]
    for g in guiones:
        lineas += [f"### {g.id} — {g.objetivo}", ""]
        for n, t in enumerate(g.turnos, start=1):
            lineas += [
                f"**{n}. Persona:** {t.mensaje}",
                "",
                f"Herramientas: {', '.join(t.herramientas) or 'ninguna'}. "
                f"Respondió en {t.segundos_respuesta:g} s.",
                "",
                *(f"> {l}" if l else ">" for l in (t.respuesta or f"(error: {t.error})").splitlines()),
                "",
            ]
    return "\n".join(lineas)


def main() -> None:
    analizador = argparse.ArgumentParser(description="M5: alertas de retroceso del seguimiento.")
    analizador.add_argument("--solo", default="", help="Ids o grupos separados por coma.")
    analizador.add_argument("--pausa", type=float, default=PAUSA_ENTRE_TURNOS)
    opciones = analizador.parse_args()

    casos = json.loads(CASOS_PATH.read_text(encoding="utf-8"))
    if opciones.solo:
        filtro = {s.strip() for s in opciones.solo.split(",") if s.strip()}
        casos = [c for c in casos if c["id"] in filtro or c["grupo"] in filtro]
        if not casos:
            sys.exit(f"Ningún guion coincide con «{opciones.solo}».")

    cargar_entorno()
    api_url = os.environ.get("CARESYNC_API_URL", "")
    email = os.environ.get("CARESYNC_EMAIL", "").strip()
    contrasena = os.environ.get("CARESYNC_PASSWORD", "")
    if not api_url:
        sys.exit("Falta CARESYNC_API_URL (la salida `api_url` de Terraform).")
    if not (email and contrasena):
        sys.exit("Falta la cuenta de prueba: CARESYNC_EMAIL y CARESYNC_PASSWORD en evaluacion/.env.")
    try:
        cuenta = Credencial.desde_contrasena(email, contrasena)
    except ErrorDeCuenta as exc:
        sys.exit(str(exc))

    _preparar_lambdas()
    from caresync_comun.roble_acceso import AccesoRoble

    print(f"{len(casos)} guiones contra {api_url}.\n")
    guiones = []
    for indice, caso_def in enumerate(casos, start=1):
        print(f"[{indice}/{len(casos)}] {caso_def['id']}: {caso_def['objetivo'][:60]}")
        # Un acceso por guion: el token de la cuenta se renueva solo, éste no.
        acceso = AccesoRoble.desde_token(cuenta.actual())
        guiones.append(_correr(api_url, cuenta, acceso, caso_def, opciones.pausa))
        print(f"    {veredicto(guiones[-1])[1]}")

    CRUDO_PATH.write_text(json.dumps([asdict(g) for g in guiones], ensure_ascii=False, indent=2), encoding="utf-8")
    INFORME_PATH.write_text(generar_informe(guiones), encoding="utf-8")
    print(f"\nCumplen {sum(veredicto(g)[0] for g in guiones)} de {len(guiones)}. Informe en {INFORME_PATH.name}")


if __name__ == "__main__":
    main()
