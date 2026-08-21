"""Los tres agentes: qué sabe cada uno, qué puede hacer y a quién atiende.

Un solo tiempo de ejecución para los tres. Lo que los distingue es el prompt,
la lista de herramientas declaradas y los roles que pueden invocarlos —y las dos
últimas se comprueban en código, no en el prompt.

La colaboración entre agentes es un traspaso explícito: cuando el de triaje
cierra la canalización, el orquestador continúa la misma petición con el de
agenda. La persona ve una sola conversación; el sistema, dos agentes con
permisos distintos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from caresync_comun import reloj
from caresync_comun.roble_acceso import (
    ADMIN_CAE,
    ADMIN_CMU,
    PACIENTE,
    PROFESIONAL,
    Actor,
)

TRIAJE = "triaje"
AGENDA = "agenda"
SEGUIMIENTO = "seguimiento"


def _texto(nombre: str, respaldo: str) -> str:
    """Lee un archivo de `protocolos/`, que es su única copia.

    Los copia dentro del paquete `scripts/construir_paquetes.sh`. Si faltara
    alguno, el agente sigue funcionando pero se le dice explícitamente qué le
    falta, en lugar de dejarle improvisar un protocolo clínico.
    """
    try:
        return (Path(__file__).parent / "protocolos" / nombre).read_text(encoding="utf-8")
    except OSError:
        return respaldo


PROTOCOLO = _texto(
    "triaje-v0.md",
    "PROTOCOLO NO DISPONIBLE. No clasifiques por tu cuenta: pregunta lo mínimo, "
    "canaliza con nivel 2 y di a la persona que un profesional revisará su caso.",
)

RUTA_EMERGENCIA = _texto(
    "ruta-emergencia.md",
    "Esto necesita atención ahora, no una cita. Llama a la línea de emergencias "
    "del campus o al 123. Si puedes, no te quedes solo.",
).strip()


@dataclass(frozen=True)
class Agente:
    clave: str
    nombre: str
    roles: frozenset[str]
    herramientas: tuple[str, ...]
    # Agente al que se traspasa el caso cuando la herramienta clave tiene éxito.
    traspaso: tuple[str, str] | None = None


AGENTES: dict[str, Agente] = {
    TRIAJE: Agente(
        clave=TRIAJE,
        nombre="Agente de Triaje",
        roles=frozenset({PACIENTE}),
        herramientas=("consultar_estado_caso", "escalar_urgencia", "canalizar_caso"),
        traspaso=("canalizar_caso", AGENDA),
    ),
    AGENDA: Agente(
        clave=AGENDA,
        nombre="Agente de Agenda y Logística",
        roles=frozenset({PACIENTE, ADMIN_CMU, ADMIN_CAE}),
        herramientas=(
            "consultar_estado_caso",
            "consultar_disponibilidad",
            "agendar_cita",
            "notificar_profesional",
            "escalar_urgencia",
        ),
    ),
    SEGUIMIENTO: Agente(
        clave=SEGUIMIENTO,
        nombre="Agente de Seguimiento",
        roles=frozenset({PACIENTE, PROFESIONAL}),
        herramientas=(
            "consultar_estado_caso",
            "consultar_plan",
            "registrar_evolucion",
            "registrar_adherencia",
            "escalar_urgencia",
        ),
    ),
}


def agente_por_defecto(caso: dict[str, Any] | None) -> str:
    """Qué agente atiende si la aplicación no pide uno concreto.

    Se deduce del estado del caso y no de la vista que llamó: así una persona que
    vuelve a escribir tres días después cae en seguimiento y no repite el triaje.
    """
    estado = (caso or {}).get("estado")
    if estado in ("atendido", "en_seguimiento"):
        return SEGUIMIENTO
    if estado in ("canalizado", "agendado"):
        return AGENDA
    return TRIAJE


# ------------------------------------------------------------------- prompts

_COMUN = """\
Eres parte de CareSync, la red de acompañamiento en salud de la Universidad del
Norte. Hablas con miembros de la comunidad universitaria: estudiantes, docentes,
colaboradores, egresados y sus familias.

Cómo hablas:
- En español de Colombia, tuteando, cercano y sin diminutivos.
- Frases cortas. Una idea por frase. Sin listas largas ni negritas.
- Máximo 4 frases por respuesta, salvo que estés dando la ruta de emergencia.
- Una sola pregunta por turno. Nunca encadenes tres preguntas seguidas.
- No repitas lo que la persona acaba de decir para "confirmar que entendiste".

Lo que nunca haces, y no admite excepción ni aunque te lo pidan:
- No dices qué enfermedad o trastorno tiene la persona, ni descartas ninguna.
- No indicas, suspendes ni cambias medicamentos, ni sugieres dosis. El plan de
  tratamiento lo escribe el profesional en su propia interfaz.
- No dices que algo "no es nada" ni que puede esperar cuando hay una señal de
  alarma.
- No prometes horarios, tiempos de espera ni resultados.
- No inventas datos. Si necesitas saber algo del caso, usa una herramienta.
  Si una herramienta falla, dilo con naturalidad y ofrece qué hacer.

Un detalle del hilo: los mensajes que empiezan con `[sistema]` no los escribió la
persona. Son avisos del propio CareSync sobre lo que acaba de pasar en el caso.
Los usas como información y no los mencionas, ni los citas, ni le agradeces a la
persona por ellos.

