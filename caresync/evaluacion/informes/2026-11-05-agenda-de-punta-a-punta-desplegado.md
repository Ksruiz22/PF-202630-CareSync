# Agenda de punta a punta, desplegada — 5 de noviembre de 2026

El mismo guion de ocho turnos del 2/11 (`2026-11-02-agenda-de-punta-a-punta-local.md`),
esta vez contra el API desplegado: `main` en 4378ba0, con la versión de noviembre
(PR #30), la migración a ROBLE producción (PR #33) y el `_id` generado por el código
(PR #35). Claude Haiku 4.5, la salvaguarda y el ROBLE de producción reales. Cuenta de
paciente de evaluación y el médico de prueba del CMU, con cupos de 8:00 a 10:00 hasta
el 13/11.

**El 4/11 esta misma corrida no pudo empezar.** Al importar el backup en ROBLE
producción, las tablas perdieron el `DEFAULT gen_random_uuid()` del `_id`, y ROBLE
saltaba cada inserción con «Tipos inválidos: _id (esperado: uuid)»: el sistema
desplegado no creaba casos, mensajes ni citas, y la persona leía «La base de datos del
proyecto no respondió». La consola no deja reponer un `DEFAULT`, así que el PR #35
pone el `_id` al crear, en las Lambdas, la PWA y la app móvil. La inserción sin `_id`
sigue fallando en la base; la del sistema ya no la hace.

## Resultado

**Ocho de ocho turnos con su herramienta**, en un solo caso (26558b87), sin que el
control de citas inventadas tuviera que intervenir.

| Turno | La persona | El agente | Herramientas |
|---|---|---|---|
| 1 | Le duele la rodilla, quiere cita | Canaliza al CMU con nivel 3 y ofrece tres cupos: viernes 06/11 a las 08:00 y a las 09:00, lunes 09/11 a las 09:00 | `canalizar_caso`, `consultar_disponibilidad` |
| 2 | «La primera» | Agenda el viernes 06/11 a las 08:00 | `agendar_cita`, `notificar_profesional` |
| 3 | «¿Puedo cambiarla para el viernes 6 a las 9:00?» | Le pregunta si confirma, con las dos horas | `reprogramar_cita` sin confirmar |
| 4 | «Sí, confirmo» | La cambia a las 09:00 | `reprogramar_cita` confirmado |
| 5 | «Quiero cancelarla» | Le pregunta si confirma | `cancelar_cita` sin confirmar |
| 6 | «Sí, cancélala» | La cancela; el caso vuelve a `canalizado` | `cancelar_cita` confirmado |
| 7 | «¿Hay algo el lunes?» | Ofrece lunes 09/11 a las 09:00 y a las 09:30, y viernes 06/11 a las 08:00 | `consultar_disponibilidad` |
| 8 | «La primera» | Agenda el lunes 09/11 a las 09:00; el caso pasa a `agendado` | `agendar_cita`, `notificar_profesional` |

En ROBLE, al terminar: la cita del viernes a las 08:00 cancelada por el cambio, la del
viernes a las 09:00 cancelada a pedido de la persona y la del lunes a las 09:00
confirmada. Los dos cupos del viernes volvieron a `libre`; el del lunes quedó
`confirmado` con el caso. La agenda del médico pasó de 28 a 27 cupos libres, uno por
la única cita en pie.

## Lo que se ve distinto de la corrida local

- Al «¿hay algo el lunes?» dos de las tres opciones fueron del lunes; el 2/11, al
  pedir el jueves, ofreció martes, miércoles y jueves. Sigue sin filtrar por día (el
  escenario A5), pero ordena mejor.
- Es una corrida. La batería adversarial del mismo día, contra el mismo despliegue,
  está en `2026-11-05-adversarial-desplegado.md`.
