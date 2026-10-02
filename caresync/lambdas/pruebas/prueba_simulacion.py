#!/usr/bin/env python3
"""
Pruebas del modo simulación de `POST /agente`.

    python pruebas/prueba_simulacion.py

El modo simulación existe para que un profesional se ponga en los zapatos de un
paciente y pueda juzgar al modelo. Su única promesa es que **nada de lo que pase
ahí tiene efecto real**, y una promesa así no se comprueba leyendo el código una
vez: se comprueba aquí, en cada cambio.

Qué protege cada bloque:

- **Quién puede simular.** Un paciente, nunca. Si pudiera, una urgencia real
  escrita en la vista del paciente quedaría atendida por un sandbox que no marca
  el caso y no emite `ESCALAMIENTO`, así que no dispara la alarma y nadie se
  entera.
- **Que el camino no produce efectos**, por dos vías: un doble de la función de
  herramientas que explota si se la llama, y una lectura del propio archivo con
  `ast` que falla si alguna función de la simulación nombra `_ejecutor`,
  `_lambda`, `abrir_caso`, `caso_visible`, `caso_abierto_de`, `actualizar_caso` o
  `invoke`.
- **Que la alarma no se dispara.** Los nombres de evento del bloque van en
  minúsculas: el filtro de métrica de CloudWatch busca el literal `ESCALAMIENTO`
  en texto plano y sensible a mayúsculas.
- **Que al modelo se le declara lo que hay que evaluar.** `canalizar_caso` es de
  pacientes y quien simula es profesional: si se filtrara por rol, la decisión
  que se quiere medir no existiría.
- **Que lo que se escribe en ROBLE son dos cosas y ninguna es un caso.**
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from entorno import (  # noqa: E402
    LAMBDAS,
    AccesoFalso,
    ActorFalso,
    cargar,
    comprobar,
    fallos,
    lanza,
    preparar,
)

preparar()

from caresync_comun.errores import SinPermiso, SolicitudInvalida  # noqa: E402

agentes = cargar("orquestador", "agentes")
orquestador = cargar("orquestador", "handler")

# El `bedrock_conversa` del handler es el suyo: `import bedrock_conversa` lo registra
# con su propio nombre y `cargar()` crearía una segunda copia. Se toma del handler
# para no acabar parcheando la copia que nadie usa.
Uso = orquestador.bedrock_conversa.Uso
Resultado = orquestador.bedrock_conversa.Resultado

FUENTE = LAMBDAS / "orquestador" / "handler.py"
# Parte de lo que hay que comprobar no es lo que el codigo hace al correr, sino lo
# que nombra: que la simulacion este enchufada en `_atender` y que ninguna de sus
# funciones mencione algo que escriba o invoque. Eso se lee del arbol y no del
# texto, porque los comentarios del bloque hablan justamente de esas funciones
# para explicar que no se llaman.
ARBOL = ast.parse(FUENTE.read_text(encoding="utf-8"))


def _funciones(filtro) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(ARBOL) if isinstance(n, ast.FunctionDef) and filtro(n.name)]


def _llamadas(funcion: ast.FunctionDef) -> set[str]:
    """Los nombres que esa funcion llama, incluidas sus funciones anidadas."""
    llamados = set()
    for nodo in ast.walk(funcion):
        if not isinstance(nodo, ast.Call):
            continue
        if isinstance(nodo.func, ast.Name):
            llamados.add(nodo.func.id)
        elif isinstance(nodo.func, ast.Attribute):
            llamados.add(nodo.func.attr)
    return llamados

# Un resumen cualquiera: lo que importa de él es que esté.
RESUMEN = "Ansiedad desde hace dos semanas, sin ideacion suicida. Pide hablar con alguien."


class ConversaFalsa:
    """Doble de `bedrock_conversa.conversar`: no habla con Bedrock y deja ver qué recibió.

    Ejecuta las llamadas a herramientas que se le pasen, en orden, contra el ejecutor
    que le dé el orquestador. Así la prueba controla qué «decide el modelo» sin
    gastar un token.
    """

    def __init__(self, llamadas=(), *, texto: str = "", intervino: bool = False) -> None:
        self.llamadas = list(llamadas)
        self.texto = texto
        self.intervino = intervino
        self.veces = 0
        self.sistema = ""
        self.mensajes: list = []
        self.herramientas: list = []

    def __call__(self, *, sistema, mensajes, herramientas, ejecutar, **_resto):
        self.veces += 1
        self.sistema = sistema
        self.mensajes = list(mensajes)
        self.herramientas = list(herramientas)

        usos = []
        for nombre, argumentos in self.llamadas:
            salida = ejecutar(nombre, argumentos)
            usos.append(Uso(nombre, argumentos, salida, not salida.get("error")))
        return Resultado(texto=self.texto, usos=usos, intervino_guardrail=self.intervino)


def _lambda_que_explota(*_args, **_kwargs):
    raise AssertionError("La simulacion intento hablar con la funcion de herramientas")


def correr(acceso, *, mensaje="Me siento muy ansioso", cuerpo=None, llamadas=(), texto=""):
    """Corre `_simular` con el bucle del modelo doblado y la Lambda minada.

    `FUNCION_HERRAMIENTAS` se pone con un valor cualquiera a propósito: vacío, el
    ejecutor real fallaría en la primera línea y la prueba no distinguiría «no se
    invocó» de «no estaba configurado».
    """
    conversa = ConversaFalsa(llamadas, texto=texto)
    original_conversar = orquestador.bedrock_conversa.conversar
    original_lambda = orquestador._lambda
    original_funcion = orquestador.FUNCION_HERRAMIENTAS

    orquestador.bedrock_conversa.conversar = conversa
    orquestador._lambda = _lambda_que_explota
    orquestador.FUNCION_HERRAMIENTAS = "caresync-herramientas-que-no-se-debe-llamar"
    try:
        respuesta = orquestador._simular(
            acceso, mensaje=mensaje, cuerpo={"simulacion": True, **(cuerpo or {})}
        )
    finally:
        orquestador.bedrock_conversa.conversar = original_conversar
        orquestador._lambda = original_lambda
        orquestador.FUNCION_HERRAMIENTAS = original_funcion

    return conversa, json.loads(respuesta["body"]), respuesta


def _profesional(**extra):
    return AccesoFalso(ActorFalso("profesional", user_id="u-prof"), **extra)


def _canalizar(centro="CAE", nivel=3, resumen=RESUMEN):
    argumentos = {"centro": centro, "nivel_urgencia": nivel}
    if resumen is not None:
        argumentos["resumen"] = resumen
    return ("canalizar_caso", argumentos)


# ------------------------------------------------------------------- las pruebas

def probar_cuando_es_simulacion() -> None:
    print("\nCuando una peticion es una simulacion")

    pide = orquestador._pide_simulacion
    comprobar("el booleano de JSON", pide({"simulacion": True}))
    comprobar("el texto, por si el cliente lo serializa", pide({"simulacion": "true"}))
    comprobar("sin el campo no es simulacion", not pide({"mensaje": "hola"}))
    comprobar("false no es simulacion", not pide({"simulacion": False}))
    comprobar("una cadena vacia tampoco", not pide({"simulacion": ""}))
    comprobar("ni la palabra que no esta en la lista", not pide({"simulacion": "quizas"}))

    # Sin esto, todo lo de abajo podria pasar con el modo inalcanzable desde la API.
    atender = _funciones(lambda n: n == "_atender")
    llamadas = _llamadas(atender[0]) if atender else set()
    comprobar("_atender existe y se mira el cuerpo antes de conversar",
              bool(atender) and "_pide_simulacion" in llamadas)
    comprobar("y desvia a _simular", "_simular" in llamadas)
    comprobar("sin perder el camino real", "_conversar" in llamadas)


def probar_saneado_del_slug() -> None:
    print("\nSaneado del simulacion_id")

    slug = orquestador._slug_de_simulacion
    comprobar("minusculas", slug("Prueba-CAE") == "prueba-cae", slug("Prueba-CAE"))
    comprobar("lo que no es [a-z0-9-] se vuelve guion",
              slug("Dolor de pecho") == "dolor-de-pecho", slug("Dolor de pecho"))
    comprobar("los guiones no se acumulan", slug("a///b") == "a-b", slug("a///b"))
    comprobar("no empieza ni termina en guion", slug("__caso__") == "caso", slug("__caso__"))
    largo = slug("x" * 80)
    comprobar("se recorta a 40", len(largo) == 40, str(len(largo)))
    comprobar("el recorte no deja un guion al final", not slug("a" * 39 + "-bcd").endswith("-"))
    comprobar("solo quedan caracteres del alfabeto",
              set(slug("Caso #3: nivel 1!")) <= set("abcdefghijklmnopqrstuvwxyz0123456789-"),
              slug("Caso #3: nivel 1!"))

    generado = slug(None)
    comprobar("sin id se genera uno del reloj, no un 400",
              generado.startswith("s-") and len(generado) <= 40, generado)
    comprobar("un id que queda vacio al sanear tambien se genera",
              slug("???").startswith("s-"), slug("???"))


def probar_quien_puede_simular() -> None:
    print("\nQuien puede simular")

    comprobar("el paciente no simula: su urgencia real quedaria en un sandbox",
              "paciente" not in orquestador.ROLES_QUE_SIMULAN)
    paciente = AccesoFalso(ActorFalso("paciente"))
    comprobar("si lo pide, es 403 y no una conversacion",
              isinstance(lanza(SinPermiso, correr, paciente), SinPermiso))
    comprobar("y nada se escribio antes de negarlo", not paciente.escrito)

    for rol in ("profesional", "admin_cmu", "admin_cae"):
        acceso = AccesoFalso(ActorFalso(rol, user_id=f"u-{rol}"))
        _conversa, cuerpo, _resp = correr(acceso, llamadas=[_canalizar()])
        comprobar(f"{rol} si simula", cuerpo.get("simulacion") is True)

    comprobar("un rol de plataforma tampoco",
              isinstance(
                  lanza(SinPermiso, correr, AccesoFalso(ActorFalso("admin_plataforma"))),
                  SinPermiso,
              ))

    otro_agente = lanza(
        SolicitudInvalida, correr, _profesional(), cuerpo={"agente": "agenda"}
    )
    comprobar("pedir otro agente es un 400 explicito, no un cambio silencioso",
              isinstance(otro_agente, SolicitudInvalida))


def probar_sin_efectos_reales() -> None:
    print("\nQue nada de esto tiene efecto real")

    # El doble de Lambda explota: si el ejecutor simulado invocara la funcion de
    # herramientas, esto seria un AssertionError y no una respuesta.
    acceso = _profesional()
    _conversa, cuerpo, _resp = correr(
        acceso,
        llamadas=[("consultar_estado_caso", {}), _canalizar(), ("escalar_urgencia", {"motivo": "x"})],
    )
    comprobar("tres herramientas simuladas sin invocar ninguna Lambda",
              len(cuerpo["acciones"]) == 3)
    comprobar("todas se marcan como simuladas",
              all(a["resultado"].get("simulado") for a in cuerpo["acciones"]))

    # Y la lectura del archivo: que no haya efectos no depende de que esta prueba
    # cubra todos los caminos, sino de que ninguna funcion del bloque nombre nada
    # que escriba. Esto falla al anadir la llamada, no al ejecutarla.
    prohibidos = {
        "_ejecutor",
        "_lambda",
        "invoke",
        "abrir_caso",
        "caso_visible",
        "caso_abierto_de",
        "actualizar_caso",
    }
    funciones = _funciones(lambda n: "simul" in n)
    comprobar("se encontraron las funciones de la simulacion", len(funciones) >= 10,
              str(len(funciones)))

    nombrados: set[str] = set()
    eventos: list[str] = []
    for funcion in funciones:
        for nodo in ast.walk(funcion):
            if isinstance(nodo, ast.Name) and nodo.id in prohibidos:
                nombrados.add(f"{funcion.name}:{nodo.id}")
            if isinstance(nodo, ast.Attribute) and nodo.attr in prohibidos:
                nombrados.add(f"{funcion.name}:{nodo.attr}")
            # Los nombres de evento: `evento(log, "nombre", ...)`.
            if (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Name)
                and nodo.func.id == "evento"
                and len(nodo.args) >= 2
                and isinstance(nodo.args[1], ast.Constant)
            ):
                eventos.append(str(nodo.args[1].value))

    comprobar("ninguna funcion de la simulacion nombra lo que escribe o invoca",
              not nombrados, ", ".join(sorted(nombrados)))
    comprobar("se leyeron los nombres de evento del bloque", len(eventos) >= 3, str(len(eventos)))
    comprobar("todos en minusculas: el filtro de CloudWatch busca ESCALAMIENTO literal",
              all(n == n.lower() for n in eventos), ", ".join(eventos))


def probar_lo_que_ve_el_modelo() -> None:
    print("\nQue se le declara y se le cuenta al modelo")

    conversa, _cuerpo, _resp = correr(_profesional(), llamadas=[_canalizar()])

    declaradas = [e["toolSpec"]["name"] for e in conversa.herramientas]
    comprobar("se declaran las tres del triaje, sin filtrar por rol",
              declaradas == ["consultar_estado_caso", "escalar_urgencia", "canalizar_caso"],
              ", ".join(declaradas))
    comprobar("canalizar_caso esta aunque el rol real no la tenga permitida",
              "canalizar_caso" in declaradas)

    comprobar("un solo agente y una sola vuelta: sin traspaso a agenda",
              conversa.veces == 1, str(conversa.veces))

    # El encabezado lleva tilde en el prompt; se corta por el prefijo para no
    # escribir caracteres fuera de ASCII en esta prueba.
    situacion = conversa.sistema.split("## Situaci")[-1]
    comprobar("al modelo se le presenta un paciente, no el profesional que simula",
              "paciente" in situacion and "profesional" not in situacion)
    comprobar("el nombre del actor sintetico es generico, sin correo real",
              "comunidad universitaria" in situacion
              and "prueba@uninorte.edu.co" not in conversa.sistema)
    comprobar("hay caso sintetico: si no, el prompt diria que no hay herramientas de caso",
              "simulacion:u-prof:" in situacion)


def probar_resultados_en_seco() -> None:
    print("\nLos resultados simulados tienen la forma de los reales")

    _c, cuerpo, _r = correr(_profesional(), llamadas=[_canalizar(centro="CMU", nivel=3)])
    canalizado = cuerpo["acciones"][0]["resultado"]
    comprobar("canalizar nivel 3: ok, centro, nivel, agendar y plazo",
              canalizado["ok"] is True
              and canalizado["centro"] == "CMU"
              and canalizado["nivel_urgencia"] == 3
              and canalizado["agendar"] is True
              and canalizado["plazo"] == orquestador._PLAZO_SIMULADO[3])
    comprobar("y queda marcado como simulado", canalizado["simulado"] is True)

    _c, cuerpo, _r = correr(_profesional(), llamadas=[_canalizar(centro="CAE", nivel=1)])
    nivel_1 = cuerpo["acciones"][0]["resultado"]
    comprobar("canalizar nivel 1: no se agenda", nivel_1["agendar"] is False)
    comprobar("canalizar nivel 1: devuelve la ruta de emergencia, igual que el real",
              nivel_1["decir_a_la_persona"] == agentes.RUTA_EMERGENCIA)
    comprobar("y la ruta llega a la respuesta aunque el modelo no la diga",
              cuerpo["respuesta"] == agentes.RUTA_EMERGENCIA)

    _c, cuerpo, _r = correr(_profesional(), llamadas=[("escalar_urgencia", {"motivo": "dolor de pecho"})])
    escalado = cuerpo["acciones"][0]["resultado"]
    comprobar("escalar: ruta, agendar false y nadie avisado",
              escalado["ok"] is True
              and escalado["decir_a_la_persona"] == agentes.RUTA_EMERGENCIA
              and escalado["agendar"] is False
              and escalado["avisado_el_equipo"] is False)
    comprobar("escalar trae la instruccion de decirlo primero",
              "antes de cualquier otra cosa" in escalado["instruccion"])

    _c, cuerpo, _r = correr(_profesional(), llamadas=[("consultar_estado_caso", {})])
    estado = cuerpo["acciones"][0]["resultado"]
    comprobar("consultar estado: un caso recien abierto, sin leer ROBLE",
              estado["estado"] == "abierto"
              and estado["centro"] is None
              and estado["citas"] == []
              and estado["indicaciones_activas"] == 0)

    # Falta un requerido: en produccion el modelo recibe un error de dominio del
    # catalogo y tiene que reintentar. Si aqui saliera una excepcion, la conversacion
    # se rompria y el profesional no veria lo que de verdad pasa.
    _c, cuerpo, _r = correr(_profesional(), llamadas=[_canalizar(resumen=None)])
    sin_resumen = cuerpo["acciones"][0]["resultado"]
    comprobar("sin un argumento requerido: error de dominio, no excepcion",
              bool(sin_resumen.get("error")) and sin_resumen["herramienta"] == "canalizar_caso")
    comprobar("y el uso queda marcado como fallido", cuerpo["acciones"][0]["ok"] is False)

    _c, cuerpo, _r = correr(_profesional(), llamadas=[_canalizar(centro="CLINICA")])
    centro_malo = cuerpo["acciones"][0]["resultado"]
    comprobar("un centro que no esta en el enum tampoco pasa",
              bool(centro_malo.get("error")))

    _c, cuerpo, _r = correr(_profesional(), llamadas=[("agendar_cita", {"inicio": "2026-10-05T09:00"})])
    no_simulable = cuerpo["acciones"][0]["resultado"]
    comprobar("una herramienta sin resultado en seco no se improvisa",
              bool(no_simulable.get("error")))


def probar_lo_que_se_escribe() -> None:
    print("\nQue se escribe en ROBLE y que no")

    acceso = _profesional()
    _c, cuerpo, _r = correr(
        acceso,
        mensaje="Me siento muy ansioso",
        cuerpo={"simulacion_id": "Prueba CAE 01"},
        llamadas=[_canalizar(centro="CAE", nivel=2)],
        texto="Te canalizo al CAE.",
    )

    tablas = {que for que, _datos in acceso.escrito}
    comprobar("solo se escriben conversaciones y eventos", tablas == {"mensaje", "evento"},
              ", ".join(sorted(tablas)))
    comprobar("nada toca casos: ni abrir, ni actualizar",
              not any(que in ("caso", "abrir_caso") for que, _d in acceso.escrito))

    mensajes = [datos for que, datos in acceso.escrito if que == "mensaje"]
    comprobar("el hilo lleva el prefijo simulacion: con el user_id de quien simula",
              all(m["caso_id"] == "simulacion:u-prof:prueba-cae-01" for m in mensajes),
              mensajes[0]["caso_id"] if mensajes else "ninguno")
    comprobar("el turno humano se anota como paciente, que es el papel que se interpreta",
              mensajes[0]["autor"] == "paciente", mensajes[0]["autor"])
    comprobar("la respuesta del agente tambien se guarda, para que el hilo tenga memoria",
              any(m["autor"] == "agente" for m in mensajes))

    eventos = [datos for que, datos in acceso.escrito if que == "evento"]
    comprobar("una decision escribe un evento", len(eventos) == 1, str(len(eventos)))
    registro = eventos[0] if eventos else {}
    comprobar("el tipo es simulacion_triaje", registro.get("tipo") == "simulacion_triaje")
    comprobar("la severidad es info, para no ensuciar la bitacora de urgencias",
              registro.get("severidad") == "info")
    detalle = registro.get("detalle") or {}
    comprobar("el detalle trae centro y nivel, que es lo que la vista compara",
              detalle.get("centro") == "CAE" and detalle.get("nivel_urgencia") == 2)
    comprobar("y el slug, para agrupar las decisiones de una misma simulacion",
              detalle.get("simulacion_id") == "prueba-cae-01")

    # Consultar el estado no decide nada: no gasta una fila de la cuota de ROBLE.
    solo_lectura = _profesional()
    correr(solo_lectura, llamadas=[("consultar_estado_caso", {})])
    comprobar("una consulta no deja evento",
              not any(que == "evento" for que, _d in solo_lectura.escrito))

    # El hilo anterior se relee: la simulacion tiene memoria de un turno a otro.
    previo = _profesional(
        mensajes=[
            {"autor": "paciente", "contenido": "Me siento muy ansioso"},
            {"autor": "agente", "contenido": "Desde cuando?"},
        ]
    )
    conversa, _cuerpo, _r = correr(previo, mensaje="Desde el lunes", llamadas=[])
    comprobar("el historial del hilo llega al modelo",
              len(conversa.mensajes) == 3 and conversa.mensajes[-1]["content"][0]["text"] == "Desde el lunes",
              str(len(conversa.mensajes)))

    # Y un fallo deja su nota, igual que en el camino real (invariante 8).
    con_fallo = _profesional()
    correr(con_fallo, llamadas=[_canalizar(resumen=None)])
    notas = [d for q, d in con_fallo.escrito if q == "mensaje" and d.get("autor") == "sistema"]
    comprobar("un fallo simulado deja constancia en el hilo", len(notas) == 1, str(len(notas)))


def probar_que_la_bitacora_no_tumba_la_simulacion() -> None:
    print("\nSi ROBLE no acepta el evento, la simulacion sigue")

    class SoloFallaElEvento(AccesoFalso):
        def registrar_evento(self, **datos):
            raise RuntimeError("ROBLE no responde (evento)")

    acceso = SoloFallaElEvento(ActorFalso("profesional", user_id="u-prof"))
    _c, cuerpo, _r = correr(acceso, llamadas=[_canalizar()])
    comprobar("la conversacion se responde igual", cuerpo["simulacion"] is True)
    comprobar("y la decision sigue en la respuesta, que es lo que el profesional juzga",
              len(cuerpo["decisiones"]) == 1)


def probar_contrato_de_la_respuesta() -> None:
    print("\nEl contrato de la respuesta en simulacion")

    conversa_llamadas = [_canalizar(centro="CAE", nivel=2)]
    _c, cuerpo, respuesta = correr(
        _profesional(),
        cuerpo={"simulacion_id": "PRUEBA CAE 01", "agente": "triaje"},
        llamadas=conversa_llamadas,
        texto="Te canalizo al CAE.",
    )

    comprobar("200", respuesta["statusCode"] == 200)
    comprobar("sin la cabecera del caso: no hay caso",
              "x-caresync-caso" not in respuesta["headers"])

    esperados = {
        "respuesta", "caso", "agentes", "acciones", "salvaguardas_intervinieron",
        "salvaguardas_detalle", "simulacion", "simulacion_id", "decisiones",
    }
    comprobar("estan los campos acordados con la PWA y ninguno de mas",
              set(cuerpo) == esperados, ", ".join(sorted(set(cuerpo) ^ esperados)) or "iguales")
    comprobar("caso va en null siempre", cuerpo["caso"] is None)
    comprobar("agentes dice que corrio uno solo", cuerpo["agentes"] == ["triaje"])
    comprobar("simulacion es true", cuerpo["simulacion"] is True)
    comprobar("simulacion_id devuelve el slug ya saneado",
              cuerpo["simulacion_id"] == "prueba-cae-01", cuerpo["simulacion_id"])
    comprobar("salvaguardas con la misma forma que en el camino real",
              cuerpo["salvaguardas_intervinieron"] is False
              and cuerpo["salvaguardas_detalle"] == [])

    decision = cuerpo["decisiones"][0]
    comprobar("decisiones lleva herramienta, argumentos, resultado y ok",
              set(decision) == {"herramienta", "argumentos", "resultado", "ok"},
              ", ".join(sorted(decision)))
    comprobar("y los argumentos, que es lo que acciones no trae",
              decision["argumentos"]["centro"] == "CAE"
              and decision["argumentos"]["nivel_urgencia"] == 2
              and bool(decision["argumentos"]["resumen"]))
    comprobar("acciones sigue teniendo la forma de siempre",
              set(cuerpo["acciones"][0]) == {"herramienta", "ok", "resultado"})


def main() -> int:
    for prueba in (
        probar_cuando_es_simulacion,
        probar_saneado_del_slug,
        probar_quien_puede_simular,
        probar_sin_efectos_reales,
        probar_lo_que_ve_el_modelo,
        probar_resultados_en_seco,
        probar_lo_que_se_escribe,
        probar_que_la_bitacora_no_tumba_la_simulacion,
        probar_contrato_de_la_respuesta,
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
