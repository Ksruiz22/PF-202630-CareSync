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

import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from entorno import LAMBDAS, AccesoFalso, ActorFalso, cargar, comprobar, fallos, preparar  # noqa: E402

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
    para_paciente = set(_nombres(de(agenda, "paciente", con_caso=True)))
    comprobar("agenda para el paciente: cancela, cambia, sube la urgencia y abre un caso nuevo",
              {"cancelar_cita", "reprogramar_cita", "subir_urgencia", "nuevo_motivo"} <= para_paciente,
              str(sorted(para_paciente)))
    comprobar("el centro cancela y cambia, pero no abre casos a nombre de nadie",
              "cancelar_cita" in con_caso and "nuevo_motivo" not in con_caso)
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
    comprobar("agenda no traspasa por una canalización", orquestador._traspaso(agenda, bien) is None)

    nuevo = Resultado(texto="", usos=[Uso("nuevo_motivo", {}, {"ok": True, "caso_nuevo": "c-2"}, True)])
    fallido = Resultado(texto="", usos=[Uso("nuevo_motivo", {}, {"error": "x"}, False)])
    seguimiento = agentes.AGENTES["seguimiento"]
    comprobar("un problema nuevo pasa de agenda a triaje", orquestador._traspaso(agenda, nuevo) == "triaje")
    comprobar("y de seguimiento a triaje", orquestador._traspaso(seguimiento, nuevo) == "triaje")
    comprobar("sabe cuál es el caso nuevo", orquestador._caso_nuevo(nuevo) == "c-2")
    comprobar("si no se abrió, no hay caso nuevo ni traspaso",
              orquestador._caso_nuevo(fallido) == "" and orquestador._traspaso(agenda, fallido) is None)

    for nivel, resultado in (
        (1, {"ok": True, "agendar": False, "decir_a_la_persona": "ruta"}),
        (4, {"ok": True, "agendar": False, "plazo": "sin cita"}),
    ):
        sin_cita = Resultado(texto="", usos=[Uso("canalizar_caso", {}, resultado, True)])
        comprobar(f"nivel {nivel}: la herramienta dice que no hay cita y no pasa a agenda",
                  orquestador._traspaso(triaje, sin_cita) is None)

    # Y si la persona vuelve a escribir, el caso canalizado lo atiende agenda: que
    # tampoco busque espacios por su cuenta.
    prompt_agenda = agentes.instrucciones(agenda, actor=ActorFalso("paciente"),
                                          caso={"_id": "k", "estado": "canalizado", "nivel_urgencia": 4})
    comprobar("agenda no busca espacios para un nivel 4 que no pidió cita",
              "Si es 4, es una orientación sin cita" in prompt_agenda)

    nota = orquestador._nota_de_traspaso({"centro": "CMU", "nivel_urgencia": 3})
    comprobar("la nota de traspaso lleva la marca [sistema]", nota.startswith("[sistema]"), nota)

    contexto = orquestador._contexto_del_traspaso({"centro": "CMU", "nivel_urgencia": 2})
    comprobar("agenda recibe el plazo del nivel con el traspaso", "72 horas" in contexto, contexto)


def probar_pausa() -> None:
    print("\nUna conversación retomada días después (T5)")

    reloj = orquestador.reloj
    hace = lambda **delta: reloj.iso(reloj.ahora() - timedelta(**delta))  # noqa: E731
    pausa = orquestador._pausa
    comprobar("un mensaje de hace una hora no es una pausa",
              pausa([{"creado_en": hace(hours=1)}, {"creado_en": hace()}]) == "")
    tres = pausa([{"creado_en": hace(days=3, hours=2)}, {"creado_en": hace()}])
    comprobar("tres días sí, y lo dice con la fecha", "3 días" in tres and "detenida" in tres, tres)
    comprobar("un día se dice en singular", "1 día:" in pausa([{"creado_en": hace(days=1, hours=1)},
                                                              {"creado_en": hace()}]))
    comprobar("sin un mensaje anterior no hay pausa", pausa([{"creado_en": hace()}]) == "")
    comprobar("sin fechas no inventa una", pausa([{"contenido": "x"}, {"contenido": "y"}]) == "")
    comprobar("el triaje vuelve a preguntar cómo sigue antes de canalizar",
              "estuvo detenida más de un día" in agentes._TRIAJE)


