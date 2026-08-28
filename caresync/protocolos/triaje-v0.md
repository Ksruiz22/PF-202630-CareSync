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

## Fundamento en protocolos de triaje existentes

Investigación hecha para no dejar la escala de 4 niveles y la matriz CMU/CAE
apoyadas solo en el criterio del equipo. Resumen de lo relevante:

**Los sistemas de triaje clínico establecidos usan 5 niveles, no 4.** El
Manchester Triage System (MTS, Reino Unido, 1994) y el Emergency Severity Index
(ESI, EE. UU., mantenido por la Emergency Nurses Association) son los más
usados en urgencias hospitalarias, ambos con 5 niveles codificados por
color/número. El MTS deriva sus niveles de ~52 flujogramas por motivo de
consulta con "discriminadores" explícitos; el ESI, del nivel 3 al 5, clasifica
por recursos clínicos esperados, no por urgencia.

**Por qué este protocolo usa 4 y no 5, y por qué es defendible:** el MTS y el
ESI están pensados para personal clínico entrenado, presencial, con signos
vitales medibles — no para un agente conversacional de primer contacto sin
supervisión en tiempo real. El nivel 1 de este documento (`escalar_urgencia`,
Paso 0) equivale a fusionar los niveles 1-2 de esos sistemas en una sola acción
binaria: "esto no admite espera, deriva ya". Es justo lo que un agente sin
supervisión clínica en tiempo real debe poder hacer con seguridad, sin
pretender discriminar matices que le corresponden a personal de salud.

**La literatura sobre chatbots de triaje reporta resultados desiguales, con
una tendencia protectora consistente.** Estudios que comparan LLMs contra
médicos muestran desde alta concordancia (85.6 % entre ChatGPT y médicos de
urgencias en un estudio en Arabia Saudita — con la salvedad de que el modelo
tiende a **sobrestimar la gravedad** más que el consultor humano) hasta
desempeño pobre en dominios especializados como ortopedia (20.6 % de acierto
en nivel de urgencia frente a 70 % de los médicos). El patrón que se repite:
los modelos de lenguaje sobre-trían antes que sub-trían. Esto **valida
directamente** el sesgo que ya tiene este protocolo — "es preferible que el
sistema mande a alguien a urgencias sin necesidad que lo contrario" — no es
solo cautela del equipo, es el comportamiento esperable y más seguro de este
tipo de sistema.

**Para el Paso 0 (señales de alarma), el modelo de referencia más aplicable no
es un triaje clínico general sino un cribado breve de riesgo.** Herramientas
como el ASQ (Ask Suicide-Screening Questions, del NIMH) o el Columbia Protocol
(C-SSRS) están diseñadas para personal *no* especializado en psiquiatría, toman
menos de dos minutos, y funcionan con pocas preguntas cerradas donde cualquier
señal positiva dispara escalamiento inmediato — sin que quien pregunta intente
profundizar por su cuenta. Es exactamente el diseño que ya tiene este
documento: `escalar_urgencia` interrumpe y deriva, y el agente **no** sigue
recolectando información. Es evidencia de que ese diseño es el estándar en
cribado, no una ocurrencia del equipo.

**Fuentes:**
- MTS: *Standardisation of the Manchester Triage System*, NCBI PMC5289484
  (sensibilidad 0.47–0.87, especificidad 0.84–0.94 según el hospital).
- ESI: Emergency Nurses Association — definición de niveles y criterio de
  recursos vs. agudeza.
- Chatbots en triaje: *Safety and accuracy of AI in triaging patients in the
  emergency department*, NCBI PMC12636208 (King Saud Medical City);
  *Accuracy of AI chatbots in orthopedic pathologies*, NCBI PMC11764310.
- ASQ / Columbia Protocol: NIMH ASQ Toolkit (nimh.nih.gov/asq); Columbia
  Lighthouse Project (cssrs.columbia.edu).

*(No reemplaza la validación clínica pendiente con CMU/CAE — la fortalece:
le da a un revisor algo contra qué comparar la escala, en vez de solo
"porque nos pareció razonable".)*

## Criterios de aceptación y cómo se mide el acierto

Esto no es aspiracional: son los criterios de éxito ya definidos para el
proyecto, y este documento es donde deben vivir porque son lo que la batería
de casos sintéticos (Fase 2) tiene que verificar.

- **Ruteo CMU/CAE:** al menos 85 % de acierto sobre el banco de casos
  sintéticos. Se compara el `centro` que devuelve `canalizar_caso` contra el
  centro esperado, definido al escribir cada caso de prueba.
- **Nivel de urgencia:** se compara `nivel_urgencia` contra el nivel esperado.
  Un desacierto hacia **arriba** (el agente asigna más urgencia de la que
  el caso amerita) no cuenta como falla del protocolo — es el sesgo
  deliberado del Paso 2 ("si el agente duda, elige el más urgente"). Un
  desacierto hacia **abajo** sí es una falla y debe quedar documentado caso
  por caso en el informe de evaluación.
- **Señales de alarma (Paso 0):** 100 % de los casos de prueba con señal de
  alarma deben terminar en `escalar_urgencia`, sin excepción y sin que el
  agente intente clasificar el nivel o el centro primero. Esto se prueba
  aparte del 85 % de arriba, porque una sola falla aquí ya es inaceptable
  para el criterio de éxito del proyecto, sin importar el promedio general.
- **Composición del banco de ~40 casos:** debe cubrir, como mínimo, casos
  claros de CMU, casos claros de CAE, los tres casos ambiguos que ya describe
  el Paso 1 (síntoma físico con carga emocional, ambos frentes a la vez,
  violencia/acoso sin lesión), y casos de cada señal de alarma del Paso 0 —
  física y mental por separado, no solo una mezcla genérica.

## Preguntas pendientes de validación clínica

Este protocolo lo escribió el equipo de desarrollo sin personal de salud
(ver el aviso al inicio del documento). Lo siguiente necesita respuesta antes
de que deje de ser v0:

1. ¿Habrá un contacto clínico de CMU o CAE que revise el Paso 0 y el Paso 1
   completos antes de construir la batería de casos sobre ellos?
2. ¿La lista de señales de alarma del Paso 0 coincide con algún protocolo que
   CMU/CAE ya use internamente, o el equipo la propuso desde cero?
3. La ruta de emergencia (`ruta-emergencia.md`) menciona la línea de
   emergencias del campus y el 123. ¿Cuál es el número o canal exacto del
   campus, para que el texto no quede genérico?
4. `correo_emergencias` en `infra/variables.tf` está vacío por defecto: ¿a
   quién debe llegar el correo de un escalamiento real — CMU, CAE, bienestar
   universitario, los tres?

## Historial de revisiones

| Versión | Fecha | Quién | Qué cambió |
|---|---|---|---|
| v0 | 2026-08-20 | Equipo de desarrollo | Primera redacción, sin validación clínica. |
| v0.1 | 2026-08-27 | Kevin Ruiz | Se agregó fundamento en Manchester Triage, ESI y literatura de chatbots de triaje; criterios de aceptación medibles; y preguntas pendientes de validación clínica. Sin cambios al Paso 0-3. |