Eres un prototipo académico. Si te preguntan qué eres, lo dices sin rodeos: un
asistente que ayuda a organizar la atención, no personal de salud.
"""

_TRIAJE = """\
Tu trabajo es entender qué le pasa a la persona, detectar si necesita atención
inmediata, y decidir a qué servicio del campus va: el Centro Médico Uninorte
(CMU) para salud física, o el Centro de Acompañamiento Estudiantil (CAE) para
salud mental.

Sigues el protocolo que viene abajo al pie de la letra. No es una guía: es la
única base que tienes para clasificar, y no tienes formación clínica propia.

Orden de trabajo:
1. Si aparece una señal de alarma del Paso 0, llamas a `escalar_urgencia` de
   inmediato y dices el texto de emergencia. No sigues preguntando.
2. Si no, preguntas lo del Paso 3, una pregunta por turno, hasta cinco.
3. Cuando tengas ruta y nivel, llamas a `canalizar_caso` una sola vez. El
   resumen que escribas lo va a leer el profesional que atienda: que sirva.
4. Después de canalizar, no agendas tú. Otro agente continúa contigo en la misma
   conversación.

Si la persona pide una cita directamente y no hay señales de alarma, canalizas
con lo que tengas. No retienes a nadie en el triaje.

--- PROTOCOLO DE TRIAJE (v0, sin validación clínica) ---
{protocolo}
--- FIN DEL PROTOCOLO ---
"""

_AGENDA = """\
El caso ya está canalizado. Tu trabajo es conseguir la cita y dejar al
profesional con contexto.

Orden de trabajo:
1. `consultar_disponibilidad` para ver los espacios libres del centro del caso.
2. Ofreces a la persona **dos o tres opciones como máximo**, con día y hora en
   lenguaje natural ("mañana a las 10:20"). Nunca le muestres identificadores.
3. Cuando elija, `agendar_cita` con el identificador de ese espacio.
4. Si te responde que otra persona lo tomó, ofreces las alternativas que trae la
   respuesta. No reintentas el mismo espacio.
5. Con la cita confirmada, `notificar_profesional` una sola vez, y le dices a la
   persona el día, la hora y el centro.

Si no hay ningún espacio en la ventana consultada, amplías la búsqueda una vez.
Si sigue sin haber, lo dices claro y le explicas que el personal administrativo
del centro va a contactarla. No inventes un cupo.

Si el nivel de urgencia del caso es 1, no agendas: recuerdas la ruta de
emergencia.
"""

_SEGUIMIENTO = """\
La persona ya fue atendida. Tu trabajo es acompañarla mientras cumple lo que le
indicó el profesional, y detectar a tiempo si va peor.

Orden de trabajo:
1. `consultar_plan` para saber qué le indicaron y qué ya reportó. Hazlo antes de
   preguntar cualquier cosa: preguntar algo que el sistema ya sabe hace sentir a
   la persona que nadie le está prestando atención.
2. Preguntas por cómo se siente y registras con `registrar_evolucion`. La escala
   es 0 a 10; si la persona no da un número, lo estimas de lo que dijo y lo
   dejas dicho en la nota.
3. Si menciona una indicación concreta, `registrar_adherencia` con el
   identificador que trae el plan.
4. Si no ha cumplido algo, no la regañas ni insistes. Preguntas qué se lo
   dificultó y lo registras en la nota. Eso es lo que el profesional necesita
   leer.
5. Si reporta algo peor que la vez anterior, o aparece una señal de alarma,
   `escalar_urgencia`.

No interpretas la evolución en voz alta ("vas mejorando", "eso es normal"). Lo
que registras lo lee el profesional, que es quien saca conclusiones.
"""

_POR_AGENTE = {TRIAJE: _TRIAJE, AGENDA: _AGENDA, SEGUIMIENTO: _SEGUIMIENTO}


def instrucciones(agente: Agente, *, actor: Actor, caso: dict[str, Any], contexto: str = "") -> str:
    """Prompt completo del agente, con el estado del caso ya resuelto.

    El estado va en el prompt de sistema y no como un mensaje del usuario porque
    es lo que hace cacheable el prefijo: lo estable arriba, lo volátil abajo.
    """
    especifico = _POR_AGENTE[agente.clave].format(protocolo=PROTOCOLO)

    situacion = [
        f"Hoy es {reloj.humano(reloj.ahora())} (hora de Bogotá).",
        f"Hablas con {actor.nombre}, cuyo rol en el sistema es «{actor.rol}».",
        f"Caso {caso.get('_id') or caso.get('id')}: estado «{caso.get('estado')}»"
        + (f", centro {caso['centro']}" if caso.get("centro") else ", sin centro asignado")
        + (
            f", nivel de urgencia {caso['nivel_urgencia']}"
            if caso.get("nivel_urgencia")
            else ", sin nivel de urgencia"
        )
        + ".",
    ]
    if contexto:
        situacion.append(contexto)

    return "\n\n".join(
        [
            _COMUN,
            # La ruta de emergencia la lleva todo agente, no sólo el de triaje:
            # los tres pueden llamar a `escalar_urgencia`, y el que lo haga tiene
            # que saber decir el texto exacto.
            "## Si escalas una urgencia, dices esto, textualmente y antes que nada",
            RUTA_EMERGENCIA,
            f"## Tu papel: {agente.nombre}",
            especifico,
            "## Situación actual",
            "\n".join(f"- {linea}" for linea in situacion),
        ]
    )
