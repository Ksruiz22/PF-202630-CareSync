#!/usr/bin/env python3
"""
Pruebas de los permisos y de la frontera entre el modelo y los efectos.

    python pruebas/prueba_permisos.py

Protegen los invariantes 1, 2 y 3 del mapa (`caresync/CLAUDE.md`): el modelo nunca
aporta identidad, los permisos se comprueban en código y no en el prompt, y ninguna
herramienta escribe el plan clínico. Son las comprobaciones que respaldan la métrica
M7 del informe —ninguna llamada de un rol a una herramienta no permitida tiene
efecto— sin necesitar un token de cada rol.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from entorno import cargar, comprobar, fallos, lanza, preparar  # noqa: E402

preparar()

from caresync_comun.catalogo_herramientas import (  # noqa: E402
    CATALOGO,
    necesita_caso,
    permitida,
)
from caresync_comun.errores import SolicitudInvalida  # noqa: E402

agentes = cargar("orquestador", "agentes")
herramientas = cargar("herramientas", "handler")

ROLES = ("paciente", "profesional", "admin_cmu", "admin_cae", "admin_plataforma")


def probar_matriz_de_roles() -> None:
    print("\nQuién puede usar qué")

    esperado = {
        "paciente": {
            "consultar_estado_caso", "canalizar_caso", "escalar_urgencia",
            "consultar_disponibilidad", "agendar_cita", "notificar_profesional",
            "consultar_plan", "registrar_evolucion", "registrar_adherencia",
        },
        "profesional": {"consultar_estado_caso", "escalar_urgencia", "consultar_plan"},
        "admin_cmu": {
            "consultar_estado_caso", "consultar_disponibilidad", "consultar_profesionales",
            "agendar_cita", "notificar_profesional",
        },
        "admin_cae": {
            "consultar_estado_caso", "consultar_disponibilidad", "consultar_profesionales",
            "agendar_cita", "notificar_profesional",
        },
        # Reparte roles; no conversa ni lee historias clínicas.
        "admin_plataforma": set(),
    }
    for rol in ROLES:
        real = {nombre for nombre in CATALOGO if permitida(nombre, rol)}
        comprobar(f"{rol}: exactamente sus herramientas", real == esperado[rol],
                  f"sobran {sorted(real - esperado[rol])}, faltan {sorted(esperado[rol] - real)}")

    comprobar("una herramienta que no existe no se permite a nadie",
              not any(permitida("borrar_caso", rol) for rol in ROLES))
    comprobar("un rol inventado no puede nada",
              not any(permitida(nombre, "superusuario") for nombre in CATALOGO))


def probar_invariantes_del_catalogo() -> None:
    print("\nInvariantes del catálogo")

    identidad = {"caso_id", "user_id", "paciente_user_id", "token", "access_token", "rol"}
    colados = {
        nombre: sorted(identidad & set(h.propiedades))
        for nombre, h in CATALOGO.items()
        if identidad & set(h.propiedades)
    }
    comprobar("ninguna herramienta recibe identidad del modelo (invariante 1)",
              not colados, str(colados))

    escriben = {nombre for nombre, h in CATALOGO.items() if h.escribe}
    comprobar(
        "sólo escriben las seis de siempre; ninguna toca el plan (invariante 3)",
        escriben == {
            "canalizar_caso", "escalar_urgencia", "agendar_cita",
            "notificar_profesional", "registrar_evolucion", "registrar_adherencia",
        },
        str(sorted(escriben)),
    )
    comprobar("ningún nombre sugiere crear o cambiar el plan",
              not [n for n in CATALOGO if ("plan" in n or "indicacion" in n) and n != "consultar_plan"])

    sin_caso = {n for n in CATALOGO if not necesita_caso(n)}
    comprobar("sin caso sólo se consulta la agenda y los profesionales",
              sin_caso == {"consultar_disponibilidad", "consultar_profesionales"}, str(sorted(sin_caso)))
    comprobar("lo que no está en el catálogo se trata como que necesita caso",
              necesita_caso("herramienta_nueva"))

    for nombre, h in CATALOGO.items():
        faltan = [r for r in h.requeridos if r not in h.propiedades]
        if faltan:
            comprobar(f"{nombre}: los requeridos están declarados", False, str(faltan))
    comprobar("todo requerido está entre las propiedades", True)

    especificacion = CATALOGO["canalizar_caso"].spec()["toolSpec"]
    comprobar("la especificación tiene la forma de Converse",
              especificacion["name"] == "canalizar_caso"
              and especificacion["inputSchema"]["json"]["type"] == "object")


def probar_agentes_y_catalogo() -> None:
    print("\nAgentes contra catálogo")

    for clave, agente in agentes.AGENTES.items():
        desconocidas = [h for h in agente.herramientas if h not in CATALOGO]
        comprobar(f"{clave}: todas sus herramientas existen", not desconocidas, str(desconocidas))
        inservibles = [h for h in agente.herramientas if not any(permitida(h, r) for r in agente.roles)]
        comprobar(f"{clave}: ninguna herramienta queda sin rol que la pueda usar",
                  not inservibles, str(inservibles))

    comprobar("el triaje sólo atiende pacientes",
              agentes.AGENTES["triaje"].roles == frozenset({"paciente"}))
    comprobar("ningún agente atiende a la plataforma",
              not any("admin_plataforma" in a.roles for a in agentes.AGENTES.values()))
    comprobar("catálogo y ejecutores alineados (lo exige el import)",
              set(herramientas.EJECUTORES) == set(CATALOGO))


def probar_argumentos() -> None:
    print("\nArgumentos del modelo")

    canalizar = CATALOGO["canalizar_caso"]
    limpios = herramientas._argumentos(canalizar, {
        "centro": "CMU", "nivel_urgencia": "2", "resumen": "Fiebre de 4 días",
        "caso_id": "el-de-otra-persona", "user_id": "u-ajeno",
    })
    comprobar("descarta caso_id y user_id colados por el modelo",
              "caso_id" not in limpios and "user_id" not in limpios, str(limpios))
    comprobar("convierte un entero que llega como texto", limpios.get("nivel_urgencia") == 2)

    alto = herramientas._argumentos(canalizar, {"centro": "CAE", "nivel_urgencia": 9, "resumen": "x"})
    bajo = herramientas._argumentos(canalizar, {"centro": "CAE", "nivel_urgencia": 0, "resumen": "x"})
    comprobar("recorta el nivel al rango del catálogo",
              alto["nivel_urgencia"] == 4 and bajo["nivel_urgencia"] == 1)

    comprobar("un centro fuera del enum se rechaza, no se adivina",
              lanza(SolicitudInvalida, herramientas._argumentos, canalizar,
                    {"centro": "urgencias", "nivel_urgencia": 2, "resumen": "x"}) is not None)
    comprobar("un nivel que no es número se rechaza",
              lanza(SolicitudInvalida, herramientas._argumentos, canalizar,
                    {"centro": "CMU", "nivel_urgencia": "alto", "resumen": "x"}) is not None)
    faltan = lanza(SolicitudInvalida, herramientas._argumentos, canalizar, {"centro": "CMU"})
    comprobar("faltar un requerido se rechaza y dice cuál",
              faltan is not None and "nivel_urgencia" in str(faltan))
    comprobar("un argumento en None cuenta como ausente",
              lanza(SolicitudInvalida, herramientas._argumentos, canalizar,
                    {"centro": "CMU", "nivel_urgencia": None, "resumen": "x"}) is not None)
    comprobar("unos argumentos que no son objeto se rechazan",
              lanza(SolicitudInvalida, herramientas._argumentos, canalizar, "centro=CMU") is not None)

    adherencia = CATALOGO["registrar_adherencia"]
    for crudo, esperado in (("sí", True), ("true", True), ("1", True), ("no", False), ("false", False)):
        valor = herramientas._argumentos(adherencia, {"indicacion_id": "i", "cumplida": crudo})["cumplida"]
        comprobar(f"«{crudo}» se lee como {esperado}", valor is esperado)


def probar_segunda_comprobacion() -> None:
    """La función de herramientas rechaza antes de tocar ROBLE lo que no debe ejecutar."""
    print("\nLa función de herramientas, antes de cualquier efecto")

    sin_token = herramientas.manejar({"herramienta": "consultar_plan", "contexto": {"caso_id": "c"}})
    comprobar("sin token no se ejecuta", "error" in sin_token and "sesión" in sin_token["error"],
              str(sin_token))

    inventada = herramientas.manejar({"herramienta": "borrar_caso", "contexto": {"access_token": "t"}})
    comprobar("una herramienta inexistente no se ejecuta", "error" in inventada)

    sin_caso = herramientas.manejar({
        "herramienta": "agendar_cita",
        "argumentos": {"inicio": "2026-10-01T09:00:00-05:00"},
        "contexto": {"access_token": "t", "caso_id": ""},
    })
    comprobar("lo que necesita caso no se ejecuta sin caso, y dice dónde se elige",
              "error" in sin_caso and "tablero" in sin_caso["error"], str(sin_caso))


def main() -> int:
    for prueba in (
        probar_matriz_de_roles,
        probar_invariantes_del_catalogo,
        probar_agentes_y_catalogo,
        probar_argumentos,
        probar_segunda_comprobacion,
    ):
        prueba()
    return _cerrar()


def _cerrar() -> int:
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
