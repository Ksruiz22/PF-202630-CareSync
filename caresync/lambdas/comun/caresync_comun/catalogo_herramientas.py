"""Catálogo de herramientas: el contrato entre el modelo y lo que puede hacer.

Una sola definición para dos consumidores. El orquestador la traduce al formato
`toolSpec` de la API Converse; la función de herramientas la usa para validar
qué le piden y con qué rol.

Reglas que este archivo hace cumplir, y que no se dejan al prompt:

* **Qué rol puede usar cada herramienta.** Un prompt puede ignorarse; una lista
  de roles comprobada en código, no.
* **Qué herramientas ve cada agente.** El modelo no puede llamar a lo que no se
  le declara, así que la separación entre agentes es real y no una sugerencia.
* **Los argumentos.** `caso_id` nunca es un argumento del modelo: lo pone el
  orquestador desde la sesión. Si el modelo pudiera elegirlo, podría pedir el
  caso de otra persona.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .roble_acceso import ADMIN_CAE, ADMIN_CMU, PACIENTE, PROFESIONAL


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    propiedades: dict[str, Any] = field(default_factory=dict)
    requeridos: tuple[str, ...] = ()
    roles: frozenset[str] = frozenset({PACIENTE})
    # Una herramienta que escribe deja rastro en `eventos` y no se puede llamar
    # dos veces por vuelta.
    escribe: bool = False

    def spec(self) -> dict[str, Any]:
        """Forma que espera `toolConfig` de la API Converse."""
        return {
            "toolSpec": {
                "name": self.nombre,
                "description": self.descripcion,
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": self.propiedades,
                        "required": list(self.requeridos),
                    }
                },
            }
        }


CATALOGO: dict[str, Herramienta] = {
    "consultar_estado_caso": Herramienta(
        nombre="consultar_estado_caso",
        descripcion=(
            "Devuelve el estado del caso actual: centro asignado, nivel de urgencia, "
            "citas, plan de tratamiento e indicaciones activas. Úsala antes de preguntar "
            "a la persona algo que el sistema ya sabe."
        ),
        roles=frozenset({PACIENTE, PROFESIONAL, ADMIN_CMU, ADMIN_CAE}),
    ),
    "canalizar_caso": Herramienta(
        nombre="canalizar_caso",
        descripcion=(
            "Cierra el triaje: fija el centro de atención y el nivel de urgencia del caso. "
            "Llámala UNA sola vez, cuando ya tengas claro si la necesidad es física (CMU) o "
            "de salud mental (CAE) y qué nivel del protocolo aplica. Después de esto el caso "
            "pasa al agente de agenda."
        ),
        propiedades={
            "centro": {
                "type": "string",
                "enum": ["CMU", "CAE"],
                "description": "CMU para salud física, CAE para salud mental.",
            },
            "nivel_urgencia": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4,
                "description": "1 emergencia, 2 prioritario (72 h), 3 regular (7 días), 4 orientación.",
            },
            "resumen": {
                "type": "string",
                "description": (
                    "Resumen para el profesional que atenderá: motivo, tiempo de evolución, "
                    "señales de alarma revisadas y lo que la persona pide. Máximo 8 líneas."
                ),
            },
        },
        requeridos=("centro", "nivel_urgencia", "resumen"),
        roles=frozenset({PACIENTE}),
        escribe=True,
    ),
    "escalar_urgencia": Herramienta(
        nombre="escalar_urgencia",
        descripcion=(
            "Activa la ruta de emergencia del campus. Úsala en cuanto aparezca una señal de "
            "alarma del protocolo, ANTES de seguir preguntando cualquier otra cosa. No es "
            "excluyente: después puedes seguir acompañando a la persona."
        ),
        propiedades={
            "motivo": {
                "type": "string",
                "description": "Qué señal de alarma se detectó, en una frase.",
            }
        },
        requeridos=("motivo",),
        roles=frozenset({PACIENTE, PROFESIONAL}),
        escribe=True,
    ),
    "consultar_disponibilidad": Herramienta(
        nombre="consultar_disponibilidad",
        descripcion=(
            "Lista los espacios libres del centro asignado al caso, del más próximo al más "
            "lejano. Devuelve el identificador de cada espacio, que es lo que necesita "
            "agendar_cita."
        ),
        propiedades={
            "dias_adelante": {
                "type": "integer",
                "minimum": 1,
                "maximum": 30,
                "description": "Ventana de búsqueda. 7 si no hay una razón para otra cosa.",
            }
        },
        roles=frozenset({PACIENTE, ADMIN_CMU, ADMIN_CAE}),
    ),
    "agendar_cita": Herramienta(
        nombre="agendar_cita",
        descripcion=(
            "Reserva y confirma uno de los espacios devueltos por consultar_disponibilidad. "
            "Si otra persona lo tomó primero, la respuesta lo dice y trae alternativas: "
            "ofrécelas, no vuelvas a intentar el mismo espacio."
        ),
        propiedades={
            "cupo_id": {
                "type": "string",
                "description": "Identificador del espacio, tal como lo devolvió consultar_disponibilidad.",
            }
        },
        requeridos=("cupo_id",),
        roles=frozenset({PACIENTE, ADMIN_CMU, ADMIN_CAE}),
        escribe=True,
    ),
    "notificar_profesional": Herramienta(
        nombre="notificar_profesional",
        descripcion=(
            "Envía al profesional que atenderá el resumen del caso, para que llegue con "
            "contexto. Llámala después de agendar, una sola vez."
        ),
        roles=frozenset({PACIENTE, ADMIN_CMU, ADMIN_CAE}),
        escribe=True,
    ),
    "consultar_plan": Herramienta(
        nombre="consultar_plan",
        descripcion=(
            "Devuelve el plan de tratamiento que escribió el profesional y las indicaciones "
            "activas con su identificador, más el historial de adherencia y de evolución."
        ),
        roles=frozenset({PACIENTE, PROFESIONAL}),
    ),
    "registrar_evolucion": Herramienta(
        nombre="registrar_evolucion",
        descripcion=(
            "Guarda cómo dice la persona que se siente. La escala es de 0 (peor que nunca) a "
            "10 (como antes de todo esto). Registra lo que la persona dijo, no tu "
            "interpretación."
        ),
        propiedades={
            "escala": {"type": "integer", "minimum": 0, "maximum": 10},
            "nota": {
                "type": "string",
                "description": "Lo que la persona reportó, en sus términos.",
            },
        },
        requeridos=("escala",),
        roles=frozenset({PACIENTE}),
        escribe=True,
    ),
    "registrar_adherencia": Herramienta(
        nombre="registrar_adherencia",
        descripcion=(
            "Marca si la persona cumplió una indicación concreta. El identificador de la "
            "indicación viene de consultar_plan. Si no cumplió, no insistas: registra el "
            "motivo en la nota."
        ),
        propiedades={
            "indicacion_id": {"type": "string"},
            "cumplida": {"type": "boolean"},
            "nota": {"type": "string", "description": "Motivo, si no la cumplió."},
        },
        requeridos=("indicacion_id", "cumplida"),
        roles=frozenset({PACIENTE}),
        escribe=True,
    ),
}


def especificaciones(nombres: tuple[str, ...]) -> list[dict[str, Any]]:
    """Traduce una lista de nombres al `tools` de `toolConfig`."""
    return [CATALOGO[n].spec() for n in nombres if n in CATALOGO]


def permitida(nombre: str, rol: str) -> bool:
    herramienta = CATALOGO.get(nombre)
    return bool(herramienta) and rol in herramienta.roles
