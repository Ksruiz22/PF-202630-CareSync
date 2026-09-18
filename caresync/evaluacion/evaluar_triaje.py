"""
Evaluación del Agente de Triaje — CareSync
==========================================

Corre el banco de `casos_evaluacion.json` contra el endpoint real (POST /agente) y
mide el acierto según los criterios de `protocolos/triaje-v0.md`.

**Por qué la conversación es de varios turnos.** La primera versión de este script
mandaba un solo mensaje por caso y leía el centro de la respuesta. Medía mal, y en
contra del agente: el Paso 3 del protocolo le dice que pregunte hasta cinco veces
antes de canalizar, así que ante «tengo fiebre desde hace 4 días» lo correcto es
preguntar por las señales de alarma, no clasificar de una. El caso volvía sin
centro y contaba como falla cuando el agente había hecho justo lo que debía. Lo
único que sí se medía bien eran las señales de alarma, porque el Paso 0 manda
escalar de inmediato.

Ahora cada caso lleva un guion de respuestas y se conversa hasta que el agente
canaliza, escala, o se agota el guion. Las respuestas del guion están escritas para
cubrir varias preguntas probables a la vez («empezó hace 4 días y sigue igual, no
tengo dificultad para respirar ni rigidez en el cuello»), porque se envían a ciegas:
no sabemos qué va a preguntar el agente. Es el límite del enfoque, y es el precio de
que la medición sea determinista y repetible.

**Un token por caso.** Un caso canalizado NO queda cerrado, y `caso_abierto_de` sólo
excluye los cerrados, así que con un token compartido el segundo caso continúa el
hilo del primero. Hoy no hay ninguna ruta del sistema que escriba el estado
`cerrado`, de modo que no hay forma de liberar el token entre casos. Este script
detecta esa contaminación y excluye del porcentaje los casos afectados, en vez de
publicar un número que no significa nada.

**La cuota de ROBLE es el techo real.** Cada turno son del orden de diez
operaciones contra ROBLE (validar sesión, perfil, caso, historial, escribir el
mensaje, lo que hagan las herramientas, escribir la respuesta) y el límite es de
100 por minuto **por IP**. De ahí que la pausa entre turnos sea de 6 segundos por
omisión: con menos, la corrida se envenena sola con 429.

Requisitos:
    pip install requests

Uso:
    export CARESYNC_API_URL="https://ow2vz6k279.execute-api.us-east-1.amazonaws.com"
    export CARESYNC_TOKENS_FILE="tokens.txt"   # un token por línea, uno por caso
    python evaluar_triaje.py

    python evaluar_triaje.py --solo cmu-01,alarma-mental-01   # prueba barata
    python evaluar_triaje.py --desde-crudo                    # rehacer el informe sin llamar
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover
    # Sólo hace falta para hablar con el API. `--desde-crudo` rehace el informe a
    # partir de las transcripciones ya guardadas y tiene que funcionar en una
    # máquina sin el entorno montado: es justo lo que se hace cuando el número del
    # informe no cuadra y no se quiere volver a gastar cuota de ROBLE.
    requests = None  # type: ignore[assignment]

RAIZ = Path(__file__).parent
CASOS_PATH = RAIZ / "casos_evaluacion.json"
INFORME_PATH = RAIZ / "informe_evaluacion.md"
CRUDO_PATH = RAIZ / "resultados_crudos.json"

# Ver el encabezado: es la cuota de ROBLE, no una cortesía con Bedrock.
PAUSA_ENTRE_TURNOS = 6.0
MAX_TURNOS = 6
TIEMPO_ESPERA = 60

# Estados que sólo puede traer un caso heredado de otra corrida: si el primer
# turno ya llega con uno de estos, ese token no venía limpio.
ESTADOS_USADOS = {"canalizado", "agendado", "atendido", "en_seguimiento", "urgencia_escalada"}


# --------------------------------------------------------------------- modelo

@dataclass
class Turno:
    numero: int
    enviado: str
    respuesta: str = ""
    acciones: list[dict[str, Any]] = field(default_factory=list)
    caso_id: str = ""
    estado: str | None = None
    centro: str | None = None
    nivel: Any = None
    guardrail: bool = False
    error: str = ""

    @property
    def escalo(self) -> bool:
        return any(a.get("herramienta") == "escalar_urgencia" and a.get("ok") for a in self.acciones)

    @property
    def canalizo(self) -> bool:
        return any(a.get("herramienta") == "canalizar_caso" and a.get("ok") for a in self.acciones)


@dataclass
class Transcripcion:
    id: str
    categoria: str
    turnos: list[Turno] = field(default_factory=list)
    contaminado: bool = False
    motivo_contaminacion: str = ""

    @property
    def escalo_en(self) -> int | None:
        return next((t.numero for t in self.turnos if t.escalo), None)

    @property
    def canalizo_en(self) -> int | None:
        return next((t.numero for t in self.turnos if t.canalizo), None)

    @property
    def ultimo(self) -> Turno | None:
        return self.turnos[-1] if self.turnos else None

    @property
    def centro_final(self) -> str | None:
        for turno in reversed(self.turnos):
            if turno.centro:
                return str(turno.centro)
        return None

    @property
    def nivel_final(self) -> int | None:
        for turno in reversed(self.turnos):
            if turno.nivel not in (None, ""):
                try:
                    return int(turno.nivel)
                except (TypeError, ValueError):
                    return None
        return None

    @property
    def guardrail_intervino(self) -> bool:
        return any(t.guardrail for t in self.turnos)

    @property
    def error_de_red(self) -> str:
        return next((t.error for t in self.turnos if t.error), "")


@dataclass
class Resultado:
    id: str
    categoria: str
    ok: bool
    detalle: str
    turnos_usados: int
    contaminado: bool = False
    motivo_contaminacion: str = ""
    # Un nivel más urgente de lo esperado no es falla (Paso 2), pero se cuenta.
    sobre_urgencia: bool = False
    # Un nivel menos urgente sí lo es, y el protocolo pide documentarlo uno a uno.
    sub_urgencia: bool = False
    sobre_escalamiento: bool = False
    guardrail: bool = False


# ------------------------------------------------------------------- entradas

def cargar_casos(filtro: str = "") -> list[dict[str, Any]]:
    casos = json.loads(CASOS_PATH.read_text(encoding="utf-8"))
    if not filtro:
        return casos
    querido = {p.strip() for p in filtro.split(",") if p.strip()}
    elegidos = [c for c in casos if c["id"] in querido or c["categoria"] in querido]
    if not elegidos:
        sys.exit(f"Ningún caso coincide con «{filtro}». Ids y categorías válidos en {CASOS_PATH.name}.")
    return elegidos


def cargar_tokens(n_casos: int) -> list[str]:
    ruta = os.environ.get("CARESYNC_TOKENS_FILE", "")
    if ruta and Path(ruta).exists():
        tokens = [l.strip() for l in Path(ruta).read_text(encoding="utf-8").splitlines() if l.strip()]
        if not tokens:
            sys.exit(f"{ruta} está vacío.")
        if len(tokens) < n_casos:
            print(
                f"AVISO: {len(tokens)} tokens para {n_casos} casos. Los que falten reusan el "
                "último, y esos casos van a quedar marcados como contaminados.",
                file=sys.stderr,
            )
            tokens += [tokens[-1]] * (n_casos - len(tokens))
        return tokens[:n_casos]

    token_unico = os.environ.get("CARESYNC_TOKEN", "")
    if not token_unico:
        sys.exit(
            "Falta CARESYNC_TOKENS_FILE (un token por caso) o CARESYNC_TOKEN (uno solo, "
            "para una prueba rápida con --solo). Ver el encabezado de este archivo."
        )
    if n_casos > 1:
        print(
            "AVISO: un solo token para varios casos. Sólo el primero es válido; el resto "
            "continuará el mismo caso y quedará marcado como contaminado.",
            file=sys.stderr,
        )
    return [token_unico] * n_casos


# ------------------------------------------------------------------ transporte

def llamar_agente(
    api_url: str, token: str, mensaje: str, caso_id: str = "", *, intentos: int = 3
) -> dict[str, Any]:
    """Un turno contra POST /agente, con reintento ante saturación.

    El 429 de ROBLE llega hasta aquí como un 502 (`ErrorDeDatos`), así que los dos
    se reintentan con espera creciente. Un 401 no se reintenta: el token no se
    arregla solo.
    """
    if requests is None:
        sys.exit("Falta la dependencia «requests» para hablar con el API: pip install requests")

    cuerpo: dict[str, Any] = {"mensaje": mensaje, "agente": "triaje"}
    if caso_id:
        cuerpo["caso_id"] = caso_id

    ultimo_fallo = ""
    for intento in range(1, intentos + 1):
        try:
            respuesta = requests.post(
                f"{api_url.rstrip('/')}/agente",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                json=cuerpo,
                timeout=TIEMPO_ESPERA,
            )
        except requests.RequestException as exc:
            ultimo_fallo = f"red: {type(exc).__name__}"
        else:
            if respuesta.status_code == 200:
                return respuesta.json()
            if respuesta.status_code == 401:
                raise SystemExit(
                    "401: ROBLE rechazó el token. Está vencido o no es de este contrato. "
                    "Los tokens de acceso de ROBLE son de vida corta: vuelve a generarlos."
                )
            ultimo_fallo = f"HTTP {respuesta.status_code}: {respuesta.text[:200]}"
            if respuesta.status_code not in (429, 502, 503, 504):
                break

        if intento < intentos:
            espera = 10 * intento
            print(f"   reintento {intento}/{intentos - 1} en {espera}s ({ultimo_fallo})", file=sys.stderr)
            time.sleep(espera)

    return {"_error": ultimo_fallo}


# ------------------------------------------------------------------ conversar

def conversar_caso(
    api_url: str, token: str, caso: dict[str, Any], *, pausa: float, max_turnos: int
) -> Transcripcion:
    """Conversa hasta que el agente resuelva el triaje o se agote el guion.

    Para en cuanto escala o canaliza: es lo que hace el agente de verdad —el Paso 0
    dice que al escalar deja de recolectar, y tras canalizar el caso pasa a agenda—,
    así que seguir hablando mediría a otro agente.
    """
    transcripcion = Transcripcion(id=caso["id"], categoria=caso["categoria"])
    guion: list[str] = list(caso.get("respuestas") or [])
    mensajes = [caso["mensaje"], *guion][:max_turnos]
    caso_id = ""

    for numero, texto in enumerate(mensajes, start=1):
        if numero > 1:
            time.sleep(pausa)

        cruda = llamar_agente(api_url, token, texto, caso_id)
        turno = Turno(numero=numero, enviado=texto)

        if "_error" in cruda:
            turno.error = str(cruda["_error"])
            transcripcion.turnos.append(turno)
            break

        datos_caso = cruda.get("caso") or {}
        turno.respuesta = str(cruda.get("respuesta") or "")
        turno.acciones = list(cruda.get("acciones") or [])
        turno.caso_id = str(datos_caso.get("id") or "")
        turno.estado = datos_caso.get("estado")
        turno.centro = datos_caso.get("centro")
        turno.nivel = datos_caso.get("nivel_urgencia")
        turno.guardrail = bool(cruda.get("salvaguardas_intervinieron"))
        transcripcion.turnos.append(turno)

        if numero == 1:
            caso_id = turno.caso_id
            # El caso llega usado: este token arrastra un caso de otra corrida o de
            # otro caso del banco, y lo que se mida aquí no es de este caso.
            if turno.estado in ESTADOS_USADOS:
                transcripcion.contaminado = True
                transcripcion.motivo_contaminacion = (
                    f"el primer turno ya llegó en estado «{turno.estado}»"
                )

        if turno.escalo or turno.canalizo:
            break

    return transcripcion


def marcar_casos_compartidos(transcripciones: list[Transcripcion]) -> None:
    """Marca los casos que acabaron sobre el mismo `caso_id` de ROBLE.

    Es la otra cara de la contaminación: no que el caso llegara usado, sino que dos
    casos del banco terminaron escribiendo en el mismo hilo por compartir token.
    """
    visto: dict[str, str] = {}
    for transcripcion in transcripciones:
        primero = transcripcion.turnos[0] if transcripcion.turnos else None
        if not primero or not primero.caso_id:
            continue
        duenio = visto.get(primero.caso_id)
        if duenio is None:
            visto[primero.caso_id] = transcripcion.id
        elif not transcripcion.contaminado:
            transcripcion.contaminado = True
            transcripcion.motivo_contaminacion = f"comparte el caso de ROBLE con «{duenio}»"


# -------------------------------------------------------------------- evaluar

def evaluar(caso: dict[str, Any], t: Transcripcion) -> Resultado:
    base = dict(
        id=t.id,
        categoria=t.categoria,
        turnos_usados=len(t.turnos),
        contaminado=t.contaminado,
        motivo_contaminacion=t.motivo_contaminacion,
        guardrail=t.guardrail_intervino,
    )

    if t.error_de_red:
        return Resultado(ok=False, detalle=f"no se pudo completar — {t.error_de_red}", **base)

    if caso.get("escalar_esperado"):
        return _evaluar_alarma(t, base)
    if caso.get("centro_esperado") is None:
        return _evaluar_orientacion(t, base)
    return _evaluar_ruteo(caso, t, base)


def _evaluar_alarma(t: Transcripcion, base: dict[str, Any]) -> Resultado:
    """Paso 0: escalar, y escalar *antes* de clasificar.

    El criterio de aceptación es explícito en que no basta con que escale: dice
    «sin que el agente intente clasificar el nivel o el centro primero». Canalizar
    y después escalar es una falla, aunque el escalamiento acabe ocurriendo.
    """
    if t.escalo_en is None:
        return Resultado(ok=False, detalle="NO escaló — falla crítica de seguridad", **base)

    if t.canalizo_en is not None and t.canalizo_en < t.escalo_en:
        return Resultado(
            ok=False,
            detalle=f"escaló en el turno {t.escalo_en} pero clasificó antes (turno {t.canalizo_en})",
            **base,
        )

    if t.escalo_en > 1:
        return Resultado(
            ok=True,
            detalle=f"escaló en el turno {t.escalo_en}, no en el primero — revisar",
            **base,
        )
    return Resultado(ok=True, detalle="escaló en el primer turno", **base)


def _evaluar_orientacion(t: Transcripcion, base: dict[str, Any]) -> Resultado:
    """Nivel 4: una duda administrativa no se escala.

    No se exige que canalice ni a qué centro: el Paso 2 dice «sin cita». Lo único
    que se mide es que no active la ruta de emergencia por una pregunta de trámite,
    que es el único error posible aquí. La versión anterior de este archivo daba
    estos dos casos por buenos siempre, con cualquier salida.
    """
    if t.escalo_en is not None:
        return Resultado(
            ok=False,
            detalle=f"escaló una consulta administrativa (turno {t.escalo_en})",
            sobre_escalamiento=True,
            **base,
        )
    destino = f"canalizó a {t.centro_final} nivel {t.nivel_final}" if t.centro_final else "no canalizó"
    return Resultado(ok=True, detalle=f"no escaló; {destino}", **base)


def _evaluar_ruteo(caso: dict[str, Any], t: Transcripcion, base: dict[str, Any]) -> Resultado:
    centro_esperado = caso["centro_esperado"]
    nivel_esperado = caso.get("nivel_esperado")

    if t.escalo_en is not None:
        return Resultado(
            ok=False,
            detalle=f"escaló sin señal de alarma en el caso (turno {t.escalo_en}) — sobre-derivación",
            sobre_escalamiento=True,
            **base,
        )

    if t.centro_final is None:
        return Resultado(
            ok=False,
            detalle=f"no canalizó en {len(t.turnos)} turnos (el Paso 3 admite hasta 5 preguntas)",
            **base,
        )

    centro_ok = t.centro_final == centro_esperado
    nivel_real = t.nivel_final
    sobre = sub = False
    nivel_ok = True

    if nivel_esperado is not None and nivel_real is not None:
        # El número bajo es el urgente: 1 emergencia … 4 orientación. Equivocarse
        # hacia arriba (más urgente) es el sesgo deliberado del Paso 2 y no cuenta
        # como falla; hacia abajo sí, y el protocolo pide listarlo caso por caso.
        sobre = nivel_real < nivel_esperado
        sub = nivel_real > nivel_esperado
        nivel_ok = not sub

    detalle = (
        f"centro {t.centro_final} (esperado {centro_esperado}), "
        f"nivel {nivel_real} (esperado {nivel_esperado})"
    )
    if sobre:
        detalle += " — más urgente de lo esperado, admitido por el Paso 2"
    if sub:
        detalle += " — MENOS urgente de lo esperado"

    return Resultado(
        ok=centro_ok and nivel_ok, detalle=detalle, sobre_urgencia=sobre, sub_urgencia=sub, **base
    )


# -------------------------------------------------------------------- informe

def _porcentaje(parte: int, total: int) -> str:
    return f"{parte / total * 100:.1f}%" if total else "sin datos"


def generar_informe(resultados: list[Resultado]) -> str:
    validos = [r for r in resultados if not r.contaminado]
    contaminados = [r for r in resultados if r.contaminado]

    alarma = [r for r in validos if r.categoria.startswith("alarma_")]
    resto = [r for r in validos if not r.categoria.startswith("alarma_")]

    ok_alarma = sum(r.ok for r in alarma)
    ok_resto = sum(r.ok for r in resto)

    lineas = [
        "# Informe de evaluación — Agente de Triaje",
        "",
        f"Generado el {time.strftime('%Y-%m-%d %H:%M')} (hora local de la máquina que lo corrió).",
        "",
        "Los criterios son los de `protocolos/triaje-v0.md`. La conversación es de varios",
        "turnos: cada caso lleva un guion de respuestas y se habla hasta que el agente",
        "canaliza, escala, o se agota el guion.",
        "",
        "## Resultado",
        "",
        "| Criterio | Objetivo | Resultado |",
        "|---|---|---|",
        f"| Señales de alarma escaladas | 100% | **{_porcentaje(ok_alarma, len(alarma))}** ({ok_alarma}/{len(alarma)}) |",
        f"| Ruta y nivel en el resto | ≥ 85% | **{_porcentaje(ok_resto, len(resto))}** ({ok_resto}/{len(resto)}) |",
        "",
    ]

    if contaminados:
        cuantos = (
            "1 caso quedó fuera" if len(contaminados) == 1 else f"{len(contaminados)} casos quedaron fuera"
        )
        lineas += [
            f"> **{cuantos} del cálculo por contaminación de token.**",
            "> Un caso canalizado no queda cerrado, así que un token reutilizado continúa el",
            "> hilo anterior en vez de abrir uno nuevo. Están listados al final.",
            "",
        ]

    sub = [r for r in validos if r.sub_urgencia]
    lineas += ["## Desaciertos de nivel hacia abajo", ""]
    if sub:
        lineas.append("El protocolo pide documentarlos uno a uno. Son los que importan:")
        lineas.append("")
        lineas += [f"- **{r.id}** ({r.categoria}): {r.detalle}" for r in sub]
    else:
        lineas.append("Ninguno. Ningún caso recibió menos urgencia de la esperada.")
    lineas.append("")

    sobre_nivel = [r for r in validos if r.sobre_urgencia]
    sobre_esc = [r for r in validos if r.sobre_escalamiento]
    lineas += [
        "## Sobre-derivación",
        "",
        f"- Nivel más urgente de lo esperado: **{len(sobre_nivel)}** casos. No cuentan como falla;",
        "  es el sesgo deliberado del Paso 2 y lo que la literatura describe para este tipo",
        "  de sistema.",
        f"- Ruta de emergencia activada sin señal de alarma: **{len(sobre_esc)}** casos. Estos sí",
        "  cuentan como falla: escalar no es subir un nivel, es mandar a alguien a urgencias.",
        "",
    ]
    if sobre_esc:
        lineas += [f"  - **{r.id}**: {r.detalle}" for r in sobre_esc] + [""]

    guardrail = [r for r in resultados if r.guardrail]
    if guardrail:
        lineas += [
            "## Intervenciones de las salvaguardas",
            "",
            "El guardrail cortó la respuesta en estos casos. En un caso clínico legítimo eso",
            "es un falso positivo y hay que revisarlo en `infra/bedrock.tf`:",
            "",
        ] + [f"- **{r.id}** ({r.categoria})" for r in guardrail] + [""]

    fallidos = [r for r in validos if not r.ok]
    lineas += ["## Casos con falla", ""]
    if fallidos:
        lineas += [f"- **{r.id}** ({r.categoria}, {r.turnos_usados} turnos): {r.detalle}" for r in fallidos]
    else:
        lineas.append("Ninguno.")
    lineas.append("")

    lineas += ["## Todos los casos", "", "| Id | Categoría | Turnos | OK | Detalle |", "|---|---|--:|:-:|---|"]
    for r in resultados:
        marca = "—" if r.contaminado else ("✅" if r.ok else "❌")
        lineas.append(f"| {r.id} | {r.categoria} | {r.turnos_usados} | {marca} | {r.detalle} |")
    lineas.append("")

    if contaminados:
        lineas += [
            "## Casos excluidos por contaminación",
            "",
            "Lo que midieron no es de este caso, así que no entra en el porcentaje.",
            "",
        ]
        lineas += [
            f"- **{r.id}**: {r.motivo_contaminacion or 'token reutilizado'}. "
            f"Lo que se observó: {r.detalle}"
            for r in contaminados
        ]
        lineas.append("")

    lineas += [
        "## Cómo leer esto",
        "",
        "El banco es sintético y lo escribió el equipo de desarrollo, que no tiene personal",
        "de salud. Un acierto aquí significa que el agente sigue el protocolo que se le dio,",
        "no que el protocolo sea clínicamente correcto. Esa validación sigue pendiente.",
        "",
    ]
    return "\n".join(lineas)


# ----------------------------------------------------------------------- main

def _guardar_crudo(transcripciones: list[Transcripcion]) -> None:
    CRUDO_PATH.write_text(
        json.dumps([asdict(t) for t in transcripciones], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _leer_crudo() -> list[Transcripcion]:
    if not CRUDO_PATH.exists():
        sys.exit(f"No hay {CRUDO_PATH.name}. Corre la evaluación al menos una vez.")
    crudo = json.loads(CRUDO_PATH.read_text(encoding="utf-8"))
    return [
        Transcripcion(
            id=t["id"],
            categoria=t["categoria"],
            turnos=[Turno(**turno) for turno in t["turnos"]],
            contaminado=t.get("contaminado", False),
            motivo_contaminacion=t.get("motivo_contaminacion", ""),
        )
        for t in crudo
    ]


def main() -> None:
    analizador = argparse.ArgumentParser(description="Evalúa el agente de triaje de CareSync.")
    analizador.add_argument("--solo", default="", help="Ids o categorías separados por coma.")
    analizador.add_argument("--pausa", type=float, default=PAUSA_ENTRE_TURNOS,
                            help="Segundos entre turnos. Bajarla arriesga el 429 de ROBLE.")
    analizador.add_argument("--max-turnos", type=int, default=MAX_TURNOS)
    analizador.add_argument("--desde-crudo", action="store_true",
                            help="Rehace el informe desde resultados_crudos.json, sin llamar al API.")
    opciones = analizador.parse_args()

    casos = cargar_casos(opciones.solo)
    por_id = {c["id"]: c for c in casos}

    if opciones.desde_crudo:
        transcripciones = [t for t in _leer_crudo() if t.id in por_id or not opciones.solo]
    else:
        api_url = os.environ.get("CARESYNC_API_URL", "")
        if not api_url:
            sys.exit("Falta CARESYNC_API_URL (la salida `api_url` de Terraform).")
        tokens = cargar_tokens(len(casos))

        print(f"{len(casos)} casos, hasta {opciones.max_turnos} turnos, {opciones.pausa}s entre turnos.")
        print(f"Peor caso: ~{sum(1 + len(c.get('respuestas') or []) for c in casos) * opciones.pausa / 60:.0f} min.\n")

        transcripciones = []
        for indice, (caso, token) in enumerate(zip(casos, tokens), start=1):
            print(f"[{indice}/{len(casos)}] {caso['id']}: {caso['mensaje'][:58]}...")
            t = conversar_caso(api_url, token, caso,
                               pausa=opciones.pausa, max_turnos=opciones.max_turnos)
            transcripciones.append(t)

            if t.error_de_red:
                print(f"    ERROR: {t.error_de_red}")
            elif t.escalo_en:
                print(f"    escaló en el turno {t.escalo_en}")
            elif t.centro_final:
                print(f"    canalizó a {t.centro_final} nivel {t.nivel_final} en {len(t.turnos)} turnos")
            else:
                print(f"    sin canalizar tras {len(t.turnos)} turnos")

            if indice < len(casos):
                time.sleep(opciones.pausa)

        marcar_casos_compartidos(transcripciones)
        _guardar_crudo(transcripciones)
        print(f"\nTranscripciones en {CRUDO_PATH.name}.")

    resultados = [evaluar(por_id[t.id], t) for t in transcripciones if t.id in por_id]
    INFORME_PATH.write_text(generar_informe(resultados), encoding="utf-8")

    validos = [r for r in resultados if not r.contaminado]
    alarma = [r for r in validos if r.categoria.startswith("alarma_")]
    resto = [r for r in validos if not r.categoria.startswith("alarma_")]
    print(f"\nAlarmas: {_porcentaje(sum(r.ok for r in alarma), len(alarma))} (objetivo 100%)")
    print(f"Ruta y nivel: {_porcentaje(sum(r.ok for r in resto), len(resto))} (objetivo >=85%)")
    if len(validos) < len(resultados):
        print(f"Excluidos por contaminación: {len(resultados) - len(validos)}")
    print(f"Informe en {INFORME_PATH.name}")


if __name__ == "__main__":
    main()
