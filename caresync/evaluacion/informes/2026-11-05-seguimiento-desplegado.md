# Informe de seguimiento (M5) — CareSync

Generado el 2026-11-05 21:36.

- **M5 — retrocesos con alerta visible en menos de 5 min: 4 de 4** guiones (meta: todos).
- Alertas sin retroceso (falsas): 0, en 2 guiones estables y en los turnos previos al retroceso.
- Tiempo hasta la alerta: 4.6 s, 3.2 s, 5.2 s, 4.3 s (desde el envío hasta la lectura que la encontró, con el reloj de esta máquina).
- Guiones que cumplen en todo (alerta, escala registrada y sin escalar): 6 de 6.

Cada guion es un caso sembrado en seguimiento con un plan de prueba; la conversación
va por `POST /agente` y lo demás se lee en ROBLE. Ver el docstring de
`evaluar_seguimiento.py`.

| Guion | Grupo | Turnos | Escalas (dicha → registrada) | Alertas por turno | Resultado |
|---|---|:-:|---|---|---|
| estable-01 | estable | 2 | 6→6, 7→7 | 0, 0 | ✅ |
| estable-02 | estable | 2 | 7→7, 6→6 | 0, 0 | ✅ |
| caida-01 | caida | 2 | 8→8, 4→4 | 0, 1 (4.6 s) | ✅ |
| caida-02 | caida | 2 | 7→7, 4→4 | 0, 1 (3.2 s) | ✅ |
| escala-01 | escala | 1 | 3→3 | 1 (5.2 s) | ✅ |
| escala-02 | escala | 2 | 4→4, 3→3 | 0, 1 (4.3 s) | ✅ |

## Conversaciones

### estable-01 — Dos reportes que mejoran: no debe salir ninguna alerta.

**1. Persona:** Hola, te cuento cómo voy con la rodilla. De 0 a 10, donde 10 es sentirme muy bien, hoy estoy en 6.

Herramientas: consultar_plan, registrar_evolucion. Respondió en 9.2 s.

> Antes de registrar, déjame ver qué te indicaron para poder acompañarte bien.
>
> Bien, veo que te indicaron hacer ejercicios de fortalecimiento de cuádriceps. Registra cómo te sientes hoy.
>
> Listo, quedó registrado. ¿Cómo te ha ido con los ejercicios de fortalecimiento?

**2. Persona:** Hoy subí las escaleras de la universidad con menos molestia. Diría que estoy en 7 de 10.

Herramientas: registrar_evolucion. Respondió en 3.5 s.

> Gracias por el reporte. ¿Has estado haciendo los ejercicios de fortalecimiento?

### estable-02 — Una baja de un punto: está por debajo de la caída relevante y no debe alertar.

**1. Persona:** Hola. Esta semana he dormido un poco mejor. De 0 a 10, donde 10 es sentirme muy bien, me pondría un 7.

Herramientas: consultar_plan, registrar_evolucion. Respondió en 6.1 s.

> Voy a revisar tu plan primero para saber qué te indicaron.
>
> Qué bien que hayas dormido mejor esta semana. Voy a registrar cómo te sientes.
>
> Gracias por el reporte. ¿Cómo te ha ido con la respiración diafragmática antes de dormir?

**2. Persona:** Anoche me costó un poco más dormirme, pero en general sigo bien: 6 de 10.

Herramientas: consultar_plan, registrar_evolucion, registrar_adherencia. Respondió en 5.4 s.

> Entiendo. Anoche se te complicó un poco, pero en general vas bien. Voy a registrar que hoy te sientes en 6.
>
> Quedó registrado que sigues practicando la respiración diafragmática. ¿Hay algo más que quieras contarme?

### caida-01 — Caída de 4 puntos sin señales de alarma: alerta por caída, sin escalar a urgencias.

**1. Persona:** Hola, vengo a contarte cómo sigo con la espalda. De 0 a 10, donde 10 es sentirme muy bien, hoy estoy en 8.

Herramientas: consultar_plan, registrar_evolucion. Respondió en 6.4 s.

> Hola. Antes de nada, déjame revisar qué te indicaron para saber cómo acompañarte mejor.
>
> Qué bien que estés en 8. Cuéntame: ¿has estado aplicando calor en la zona lumbar y haciendo pausas activas durante el estudio?
>
> Gracias por el reporte.

**2. Persona:** Hoy amanecí peor, me duele más la espalda al agacharme. No tengo hormigueo ni debilidad en las piernas. Estoy en 4 de 10.

Herramientas: consultar_plan, registrar_evolucion. Respondió en 4.5 s.

> Entendido. Eso quedó registrado y el profesional lo va a ver.
>
> ¿Hoy aplicaste calor en la espalda?

### caida-02 — Caída de 3 puntos, justo en el umbral, en un caso del CAE.

**1. Persona:** Hola. Esta semana me he sentido más en calma con los ejercicios de respiración. De 0 a 10, donde 10 es sentirme muy bien, estoy en 7.

Herramientas: consultar_plan, registrar_evolucion. Respondió en 5.1 s.

> Qué bien que los ejercicios te estén ayudando. Déjame revisar el plan que te dejó el profesional para saber qué más estás trabajando.
>
> Perfecto. Voy a registrar cómo te sientes hoy.
>
> Gracias por el reporte. ¿Cómo te ha ido con la organización del tiempo que también te indicó el profesional?

**2. Persona:** Estos días volví a sentirme ansioso por las entregas y me cuesta concentrarme, aunque estoy a salvo y con mi familia. Hoy estoy en 4 de 10.

Herramientas: registrar_evolucion. Respondió en 3 s.

> Entiendo. ¿Qué pasó entre esta semana y la anterior que cambió?

### escala-01 — Primer reporte en 3: alerta por escala baja aunque no haya un reporte anterior.

**1. Persona:** Hola, te cuento: sigo con el malestar de estómago y casi no he tenido apetito. No tengo fiebre, ni vómito, ni sangre en las heces. De 0 a 10, donde 10 es sentirme muy bien, estoy en 3.

Herramientas: consultar_plan, registrar_evolucion. Respondió en 5.1 s.

> Déjame revisar qué te indicaron para poder acompañarte bien.
>
> Entiendo. Veo que te indicaron comer porciones pequeñas varias veces al día y evitar irritantes. Cuéntame: ¿cómo te ha ido con eso?

### escala-02 — Baja de un punto que llega a 3: alerta por escala, no por caída.

**1. Persona:** Hola. La tos sigue más o menos igual. De 0 a 10, donde 10 es sentirme muy bien, hoy estoy en 4.

Herramientas: consultar_plan, registrar_evolucion. Respondió en 6 s.

> Voy a revisar qué te indicaron para poder acompañarte mejor.
>
> Entendido. Voy a registrar cómo te sientes hoy.
>
> Listo, quedó registrado. ¿Cómo va con el líquido y el descanso que te indicaron?

**2. Persona:** Hoy me siento un poco peor, con más cansancio, pero sin fiebre y respiro bien. Estoy en 3 de 10.

Herramientas: registrar_evolucion. Respondió en 4.2 s.

> ¿Cómo va con lo que te indicaron: el líquido, el descanso y lo demás?
