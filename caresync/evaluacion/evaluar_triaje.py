"""
Evaluación del Agente de Triaje — CareSync
============================================

Corre el banco de casos de `casos_evaluacion.json` contra el endpoint real
(POST /agente) y mide el acierto según los criterios ya definidos en
protocolos/triaje-v0.md:

  - Ruteo CMU/CAE:      >= 85% de acierto (casos no-alarma)
  - Nivel de urgencia:  desacierto hacia arriba no cuenta como falla;
                        hacia abajo sí.
  - Señales de alarma:  100% deben terminar en escalar_urgencia, sin excepción.

DEPENDENCIA PENDIENTE CON ALEJANDRO: cada caso necesita un token de un
paciente de prueba de ROBLE. Si dos casos usan el MISMO token y el primer
caso no queda canalizado o escalado (osea sigue "abierto"), el segundo
mensaje CONTINÚA el primer caso en vez de abrir uno nuevo — contaminaría el
resultado. La forma segura es un token distinto por caso. Pregúntale a
Alejandro cómo generar ~40 usuarios de prueba (rol paciente) en ROBLE, o si
confirma que un caso ya canalizado/escalado sí libera al siguiente mensaje
para abrir uno nuevo, en cuyo caso un solo token alcanza.

Requisitos:
    pip install requests

Uso:
    export CARESYNC_API_URL="https://xxxx.execute-api.us-east-1.amazonaws.com"
    export CARESYNC_TOKENS_FILE="tokens.txt"   # un token por línea, mismo orden que los casos
    python evaluar_triaje.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

RAIZ = Path(__file__).parent
CASOS_PATH = RAIZ / "casos_evaluacion.json"
REPORTE_PATH = RAIZ / "informe_evaluacion.md"


@dataclass
class ResultadoCaso:
    id: str
    categoria: str
    mensaje: str
    ok: bool
    detalle: str
    crudo: dict[str, Any] = field(default_factory=dict)


def cargar_casos() -> list[dict[str, Any]]:
    return json.loads(CASOS_PATH.read_text(encoding="utf-8"))


def cargar_tokens(n_casos: int) -> list[str]:
    ruta = os.environ.get("CARESYNC_TOKENS_FILE", "")
    if ruta and Path(ruta).exists():
        tokens = [l.strip() for l in Path(ruta).read_text().splitlines() if l.strip()]
        if len(tokens) < n_casos:
            print(
                f"AVISO: hay {len(tokens)} tokens para {n_casos} casos. "
                "Los que falten reusan el último token (riesgo de contaminar el caso).",
                file=sys.stderr,
            )
            tokens += [tokens[-1]] * (n_casos - len(tokens))
        return tokens[:n_casos]

    token_unico = os.environ.get("CARESYNC_TOKEN", "")
    if not token_unico:
        sys.exit(
            "Falta CARESYNC_TOKENS_FILE (un token por caso) o CARESYNC_TOKEN "
            "(uno solo, para pruebas rápidas). Ver el docstring de este archivo."
        )
    print(
        "AVISO: usando un solo token para todos los casos. Si un caso no queda "
        "canalizado o escalado, el siguiente mensaje puede continuar el mismo "
        "caso en vez de abrir uno nuevo. Revisa informe_evaluacion.md con cuidado.",
        file=sys.stderr,
    )
    return [token_unico] * n_casos


def llamar_agente(api_url: str, token: str, mensaje: str) -> dict[str, Any]:
    respuesta = requests.post(
        f"{api_url.rstrip('/')}/agente",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        json={"mensaje": mensaje, "agente": "triaje"},
        timeout=45,
    )
    respuesta.raise_for_status()
    return respuesta.json()


def evaluar_caso(caso: dict[str, Any], cruda: dict[str, Any]) -> ResultadoCaso:
    acciones = cruda.get("acciones", [])
    escalo = any(a.get("herramienta") == "escalar_urgencia" and a.get("ok") for a in acciones)

    if caso.get("escalar_esperado"):
        ok = escalo
        detalle = "escaló correctamente" if ok else "NO escaló — falla crítica de seguridad"
        return ResultadoCaso(caso["id"], caso["categoria"], caso["mensaje"], ok, detalle, cruda)

    if escalo:
        return ResultadoCaso(
            caso["id"], caso["categoria"], caso["mensaje"], False,
            "escaló sin que el caso lo requiriera (sobre-derivación, revisar si es aceptable)",
            cruda,
        )

    centro_real = (cruda.get("caso") or {}).get("centro")
    nivel_real = (cruda.get("caso") or {}).get("nivel_urgencia")
    centro_esperado = caso.get("centro_esperado")
    nivel_esperado = caso.get("nivel_esperado")

    centro_ok = centro_esperado is None or centro_real == centro_esperado
    if nivel_esperado is None or nivel_real is None:
        nivel_ok = True
    else:
        # Desacierto hacia arriba (más urgente de lo esperado) no es falla,
        # es el sesgo deliberado del protocolo. Hacia abajo, sí.
        nivel_ok = int(nivel_real) <= int(nivel_esperado)

    ok = centro_ok and nivel_ok
    detalle = f"centro={centro_real} (esperado {centro_esperado}), nivel={nivel_real} (esperado {nivel_esperado})"
    return ResultadoCaso(caso["id"], caso["categoria"], caso["mensaje"], ok, detalle, cruda)


def generar_informe(resultados: list[ResultadoCaso]) -> str:
    alarma = [r for r in resultados if r.categoria.startswith("alarma_")]
    resto = [r for r in resultados if not r.categoria.startswith("alarma_")]

    acierto_alarma = sum(r.ok for r in alarma) / len(alarma) * 100 if alarma else 0
    acierto_resto = sum(r.ok for r in resto) / len(resto) * 100 if resto else 0

    lineas = [
        "# Informe de evaluación — Agente de Triaje",
        "",
        f"- Señales de alarma correctamente escaladas: **{acierto_alarma:.1f}%** "
        f"({sum(r.ok for r in alarma)}/{len(alarma)}) — objetivo: 100%",
        f"- Acierto de ruta/nivel en el resto de casos: **{acierto_resto:.1f}%** "
        f"({sum(r.ok for r in resto)}/{len(resto)}) — objetivo: >= 85%",
        "",
        "## Casos con falla",
        "",
    ]
    fallidos = [r for r in resultados if not r.ok]
    if not fallidos:
        lineas.append("Ninguno.")
    else:
        for r in fallidos:
            lineas.append(f"- **{r.id}** ({r.categoria}): {r.detalle}")
            lineas.append(f"  - Mensaje: _{r.mensaje}_")

    lineas += ["", "## Todos los casos", "", "| Id | Categoría | OK | Detalle |", "|---|---|---|---|"]
    for r in resultados:
        marca = "✅" if r.ok else "❌"
        lineas.append(f"| {r.id} | {r.categoria} | {marca} | {r.detalle} |")

    return "\n".join(lineas)


def main() -> None:
    api_url = os.environ.get("CARESYNC_API_URL", "")
    if not api_url:
        sys.exit("Falta CARESYNC_API_URL (la salida de Terraform del API Gateway).")

    casos = cargar_casos()
    tokens = cargar_tokens(len(casos))

    resultados: list[ResultadoCaso] = []
    for caso, token in zip(casos, tokens):
        print(f"-> {caso['id']}: {caso['mensaje'][:60]}...")
        try:
            cruda = llamar_agente(api_url, token, caso["mensaje"])
        except requests.RequestException as exc:
            resultados.append(
                ResultadoCaso(caso["id"], caso["categoria"], caso["mensaje"], False, f"error de red: {exc}")
            )
            continue
        resultados.append(evaluar_caso(caso, cruda))
        time.sleep(0.5)  # no saturar Bedrock

    informe = generar_informe(resultados)
    REPORTE_PATH.write_text(informe, encoding="utf-8")
    print(f"\nListo. Informe en {REPORTE_PATH}")


if __name__ == "__main__":
    main()
