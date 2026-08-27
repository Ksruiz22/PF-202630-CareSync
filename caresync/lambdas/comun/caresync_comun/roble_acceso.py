"""Módulo de acceso a datos: la única puerta a ROBLE.

Ninguna otra parte del sistema importa `roble` ni conoce un nombre de tabla. El
motivo no es purismo: ROBLE es una plataforma de la universidad, gratuita y en
evolución, y el prototipo tiene que poder cambiarla por otra persistencia sin
tocar la lógica de los agentes.

Tres cosas que esta capa resuelve y que no son evidentes:

**Quién actúa.** El sistema no tiene una cuenta de servicio omnipotente. La
Lambda recibe el token del propio llamante y lo inyecta en el cliente de ROBLE,
así que los permisos por tabla y por rol que están configurados en la consola de
ROBLE se aplican de verdad. La única excepción es la función de recordatorios,
que corre por reloj y usa `como_servicio()`.

**Los filtros son de igualdad.** `read` no admite rangos, orden ni paginación,
así que los rangos de fechas se filtran en memoria. Es aceptable con los
volúmenes de un prototipo, y el camino de salida está documentado: consultas
guardadas en la consola, invocadas con `execute_query`.

**No hay escrituras condicionales.** No existe un `UPDATE ... WHERE estado =
'libre'` atómico, así que dos personas pueden pedir el mismo cupo a la vez. El
control es *reservar, releer y reconciliar*: se marca la reserva con un testigo
único, se vuelve a leer, y quien no encuentra su testigo cede. Ver
`reservar_cupo`.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from roble import (
    MemoryStorage,
    RobleAuthError,
    RobleClient,
    RobleError,
    RobleHttpError,
    RobleNetworkError,
    RobleTimeoutError,
    User,
)

from . import reloj
from .config import config, credenciales_servicio
from .errores import Conflicto, ErrorDeDatos, NoAutorizado, NoEncontrado, SinPermiso
from .registro import evento, registro

log = registro(__name__)

# --------------------------------------------------------------------- tablas

CASOS = "casos"
CONVERSACIONES = "conversaciones"
PERFILES = "perfiles"
PROFESIONALES = "profesionales"
HORARIOS = "horarios"
CUPOS = "cupos"
CITAS = "citas"
PLANES = "planes"
INDICACIONES = "indicaciones"
ADHERENCIA = "adherencia"
EVOLUCION = "evolucion"
EVENTOS = "eventos"
RECORDATORIOS = "recordatorios"

# ---------------------------------------------------------------------- roles

PACIENTE = "paciente"
PROFESIONAL = "profesional"
ADMIN_CMU = "admin_cmu"
ADMIN_CAE = "admin_cae"
SERVICIO = "servicio"

ROLES = {PACIENTE, PROFESIONAL, ADMIN_CMU, ADMIN_CAE, SERVICIO}

# El centro que administra cada rol administrativo. Un admin del CMU no ve la
# agenda del CAE: son servicios distintos y los datos de salud mental tienen
# una sensibilidad propia.
CENTRO_DE_ROL = {ADMIN_CMU: "CMU", ADMIN_CAE: "CAE"}

CMU = "CMU"
CAE = "CAE"

# --------------------------------------------------------------- estados

CASO_ABIERTO = "abierto"
CASO_CANALIZADO = "canalizado"
CASO_AGENDADO = "agendado"
CASO_ATENDIDO = "atendido"
CASO_SEGUIMIENTO = "en_seguimiento"
CASO_CERRADO = "cerrado"
CASO_URGENTE = "urgencia_escalada"

CUPO_LIBRE = "libre"
CUPO_RESERVADO = "reservado"
CUPO_CONFIRMADO = "confirmado"


@dataclass(frozen=True)
class Actor:
    """Quién está actuando, ya resuelto: identidad de ROBLE más rol y centro."""

    user_id: str
    email: str
    nombre: str
    rol: str
    centro: str | None = None
    perfil_id: str | None = None

    @property
    def es_paciente(self) -> bool:
        return self.rol == PACIENTE

    @property
    def es_administrativo(self) -> bool:
        return self.rol in CENTRO_DE_ROL


def fila_id(fila: dict[str, Any] | None) -> str | None:
    """El identificador de una fila, sea cual sea la forma en que llegue.

    ROBLE devuelve `_id` en `/insert-one`, pero según la tabla y el endpoint el
    campo aparece como `id`, o la fila viene envuelta en `inserted`.
    """
    if not isinstance(fila, dict):
        return None
    for clave in ("_id", "id"):
        if fila.get(clave) not in (None, ""):
            return str(fila[clave])
    insertadas = fila.get("inserted")
    if isinstance(insertadas, list) and insertadas:
        return fila_id(insertadas[0])
    return None


class AccesoRoble:
    """Puerta única a los datos. Se construye con `desde_token` o `como_servicio`."""

    def __init__(self, cliente: RobleClient, actor: Actor) -> None:
        self._db = cliente
        self.actor = actor

    # ------------------------------------------------------------ construcción

    @classmethod
    def desde_token(cls, token: str) -> AccesoRoble:
        """Actúa en nombre de quien llama, con su propio token de ROBLE.

        El token se inyecta a través del almacén de sesión del SDK, que es su
        contrato público, en lugar de tocar atributos privados del cliente. Se
        inyecta **sólo el access token**: mandar también el refresh token al
        backend ampliaría la exposición sin necesidad. La consecuencia es que si
        el access token está vencido, la respuesta es 401 y quien renueva es la
        aplicación, que ya tiene el refresh token.
        """
        ajustes = config()
        almacen = MemoryStorage()
        almacen.set_item(
            f"roble.session.{ajustes.roble_contract_id}",
            json.dumps({"accessToken": token, "refreshToken": token}),
        )

        cliente = RobleClient(
            base_url=ajustes.roble_base_url,
            contract_id=ajustes.roble_contract_id,
            storage=almacen,
            timeout=15.0,
        )
        cliente.restore_session(verify=False)

        try:
            usuario = cliente.current_user()
        except RobleHttpError as exc:
            if exc.status_code in (401, 403):
                raise NoAutorizado("ROBLE rechazó el token del llamante") from exc
            raise ErrorDeDatos(f"ROBLE respondió {exc.status_code} al validar la sesión") from exc
        except (RobleNetworkError, RobleTimeoutError) as exc:
            raise ErrorDeDatos("No se pudo alcanzar ROBLE para validar la sesión") from exc
        except RobleError as exc:
            raise ErrorDeDatos(f"Fallo al validar la sesión: {exc}") from exc

        acceso = cls(cliente, Actor(user_id="", email="", nombre="", rol=PACIENTE))
        acceso.actor = acceso._resolver_actor(usuario)
        evento(log, "sesion_validada", rol=acceso.actor.rol, centro=acceso.actor.centro)
        return acceso

    @classmethod
    def como_servicio(cls) -> AccesoRoble:
        """Actúa como la cuenta de servicio. Sólo para trabajo por reloj."""
        ajustes = config()
        email, password = credenciales_servicio()

        cliente = RobleClient(
            base_url=ajustes.roble_base_url,
            contract_id=ajustes.roble_contract_id,
            timeout=20.0,
        )
        try:
            usuario = cliente.login(email=email, password=password, persist_session=False)
        except RobleHttpError as exc:
            if exc.status_code == 401:
                raise NoAutorizado(
                    "La cuenta de servicio de ROBLE no autenticó: revisa las credenciales en Parameter Store"
                ) from exc
            raise ErrorDeDatos(f"ROBLE respondió {exc.status_code} al autenticar el servicio") from exc
        except (RobleNetworkError, RobleTimeoutError) as exc:
            raise ErrorDeDatos("No se pudo alcanzar ROBLE para autenticar el servicio") from exc

        actor = Actor(
            user_id=usuario.user_id or usuario.id,
            email=usuario.email,
            nombre=usuario.name or "servicio",
            rol=SERVICIO,
        )
        return cls(cliente, actor)

    def cerrar(self) -> None:
        self._db.close()

    # --------------------------------------------------------------- identidad

    def _resolver_actor(self, usuario: User) -> Actor:
        """Deduce el rol del usuario autenticado.

        El `User` del SDK no tiene campo `rol`: ROBLE lo entrega —cuando lo
        entrega— dentro del cuerpo crudo de `/me` o en `extra`. Se busca ahí
        primero y, si no aparece, se cae a la tabla `perfiles`, que es la fuente
        que este proyecto controla. Sin ninguna de las dos, el rol es
        `paciente`: el menos privilegiado.
        """
        user_id = usuario.user_id or usuario.id
        rol = _rol_declarado(usuario)
        centro = _centro_declarado(usuario)
        perfil_id = None

        if rol is None or centro is None:
            perfil = self._perfil_de(user_id)
            if perfil:
                perfil_id = fila_id(perfil)
                rol = rol or _normalizar_rol(perfil.get("rol"))
                centro = centro or _normalizar_centro(perfil.get("centro"))

        if rol is None:
            evento(log, "rol_no_declarado", user_id=user_id)
            rol = PACIENTE

        # Un administrativo tiene centro por definición del rol; no se acepta
        # que la tabla diga otra cosa.
        if rol in CENTRO_DE_ROL:
            centro = CENTRO_DE_ROL[rol]

        return Actor(
            user_id=user_id,
            email=usuario.email,
            nombre=usuario.name or usuario.email,
            rol=rol,
            centro=centro,
            perfil_id=perfil_id,
        )

    def _perfil_de(self, user_id: str) -> dict[str, Any] | None:
        filas = self._leer(PERFILES, {"user_id": user_id})
        return filas[0] if filas else None

    def perfil_de(self, user_id: str) -> dict[str, Any] | None:
        return self._perfil_de(user_id)

    # ------------------------------------------------------------- transporte

    def _leer(self, tabla: str, filtros: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            return self._db.read(tabla, filtros or {})
        except RobleHttpError as exc:
            if exc.status_code in (401, 403):
                raise NoAutorizado(f"ROBLE no autoriza leer {tabla}: {exc}") from exc
            if exc.status_code == 400:
                # 400 en /read significa tabla o columna inexistente: es un
                # error nuestro de esquema, no del usuario.
                raise ErrorDeDatos(f"Esquema inesperado leyendo {tabla}: {exc}") from exc
            raise ErrorDeDatos(f"ROBLE respondió {exc.status_code} leyendo {tabla}") from exc
        except (RobleNetworkError, RobleTimeoutError) as exc:
            raise ErrorDeDatos(f"ROBLE no respondió leyendo {tabla}") from exc

    def _crear(self, tabla: str, datos: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._db.create(tabla, datos)
        except RobleHttpError as exc:
            if exc.status_code in (401, 403):
                raise NoAutorizado(f"ROBLE no autoriza escribir en {tabla}: {exc}") from exc
            if exc.status_code == 400:
                raise ErrorDeDatos(
                    f"Esquema inesperado escribiendo en {tabla}"
                    f" (¿columna que no existe?): {exc}"
                ) from exc
            raise ErrorDeDatos(f"ROBLE respondió {exc.status_code} escribiendo en {tabla}") from exc
        except (RobleNetworkError, RobleTimeoutError) as exc:
            raise ErrorDeDatos(f"ROBLE no respondió escribiendo en {tabla}") from exc

    def _actualizar(self, tabla: str, fila_id: str, datos: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._db.update(tabla, fila_id, datos)
        except RobleHttpError as exc:
            if exc.status_code == 404:
                raise NoEncontrado(f"No existe el registro {fila_id} en {tabla}") from exc
            if exc.status_code in (401, 403):
                raise NoAutorizado(f"ROBLE no autoriza actualizar {tabla}: {exc}") from exc
            if exc.status_code == 400:
                # El 400 de una actualización es casi siempre una columna que no
                # existe, y el mensaje genérico costó una tarde: `canalizar_caso`
                # enviaba `canalizado_en` y el log sólo decía «ROBLE respondió 400
                # actualizando casos», que se lee como un problema de permisos.
                raise ErrorDeDatos(
                    f"Esquema inesperado actualizando {tabla}"
                    f" (¿columna que no existe?): {exc}"
                ) from exc
            raise ErrorDeDatos(f"ROBLE respondió {exc.status_code} actualizando {tabla}") from exc
        except (RobleNetworkError, RobleTimeoutError) as exc:
            raise ErrorDeDatos(f"ROBLE no respondió actualizando {tabla}") from exc
        except RobleAuthError as exc:
            raise NoAutorizado("La sesión del llamante venció durante la operación") from exc

    # ------------------------------------------------------------------- casos

    def caso(self, caso_id: str) -> dict[str, Any]:
        filas = self._leer(CASOS, {"_id": caso_id})
        if not filas:
            raise NoEncontrado(f"No existe el caso {caso_id}")
        return filas[0]

    def caso_visible(self, caso_id: str) -> dict[str, Any]:
        """El caso, comprobando además que este actor tenga por qué verlo.

        ROBLE ya filtra por rol a nivel de tabla, pero eso no distingue *qué
        filas* de `casos` corresponden a quién. Esa comprobación es del dominio
        y va aquí, no en el prompt del agente: un modelo no es un control de
        acceso.
        """
        registro_caso = self.caso(caso_id)
        actor = self.actor

        if actor.rol == SERVICIO:
            return registro_caso
        if actor.es_paciente:
            if registro_caso.get("paciente_user_id") != actor.user_id:
                raise SinPermiso("Ese caso no es tuyo")
            return registro_caso
        if actor.es_administrativo:
            if registro_caso.get("centro") != actor.centro:
                raise SinPermiso(f"Ese caso no pertenece al {actor.centro}")
            return registro_caso
        if actor.rol == PROFESIONAL:
            citas = self._leer(CITAS, {"caso_id": caso_id})
            mias = [c for c in citas if c.get("profesional_user_id") == actor.user_id]
            if not mias:
                raise SinPermiso("No tienes una cita asignada con ese caso")
            return registro_caso

        raise SinPermiso("Rol sin acceso a casos")

    def caso_abierto_de(self, user_id: str) -> dict[str, Any] | None:
        """El caso vivo del paciente, si tiene uno.

        Un paciente tiene como máximo un caso sin cerrar: si vuelve a escribir,
        continúa el mismo hilo en lugar de abrir uno nuevo. Es lo que hace que
        el seguimiento tenga sentido.
        """
        abiertos = [
            c
            for c in self._leer(CASOS, {"paciente_user_id": user_id})
            if c.get("estado") != CASO_CERRADO
        ]
        abiertos.sort(key=lambda c: str(c.get("creado_en") or ""), reverse=True)
        return abiertos[0] if abiertos else None

    def abrir_caso(self, *, motivo: str) -> dict[str, Any]:
        fila = self._crear(
            CASOS,
            {
                "paciente_user_id": self.actor.user_id,
                "paciente_nombre": self.actor.nombre,
                "paciente_email": self.actor.email,
                "estado": CASO_ABIERTO,
                "centro": None,
                "nivel_urgencia": None,
                "motivo": motivo[:500],
                "resumen_triaje": None,
                "creado_en": reloj.iso(),
                "actualizado_en": reloj.iso(),
            },
        )
        evento(log, "caso_abierto", caso_id=fila_id(fila))
        return fila

    def actualizar_caso(self, caso_id: str, cambios: dict[str, Any]) -> dict[str, Any]:
        cambios = {**cambios, "actualizado_en": reloj.iso()}
        return self._actualizar(CASOS, caso_id, cambios)

    def casos_del_centro(self, centro: str) -> list[dict[str, Any]]:
        return self._leer(CASOS, {"centro": centro})

    # ---------------------------------------------------------- conversaciones

    def mensajes(self, caso_id: str, *, maximo: int = 30) -> list[dict[str, Any]]:
        """Historial del caso, en orden y recortado a las últimas vueltas.

        El recorte no es sólo por coste de tokens: un historial largo diluye las
        instrucciones del agente. Lo que hay antes del recorte sigue en ROBLE.
        """
        filas = self._leer(CONVERSACIONES, {"caso_id": caso_id})
        filas.sort(key=lambda f: str(f.get("creado_en") or ""))
        return filas[-maximo:]

    def anotar_mensaje(self, *, caso_id: str, agente: str, autor: str, contenido: str) -> None:
        self._crear(
            CONVERSACIONES,
            {
                "caso_id": caso_id,
                "agente": agente,
                "autor": autor,  # paciente | agente | herramienta
                "contenido": contenido,
                "creado_en": reloj.iso(),
            },
        )

    # ------------------------------------------------------------ profesionales

    def profesionales_de(self, centro: str) -> list[dict[str, Any]]:
        return [
            p
            for p in self._leer(PROFESIONALES, {"centro": centro})
            if p.get("activo") in (True, "true", 1, None)
        ]

    def profesional(self, profesional_id: str) -> dict[str, Any]:
        filas = self._leer(PROFESIONALES, {"_id": profesional_id})
        if not filas:
            raise NoEncontrado(f"No existe el profesional {profesional_id}")
        return filas[0]

    def horarios_de(self, profesional_id: str) -> list[dict[str, Any]]:
        return self._leer(HORARIOS, {"profesional_id": profesional_id})

    # -------------------------------------------------------------------- cupos

    def cupos_libres(
        self,
        *,
        centro: str,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        maximo: int = 10,
    ) -> list[dict[str, Any]]:
        """Cupos disponibles del centro, ordenados por cercanía.

        El rango de fechas se filtra en memoria porque `read` sólo admite
        igualdad. Con la agenda de un prototipo son decenas de filas; cuando
        deje de serlo, esto pasa a una consulta guardada con `execute_query`.
        """
        inicio = desde or reloj.ahora()
        filas = self._leer(CUPOS, {"centro": centro, "estado": CUPO_LIBRE})

        candidatos = []
        for cupo in filas:
            momento = reloj.desde_iso(cupo.get("inicio"))
            if not momento or momento < inicio:
                continue
            if hasta and momento > hasta:
                continue
            candidatos.append((momento, cupo))

        candidatos.sort(key=lambda par: par[0])
        return [cupo for _, cupo in candidatos[:maximo]]

    def cupo(self, cupo_id: str) -> dict[str, Any]:
        filas = self._leer(CUPOS, {"_id": cupo_id})
        if not filas:
            raise NoEncontrado(f"No existe el cupo {cupo_id}")
        return filas[0]

    def reservar_cupo(self, *, cupo_id: str, caso_id: str) -> dict[str, Any]:
        """Reserva un cupo con el patrón reservar-releer-reconciliar.

        ROBLE no tiene escritura condicional, así que dos peticiones simultáneas
        pueden pasar las dos por el `if estado == libre`. Lo que las separa es el
        testigo: cada intento escribe un identificador propio y vuelve a leer.
        La última escritura gana, y la otra parte lo descubre porque su testigo
        ya no está en la fila.

        No es serialización perfecta —hay una ventana en la que ambas ven
        `libre`—, pero sí garantiza que **nunca queden dos citas sobre el mismo
        cupo**, que es la propiedad que importa. La consecuencia visible para el
        perdedor es un 409 y una lista de alternativas, no una doble reserva.
        """
        actual = self.cupo(cupo_id)
        if actual.get("estado") == CUPO_CONFIRMADO:
            raise Conflicto("Ese espacio ya fue confirmado por otra persona")

        reservado_hace = reloj.desde_iso(actual.get("reservado_en"))
        if actual.get("estado") == CUPO_RESERVADO and reservado_hace:
            # Una reserva reciente de otro caso se respeta; una vieja se pisa
            # (la limpia además `liberar_reservas_vencidas`).
            if actual.get("caso_id") != caso_id and reservado_hace > reloj.mas(minutos=-2):
                raise Conflicto("Alguien está reservando ese espacio en este momento")

        testigo = uuid.uuid4().hex
        self._actualizar(
            CUPOS,
            cupo_id,
            {
                "estado": CUPO_RESERVADO,
                "caso_id": caso_id,
                "reserva_testigo": testigo,
                "reservado_en": reloj.iso(),
            },
        )

        # Releer: es el único árbitro disponible.
        confirmado = self.cupo(cupo_id)
        if confirmado.get("reserva_testigo") != testigo:
            evento(log, "reserva_perdida", cupo_id=cupo_id, caso_id=caso_id)
            raise Conflicto("Otra persona tomó ese espacio mientras lo reservábamos")

        evento(log, "cupo_reservado", cupo_id=cupo_id, caso_id=caso_id)
        return confirmado

    def confirmar_cita(self, *, cupo_id: str, caso_id: str) -> dict[str, Any]:
        """Convierte una reserva propia en cita. Debe seguir a `reservar_cupo`."""
        cupo = self.cupo(cupo_id)
        if cupo.get("caso_id") != caso_id or cupo.get("estado") != CUPO_RESERVADO:
            raise Conflicto("La reserva de ese espacio ya no es válida")

        profesional = self.profesional(str(cupo.get("profesional_id")))
        caso = self.caso(caso_id)

        cita = self._crear(
            CITAS,
            {
                "caso_id": caso_id,
                "cupo_id": cupo_id,
                "profesional_id": cupo.get("profesional_id"),
                "profesional_user_id": profesional.get("user_id"),
                "profesional_nombre": profesional.get("nombre"),
                "paciente_user_id": caso.get("paciente_user_id"),
                "centro": cupo.get("centro"),
                "inicio": cupo.get("inicio"),
                "fin": cupo.get("fin"),
                "estado": "confirmada",
                "creado_en": reloj.iso(),
            },
        )

        self._actualizar(CUPOS, cupo_id, {"estado": CUPO_CONFIRMADO})
        self.actualizar_caso(caso_id, {"estado": CASO_AGENDADO})
        evento(log, "cita_confirmada", caso_id=caso_id, cupo_id=cupo_id, cita_id=fila_id(cita))
        return cita

    def liberar_cupo(self, cupo_id: str) -> None:
        self._actualizar(
            CUPOS,
            cupo_id,
            {"estado": CUPO_LIBRE, "caso_id": None, "reserva_testigo": None, "reservado_en": None},
        )

    def liberar_reservas_vencidas(self, *, minutos: int = 2) -> int:
        """Devuelve a `libre` los cupos reservados que nadie confirmó.

        Es la mitad "reconciliar" del patrón: sin esto, una Lambda que muere
        entre la reserva y la confirmación deja el cupo bloqueado para siempre.
        """
        limite = reloj.mas(minutos=-minutos)
        liberados = 0
        for cupo in self._leer(CUPOS, {"estado": CUPO_RESERVADO}):
            desde = reloj.desde_iso(cupo.get("reservado_en"))
            if desde and desde < limite:
                cupo_id = fila_id(cupo)
                if cupo_id:
                    self.liberar_cupo(cupo_id)
                    liberados += 1
        if liberados:
            evento(log, "reservas_liberadas", cantidad=liberados)
        return liberados

    def citas_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
        return self._leer(CITAS, {"caso_id": caso_id})

    def citas_del_profesional(self, user_id: str) -> list[dict[str, Any]]:
        return self._leer(CITAS, {"profesional_user_id": user_id})

    # ------------------------------------------------------- plan y seguimiento

    def plan_del_caso(self, caso_id: str) -> dict[str, Any] | None:
        planes = self._leer(PLANES, {"caso_id": caso_id})
        planes.sort(key=lambda p: str(p.get("creado_en") or ""))
        return planes[-1] if planes else None

    def indicaciones_activas(self, caso_id: str) -> list[dict[str, Any]]:
        return [
            i
            for i in self._leer(INDICACIONES, {"caso_id": caso_id})
            if i.get("activa") in (True, "true", 1)
        ]

    def todas_las_indicaciones_activas(self) -> list[dict[str, Any]]:
        return self._leer(INDICACIONES, {"activa": True})

    def registrar_adherencia(
        self, *, caso_id: str, indicacion_id: str, cumplida: bool, nota: str = ""
    ) -> dict[str, Any]:
        return self._crear(
            ADHERENCIA,
            {
                "caso_id": caso_id,
                "indicacion_id": indicacion_id,
                "cumplida": cumplida,
                "nota": nota[:400],
                "reportado_en": reloj.iso(),
            },
        )

    def adherencia_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
        filas = self._leer(ADHERENCIA, {"caso_id": caso_id})
        filas.sort(key=lambda f: str(f.get("reportado_en") or ""))
        return filas

    def registrar_evolucion(
        self, *, caso_id: str, escala: int, nota: str = ""
    ) -> dict[str, Any]:
        return self._crear(
            EVOLUCION,
            {
                "caso_id": caso_id,
                "escala": max(0, min(10, int(escala))),
                "nota": nota[:1000],
                "reportado_en": reloj.iso(),
            },
        )

    def evolucion_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
        filas = self._leer(EVOLUCION, {"caso_id": caso_id})
        filas.sort(key=lambda f: str(f.get("reportado_en") or ""))
        return filas

    # ------------------------------------------------------------------ eventos

    def registrar_evento(
        self, *, caso_id: str | None, tipo: str, severidad: str = "info", detalle: Any = None
    ) -> dict[str, Any]:
        """Rastro de lo que pasó. Es la bitácora del caso, no un log técnico.

        Se escribe en ROBLE y no sólo en CloudWatch porque el profesional que
        atiende tiene que poder verla, y no tiene acceso a la cuenta de AWS.
        """
        return self._crear(
            EVENTOS,
            {
                "caso_id": caso_id,
                "tipo": tipo,
                "severidad": severidad,
                "actor_user_id": self.actor.user_id,
                "actor_rol": self.actor.rol,
                "detalle": detalle if isinstance(detalle, (dict, list)) else {"texto": str(detalle or "")},
                "creado_en": reloj.iso(),
            },
        )

    def eventos_del_caso(self, caso_id: str) -> list[dict[str, Any]]:
        filas = self._leer(EVENTOS, {"caso_id": caso_id})
        filas.sort(key=lambda f: str(f.get("creado_en") or ""))
        return filas

    # ------------------------------------------------------------ recordatorios

    def recordatorios_pendientes(self, *, hasta: datetime) -> list[dict[str, Any]]:
        pendientes = []
        for fila in self._leer(RECORDATORIOS, {"estado": "pendiente"}):
            momento = reloj.desde_iso(fila.get("programado_para"))
            if momento and momento <= hasta:
                pendientes.append(fila)
        pendientes.sort(key=lambda f: str(f.get("programado_para") or ""))
        return pendientes

    def recordatorios_de_indicacion(self, indicacion_id: str) -> list[dict[str, Any]]:
        return self._leer(RECORDATORIOS, {"indicacion_id": indicacion_id})

    def programar_recordatorio(
        self, *, caso_id: str, indicacion_id: str, cuando: datetime, texto: str
    ) -> dict[str, Any]:
        return self._crear(
            RECORDATORIOS,
            {
                "caso_id": caso_id,
                "indicacion_id": indicacion_id,
                "programado_para": reloj.iso(cuando),
                "estado": "pendiente",
                "canal": "correo",
                "texto": texto[:500],
                "creado_en": reloj.iso(),
            },
        )

    def marcar_recordatorio(self, recordatorio_id: str, *, estado: str, detalle: str = "") -> None:
        self._actualizar(
            RECORDATORIOS,
            recordatorio_id,
            {"estado": estado, "detalle": detalle[:300], "enviado_en": reloj.iso()},
        )


# --------------------------------------------------------- lectura defensiva

def _normalizar_rol(valor: Any) -> str | None:
    if not valor:
        return None
    if isinstance(valor, (list, tuple)):
        for elemento in valor:
            rol = _normalizar_rol(elemento)
            if rol:
                return rol
        return None
    texto = str(valor).strip().lower().replace("-", "_").replace(" ", "_")
    equivalencias = {
        "admin_cmu": ADMIN_CMU,
        "administrativa_cmu": ADMIN_CMU,
        "cmu": ADMIN_CMU,
        "admin_cae": ADMIN_CAE,
        "administrativa_cae": ADMIN_CAE,
        "cae": ADMIN_CAE,
        "medico": PROFESIONAL,
        "psicologo": PROFESIONAL,
        "profesional": PROFESIONAL,
        "paciente": PACIENTE,
        "usuario": PACIENTE,
        "servicio": SERVICIO,
    }
    return equivalencias.get(texto, texto if texto in ROLES else None)


def _normalizar_centro(valor: Any) -> str | None:
    if not valor:
        return None
    texto = str(valor).strip().upper()
    return texto if texto in (CMU, CAE) else None


def _rol_declarado(usuario: User) -> str | None:
    """Busca el rol en todos los sitios donde ROBLE lo ha puesto o podría ponerlo."""
    fuentes: list[Any] = []
    crudo = usuario.raw or {}
    for clave in ("role", "rol", "roles", "userRole"):
        if crudo.get(clave):
            fuentes.append(crudo[clave])
    extra = usuario.extra or {}
    for clave in ("role", "rol", "roles"):
        if extra.get(clave):
            fuentes.append(extra[clave])

    for fuente in fuentes:
        rol = _normalizar_rol(fuente)
        if rol:
            return rol
    return None


def _centro_declarado(usuario: User) -> str | None:
    for contenedor in (usuario.raw or {}, usuario.extra or {}):
        for clave in ("centro", "center", "sede"):
            centro = _normalizar_centro(contenedor.get(clave))
            if centro:
                return centro
    return None
