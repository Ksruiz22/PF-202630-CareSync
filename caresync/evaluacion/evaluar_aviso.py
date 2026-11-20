"""
Evaluación del aviso al profesional (M6) — CareSync
===================================================

M6 pide que **el profesional reciba el resumen del caso en menos de 5 minutos tras el
agendamiento**. Hasta el 19/11 sólo se sabía que la herramienta avisaba —la prueba de
humo del 7/11—, sin medir cuánto tardaba.

Este evaluador **sólo lee**: no agenda nada. Recorre la bitácora (`eventos`) y empareja
cada agendamiento (`cita_agendada`, `control_agendado` o `cita_reprogramada`) con el
`profesional_notificado` de la misma cita —el evento lleva el `cita_id`— o, en las
filas viejas que no lo traen, con el primero del mismo caso después del agendamiento.
De cada aviso dice si SES aceptó el correo (`enviado`), que es lo que separa «se
intentó» de «salió».

Dos límites que el informe declara:

- **La resolución es de un minuto.** ROBLE devuelve `creado_en` cortado al minuto
  (ver `momento_de_mensaje` en `roble_acceso.py`), así que «0 min» quiere decir «en el
  mismo minuto». Alcanza para la meta de 5.
- **Lo que mide es la salida, no la llegada al buzón.** Entre que SES acepta y el
  correo aparece en la bandeja pasan segundos, pero eso lo dice el buzón del
  profesional. El informe deja una tabla para anotar, a mano, la hora de llegada de
  los correos con `[CareSync] Caso asignado` en el asunto.

Lee la bitácora de todos los casos: con la cuenta de evaluación funciona porque el rol
`user` de ROBLE tiene `all:read` (ver `docs/runbook-roble.md`). El día que eso se
cierre, correrlo con una cuenta del centro.

Uso:
    python evaluar_aviso.py                      # todo lo que haya en la bitácora
    python evaluar_aviso.py --desde 2026-11-07   # sólo desde que SES tiene remitente
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cuenta_roble import ErrorDeCuenta, Credencial, cargar_entorno

RAIZ = Path(__file__).parent
INFORME_PATH = RAIZ / "informe_aviso.md"
CRUDO_PATH = RAIZ / "resultados_aviso.json"

LIMITE_MINUTOS = 5
AGENDAMIENTOS = ("cita_agendada", "control_agendado", "cita_reprogramada")
AVISO = "profesional_notificado"


@dataclass
class Par:
    caso: str
    tipo: str
    agendado: str
    avisado: str | None
    minutos: float | None
    enviado: bool | None
    por_cita: bool


def _momento(valor: Any) -> datetime | None:
    texto = str(valor or "")[:19].rstrip("Z")
    for formato in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def _detalle(evento: dict[str, Any]) -> dict[str, Any]:
    detalle = evento.get("detalle")
    if isinstance(detalle, str):
        try:
            detalle = json.loads(detalle)
        except ValueError:
            return {}
    return detalle if isinstance(detalle, dict) else {}


def emparejar(eventos: list[dict[str, Any]], desde: datetime | None = None) -> list[Par]:
    """Cada agendamiento con su aviso. Un aviso no se usa para dos agendamientos."""
    por_caso: dict[str, list[dict[str, Any]]] = {}
    for e in eventos:
        por_caso.setdefault(str(e.get("caso_id")), []).append(e)

    pares: list[Par] = []
    for caso, lista in por_caso.items():
        lista = sorted(lista, key=lambda e: _momento(e.get("creado_en")) or datetime.min)
        avisos = [e for e in lista if e.get("tipo") == AVISO]
        usados: set[int] = set()
        for e in lista:
            if e.get("tipo") not in AGENDAMIENTOS:
                continue
            cuando = _momento(e.get("creado_en"))
            if not cuando or (desde and cuando < desde):
                continue
            cita = _detalle(e).get("cita_id")
            elegido, por_cita = None, False
            if cita:
                for n, a in enumerate(avisos):
                    if n not in usados and _detalle(a).get("cita_id") == cita:
                        elegido, por_cita = n, True
                        break
            if elegido is None:
                # Filas viejas sin `cita_id`: el primer aviso libre desde ese minuto.
                for n, a in enumerate(avisos):
                    momento = _momento(a.get("creado_en"))
                    if n not in usados and momento and momento >= cuando:
                        elegido = n
                        break
            if elegido is None:
                pares.append(Par(caso[:8], str(e.get("tipo")), cuando.strftime("%Y-%m-%d %H:%M"), None, None, None, False))
                continue
            usados.add(elegido)
            aviso = avisos[elegido]
            momento = _momento(aviso.get("creado_en"))
            pares.append(Par(
                caso[:8], str(e.get("tipo")), cuando.strftime("%Y-%m-%d %H:%M"),
                momento.strftime("%Y-%m-%d %H:%M") if momento else None,
                round((momento - cuando).total_seconds() / 60, 1) if momento else None,
                _detalle(aviso).get("enviado"), por_cita,
            ))
    return sorted(pares, key=lambda p: p.agendado)


def generar_informe(pares: list[Par], desde: str) -> str:
    con_aviso = [p for p in pares if p.minutos is not None]
    salieron = [p for p in con_aviso if p.enviado]
    a_tiempo = [p for p in salieron if p.minutos <= LIMITE_MINUTOS]
    maximo = max((p.minutos for p in salieron), default=None)
    lineas = [
        "# Informe del aviso al profesional (M6) — CareSync",
        "",
        f"Generado el {datetime.now().strftime('%Y-%m-%d %H:%M')}, sobre la bitácora"
        + (f" desde el {desde}." if desde else " completa."),
        "",
        f"- **M6 — avisos que salieron en menos de {LIMITE_MINUTOS} min: {len(a_tiempo)} de {len(salieron)}** "
        f"(máximo: {maximo:g} min)." if salieron else "- **M6**: ningún aviso con el correo enviado en el período.",
        f"- Agendamientos: {len(pares)}. Con aviso registrado: {len(con_aviso)}. "
        f"Con el correo aceptado por SES: {len(salieron)}. "
        f"Sin correo (SES sin remitente, o destinatario sin verificar en sandbox): {len(con_aviso) - len(salieron)}.",
        "- Resolución de un minuto: «0» es el mismo minuto. Ver el docstring de `evaluar_aviso.py`.",
        "",
        "| Agendado (UTC) | Caso | Tipo | Aviso (UTC) | Minutos | Correo | Emparejado por |",
        "|---|---|---|---|:-:|:-:|---|",
    ]
    for p in pares:
        lineas.append(
            f"| {p.agendado} | {p.caso} | {p.tipo} | {p.avisado or '—'} | "
            f"{'—' if p.minutos is None else f'{p.minutos:g}'} | "
            f"{'sí' if p.enviado else ('no' if p.enviado is False else '—')} | "
            f"{'cita' if p.por_cita else 'caso y hora'} |"
        )
    lineas += [
        "",
        "## Llegada al buzón",
        "",
        "La salida la mide la bitácora; la llegada, el buzón del profesional. Se anota a mano",
        "la hora en que llegó cada correo con `[CareSync] Caso asignado` en el asunto",
        "(en Gmail, «Mostrar original» da la hora exacta de recepción).",
        "",
        "| Agendado (UTC) | Caso | Llegó al buzón (UTC) | Minutos desde el agendamiento |",
        "|---|---|---|:-:|",
        *(f"| {p.agendado} | {p.caso} | | |" for p in salieron),
    ]
    return "\n".join(lineas)


def main() -> None:
    analizador = argparse.ArgumentParser(description="M6: tiempo del aviso al profesional.")
    analizador.add_argument("--desde", default="", help="AAAA-MM-DD: sólo agendamientos desde ese día.")
    opciones = analizador.parse_args()

    cargar_entorno()
    email = os.environ.get("CARESYNC_EMAIL", "").strip()
    contrasena = os.environ.get("CARESYNC_PASSWORD", "")
    if not (email and contrasena):
        sys.exit("Falta la cuenta de prueba: CARESYNC_EMAIL y CARESYNC_PASSWORD en evaluacion/.env.")
    try:
        cuenta = Credencial.desde_contrasena(email, contrasena)
    except ErrorDeCuenta as exc:
        sys.exit(str(exc))

    r = cuenta._pedir("GET", f"{cuenta._datos}/read", params={"tableName": "eventos"})
    eventos = r.json() if r.status_code == 200 else []
    desde = datetime.strptime(opciones.desde, "%Y-%m-%d") if opciones.desde else None
    pares = emparejar([e for e in eventos if isinstance(e, dict)], desde)

    CRUDO_PATH.write_text(json.dumps([asdict(p) for p in pares], ensure_ascii=False, indent=2), encoding="utf-8")
    INFORME_PATH.write_text(generar_informe(pares, opciones.desde), encoding="utf-8")
    salieron = [p for p in pares if p.enviado and p.minutos is not None]
    print(f"{len(pares)} agendamientos; {len(salieron)} con correo; "
          f"{sum(p.minutos <= LIMITE_MINUTOS for p in salieron)} a tiempo. Informe en {INFORME_PATH.name}")


if __name__ == "__main__":
    main()
