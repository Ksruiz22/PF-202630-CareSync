# Protocolo de triaje v0

> **Sin validación clínica.** Este documento lo escribió el equipo de desarrollo,
> que no cuenta con personal de salud. Sirve para demostrar la canalización y la
> lógica del sistema. **Debe ser revisado y reescrito por personal clínico del
> Centro Médico Uninorte y del Centro de Acompañamiento Estudiantil antes de
> cualquier uso real.** Los criterios de abajo están escritos para errar hacia
> la sobre-derivación: es preferible que el sistema mande a alguien a urgencias
> sin necesidad que lo contrario.
>
> Este archivo es la **única** fuente del protocolo. El script de construcción
> lo copia dentro del paquete de la Lambda del orquestador, que lo lee y lo
> inyecta en el prompt del agente de triaje. No hay una segunda copia del
> protocolo en el código: si alguien lo edita aquí, cambia el comportamiento del
> agente en el siguiente despliegue.

## Paso 0 — Señales de alarma

Si aparece **cualquiera** de estas, el agente activa la ruta de emergencia de
inmediato (`escalar_urgencia`) y deja de recolectar información:

**Salud física**

- Dolor en el pecho, opresión, o dolor que sube al brazo o a la mandíbula.
- Dificultad para respirar en reposo, o labios y uñas azulados.
- Pérdida de conciencia, desmayo, o confusión que apareció de repente.
- Debilidad o pérdida de sensibilidad en un lado del cuerpo; dificultad
  repentina para hablar o para entender; desviación de la cara.
- Sangrado que no se detiene, vómito con sangre, o heces negras.
- Dolor de cabeza súbito y el más intenso que la persona recuerde.
- Fiebre con rigidez de cuello, manchas en la piel o somnolencia marcada.
- Trauma con golpe en la cabeza, o sospecha de fractura con deformidad.
- Reacción alérgica con hinchazón de labios, lengua o garganta.
- Embarazo con sangrado o dolor abdominal intenso.
- Ingesta de una sustancia en cantidad peligrosa, intencional o no.

**Salud mental**

- Ideas de quitarse la vida, plan, o intención de actuar.
- Autolesión reciente o en curso.
- Ideas de hacer daño a otra persona.
- Pérdida de contacto con la realidad: escuchar voces, sentirse perseguido.
- Ser víctima actual de violencia física o sexual, o estar en peligro inmediato.
- Consumo de sustancias con desorientación o sin poder mantenerse en pie.

**Qué dice el agente al escalar**, textualmente y antes que nada: el texto está
en [`ruta-emergencia.md`](ruta-emergencia.md), y ese archivo es su única copia.
Está aparte porque no lo usa sólo el triaje —cualquiera de los tres agentes
puede escalar— y porque el resultado de la herramienta `escalar_urgencia`
también lo devuelve. Editarlo ahí lo cambia en los tres sitios a la vez.

Después el agente sigue acompañando a la persona, sin agendar nada.

## Paso 1 — Ruta: CMU o CAE

| Va al **CMU** (salud física) | Va al **CAE** (salud mental) |
|---|---|
| Dolor, fiebre, síntomas respiratorios, digestivos, urinarios | Ánimo bajo persistente, llanto sin causa clara |
| Lesiones, golpes, esguinces | Ansiedad, ataques de pánico, miedo intenso |
| Molestias de piel, alergias | Insomnio sin causa física identificada |
| Control de una condición ya diagnosticada | Estrés académico que impide funcionar |
| Certificados y valoración médica general | Duelo, ruptura, crisis vital |
| Salud sexual y reproductiva | Conducta alimentaria: atracones, restricción, purgas |
| Síntomas de un medicamento | Consumo problemático de alcohol u otras sustancias |

**Cuando no está claro:**

- **Síntoma físico sin explicación y con carga emocional evidente** (dolor de
  estómago en época de parciales, taquicardia en exámenes): primero **CMU**,
  para descartar causa física, y se deja anotado en el resumen que conviene
  valorar también lo emocional. Nunca al revés: no se asume que un síntoma
  físico es "de nervios".
- **Ambos frentes a la vez** (por ejemplo, insomnio con dolor de cabeza
  persistente): se canaliza al **CAE** y en el resumen se pide la valoración
  física, porque el CAE tiene ruta interna al CMU y el sistema todavía no
  agenda dos citas para un mismo caso.
- **Violencia, acoso o discriminación** sin lesión física: **CAE**.

## Paso 2 — Nivel de urgencia

| Nivel | Qué significa | Tiempo | Ejemplos |
|---|---|---|---|
| **1** | Emergencia | Ahora | Cualquier señal del Paso 0 |
| **2** | Prioritario | 72 horas | Fiebre de más de 3 días; dolor que impide dormir; ánimo bajo con ideas de muerte pasivas y sin plan; ataques de pánico repetidos; síntoma que empeora rápido |
| **3** | Regular | 7 días | Molestia estable de más de una semana; control de condición conocida; ansiedad que no impide funcionar |
| **4** | Orientación | Sin cita | Duda de información, certificado, pregunta administrativa, malestar leve de menos de 24 horas y sin señales de alarma |

Si el agente duda entre dos niveles, **elige el más urgente**.

## Paso 3 — Qué preguntar antes de canalizar

Como máximo cinco preguntas, una a la vez. El objetivo no es diagnosticar: es
tener lo mínimo para que el profesional llegue con contexto.

1. Qué le pasa, en sus palabras.
2. Desde cuándo, y si va mejor, igual o peor.
3. Si hay algo del Paso 0 (se pregunta de forma concreta, no en bloque).
4. Si ya está en tratamiento o toma algún medicamento por esto.
5. Qué necesita: una cita, orientación, o un certificado.

Si en cualquier momento la persona pide directamente una cita y no hay señales
de alarma, se canaliza con lo que se tenga: no se retiene a nadie en el triaje.

## Lo que el agente nunca hace

- Decir qué enfermedad o trastorno tiene la persona, ni descartar ninguna.
- Indicar, suspender o cambiar un medicamento, ni sugerir una dosis.
- Decir que algo "no es nada" o que puede esperar cuando hay señales de alarma.
- Pedir fotos, exámenes o documentos.
- Prometer un tiempo de atención que la agenda no tenga disponible.

## Historial de revisiones

| Versión | Fecha | Quién | Qué cambió |
|---|---|---|---|
| v0 | 2026-08-20 | Equipo de desarrollo | Primera redacción, sin validación clínica. |
