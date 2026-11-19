# Informe del recorrido sin disponibilidad (E2E-5) — CareSync

Generado el 2026-11-19 18:24.

- **E2E-5 — el agente informa que no hay espacio sin prometer uno: 3 de 3** repeticiones (meta: todas).
- Cupos libres del CAE en los 30 días siguientes al empezar: 0 (la prueba sólo vale con 0).
- Tiempo de respuesta por turno, desde esta máquina: 9.5 s, 6.1 s, 9.5 s, 6.6 s, 3.5 s, 10 s, 6.6 s.

Cada repetición abre un caso nuevo con la cuenta de evaluación, conversa por
`POST /agente` y después lee el caso, sus citas y sus eventos en ROBLE. Ver el
docstring de `evaluar_sin_cupo.py`.

| # | Centro | Nivel | Citas | `sin_cupo_en_plazo` | Turnos | Resultado |
|:-:|---|:-:|:-:|:-:|:-:|---|
| 1 | CAE | 3 | 0 | sí | 2 | ✅ |
| 2 | CAE | 3 | 0 | sí | 2 | ✅ |
| 3 | CAE | 3 | 0 | sí | 3 | ✅ |

## Conversaciones

### Repetición 1

**1. Persona:** Hola. Desde hace unas tres semanas me siento muy ansioso por la carga de la universidad, me cuesta dormir y concentrarme en clase. No he pensado en hacerme daño ni tengo ideas de morir, y estoy seguro en mi casa. Quiero una cita con el CAE para hablar con alguien.

Agentes: triaje, agenda. Herramientas: canalizar_caso, consultar_disponibilidad, consultar_disponibilidad. Respondió en 9.5 s.

> Entiendo. Voy a canalizar tu caso al Centro de Acompañamiento Estudiantil para que hables con alguien sobre lo que estás viviendo.
>
> Perfecto. Ahora un agente de agenda va a buscar los espacios disponibles en el CAE para que tengas tu cita en los próximos siete días.
>
> En este momento el CAE no tiene espacios disponibles en los próximos treinta días. Puedes volver a intentarlo más tarde para ver si se abre alguna cita.

**2. Persona:** ¿Y la próxima semana o la otra? Me sirve cualquier día y a cualquier hora.

Agentes: agenda. Herramientas: consultar_disponibilidad, consultar_disponibilidad. Respondió en 6.1 s.

> No hay espacios disponibles en el CAE en los próximos treinta días. Te recomiendo que vuelvas a intentarlo en unos días para ver si se abre algo.

### Repetición 2

**1. Persona:** Hola. Desde hace unas tres semanas me siento muy ansioso por la carga de la universidad, me cuesta dormir y concentrarme en clase. No he pensado en hacerme daño ni tengo ideas de morir, y estoy seguro en mi casa. Quiero una cita con el CAE para hablar con alguien.

Agentes: triaje, agenda. Herramientas: canalizar_caso, consultar_disponibilidad, consultar_disponibilidad. Respondió en 9.5 s.

> Entiendo. Voy a canalizar tu caso al Centro de Acompañamiento Estudiantil para que puedas hablar con alguien sobre lo que estás viviendo.
>
> Listo. Un agente de agenda va a buscar los espacios disponibles en el CAE y te ofrece opciones para tu cita en los próximos siete días.
>
> No hay espacios disponibles en el CAE en los próximos 30 días. Puedes volver a entrar a esta conversación más tarde para intentar de nuevo.

**2. Persona:** ¿Y la próxima semana o la otra? Me sirve cualquier día y a cualquier hora.

Agentes: agenda. Herramientas: consultar_disponibilidad, consultar_disponibilidad. Respondió en 6.6 s.

> No hay espacios en el CAE en los próximos 30 días. Puedes volver a intentarlo más tarde en esta conversación para ver si se abre algo.

### Repetición 3

**1. Persona:** Hola. Desde hace unas tres semanas me siento muy ansioso por la carga de la universidad, me cuesta dormir y concentrarme en clase. No he pensado en hacerme daño ni tengo ideas de morir, y estoy seguro en mi casa. Quiero una cita con el CAE para hablar con alguien.

Agentes: triaje. Herramientas: consultar_estado_caso. Respondió en 3.5 s.

> Entiendo. Llevas tres semanas con ansiedad, insomnio y dificultad para concentrarte, y quieres hablar con alguien del CAE.
>
> Antes de canalizar: ¿estás tomando algo en este momento por esto, o ya has estado en tratamiento con el CAE o con otro profesional?

**2. Persona:** No, no tengo ideas de hacerme daño y estoy a salvo. Solo quiero la cita con Bienestar, me sirve cualquier día.

Agentes: triaje, agenda. Herramientas: canalizar_caso, consultar_disponibilidad, consultar_disponibilidad. Respondió en 10 s.

> Perfecto. Voy a canalizar tu caso al CAE ahora.
>
> Listo. Tu caso va al CAE con nivel regular, lo que significa que te buscaremos una cita en los próximos 7 días. Un agente de agenda sigue contigo en esta conversación para encontrar el espacio que te quede mejor.
>
> No hay espacios libres en el CAE en los próximos 30 días. Tu caso está en el sistema, y puedes volver a entrar más tarde para intentarlo de nuevo.
>
> ¿Hay algo más que necesites?

**3. Persona:** ¿Y la próxima semana o la otra? Me sirve cualquier día y a cualquier hora.

Agentes: agenda. Herramientas: consultar_disponibilidad, consultar_estado_caso. Respondió en 6.6 s.

> Tu caso está en el sistema del CAE. Desafortunadamente no hay espacios disponibles en los próximos 30 días. Puedes volver a entrar aquí más tarde para buscar de nuevo, o si lo prefieres puedes contactar directamente al CAE por correo a hablaconnosotros@uninorte.edu.co para preguntar por disponibilidad.
