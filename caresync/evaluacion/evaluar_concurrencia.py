"""
Evaluación de la concurrencia de reservas (M4) — CareSync
=========================================================

Mide la métrica M4 del segundo informe: **cero dobles reservas en 10 pares de
solicitudes simultáneas sobre el mismo cupo**, con 10 citas en firme y 10
alternativas.

ROBLE no tiene transacciones ni escrituras condicionales, así que la agenda se
protege con *reservar, releer y reconciliar* (`AccesoRoble.reservar_cupo`): cada
intento escribe un testigo propio en el cupo, vuelve a leer, y quien no encuentra su
testigo cede. Este script pone a competir dos casos por el mismo cupo, en el mismo
instante, y mira qué quedó escrito en ROBLE.

**Qué se ejecuta y contra qué.** Cada lado del par llama a
`agenda._reservar_y_confirmar`, la misma función que usan `agendar_cita` y
`reprogramar_cita` en la Lambda de herramientas, con su propio cliente de ROBLE y
contra la base real. Las dos llamadas arrancan juntas detrás de una barrera. No se
pasa por `/agente`: el modelo tarda segundos en decidir, así que dos conversaciones
nunca llegan a la reserva en el mismo instante, y la prueba mediría la ruta
secuencial («ese ya lo tomaron») y no la carrera. El árbitro de la carrera es ROBLE,
y ése sí es el real.

**Qué cuenta como doble reserva.** Dos citas `confirmada` sobre el mismo cupo. El
informe distingue además un estado **latente**: una cita confirmada sobre un cupo
que quedó `libre`, porque un tercero podría tomarlo después y entonces sí habría dos.

**Qué deja en ROBLE.** Dos casos de prueba de la cuenta de `evaluacion/.env`, con el
motivo «Evaluación M4», cerrados al terminar. Cada cita creada se cancela y su cupo
vuelve a `libre` antes del par siguiente. Los cupos se toman de los más lejanos del
centro, para no tocar los de los próximos días.

Requisitos: las dependencias de las Lambdas (`requests`, `boto3`, el SDK de ROBLE).

Uso:
    python evaluar_concurrencia.py                       # 10 pares en el CMU
    python evaluar_concurrencia.py --pares 2             # una prueba barata primero
    python evaluar_concurrencia.py --profesional a2a7bb08  # sólo cupos de ese profesional
    python evaluar_concurrencia.py --desfase-ms 150      # el segundo arranca 150 ms después
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cuenta_roble import ROBLE_CONTRATO, ROBLE_URL, ErrorDeCuenta, Credencial, cargar_entorno

RAIZ = Path(__file__).parent
LAMBDAS = RAIZ.parent / "lambdas"
INFORME_PATH = RAIZ / "informe_concurrencia.md"
CRUDO_PATH = RAIZ / "resultados_concurrencia.json"

MOTIVO = "Evaluación M4: concurrencia de reservas"
# Un par gasta unas 25 operaciones de ROBLE entre las dos carreras, la revisión y la
# limpieza, y el límite es de 100 por minuto y por IP: con menos pausa, los 429 de la
# segunda mitad se confundirían con fallos de la reserva.
PAUSA_ENTRE_PARES = 15.0
# El token de acceso de ROBLE dura unos 15 minutos; se renueva antes, con el refresco.
RENOVAR_CADA = 8 * 60
# Los cupos se toman a partir de aquí: ninguno que alguien pueda estar mirando ahora.
HORAS_DE_MARGEN = 3


def _preparar_lambdas() -> None:
    """Importa el código de las Lambdas como lo usa la de herramientas, sin SSM.

    En AWS la configuración sale de Parameter Store. Aquí se le dan los mismos dos
    valores públicos que usa `cuenta_roble` y nada más: sin remitente, no sale correo.
    """
    for ruta in (LAMBDAS / "comun", LAMBDAS / "herramientas"):
        if str(ruta) not in sys.path:
            sys.path.insert(0, str(ruta))
    os.environ.setdefault("SSM_PREFIJO", "/caresync/evaluacion")
    os.environ.setdefault("ENTORNO", "evaluacion")

    from caresync_comun import config as config_mod

    valores = {
        "base_url": os.environ.get("CARESYNC_ROBLE_URL") or ROBLE_URL,
        "contract_id": os.environ.get("CARESYNC_ROBLE_CONTRATO") or ROBLE_CONTRATO,
        "remitente": config_mod.RELLENO,
        "emergencias": config_mod.RELLENO,
    }
    config_mod._leer = lambda nombres, *, descifrar: {k: valores[k] for k in nombres}
    config_mod.config.cache_clear()


@dataclass
class Lado:
    caso: str
    resultado: str = ""  # cita | tomado | error
    detalle: str = ""
    alternativas: int = 0
    cita_id: str = ""
    ms: int = 0


@dataclass
class Par:
    numero: int
    cupo_id: str
    inicio: str
    a: Lado
    b: Lado
    confirmadas: int = 0
    estado_cupo: str = ""
    caso_del_cupo: str = ""
    doble: bool = False
    latente: bool = False
    en_firme: bool = False
    con_alternativas: bool = False
    limpieza: list[str] = field(default_factory=list)


def _competir(acceso_a, acceso_b, caso_a, caso_b, cupo, *, centro: str, desfase: float) -> tuple[Lado, Lado]:
    from caresync_comun.roble_acceso import fila_id
    import agenda

    barrera = threading.Barrier(2)
    lados = {"a": Lado(caso=str(fila_id(caso_a))), "b": Lado(caso=str(fila_id(caso_b)))}

    def intento(clave: str, acceso, caso, retraso: float) -> None:
        lado = lados[clave]
        barrera.wait()
        if retraso:
            time.sleep(retraso)
        t0 = time.perf_counter()
        try:
            cita, tomado = agenda._reservar_y_confirmar(acceso, caso=caso, centro=centro, cupo=cupo)
        except Exception as exc:  # noqa: BLE001 - se registra, no se oculta
            lado.resultado, lado.detalle = "error", f"{type(exc).__name__}: {exc}"[:200]
        else:
            if cita:
                lado.resultado, lado.cita_id = "cita", str(fila_id(cita))
            else:
                lado.resultado = "tomado"
                lado.detalle = str((tomado or {}).get("error") or "")[:200]
                lado.alternativas = len((tomado or {}).get("alternativas") or [])
        lado.ms = round((time.perf_counter() - t0) * 1000)

    hilos = [
        threading.Thread(target=intento, args=("a", acceso_a, caso_a, 0.0)),
        threading.Thread(target=intento, args=("b", acceso_b, caso_b, desfase)),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    return lados["a"], lados["b"]


def _revisar(acceso, par: Par) -> list[dict[str, Any]]:
    """Lo que quedó en ROBLE sobre el cupo: las citas confirmadas y el estado del cupo."""
    from caresync_comun.roble_acceso import CITA_CONFIRMADA, CUPO_CONFIRMADO, CUPO_LIBRE

    citas = acceso._leer("citas", {"cupo_id": par.cupo_id})
    nuestras = {par.a.caso, par.b.caso}
    confirmadas = [c for c in citas if c.get("estado") == CITA_CONFIRMADA and c.get("caso_id") in nuestras]
    cupo = acceso.cupo(par.cupo_id)

    par.confirmadas = len(confirmadas)
    par.estado_cupo = str(cupo.get("estado"))
    par.caso_del_cupo = str(cupo.get("caso_id") or "")
    par.doble = par.confirmadas > 1
    par.latente = par.confirmadas >= 1 and par.estado_cupo == CUPO_LIBRE
    par.en_firme = par.confirmadas == 1 and par.estado_cupo == CUPO_CONFIRMADO
    ganadores = [l for l in (par.a, par.b) if l.resultado == "cita"]
    perdedores = [l for l in (par.a, par.b) if l.resultado == "tomado" and l.alternativas]
    par.con_alternativas = len(ganadores) == 1 and len(perdedores) == 1
    return confirmadas


def _limpiar(acceso, par: Par, confirmadas: list[dict[str, Any]]) -> None:
    """Cancela las citas de la prueba y devuelve el cupo a la agenda."""
    from caresync_comun.roble_acceso import CUPO_LIBRE

    for cita in confirmadas:
        acceso.cancelar_cita(cita)
        par.limpieza.append(f"cita {str(cita.get('_id'))[:8]} cancelada")
    if acceso.cupo(par.cupo_id).get("estado") != CUPO_LIBRE:
        acceso.liberar_cupo(par.cupo_id)
        par.limpieza.append("cupo liberado")


def _cupos(acceso, *, centro: str, profesional: str, cuantos: int) -> list[dict[str, Any]]:
    from caresync_comun import reloj

    libres = acceso.cupos_libres(
        centro=centro, desde=reloj.ahora() + timedelta(hours=HORAS_DE_MARGEN), maximo=1000
    )
    if profesional:
        libres = [c for c in libres if str(c.get("profesional_id") or "").startswith(profesional)]
    # Los más lejanos: los cercanos son los que una persona real podría estar pidiendo.
    return list(reversed(libres))[:cuantos]


def _bogota(iso: str) -> str:
    t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone(timedelta(hours=-5))).strftime("%d/%m %H:%M")


def generar_informe(pares: list[Par], *, centro: str, desfase_ms: int) -> str:
    total = len(pares)
    dobles = sum(p.doble for p in pares)
    latentes = sum(p.latente for p in pares)
    firmes = sum(p.en_firme for p in pares)
    alternativas = sum(p.con_alternativas for p in pares)
    errores = sum((p.a.resultado == "error") + (p.b.resultado == "error") for p in pares)
    ninguna = sum(p.confirmadas == 0 for p in pares)

    lineas = [
        "# Informe de concurrencia de reservas (M4) — CareSync",
        "",
        f"Generado el {datetime.now().strftime('%Y-%m-%d %H:%M')}. Centro {centro}, "
        f"{total} pares, desfase del segundo intento {desfase_ms} ms.",
        "",
        f"- **Dobles reservas: {dobles} de {total}** (meta: 0).",
        f"- Citas en firme: {firmes} de {total} (meta: {total}).",
        f"- Pares en que el perdedor recibió alternativas: {alternativas} de {total} (meta: {total}).",
        f"- Citas sobre un cupo que quedó libre (doble reserva latente): {latentes}.",
        f"- Pares sin ninguna cita (los dos cedieron): {ninguna}.",
        f"- Intentos que terminaron en error y no en «ese ya lo tomaron»: {errores}.",
        "",
        "Cada par son dos casos de prueba compitiendo por el mismo cupo con",
        "`agenda._reservar_y_confirmar`, la función de la Lambda de herramientas, contra",
        "ROBLE real. Ver el docstring de `evaluar_concurrencia.py`.",
        "",
        "| Par | Cupo | A | B | Citas confirmadas | Cupo después | Resultado |",
        "|---|---|---|---|:-:|---|---|",
    ]

    def lado(l: Lado) -> str:
        if l.resultado == "cita":
            return f"cita ({l.ms} ms)"
        if l.resultado == "tomado":
            return f"tomado, {l.alternativas} alt. ({l.ms} ms)"
        return f"**error** ({l.ms} ms): {l.detalle}"

    for p in pares:
        if p.doble:
            veredicto = "❌ doble reserva"
        elif p.latente:
            veredicto = "⚠️ cita sobre cupo libre"
        elif p.en_firme and p.con_alternativas:
            veredicto = "✅"
        elif p.en_firme:
            veredicto = "⚠️ en firme, sin alternativas para el perdedor"
        else:
            veredicto = "⚠️ ninguna cita"
        lineas.append(
            f"| {p.numero} | {p.cupo_id[:8]} {_bogota(p.inicio)} | {lado(p.a)} | {lado(p.b)} | "
            f"{p.confirmadas} | {p.estado_cupo} | {veredicto} |"
        )
    lineas.append("")
    return "\n".join(lineas)


def main() -> None:
    analizador = argparse.ArgumentParser(description="M4: dobles reservas en pares simultáneos.")
    analizador.add_argument("--pares", type=int, default=10)
    analizador.add_argument("--centro", default="CMU")
    analizador.add_argument("--profesional", default="", help="Prefijo del profesional_id.")
    analizador.add_argument("--pausa", type=float, default=PAUSA_ENTRE_PARES)
    analizador.add_argument("--desfase-ms", type=int, default=0)
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

    _preparar_lambdas()
    from caresync_comun.roble_acceso import CASO_CANALIZADO, AccesoRoble, fila_id

    acceso = AccesoRoble.desde_token(cuenta.actual())
    casos = []
    for letra in ("A", "B"):
        caso = acceso.abrir_caso(motivo=f"{MOTIVO} ({letra})")
        acceso.actualizar_caso(
            str(fila_id(caso)), {"estado": CASO_CANALIZADO, "centro": opciones.centro, "nivel_urgencia": 3}
        )
        casos.append(acceso.caso(str(fila_id(caso))))
    print(f"Casos de prueba: {', '.join(str(fila_id(c))[:8] for c in casos)}")

    cupos = _cupos(acceso, centro=opciones.centro, profesional=opciones.profesional, cuantos=opciones.pares)
    if len(cupos) < opciones.pares:
        print(f"AVISO: sólo hay {len(cupos)} cupos libres con margen; se corren {len(cupos)} pares.")

    pares: list[Par] = []
    renovado = time.monotonic()
    try:
        for numero, cupo in enumerate(cupos, start=1):
            if time.monotonic() - renovado > RENOVAR_CADA:
                cuenta.renovar()
                acceso = AccesoRoble.desde_token(cuenta.actual())
                renovado = time.monotonic()
            # Un cliente por lado, como dos Lambdas: no comparten conexión ni sesión.
            lado_a = AccesoRoble.desde_token(cuenta.actual())
            lado_b = AccesoRoble.desde_token(cuenta.actual())
            a, b = _competir(
                lado_a, lado_b, casos[0], casos[1], cupo,
                centro=opciones.centro, desfase=opciones.desfase_ms / 1000,
            )
            par = Par(numero=numero, cupo_id=str(fila_id(cupo)), inicio=str(cupo.get("inicio")), a=a, b=b)
            time.sleep(1)  # que las dos escrituras ya estén en la base antes de leer
            confirmadas = _revisar(acceso, par)
            _limpiar(acceso, par, confirmadas)
            pares.append(par)
            print(
                f"[{numero}/{len(cupos)}] cupo {par.cupo_id[:8]} {_bogota(par.inicio)}: "
                f"A={a.resultado} B={b.resultado} confirmadas={par.confirmadas} "
                f"cupo={par.estado_cupo}{' DOBLE' if par.doble else ''}{' LATENTE' if par.latente else ''}"
            )
            if numero < len(cupos):
                time.sleep(opciones.pausa)
    finally:
        for caso in casos:
            if cuenta.cerrar_caso(str(fila_id(caso))):
                print(f"Caso {str(fila_id(caso))[:8]} cerrado.")
            else:
                print(f"AVISO: no se pudo cerrar el caso {str(fila_id(caso))[:8]}.")

    CRUDO_PATH.write_text(json.dumps([asdict(p) for p in pares], ensure_ascii=False, indent=2), encoding="utf-8")
    INFORME_PATH.write_text(
        generar_informe(pares, centro=opciones.centro, desfase_ms=opciones.desfase_ms), encoding="utf-8"
    )
    dobles = sum(p.doble for p in pares)
    print(f"\nDobles reservas: {dobles} de {len(pares)}. Informe en {INFORME_PATH.name}")


if __name__ == "__main__":
    main()