def probar_cambio_de_caso() -> None:
    """T1: el problema nuevo se tría en su propio caso, en el mismo turno."""
    print("\nUn problema nuevo sigue en un caso aparte (T1)")

    Resultado, Uso = bedrock_conversa.Resultado, bedrock_conversa.Uso
    viejo = {"_id": "viejo", "estado": "en_seguimiento", "centro": "CAE", "nivel_urgencia": 3}
    nuevo = {"_id": "nuevo", "estado": "abierto"}

    class _Acceso(AccesoFalso):
        def caso(self, caso_id: str) -> dict:
            return {"viejo": viejo, "nuevo": nuevo}[caso_id]

    acceso = _Acceso(ActorFalso("paciente"), casos={"viejo": viejo}, abierto=viejo)
    vueltas = iter([
        Resultado(texto="Eso lo vemos aparte.",
                  usos=[Uso("nuevo_motivo", {"motivo": "rodilla"}, {"ok": True, "caso_nuevo": "nuevo"}, True)]),
        Resultado(texto="¿Desde cuándo te duele la rodilla?"),
    ])
    llamadas: list[dict] = []

    def conversar(**argumentos):
        llamadas.append(argumentos)
        return next(vueltas)

    original = orquestador.bedrock_conversa.conversar
    orquestador.bedrock_conversa.conversar = conversar
    try:
        respuesta = orquestador._conversar(acceso, token="t", mensaje="Además me duele la rodilla",
                                           cuerpo={"caso_id": "viejo"})
    finally:
        orquestador.bedrock_conversa.conversar = original
    cuerpo = json.loads(respuesta["body"])

    comprobar("atiende seguimiento y después triaje", cuerpo["agentes"] == ["seguimiento", "triaje"],
              str(cuerpo["agentes"]))
    comprobar("la respuesta ya es del caso nuevo, y la vista sigue en él",
              cuerpo["caso"]["id"] == "nuevo", str(cuerpo["caso"]))
    comprobar("el triaje empieza sólo con el mensaje de la persona, no con el hilo del otro caso",
              [b["text"] for m in llamadas[1]["mensajes"] for b in m["content"]] == ["Además me duele la rodilla"])
    comprobar("y con las instrucciones del triaje", "Agente de Triaje" in "".join(llamadas[1]["sistema"]))
    escritos = [(d["caso_id"], d["autor"], d["contenido"]) for que, d in acceso.escrito if que == "mensaje"]
    comprobar("cada caso guarda lo suyo: el viejo, lo que dijo seguimiento; el nuevo, el mensaje y el triaje",
              escritos == [
                  ("viejo", "paciente", "Además me duele la rodilla"),
                  ("viejo", "agente", "Eso lo vemos aparte."),
                  ("nuevo", "paciente", "Además me duele la rodilla"),
                  ("nuevo", "agente", "¿Desde cuándo te duele la rodilla?"),
              ], str(escritos))
    comprobar("la persona recibe las dos cosas en una sola respuesta",
              cuerpo["respuesta"] == "Eso lo vemos aparte.\n\n¿Desde cuándo te duele la rodilla?")


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


def probar_ruta_de_emergencia_garantizada() -> None:
    """El PR #18: la ruta llega aunque la salvaguarda corte lo que el modelo iba a decir."""
    print("\nLa ruta de emergencia no depende del modelo")

    Uso = bedrock_conversa.Uso
    ruta = "Por lo que me cuentas, esto necesita atención ahora. Llama al 123."
    escalo = [Uso("escalar_urgencia", {}, {"ok": True, "decir_a_la_persona": ruta}, True)]
    cortada = "Prefiero no responder eso: no soy personal clínico."
    garantizar = orquestador._con_la_ruta_de_emergencia

    comprobar("con salvaguarda y escalamiento se dice la ruta, sin la negativa",
              garantizar(cortada, escalo, intervino=True) == ruta)
    comprobar("si el modelo no dijo nada, se dice la ruta", garantizar("", escalo, intervino=False) == ruta)
    comprobar("si ya la dijo, aunque con otros saltos de línea, no se duplica",
              garantizar(ruta.replace(". ", ".\n") + " ¿Dónde estás?", escalo, intervino=False).count("123") == 1)
    comprobar("si no la dijo, se antepone a lo que dijo",
              garantizar("Aquí sigo contigo.", escalo, intervino=False).startswith(ruta))
    nivel_1 = [Uso("canalizar_caso", {}, {"ok": True, "agendar": False, "decir_a_la_persona": ruta}, True)]
    comprobar("canalizar con nivel 1 también la garantiza",
              garantizar(cortada, nivel_1, intervino=True) == ruta)
    fallida = [Uso("escalar_urgencia", {}, {"error": "x", "decir_a_la_persona": ruta}, False)]
    comprobar("una herramienta fallida no cuenta", garantizar("hola", fallida, intervino=False) == "hola")
    comprobar("sin escalamiento el texto no se toca",
              garantizar(cortada, [Uso("consultar_plan", {}, {}, True)], intervino=True) == cortada)


