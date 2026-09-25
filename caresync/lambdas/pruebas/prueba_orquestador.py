#!/usr/bin/env python3
"""
Pruebas del orquestador: qué agente atiende, qué ve el modelo y sobre qué caso.

    python pruebas/prueba_orquestador.py

Cada bloque protege algo que ya se rompió una vez o que rompería en silencio:

- **La selección de agente.** Sin caso cae por el rol; con caso, por su estado. Si
  el respaldo volviera a ser el triaje, el personal de un centro recibiría un 403 al
  preguntar por sus horarios.
- **El historial.** Converse exige alternancia estricta y que el último turno sea
  del usuario, y el turno que escribió el centro tiene que llegar marcado como suyo:
  sin la marca, el modelo le atribuía al paciente lo que preguntó el personal.
- **El caso de la petición.** Un paciente no reabre un caso cerrado por el
  `caso_id` que la vista reenvía.
- **La constancia de fallos** (invariante 8), que tiene que escribirse aunque el
  turno salga sin texto.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from entorno import AccesoFalso, ActorFalso, cargar, comprobar, fallos, preparar  # noqa: E402

preparar()

agentes = cargar("orquestador", "agentes")
bedrock_conversa = cargar("orquestador", "bedrock_conversa")
orquestador = cargar("orquestador", "handler")


def _nombres(especificaciones: list[dict]) -> list[str]:
    return [e["toolSpec"]["name"] for e in especificaciones]


def probar_agente_por_defecto() -> None:
    print("\nQué agente atiende")

    por_defecto = agentes.agente_por_defecto
    comprobar("paciente sin caso: triaje", por_defecto(None, rol="paciente") == "triaje")
    comprobar("admin CMU sin caso: agenda, no un 403 del triaje",
              por_defecto(None, rol="admin_cmu") == "agenda")
    comprobar("admin CAE sin caso: agenda", por_defecto(None, rol="admin_cae") == "agenda")
    comprobar("profesional sin caso: seguimiento", por_defecto(None, rol="profesional") == "seguimiento")

    for estado, esperado in (
        ("abierto", "triaje"),
        ("urgencia_escalada", "triaje"),
        ("canalizado", "agenda"),
        ("agendado", "agenda"),
        ("atendido", "seguimiento"),
        ("en_seguimiento", "seguimiento"),
        ("cerrado", "triaje"),
    ):
        real = por_defecto({"estado": estado}, rol="paciente")
        comprobar(f"caso «{estado}»: {esperado}", real == esperado, real)


def probar_historial() -> None:
    print("\nEl historial que ve el modelo")

    def historial(filas: list[dict]) -> list[dict]:
        return orquestador._historial(AccesoFalso(ActorFalso("paciente"), mensajes=filas), "k")

    filas = [
        {"autor": "paciente", "contenido": "Me duele la garganta"},
        {"autor": "agente", "contenido": "¿Desde cuándo?"},
        {"autor": "paciente", "contenido": "Desde el lunes"},
        {"autor": "agente", "contenido": "Te canalizo al CMU."},
        {"autor": "sistema", "contenido": "[sistema] En el turno anterior no se completó: agendar_cita."},
        # El mensaje que se acaba de anotar: lo vuelve a añadir quien llama.
        {"autor": "paciente", "contenido": "¿Y la cita?"},
    ]
    resultado = historial(filas)
    papeles = [m["role"] for m in resultado]
    comprobar("alterna usuario y agente, sin dos seguidos iguales",
              all(a != b for a, b in zip(papeles, papeles[1:])), str(papeles))
    comprobar("empieza por el usuario", papeles[0] == "user")
    comprobar("no termina en el usuario: el turno nuevo lo añade quien llama",
              papeles[-1] == "assistant", str(papeles))
    comprobar("la nota [sistema] va del lado del agente, junto a su último turno",
              len(resultado[-1]["content"]) == 2
              and resultado[-1]["content"][1]["text"].startswith("[sistema]"))

    comienza_mal = historial([
        {"autor": "agente", "contenido": "Hola"},
        {"autor": "paciente", "contenido": "Hola"},
        {"autor": "agente", "contenido": "Cuéntame"},
    ])
    comprobar("descarta lo que haya antes del primer turno del usuario",
              [m["role"] for m in comienza_mal] == ["user", "assistant"])

    con_centro = historial([
        {"autor": "paciente", "contenido": "Tengo ansiedad"},
        {"autor": "agente", "contenido": "Te canalizo al CAE."},
        {"autor": "admin_cae", "contenido": "¿Por qué no se ha asignado cita?"},
        {"autor": "agente", "contenido": "Porque no hay cupos."},
    ])
    turno_centro = con_centro[2]["content"][0]["text"]
    comprobar("lo que escribe el centro va como usuario y marcado como suyo",
              con_centro[2]["role"] == "user" and turno_centro.startswith("[personal del CAE]"),
              turno_centro)
    comprobar("lo del paciente no lleva marca",
              not con_centro[0]["content"][0]["text"].startswith("["))

    del_profesional = historial([
        {"autor": "profesional", "contenido": "¿Cómo va con el plan?"},
        {"autor": "agente", "contenido": "Bien."},
    ])
    comprobar("el profesional también se marca",
              del_profesional[0]["content"][0]["text"].startswith("[profesional que atiende]"))

    vacios = historial([
        {"autor": "paciente", "contenido": "   "},
        {"autor": "paciente", "contenido": "Hola"},
        {"autor": "agente", "contenido": ""},
        {"autor": "agente", "contenido": "¿Qué te pasa?"},
    ])
    comprobar("los turnos vacíos no llegan al modelo",
              [b["text"] for m in vacios for b in m["content"]] == ["Hola", "¿Qué te pasa?"])
    comprobar("sin filas no hay historial", historial([]) == [])


def probar_resolver_caso() -> None:
    print("\nSobre qué caso se conversa")

    abierto = {"_id": "abierto-1", "estado": "canalizado"}
    cerrado = {"_id": "cerrado-1", "estado": "cerrado"}
    casos = {"abierto-1": abierto, "cerrado-1": cerrado}

    paciente = AccesoFalso(ActorFalso("paciente"), casos=casos, abierto=abierto)
    comprobar("el caso que pide un paciente, si está vivo",
              orquestador._resolver_caso(paciente, cuerpo={"caso_id": "abierto-1"}, mensaje="x") is abierto)
    comprobar("un caso cerrado no se reabre: se sigue en el vigente",
              orquestador._resolver_caso(paciente, cuerpo={"caso_id": "cerrado-1"}, mensaje="x") is abierto)

    sin_vigente = AccesoFalso(ActorFalso("paciente"), casos=casos, abierto=None)
    nuevo = orquestador._resolver_caso(sin_vigente, cuerpo={"caso_id": "cerrado-1"}, mensaje="Me mareo")
    comprobar("y si no hay vigente, se abre uno nuevo con el mensaje como motivo",
              nuevo.get("estado") == "abierto" and nuevo.get("motivo") == "Me mareo", str(nuevo))

    primera_vez = AccesoFalso(ActorFalso("paciente"), abierto=None)
    comprobar("un paciente que escribe por primera vez abre caso",
              orquestador._resolver_caso(primera_vez, cuerpo={}, mensaje="Hola").get("estado") == "abierto")

    centro = AccesoFalso(ActorFalso("admin_cmu", centro="CMU"), casos=casos)
    comprobar("el centro sin caso elegido conversa sin caso",
              orquestador._resolver_caso(centro, cuerpo={}, mensaje="¿Quién atiende?") is None)
    comprobar("el centro nunca abre un caso", not centro.escrito)
    comprobar("al centro sí se le devuelve el caso cerrado que eligió",
              orquestador._resolver_caso(centro, cuerpo={"caso_id": "cerrado-1"}, mensaje="x") is cerrado)


def probar_herramientas_declaradas() -> None:
    print("\nQué herramientas se le declaran al modelo")

    de = orquestador._herramientas_de
    agenda, triaje, seguimiento = (agentes.AGENTES[k] for k in ("agenda", "triaje", "seguimiento"))

    comprobar("agenda sin caso, para el centro: sólo consultar agenda y profesionales",
              _nombres(de(agenda, "admin_cmu", con_caso=False))
              == ["consultar_disponibilidad", "consultar_profesionales"])
    con_caso = _nombres(de(agenda, "admin_cae", con_caso=True))
    comprobar("agenda con caso, para el centro: puede agendar y avisar",
              "agendar_cita" in con_caso and "notificar_profesional" in con_caso, str(con_caso))
    comprobar("el centro no escala urgencias ni ve lo que no le toca",
              "escalar_urgencia" not in con_caso)
    comprobar("agenda para el paciente: no consulta profesionales",
              "consultar_profesionales" not in _nombres(de(agenda, "paciente", con_caso=True)))
    comprobar("triaje para el paciente: estado, escalar y canalizar",
              _nombres(de(triaje, "paciente", con_caso=True))
              == ["consultar_estado_caso", "escalar_urgencia", "canalizar_caso"])
    comprobar("seguimiento para el profesional: no registra por la persona",
              _nombres(de(seguimiento, "profesional", con_caso=True))
              == ["consultar_estado_caso", "consultar_plan", "escalar_urgencia"])


def probar_traspaso() -> None:
    print("\nTraspaso entre agentes")

    Resultado, Uso = bedrock_conversa.Resultado, bedrock_conversa.Uso
    triaje, agenda = agentes.AGENTES["triaje"], agentes.AGENTES["agenda"]

    bien = Resultado(texto="", usos=[Uso("canalizar_caso", {}, {"ok": True}, True)])
    mal = Resultado(texto="", usos=[Uso("canalizar_caso", {}, {"error": "x"}, False)])
    nada = Resultado(texto="", usos=[Uso("consultar_estado_caso", {}, {}, True)])

    comprobar("canalizar con éxito pasa a agenda", orquestador._traspaso(triaje, bien) == "agenda")
    comprobar("una canalización fallida no traspasa", orquestador._traspaso(triaje, mal) is None)
    comprobar("sin canalizar no hay traspaso", orquestador._traspaso(triaje, nada) is None)
    comprobar("agenda no traspasa a nadie", orquestador._traspaso(agenda, bien) is None)

    nota = orquestador._nota_de_traspaso({"centro": "CMU", "nivel_urgencia": 3})
    comprobar("la nota de traspaso lleva la marca [sistema]", nota.startswith("[sistema]"), nota)


def probar_constancia_de_fallos() -> None:
    print("\nConstancia de los fallos (invariante 8)")

    Uso = bedrock_conversa.Uso
    acceso = AccesoFalso(ActorFalso("paciente"))
    orquestador._dejar_constancia_de_los_fallos(
        acceso, hilo_id="k", agente="agenda",
        usos=[Uso("consultar_disponibilidad", {}, {}, True), Uso("agendar_cita", {}, {"error": "x"}, False)],
    )
    escritas = [datos for que, datos in acceso.escrito if que == "mensaje"]
    comprobar("un fallo deja una nota", len(escritas) == 1)
    nota = escritas[0] if escritas else {}
    comprobar("la nota es del sistema, no del agente ni de la persona", nota.get("autor") == "sistema")
    comprobar("nombra lo que no se completó y sólo eso",
              "agendar_cita" in str(nota.get("contenido")) and "consultar_disponibilidad" not in str(nota.get("contenido")))

    sin_fallos = AccesoFalso(ActorFalso("paciente"))
    orquestador._dejar_constancia_de_los_fallos(
        sin_fallos, hilo_id="k", agente="agenda", usos=[Uso("agendar_cita", {}, {"ok": True}, True)]
    )
    comprobar("sin fallos no se escribe nada: cada escritura gasta cuota de ROBLE", not sin_fallos.escrito)


def probar_instrucciones() -> None:
    print("\nEl prompt de sistema")

    actor = ActorFalso("admin_cmu", centro="CMU")
    sin_caso = agentes.instrucciones(agentes.AGENTES["agenda"], actor=actor, caso=None)
    comprobar("sin caso lo dice, en vez de describir un caso vacío",
              "no es sobre ningún caso" in sin_caso and "Caso " not in sin_caso.split("## Situación actual")[1])
    comprobar("todo agente lleva la ruta de emergencia", agentes.RUTA_EMERGENCIA in sin_caso)

    paciente = ActorFalso("paciente")
    con_caso = agentes.instrucciones(
        agentes.AGENTES["triaje"], actor=paciente,
        caso={"_id": "k-1", "estado": "abierto", "centro": None, "nivel_urgencia": None},
    )
    situacion = con_caso.split("## Situación actual")[1]
    comprobar("con caso describe estado, centro y nivel",
              "k-1" in situacion and "sin centro asignado" in situacion and "sin nivel de urgencia" in situacion)
    comprobar("lo volátil va al final, para que el prefijo se pueda cachear",
              con_caso.index("## Situación actual") > con_caso.index("## Tu papel"))
    comprobar("el prompt común declara las marcas de autor",
              "[personal del CMU]" in agentes._COMUN and "[sistema]" in agentes._COMUN)
    comprobar("el prompt común prohíbe prometer contacto humano (invariante 7)",
              "No prometes que alguien va a llamar" in agentes._COMUN)


def main() -> int:
    for prueba in (
        probar_agente_por_defecto,
        probar_historial,
        probar_resolver_caso,
        probar_herramientas_declaradas,
        probar_traspaso,
        probar_constancia_de_fallos,
        probar_instrucciones,
    ):
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
