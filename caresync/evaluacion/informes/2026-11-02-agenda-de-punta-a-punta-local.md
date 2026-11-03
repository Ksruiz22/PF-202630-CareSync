# Agenda de punta a punta, en local — 2 de noviembre de 2026

Orquestador en local (`servidor.py`) con el código de `kr-version-noviembre`, contra
el Bedrock (Claude Haiku 4.5), la salvaguarda y el ROBLE reales. Cuenta de paciente de
evaluación. Un médico de prueba nuevo del CMU, con 36 cupos libres entre el 3 y el
13/11, de 8:00 a 10:00. El guion es de ocho turnos: síntomas, elegir un cupo, pedir el
cambio, confirmarlo, pedir la cancelación, confirmarla, volver a pedir cita y elegirla.

Es la primera vez que la agenda se prueba completa contra el modelo. Cancelar y
cambiar una cita existen desde el 29/10, y hasta hoy sólo tenían pruebas sin red.

## Las corridas

| Corrida | Código | Qué pasó |
|---|---|---|
| 1 | La rama tal cual | Agendó bien. Al «sí, confirmo» del cambio respondió «listo, tu cita está reprogramada» **sin llamar a nada**, y la cita siguió el martes. |
| 2 | + nota `[sistema]` del cambio por confirmar, prompt reforzado | `agendar_cita` no encontró un cupo que estaba libre: el modelo reconstruyó mal su hora. Después preguntó por cambiar una cita del martes a las 9:00 que no existía y cerró con «listo, tu cita quedó agendada» sin ninguna cita. |
| 3 | + espacios mostrados en la nota, control de citas inventadas | Agendó bien. El modelo volvió a anunciar el cambio sin hacerlo; el control lo frenó y en la segunda respuesta llamó a `reprogramar_cita`. La persona leyó «Tienes razón, disculpa»: el modelo le contestó al aviso interno. |
| 4 | Mismo caso: cancelar y volver a agendar | Cuatro turnos sin herramientas. El control frenó dos afirmaciones falsas, que la persona recibió como texto fijo con su cita real, y el agente ofreció un cupo a las 10:00 que no existe. |
| 5 | + recordatorio junto al mensaje | Turnos 1 a 4 bien. Al cancelar escribió «queda cancelada» sin herramienta, y el control no lo atrapó: sólo reconocía «quedó». |
| 6 | + herramienta exigida en la primera vuelta | **Ocho de ocho turnos con su herramienta.** El control no tuvo que intervenir. |

Las corridas 2 a 6 empiezan con un caso nuevo, salvo la 4, que siguió el de la 3.

## La corrida 6, turno a turno

| Turno | La persona | El agente | Herramientas |
|---|---|---|---|
| 1 | Le duele la rodilla, quiere cita | Canaliza al CMU con nivel 3 y ofrece tres cupos | `canalizar_caso`, `consultar_disponibilidad` |
| 2 | «La primera» | Agenda el martes 03/11 a las 08:30 | `agendar_cita`, `notificar_profesional` |
| 3 | «¿Puedo cambiarla al miércoles 4 a las 9:00?» | Le pregunta si confirma, con las dos fechas | `reprogramar_cita` sin confirmar |
| 4 | «Sí, confirmo» | La cambia | `reprogramar_cita` confirmado |
| 5 | «Quiero cancelarla» | Le pregunta si confirma | `cancelar_cita` sin confirmar |
| 6 | «Sí, cancélala» | La cancela; el caso vuelve a `canalizado` | `cancelar_cita` confirmado |
| 7 | «¿Hay algo el jueves?» | Ofrece martes, miércoles y jueves | `consultar_disponibilidad` |
| 8 | «La primera» | Agenda el martes 03/11 a las 08:30 | `agendar_cita`, `notificar_profesional` |

Las citas del caso en ROBLE al terminar: la del martes a las 08:30 cancelada por el
cambio, la del miércoles a las 09:00 cancelada a pedido de la persona y otra vez la
del martes a las 08:30, confirmada. Cada cupo quedó libre o tomado según su cita.

## Por qué pasaba

El historial que recibe el modelo es sólo texto: los bloques de herramientas no se
rehidratan entre peticiones. En una conversación larga, todas sus respuestas
anteriores son prosa y el modelo la imita. Por eso fallaba de la tercera vuelta en
adelante y casi nunca en la primera. Reforzar el prompt no bastó, y el recordatorio
tampoco. Lo que lo resolvió fue exigir una herramienta en la primera vuelta de cada
turno de agenda (`toolChoice: any`). Las otras tres piezas —recordatorio, nota de
espacios y control de citas inventadas— quedan como red: la nota le da la hora literal
del cupo elegido, y el control impide que una afirmación falsa llegue a la persona.

## Lo que queda

- **Es una sola corrida buena.** Falta repetir el guion varias veces, medir cuánto
  tarda cada turno con la vuelta exigida y hacerlo también contra lo desplegado.
- Al «¿hay algo el jueves?» ofreció martes, miércoles y jueves: no filtra por día. Es
  el escenario A5 de la revisión, fuera del alcance de noviembre.
- En el primer turno, el texto junta lo que dicen triaje y agenda, con frases repetidas
  («voy a buscar los espacios»).
- La respuesta dice «Centro Médico Uninorte» y la PWA, «Centro Médico Universitario».
- Las corridas dejaron tres citas confirmadas en casos que el script de prueba cerró
  (3/11 a las 8:00, y 4/11 a las 8:00 y a las 8:30). Ocupan cupos del médico de prueba.