def probar_detalle_de_la_salvaguarda() -> None:
    print("\nQué política de la salvaguarda actuó")

    politicas = bedrock_conversa.politicas_que_bloquearon
    traza = {"guardrail": {
        "inputAssessment": {"g": {
            "contentPolicy": {"filters": [
                {"type": "SEXUAL", "confidence": "MEDIUM", "action": "BLOCKED"},
                {"type": "VIOLENCE", "confidence": "HIGH", "action": "NONE"},
            ]},
        }},
        "outputAssessments": {"g": [{
            "topicPolicy": {"topics": [{"name": "prescripcion", "type": "DENY", "action": "BLOCKED"}]},
            "sensitiveInformationPolicy": {"piiEntities": [
                {"match": "4111-1111-1111-1111", "type": "CREDIT_DEBIT_CARD_NUMBER", "action": "BLOCKED"},
            ]},
        }]},
    }}
    leidas = politicas(traza)
    comprobar("lee entrada y salida, y sólo lo que bloqueó",
              leidas == ["entrada:filtro:SEXUAL:MEDIUM", "salida:dato:CREDIT_DEBIT_CARD_NUMBER",
                         "salida:tema:prescripcion"], str(leidas))
    comprobar("nunca incluye el valor del dato sensible", "4111" not in str(leidas))
    comprobar("sin traza no inventa nada", politicas(None) == [] and politicas({}) == [])


