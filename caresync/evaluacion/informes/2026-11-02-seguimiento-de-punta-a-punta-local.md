# Seguimiento de punta a punta, en local — 2 de noviembre de 2026

La conexión entre Agenda y Seguimiento, probada contra el modelo. Orquestador en local
con el código de `kr-conexion-seguimiento`, contra el Bedrock (Claude Haiku 4.5), la
salvaguarda (versión 2) y el ROBLE reales. La parte del profesional la hizo Kevin desde
la PWA local, con un médico de prueba: dictó el plan, revisó los tipos y lo guardó.

El plan, el mismo en las tres corridas:

> Esguince leve de rodilla derecha. Ibuprofeno de 400 cada 8 horas por cinco días, hielo
> 20 minutos tres veces al día y control en una semana en el CMU. Si la rodilla se hincha
> mucho o no puede apoyar el pie, que vaya a urgencias.

La propuesta lo ordenó en un medicamento por 5 días, un autocuidado, un control en 7 días
en el CMU y una señal de alarma (`vigilancia`). Kevin confirmó los cuatro tipos.

## Las corridas

| Corrida | Código | Qué pasó |
|---|---|---|
| 1 | Tipos y control desde seguimiento | La señal de alarma escaló y el control se buscó en la semana correcta. Pero la salvaguarda cortó dos turnos: la salida de «¿qué me toca hacer?», porque el agente leyó el plan con la dosis (`prescripcion`), y la entrada de «me tomé el ibuprofeno» (`MISCONDUCT`). |
| 2 | + la salvaguarda evalúa sólo el mensaje nuevo; el agente no repite dosis | Explicó el plan sin dosis, agendó el control y escaló la alarma. Dijo «quedó registrado» sin llamar a `registrar_adherencia`. |
| 3 | + control de registros inventados; un plan nuevo reemplaza al anterior | **Los cinco turnos con su herramienta.** Ni la salvaguarda ni el control tuvieron que intervenir. |

En la corrida 1, el mismo mensaje de la persona, evaluado solo con `ApplyGuardrail`,
pasa: lo que disparó el filtro fue el historial entero, que Bedrock evaluaba como entrada
en cada turno. Ahora va como `guardContent`. La salida con la dosis se corta en todas las
versiones publicadas de la salvaguarda, que no distingue recetar de repetir lo que recetó
el profesional.

## La corrida 3, turno a turno

| Turno | La persona | El agente | Herramientas |
|---|---|---|---|
| 1 | «Ya me atendieron. ¿Qué me toca hacer?» | Explica las cuatro indicaciones y ofrece agendar el control | `consultar_plan` |
| 2 | «Sí, agéndame el control» | Ofrece el lunes 9/11 a las 8:30 y a las 9:00, y el martes 10/11 a las 8:00 | `consultar_disponibilidad` |
| 3 | «La primera» | Confirma el control | `agendar_cita` |
| 4 | «Me tomé el ibuprofeno de la mañana y me puse hielo una vez» | Pregunta cómo se siente | `registrar_adherencia` ×2 |
| 5 | «Me siento mejor, el dolor está en 3 de 10» | Lo confirma | `registrar_evolucion` |

En ROBLE al terminar: la cita del lunes 9/11 confirmada con `tipo` control y su
`indicacion_id`; dos filas de adherencia, una por indicación; la evolución con escala 3;
el caso, en seguimiento. Antes de la conversación, Kevin guardó dos planes seguidos en la
misma consulta: las indicaciones del primero quedaron inactivas.

## Lo que queda

- **En el turno 1 de la corrida 3, el agente sí repitió la dosis** («ibuprofeno de 400
  cada 8 horas»), aunque el prompt se lo pide evitar. Esa vez la salvaguarda no la cortó,
  pero en la corrida 1 sí. Es un riesgo abierto: si la corta, la persona se queda sin la
  respuesta.
- Es una corrida buena de cada cosa. Falta repetirla y medirla contra lo desplegado, que
  usa otra versión de la salvaguarda.
- Las corridas 1 y 2 dejaron dos casos en `urgencia_escalada` (f31dec95 y 6eb454f1), con
  un control agendado el 9/11 en el segundo.