def probar_orden_del_triaje() -> None:
    """El PR #20: el orden de trabajo es lo que el modelo sigue, así que el orden importa."""
    print("\nEl orden de trabajo del triaje")

    prompt = agentes._TRIAJE
    alarma = prompt.index("señal de alarma del Paso 0")
    cita = prompt.index("pidió una cita")
    pregunta = prompt.index("siguiente pregunta del Paso 3")
    comprobar("primero la alarma, después la cita, y sólo al final otra pregunta",
              alarma < cita < pregunta)
    comprobar("ante la duda sobre una alarma, escala sin confirmar", "Si dudas, escalas" in prompt)
    comprobar("la herramienta de urgencia va sola, sin texto antes", "sin escribir nada antes" in prompt)
    comprobar("no repite preguntas ya respondidas", "nunca una que la persona ya respondió" in prompt)
    # cae-09, 26/09: la respuesta no aclaró la pregunta y el agente la repitió en vez
    # de canalizar, hasta agotar la conversación.
    comprobar("ni vuelve a hacer una que no le aclararon", "ni\n   una que ya hiciste" in prompt)
    comprobar("pedir orientación canaliza como pedir una cita", "que la revisen u orientación" in prompt)
    # cmu-08, 26/09: tomó una duda de información por algo que no pasaba por el
    # triaje y mandó a la persona a un correo y una línea que no existen.
    comprobar("todo triaje termina en escalar o canalizar, también la duda de información",
              "Todo triaje termina en una de dos herramientas" in prompt and "nivel 4" in prompt)


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

    # El punto de caché iba al final de todo, con la hora al minuto dentro de lo
    # cacheado: la caché no servía de un mensaje a otro.
    fijo, variable = agentes.instrucciones_partidas(
        agentes.AGENTES["triaje"], actor=paciente, caso={"_id": "k-1", "estado": "abierto"}
    )
    bloques = bedrock_conversa.bloques_de_sistema((fijo, variable), usar_cache=True)
    comprobar("el punto de caché queda entre lo fijo y la situación actual",
              [list(b) for b in bloques] == [["text"], ["cachePoint"], ["text"]]
              and "Hoy es" in bloques[2]["text"] and "Hoy es" not in bloques[0]["text"]
              and "k-1" not in bloques[0]["text"])
    comprobar("partido o junto, el prompt es el mismo",
              "\n\n".join((fijo, variable)) == agentes.instrucciones(
                  agentes.AGENTES["triaje"], actor=paciente, caso={"_id": "k-1", "estado": "abierto"}))
    comprobar("un texto suelto sigue funcionando, con el punto al final",
              bedrock_conversa.bloques_de_sistema("x", usar_cache=True) == [{"text": "x"}, {"cachePoint": {"type": "default"}}])
    comprobar("el prompt común declara las marcas de autor",
              "[personal del CMU]" in agentes._COMUN and "[sistema]" in agentes._COMUN)
    comprobar("el prompt común prohíbe prometer contacto humano (invariante 7)",
              "No prometes que alguien va a llamar" in agentes._COMUN)
    comprobar("y mandar a un canal que no está en las instrucciones",
              "No mandas a la persona a otro canal" in agentes._COMUN)

    # Prueba de punta a punta del 14/10: «no hice las gárgaras» acabó en un segundo
    # registro de evolución, sin adherencia, y el agente dijo «quedó registrado».
    seguimiento = agentes._SEGUIMIENTO
    comprobar("seguimiento: la evolución se registra una vez por reporte", "una vez\n   por reporte" in seguimiento)
    comprobar("seguimiento: lo que hizo o no hizo va a registrar_adherencia",
              "Eso no se registra con `registrar_evolucion`" in seguimiento)
    comprobar("seguimiento: no dice «quedó registrado» sin una herramienta que lo registre",
              "Sólo dices que algo quedó registrado si lo registró una herramienta" in seguimiento)
    comprobar("seguimiento: ir peor sin señal de alarma no se escala",
              "Ir peor sin\n   señal de alarma no se escala" in seguimiento)

    # Hasta el 29/10 agenda y seguimiento escalaban «ante una señal del Paso 0» sin
    # tener el Paso 0. Se les da del mismo archivo del protocolo (invariante 4).
    #
    # Los archivos de `protocolos/` se copian junto a la Lambda al construir los
    # paquetes, así que aquí `agentes` carga sus textos de respaldo. Las funciones se
    # prueban contra los archivos de verdad, y el prompt contra lo que haya cargado.
    protocolos = LAMBDAS.parent / "protocolos"
    protocolo = (protocolos / "triaje-v0.md").read_text(encoding="utf-8")
    senales = agentes._seccion(protocolo, "Paso 0")
    niveles = agentes._seccion(protocolo, "Paso 2")
    comprobar("del protocolo sale el Paso 0 entero y sólo él",
              senales.startswith("## Paso 0") and "Dolor en el pecho" in senales and "## Paso 1" not in senales)
    comprobar("y el Paso 2 con sus niveles", niveles.startswith("## Paso 2") and "Prioritario" in niveles)
    orientacion = agentes._sin_comentarios((protocolos / "orientacion.md").read_text(encoding="utf-8"))
    comprobar("la información de los centros llega sin los comentarios para quien la mantiene",
              "Centro Médico Uninorte" in orientacion and "<!--" not in orientacion
              and "Pendiente de los centros" not in orientacion)

    paciente = ActorFalso("paciente")
    caso = {"_id": "k", "estado": "agendado", "centro": "CMU", "nivel_urgencia": 3}
    prompts = {clave: agentes.instrucciones(a, actor=paciente, caso=caso) for clave, a in agentes.AGENTES.items()}
    comprobar("agenda lleva las señales de alarma y los niveles",
              agentes.SENALES_DE_ALARMA in prompts["agenda"] and agentes.NIVELES in prompts["agenda"])
    comprobar("seguimiento lleva las señales de alarma",
              agentes.SENALES_DE_ALARMA in prompts["seguimiento"])
    comprobar("los tres llevan la información de los centros",
              all(agentes.ORIENTACION in p for p in prompts.values()))
    comprobar("agenda: cancelar y cambiar piden confirmación antes del efecto",
              "`confirmado` en true sólo después de que la persona oyó la fecha" in agentes._AGENDA)
    comprobar("triaje: lo que no es de salud no se canaliza, pero un saludo sí se atiende",
              "Ese no se\ncanaliza" in agentes._TRIAJE and "Un\nsaludo no es una excepción" in agentes._TRIAJE)


def main() -> int:
    for prueba in (
        probar_agente_por_defecto,
        probar_historial,
        probar_resolver_caso,
        probar_herramientas_declaradas,
        probar_traspaso,
        probar_pausa,
        probar_cambio_de_caso,
        probar_constancia_de_fallos,
        probar_ruta_de_emergencia_garantizada,
        probar_detalle_de_la_salvaguarda,
        probar_orden_del_triaje,
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
