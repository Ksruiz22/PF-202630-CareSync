# Primer Informe de Proyecto Final

## CareSync Agentic Network

**Universidad del Norte — Proyecto Final, Campo: Salud**  
**Docente proponente:** Dadier Jabba  
**Co-asesor:** Augusto Salazar  
**Integrantes:** Alejandro Santiago, Kevin Ruiz y Bernardo Álvarez  
**Fecha:** agosto de 2026

---

## Resumen / Abstract

CareSync Agentic Network es un prototipo funcional de extremo a extremo orientado a demostrar cómo una red de agentes de inteligencia artificial puede sostener la continuidad del cuidado de un miembro de la comunidad universitaria desde el primer síntoma hasta el seguimiento posterior a la atención. La propuesta aborda una situación en la que los servicios de atención concentran carga administrativa en el agendamiento y el seguimiento manual, mientras que para la persona que consulta no siempre resulta evidente cuál es la ruta adecuada entre atención de salud física y salud mental. La solución plantea tres agentes especializados: un Agente de Triaje que evalúa la gravedad y canaliza el caso, un Agente de Agenda y Logística que reserva la cita y entrega el contexto al profesional, y un Agente de Seguimiento que programa recordatorios, registra la evolución y escala anomalías.

La solución se implementará como una PWA con cuatro vistas diferenciadas por rol: paciente, profesional, administrador del Centro Médico Uninorte (CMU) y administrador del Centro de Acompañamiento Estudiantil (CAE). La arquitectura utiliza una infraestructura serverless mínima, con persistencia y autenticación centralizadas en ROBLE y servicios AWS para el razonamiento de los agentes, automatización, correo, observabilidad y despliegue. El prototipo utilizará exclusivamente datos sintéticos y no pretende constituir un sistema clínico de producción ni sustituir la validación de profesionales de la salud.

El desarrollo seguirá un enfoque de prototipado iterativo y vertical durante 16 semanas. Cada fase debe producir un recorrido funcional y demostrable, con validaciones técnicas, funcionales y de usabilidad. El plan contempla siete fases y siete hitos, desde el encuadre y la arquitectura hasta las pruebas E2E, documentación y sustentación final. La meta principal es demostrar la continuidad técnica del caso y la coordinación entre agentes, manteniendo explícitamente fuera del alcance la validación clínica necesaria para un uso real.

---

# 1. Introducción

La atención en salud constituye un dominio en el que los sistemas de información cumplen un papel cada vez más importante para organizar la interacción entre pacientes, profesionales, servicios de atención y datos clínicos. En este contexto han adquirido relevancia los evaluadores digitales de síntomas, los asistentes conversacionales y, más recientemente, las arquitecturas basadas en inteligencia artificial generativa y agentes capaces de ejecutar acciones sobre sistemas externos. Soluciones comerciales como Ada utilizan razonamiento probabilístico para analizar síntomas y ofrecer posibles explicaciones y orientación, mientras que Buoy utiliza inteligencia artificial para conversar sobre síntomas y orientar al usuario hacia los siguientes pasos de atención [1][2]. Paralelamente, organismos como la Organización Mundial de la Salud han señalado que la IA puede aportar beneficios en medicina y sistemas de salud, pero que su diseño y utilización deben considerar seguridad, derechos humanos, transparencia, equidad y supervisión humana [3].

A pesar de la existencia de herramientas de evaluación de síntomas y chatbots de salud, estas soluciones no necesariamente resuelven de forma integral la continuidad del caso dentro de una comunidad universitaria. Un evaluador puede ayudar al usuario a interpretar sus síntomas y decidir qué hacer, pero el problema planteado por CareSync se extiende al proceso posterior: canalizar al servicio apropiado, gestionar una cita con contexto, permitir que el profesional registre un plan y mantener un seguimiento posterior que detecte retrocesos. En el contexto definido para el proyecto, los servicios de salud del campus concentran carga administrativa en el agendamiento y el seguimiento manual, y un caso tratable puede deteriorarse si no existe una comprobación posterior de la adherencia o evolución. La propuesta, por tanto, no parte de la inexistencia de herramientas de IA para salud, sino de la oportunidad de conectar las diferentes etapas de un caso dentro de un mismo recorrido.

La necesidad técnica identificada consiste en construir una arquitectura capaz de coordinar diferentes responsabilidades de IA y de aplicación sobre un estado compartido y trazable, sin convertir el prototipo académico en una infraestructura excesivamente costosa o difícil de operar. CareSync plantea una red de tres agentes especializados, con herramientas para consultar, reservar, notificar y escalar, apoyada en persistencia centralizada y controles de acceso por rol. La arquitectura también debe incorporar salvaguardas específicas para el dominio: uso exclusivo de datos sintéticos, guardrails para contenido sensible, una ruta de emergencia ante señales de riesgo, registro de decisiones y pruebas de casos límite. Este enfoque coincide con la necesidad de gestionar explícitamente los riesgos de sistemas de IA en salud señalada por la OMS y con el principio de incorporar consideraciones de confiabilidad y gestión de riesgos durante todo el ciclo de vida de un sistema de IA, como propone el AI Risk Management Framework de NIST [3][4].

Como respuesta a esta necesidad se propone **CareSync Agentic Network**, un prototipo funcional E2E que acompaña el recorrido desde el contacto inicial hasta el seguimiento. El sistema integra una PWA con cuatro vistas por rol, tres agentes especializados, autenticación y persistencia mediante ROBLE, y una capa serverless de AWS basada principalmente en Lambda, Amazon Bedrock, Bedrock Guardrails, EventBridge Scheduler, SES, CloudWatch y AWS CDK. El recorrido esperado comprende contacto, triaje, canalización, agendamiento, atención y seguimiento. El impacto esperado no se plantea como una sustitución del personal de salud, sino como una demostración técnica de que una arquitectura de agentes puede mantener el contexto de un caso y automatizar partes del recorrido administrativo y de seguimiento, dentro de los límites de un prototipo académico.

---

# 2. Planteamiento del problema

## 2.1 Descripción del problema

En los servicios de atención en salud de una comunidad universitaria, la continuidad de un caso puede verse afectada por la separación entre las actividades de orientación inicial, canalización, agendamiento y seguimiento posterior. La problemática se manifiesta cuando una persona presenta un malestar, pero la ruta entre atención física y atención de salud mental no resulta evidente para quien consulta, mientras que el agendamiento y el seguimiento dependen de actividades administrativas que pueden requerir intervención manual.

Esta situación puede generar consecuencias en dos puntos principales. Primero, la persona puede no llegar oportunamente al servicio que corresponde a su necesidad. Segundo, después de la atención, puede no existir una comprobación automatizada de si siguió las indicaciones o de si presentó un retroceso que requiera informar nuevamente al equipo tratante. En consecuencia, la continuidad del caso queda fragmentada entre etapas que no necesariamente comparten el mismo contexto.

El problema no se formula como la ausencia de una aplicación específica, sino como una **deficiencia en la continuidad y coordinación del recorrido de atención**, particularmente en la transición entre orientación, canalización, agendamiento y seguimiento. La población objetivo del prototipo es la comunidad universitaria que utilizaría los servicios de atención física y de salud mental representados por el CMU y el CAE, junto con los profesionales y administradores que participan en dicho recorrido.

La propuesta reconoce además que automatizar decisiones relacionadas con salud introduce riesgos. Un triaje sin validación clínica puede clasificar incorrectamente un caso, los datos de salud requieren protección y las respuestas de un modelo pueden ser inadecuadas, especialmente en salud mental. Por esta razón, el problema tecnológico no se limita a automatizar un flujo, sino que incluye la necesidad de mantener límites claros entre el prototipo y un sistema clínico real.

## 2.2 Justificación

La atención de esta problemática es pertinente porque la continuidad del cuidado requiere que la información relevante de un caso acompañe al usuario durante las diferentes etapas del recorrido. Desde el punto de vista práctico, la propuesta busca reducir la fragmentación entre el primer contacto, la canalización, el agendamiento y el seguimiento mediante un estado compartido y agentes con responsabilidades específicas.

Desde el punto de vista técnico, el proyecto permite estudiar y demostrar una arquitectura de agentes aplicada a un flujo de salud que combina conversación, clasificación, persistencia, agenda, notificaciones y seguimiento. La propuesta también plantea una decisión de ingeniería deliberadamente austera: utilizar ROBLE como plataforma de autenticación y persistencia y reservar AWS principalmente para las capacidades que no aporta ROBLE, particularmente el razonamiento mediante modelos, automatización, correo, observabilidad y despliegue.

La pertinencia académica se encuentra en evaluar si una red de agentes especializados puede sostener un recorrido E2E trazable y verificable dentro de las restricciones de un proyecto final de 16 semanas. El proyecto establece criterios medibles, entre ellos alcanzar al menos 85 % de acierto en la canalización sobre un banco de casos sintéticos, derivar el 100 % de los casos con señal de riesgo hacia emergencias y generar una alerta al profesional en menos de cinco minutos ante un retroceso reportado.

Finalmente, la propuesta mantiene una delimitación responsable: el éxito del prototipo no se define por demostrar corrección clínica. La validación clínica de los protocolos por personal de salud calificado queda explícitamente como trabajo futuro.

## 2.3 Restricciones y supuestos iniciales

Las principales restricciones y supuestos son:

- El proyecto tiene una duración total de **16 semanas**.
- El equipo está conformado por **tres integrantes**, con frentes de infraestructura y despliegues, agentes e IA, y aplicación y experiencia.
- La solución se desarrolla como **prototipo funcional E2E**, no como sistema clínico de producción.
- Se utilizarán **100 % datos sintéticos** durante el proyecto.
- La integración real con los servicios institucionales del CMU y CAE queda fuera del alcance; se utilizará un adaptador con contrato definido y backend simulado.
- El triaje se basa en protocolos deliberadamente básicos y versionados, sin pretender sustituir una valoración clínica.
- La persistencia y autenticación dependen de ROBLE, plataforma de OPENLAB, por lo que su estabilidad, respaldos y evolución constituyen un riesgo identificado.
- La API de datos utilizada no ofrece escritura condicional documentada; por ello, el control de doble agendamiento se implementará mediante reservar, releer y reconciliar.
- Las consultas de datos se diseñarán alrededor de filtros de igualdad debido a las limitaciones identificadas en la API de ROBLE.
- El prototipo no maneja archivos binarios ni adjuntos.
- La arquitectura deliberadamente mínima omite controles que serían necesarios antes de cualquier uso real con datos de salud, entre ellos aislamiento de red, llaves de cifrado propias con rotación, WAF, auditoría de eventos de datos mediante CloudTrail, una base de conocimiento revisable con RAG y validación clínica.
- La nube se mantendrá bajo control de costos mediante límites de tokens, alertas de presupuesto y un único entorno permanente de demostración.

---

# 3. Alcance del proyecto

## Incluye

### Funcionalidades principales

El prototipo incluye:

1. **Autenticación y control de acceso** mediante ROBLE.
2. **PWA única con enrutamiento por rol**.
3. **Vista del paciente** para iniciar la conversación, recibir el resultado del triaje, consultar la ruta asignada, reportar evolución y adherencia.
4. **Agente de Triaje** para realizar preguntas, evaluar gravedad según protocolos básicos, establecer nivel de urgencia y decidir la ruta CMU/CAE.
5. **Ruta de emergencia** ante señales de riesgo.
6. **Agente de Agenda y Logística** para consultar disponibilidad, reservar citas y generar el resumen estructurado del caso.
7. **Consolas administrativas** para CMU y CAE, incluyendo profesionales, horarios y agenda.
8. **Vista del profesional** para consultar el caso, registrar el plan de tratamiento por texto o dictado de voz y consultar el progreso.
9. **Agente de Seguimiento** para programar recordatorios, registrar adherencia y evolución, detectar retrocesos y generar alertas.
10. **Notificaciones por correo** mediante SES.
11. **Automatización de recordatorios** mediante EventBridge Scheduler y Lambda.
12. **Registro y trazabilidad** mediante persistencia en ROBLE y logs en CloudWatch.
13. **Pruebas E2E**, pruebas de concurrencia, casos límite y pruebas de usabilidad.
14. **Infraestructura como código** mediante AWS CDK.

### Usuarios involucrados

El sistema contempla cuatro roles:

- Paciente o miembro de la comunidad.
- Profesional de atención.
- Administrador del CMU.
- Administrador del CAE.

### Nivel de madurez

La solución corresponde a un **prototipo funcional de extremo a extremo**, orientado a demostración académica. No constituye una implementación productiva ni un sistema clínico validado.

### Entornos cubiertos

- Aplicación web/PWA.
- Backend serverless.
- Agentes de IA.
- Persistencia y autenticación.
- Automatización y notificaciones.
- Integración mediante backend simulado.

## No incluye

Quedan fuera del alcance:

- Atención clínica real.
- Uso de datos reales de pacientes.
- Validación clínica definitiva de los protocolos de triaje.
- Integración real con los sistemas institucionales del CMU y CAE.
- Implementación productiva a escala institucional.
- Manejo de archivos o adjuntos.
- Sustitución del profesional de salud por IA.
- Diagnóstico o prescripción autónoma.
- Infraestructura de seguridad completa para producción.
- Aislamiento de red, WAF y llaves de cifrado propias con rotación en la arquitectura del prototipo.
- Auditoría de eventos de datos mediante CloudTrail como capacidad completa de producción.
- Base de conocimiento RAG para los protocolos en la versión inicial.
- Soporte operativo posterior al proyecto.
- Funcionalidades futuras que no sean necesarias para demostrar el recorrido E2E.

---

# 4. Objetivos

## 4.1 Objetivo general

**Desarrollar y evaluar un prototipo funcional de extremo a extremo que coordine una red de agentes de inteligencia artificial para mantener la continuidad del recorrido de atención de un miembro de la comunidad universitaria, desde el reporte inicial de síntomas hasta el seguimiento posterior, integrando triaje conversacional, canalización, agendamiento contextualizado y seguimiento proactivo dentro de una arquitectura serverless con datos sintéticos, durante las 16 semanas del proyecto.**

### Análisis SMART

- **S — Específico:** define una red de agentes y el recorrido concreto que debe cubrir.
- **M — Medible:** se evalúa mediante criterios funcionales, pruebas E2E, precisión de canalización, detección de riesgo y tiempos de alerta.
- **A — Alcanzable:** se limita a un prototipo con datos sintéticos, backend institucional simulado y arquitectura mínima.
- **R — Relevante:** responde directamente al problema de continuidad y coordinación del recorrido de atención.
- **T — Temporal:** se desarrolla y evalúa dentro de las 16 semanas establecidas.

## 4.2 Objetivos específicos

1. **Diseñar** una arquitectura serverless mínima que permita ejecutar y coordinar tres agentes especializados, persistir el estado del caso y separar los permisos de los cuatro roles del sistema.

2. **Implementar** un Agente de Triaje que conduzca una conversación estructurada, aplique los protocolos definidos, determine un nivel de urgencia y canalice el caso hacia CMU, CAE o emergencias.

3. **Implementar** un Agente de Agenda y Logística que consulte disponibilidad, gestione la reserva de citas y entregue al profesional un resumen estructurado del caso, incluyendo un mecanismo de reconciliación para evitar dobles agendamientos.

4. **Implementar** un Agente de Seguimiento que programe recordatorios, registre adherencia y evolución, detecte retrocesos y genere alertas dirigidas al equipo tratante.

5. **Construir** una PWA con vistas diferenciadas para paciente, profesional, administrador CMU y administrador CAE, con control de acceso basado en roles.

6. **Evaluar** el funcionamiento del recorrido E2E mediante casos sintéticos, pruebas de concurrencia, casos límite, pruebas de seguridad y sesiones de usabilidad.

7. **Validar** el desempeño del prototipo mediante criterios verificables, incluyendo un mínimo de 85 % de acierto en el ruteo CMU/CAE sobre el banco de casos sintéticos, derivación del 100 % de los casos con señal de riesgo a emergencias y generación de alertas de retroceso en menos de cinco minutos.

8. **Documentar** la arquitectura, el despliegue, los resultados de evaluación, las limitaciones y la hoja de ruta necesaria antes de considerar cualquier uso real.

---

# 5. Solución propuesta

CareSync Agentic Network propone una red de tres agentes especializados que comparten el estado de un caso y se transfieren responsabilidades durante el recorrido:

- **Agente de Triaje:** evalúa la gravedad mediante conversación y protocolos básicos, determina el nivel de urgencia y decide si el caso corresponde al CMU, al CAE o a emergencias.
- **Agente de Agenda y Logística:** consulta disponibilidad, reserva el cupo correspondiente y entrega al profesional un resumen estructurado del caso.
- **Agente de Seguimiento:** programa recordatorios, registra adherencia y evolución, detecta anomalías o retrocesos y alerta al equipo tratante.

El recorrido E2E se estructura en seis etapas:

1. **Contacto:** el paciente describe su malestar mediante la PWA.
2. **Triaje:** el agente realiza preguntas y evalúa la gravedad.
3. **Canalización:** se decide la ruta CMU, CAE o emergencias.
4. **Agendamiento:** se reserva el cupo y se entrega el contexto al profesional.
5. **Atención:** el profesional registra el plan de tratamiento, incluyendo dictado por voz.
6. **Seguimiento:** se envían recordatorios, se registra la evolución y se escalan retrocesos.

La arquitectura utiliza ROBLE para autenticación, roles, permisos y base de datos PostgreSQL administrada. AWS se utiliza principalmente para la capa de inteligencia y automatización: Amazon Bedrock con Claude Haiku 4.5 y prompt caching, Bedrock Guardrails, funciones Lambda, EventBridge Scheduler, SES, CloudWatch, SSM Parameter Store, Amplify Hosting y AWS CDK. El acceso a ROBLE se concentra en un módulo de datos para evitar que las diferentes partes de la aplicación dependan directamente de la plataforma.

Una decisión importante de la propuesta es evitar una arquitectura más compleja cuando no es necesaria para el prototipo. El runtime de los agentes se implementa mediante un bucle de herramientas en Lambda sobre la Converse API de Bedrock, en lugar de utilizar Bedrock AgentCore. Los protocolos se mantienen como documentos versionados e inyectados en el prompt, en lugar de desplegar inicialmente una base vectorial con RAG. La persistencia se mantiene en ROBLE en lugar de DynamoDB o Aurora Serverless. Estas decisiones reducen infraestructura, costos y tiempo de implementación, aunque también implican limitaciones explícitas que deberán revertirse antes de cualquier uso real.

---

# 6. Estado del arte / soluciones relacionadas

## 6.1 Productos comerciales

### Ada Health

Ada es una solución comercial de evaluación de síntomas que utiliza una tecnología de razonamiento probabilístico desarrollada por su equipo para analizar los síntomas y la información proporcionada por el usuario y compararlos con una base de condiciones y enfermedades. La aplicación genera un informe con posibles explicaciones y orientación sobre los siguientes pasos [1]. Ada declara además que no pretende realizar un diagnóstico directo ni sustituir a un médico [5].

**Fortalezas frente a CareSync:**

- Motor de evaluación de síntomas maduro.
- Amplia base de condiciones y síntomas.
- Experiencia de usuario enfocada específicamente en la evaluación de síntomas.
- Uso de evidencia clínica y participación de profesionales médicos.

**Limitaciones respecto a la problemática de CareSync:**

- Su función principal es la evaluación/orientación de síntomas.
- No constituye, según la información consultada, el mismo flujo institucional integrado que CareSync busca demostrar entre triaje, canalización, agenda, profesional y seguimiento.
- El problema de CareSync no es únicamente determinar posibles causas, sino conservar el contexto del caso y coordinar acciones posteriores dentro de una comunidad universitaria.

### Buoy Health

Buoy ofrece un evaluador conversacional de síntomas que hace preguntas, ayuda a interpretar el problema y orienta al usuario sobre qué hacer a continuación. La plataforma declara que combina los síntomas con información médica y proporciona próximos pasos para buscar atención. Buoy también ha publicado resultados de investigación sobre el efecto de su herramienta de triaje en la incertidumbre de los usuarios respecto al nivel de atención [2].

**Fortalezas frente a CareSync:**

- Conversación orientada a síntomas.
- Orientación hacia el nivel de atención.
- Uso de información médica y evidencia.
- Experiencia accesible desde navegador.

**Limitaciones respecto a CareSync:**

- El enfoque principal está en el symptom checking y la orientación inicial.
- No se observa en la solución pública consultada el mismo énfasis que CareSync en integrar un estado compartido entre varios agentes especializados, agenda institucional, interfaz profesional y seguimiento longitudinal del caso.
- Buoy es una plataforma general, mientras que CareSync está delimitada a un flujo concreto de atención universitaria.

## 6.2 Soluciones open-source

### LangDoc

LangDoc es un proyecto open-source de evaluación de síntomas y anamnesis mediante conversación en lenguaje natural. El proyecto utiliza una arquitectura modular basada en LangChain y puede realizar entrevistas dinámicas, resumir información del paciente y estructurar el proceso de entrevista. Su documentación indica que utiliza subagentes y que puede configurarse con diferentes modelos de lenguaje [6].

**Fortalezas:**

- Entrevista conversacional en lenguaje natural.
- Arquitectura modular.
- Uso de subagentes.
- Posibilidad de adaptar el modelo subyacente.
- Código disponible para experimentación y despliegue.

**Limitaciones respecto a CareSync:**

- Su foco principal está en la entrevista/anamnesis.
- No presenta en su descripción pública el recorrido institucional completo de CareSync con agenda, profesionales, administradores y seguimiento automatizado.
- El front-end descrito originalmente utiliza Discord, por lo que requiere adaptación para convertirse en una PWA con control de roles y flujo institucional.

### AI Medical Chatbot

El proyecto `ai-medical-chatbot` de GitHub plantea un asistente médico open-source basado en IA generativa, con RAG, múltiples modelos de lenguaje y una interfaz para asistencia en consultas médicas. El repositorio incluye capacidades de entrevista médica y afirma utilizar fuentes y enfoques de grounding médico [7].

**Fortalezas:**

- Código abierto.
- Uso de RAG para fundamentar respuestas.
- Arquitectura adaptable a diferentes modelos.
- Enfoque específico en conversación médica.

**Limitaciones respecto a CareSync:**

- El foco principal está en la asistencia conversacional y no en la continuidad completa del caso.
- No se plantea como eje central la coordinación de tres agentes especializados con agenda y seguimiento.
- La adopción en un entorno institucional requiere construir controles de acceso, integración, persistencia y reglas específicas del dominio.

### Health Chatbot

Otro ejemplo open-source es `health-chatbot`, que combina autenticación, control de acceso por roles, reserva de citas, administración de disponibilidad, chat entre pacientes y doctores, un symptom checker y notificaciones [8].

Este proyecto es especialmente cercano a CareSync porque combina funcionalidades que normalmente aparecen separadas: síntomas, citas, usuarios y comunicación.

**Limitaciones respecto a CareSync:**

- El symptom checker se plantea como una funcionalidad NLP dentro de una aplicación web, mientras que CareSync plantea agentes especializados con responsabilidades diferenciadas.
- No se encuentra en la descripción pública consultada el mismo énfasis en el control de riesgos de IA para salud mental, protocolos versionados, ruta de emergencia y evaluación sistemática del ruteo.
- CareSync prioriza demostrar un recorrido E2E trazable y la coordinación entre agentes, mientras que este tipo de proyectos open-source reúne funcionalidades en una aplicación tradicional.

## 6.3 Arquitecturas y enfoques técnicos relevantes

El estado actual de la tecnología muestra dos enfoques relevantes para CareSync.

El primero es el **symptom checking conversacional**, representado por Ada y Buoy, en el que el sistema recoge síntomas, formula preguntas y genera orientación. Este enfoque demuestra que la conversación puede utilizarse como interfaz de acceso inicial a servicios de salud [1][2].

El segundo es la **arquitectura agentic**, en la que un modelo puede utilizar herramientas y ejecutar acciones sobre sistemas externos. AWS documenta actualmente arquitecturas de IA generativa para salud que combinan agentes, modelos, herramientas, controles de seguridad y servicios administrados [9][10]. Esto resulta relevante para CareSync porque el proyecto no pretende que el modelo solo genere texto: los agentes deben consultar datos, reservar citas, generar notificaciones y actualizar el estado del caso.

Para el control de riesgos, la propuesta también encuentra respaldo conceptual en la guía de la OMS sobre ética y gobernanza de IA en salud y en el AI RMF de NIST. La OMS recomienda que la IA en salud incorpore consideraciones éticas y de derechos humanos desde su diseño y utilización, mientras que NIST propone un marco para gestionar riesgos y promover sistemas de IA confiables y responsables [3][4].

## 6.4 Comparación

| Solución / enfoque | Funcionalidad | Escalabilidad | Costos | Usabilidad | Limitaciones frente a CareSync |
|---|---|---|---|---|---|
| **Ada Health** | Evaluación conversacional de síntomas y orientación | Plataforma comercial de gran escala | Servicio comercial; costos internos no comparables directamente con el prototipo | Alta, orientada al usuario final | No tiene como foco el flujo institucional completo de triaje → agenda → atención → seguimiento planteado por CareSync |
| **Buoy Health** | Symptom checking, preguntas y orientación de atención | Plataforma comercial | Modelo comercial; costo del producto institucional depende del servicio | Alta, basada en conversación | Se concentra principalmente en orientación/triaje y no en la coordinación del caso completo planteada por CareSync |
| **LangDoc** | Anamnesis conversacional y resumen de información | Depende de la infraestructura y modelo utilizado | Open-source, pero con costos de infraestructura/modelo según despliegue | Interfaz adaptable; proyecto descrito originalmente con Discord | No ofrece como foco principal agenda institucional, cuatro roles y seguimiento E2E |
| **AI Medical Chatbot** | Chat médico, RAG y asistencia conversacional | Depende del modelo e infraestructura elegidos | Open-source; costos dependen del despliegue | Interfaz web disponible | Orientado a conversación/consulta; requiere adaptación para flujo institucional completo |
| **Health Chatbot** | Citas, disponibilidad, roles, chat y symptom checker | Aplicación web convencional; escalabilidad depende de despliegue | Open-source; infraestructura propia | Reúne varias funciones en una aplicación | Menor énfasis en agentes especializados, guardrails de salud mental, protocolos versionados y evaluación E2E específica |
| **CareSync** | Triaje + canalización + agenda + contexto profesional + seguimiento + alertas | Prototipo serverless; escalabilidad futura requiere endurecimiento | Objetivo de bajo costo; estimación del prototipo: USD 4–20/mes | PWA única con cuatro vistas y flujo continuo | No es clínicamente validado, usa datos sintéticos, integración institucional simulada y requiere controles de producción antes de datos reales |

## 6.5 Vacíos y oportunidad identificada

La comparación permite identificar que existe una separación entre dos grupos de soluciones. Por un lado, las herramientas comerciales de symptom checking muestran que la conversación puede utilizarse para recoger síntomas y orientar al usuario. Por otro, los proyectos open-source muestran que es posible construir entrevistas médicas, chatbots, control de roles y agendamiento mediante componentes de software accesibles.

La oportunidad de CareSync consiste en **integrar estas capacidades dentro de un único recorrido de continuidad**, utilizando agentes especializados que compartan el estado del caso y ejecuten acciones posteriores al triaje. La diferenciación no pretende ser un nuevo algoritmo clínico ni un nuevo modelo de lenguaje. El aporte técnico propuesto es demostrar una arquitectura de coordinación entre agentes para un flujo universitario específico, con trazabilidad, control por roles, agenda, seguimiento y mecanismos explícitos de seguridad.

El estado del arte también evidencia que la propuesta no puede interpretarse como una solución clínica lista para producción. Las recomendaciones de la OMS y los marcos de gestión de riesgos de IA refuerzan la necesidad de validación, supervisión humana y gobernanza antes de utilizar sistemas de IA sobre datos reales de salud [3][4]. Esto coincide directamente con las restricciones declaradas por CareSync.

---

# 7. Metodología de desarrollo y plan de trabajo

## 7.1 Enfoque metodológico

El proyecto utilizará un enfoque de **prototipado iterativo**, organizado en ciclos sucesivos de diseño, construcción, prueba y ajuste.

La estrategia será **vertical y no por capas**. En lugar de construir primero todo el backend y posteriormente las interfaces, cada fase buscará producir un recorrido funcional de punta a punta que pueda ser desplegado y demostrado. De esta manera, si una fase presenta retrasos, se puede reducir la profundidad de funciones secundarias sin perder el recorrido principal que se debe sustentar.

El desarrollo se organizará en tres frentes paralelos:

- **Alejandro Santiago — Infraestructura y despliegues:** AWS, CDK, ROBLE, módulo de acceso a datos, entornos, observabilidad y costos.
- **Kevin Ruiz — Agentes e inteligencia artificial:** agentes, prompts, herramientas, protocolos de triaje, guardrails, evaluación y lógica de agenda.
- **Bernardo Álvarez — Aplicación y experiencia:** PWA, cuatro vistas, autenticación desde el cliente, conversación, dictado por voz, consolas administrativas y experiencia de usuario.

Los tres integrantes realizarán revisión cruzada de código y convergerán especialmente durante las pruebas de aceptación y el cierre.

## 7.2 Iteraciones o fases de desarrollo

### Fase 0 — Encuadre y descubrimiento
**Semanas 1–3 | 27 de julio–16 de agosto de 2026**

**Propósito:** cerrar alcance, validar arquitectura y preparar las bases del desarrollo.

**Actividades principales:**

- Levantamiento del flujo actual con los asesores.
- Congelamiento del alcance.
- Diseño y validación de arquitectura.
- Protocolos de triaje v0.
- Habilitación de AWS y alertas de presupuesto.
- Repositorio, tablero y convenciones de trabajo.

**Entregables:**

- Documento de alcance.
- Arquitectura AWS aprobada.
- Protocolos de triaje v0.
- Matriz CMU/CAE.
- Cuenta AWS con límite de gasto.
- Backlog priorizado.

**Hito 1:** alcance y arquitectura aprobados.

### Fase 1 — Fundamentos y esqueleto vivo
**Semanas 4–6 | 17 de agosto–6 de septiembre de 2026**

**Actividades:**

- Prueba de humo de autenticación y CRUD en ROBLE.
- Tablas, tipos y permisos.
- Módulo único de acceso a datos.
- Infraestructura como código con CDK.
- Cascarón de PWA.
- Primer agente mínimo contra Bedrock.
- CI/CD y entornos dev/demo.

**Entregables:**

- Walking skeleton desplegado.
- Informe de prueba de humo de ROBLE.
- Modelo de datos documentado.
- Repositorio reproducible.

**Hito 2:** usuario autenticado que envía un mensaje y recibe respuesta del modelo en AWS.

### Fase 2 — Agente de Triaje e interfaz del paciente
**Semanas 6–9 | 31 de agosto–27 de septiembre de 2026**

**Actividades:**

- Protocolos versionados y prompt caching.
- Preguntas de seguimiento.
- Clasificación de urgencia.
- Ruteo CMU/CAE.
- Guardrails.
- Ruta de emergencia.
- Interfaz completa del paciente.
- Banco aproximado de 40 casos sintéticos.

**Entregables:**

- Agente de Triaje.
- Informe de evaluación.
- Interfaz del paciente.
- Registro de auditoría.

**Hito 3:** Demo 1 con casos físico leve, mental moderado y señal de riesgo.

### Fase 3 — Agenda, logística e interfaces administrativas
**Semanas 9–11 | 21 de septiembre–11 de octubre de 2026**

**Actividades:**

- Motor de disponibilidad.
- Agente de Agenda y Logística.
- Control de doble reserva.
- Resumen estructurado.
- Consolas CMU y CAE.
- Confirmación de citas.
- Adaptador de integración.

**Entregables:**

- Agente de Agenda y Logística.
- Dos consolas administrativas.
- Contrato de integración.
- Plantilla del resumen de caso.

**Hito 4:** Demo 2 con cita agendada y contexto visible para el profesional.

### Fase 4 — Agente de Seguimiento e interfaz profesional
**Semanas 11–13 | 5–25 de octubre de 2026**

**Actividades:**

- Vista profesional.
- Dictado de plan de tratamiento.
- Vista de progreso.
- Recordatorios.
- Registro de adherencia.
- Detección de retrocesos.
- Alertas.
- Ciclo de vida del caso.

**Entregables:**

- Agente de Seguimiento.
- Vista profesional.
- Reglas de alerta.
- Ciclo de vida completo.

**Hito 5:** Demo 3 con plan dictado, recordatorio, reporte de retroceso y alerta.

### Fase 5 — Integración, endurecimiento y pruebas
**Semanas 13–15 | 19 de octubre–8 de noviembre de 2026**

**Actividades:**

- Pruebas E2E de los cuatro roles.
- Revisión de seguridad.
- Pruebas de usabilidad con 6–8 personas y datos sintéticos.
- Ajustes.
- Casos límite.
- Cierre de costos.

**Entregables:**

- Suite E2E.
- Informe de seguridad y privacidad.
- Informe de usabilidad.
- Entorno de demo estable.

**Hito 6:** congelamiento de funcionalidad.

### Fase 6 — Cierre, documentación y sustentación
**Semanas 15–16 | 2–15 de noviembre de 2026**

**Actividades:**

- Documento final.
- Manual de despliegue.
- Guion de demo.
- Video de respaldo.
- Presentación.
- Ensayo.
- Hoja de ruta futura.
- Entrega de repositorio e infraestructura.

**Entregables:**

- Documento final.
- Demo y video.
- Presentación.
- Hoja de ruta.

**Hito 7:** sustentación final prevista para el 13 de noviembre de 2026.

## 7.3 Estrategia de validación

La validación combinará pruebas funcionales, técnicas, de seguridad y de usabilidad.

### Validación funcional

Se verificará que:

- Un caso pueda recorrer las seis etapas E2E.
- Los tres agentes compartan y transfieran un estado trazable.
- Los cuatro roles tengan permisos separados.
- Dos reservas simultáneas sobre un mismo cupo produzcan una sola cita en firme y una alternativa para la segunda persona.
- El plan de tratamiento pueda dictarse por voz y guardarse después de confirmación.
- Un retroceso genere una alerta en menos de cinco minutos.

### Validación del triaje

Se utilizará un banco de casos sintéticos, con una meta mínima de 85 % de acierto en el ruteo CMU/CAE. Los casos con señal de riesgo deberán derivarse a emergencias en el 100 % de las pruebas.

La propuesta no considera que este resultado constituya validación clínica. El objetivo es evaluar el comportamiento del prototipo frente a los protocolos definidos. La validación clínica real requeriría profesionales de salud calificados.

### Validación de usabilidad

En la Fase 5 se realizarán pruebas con **6 a 8 personas de la comunidad**, utilizando exclusivamente datos sintéticos. Las observaciones obtenidas se utilizarán para ajustar las interfaces y las conversaciones.

### Validación de seguridad

Se revisarán:

- Permisos mínimos por función.
- Cifrado en reposo.
- Configuración mediante Parameter Store.
- Registro de accesos.
- Manejo de contenido sensible.
- Guardrails.
- Casos adversariales.
- Ausencia de datos reales.

### Validación de costos

Se comparará el consumo real con la estimación y se revisarán:

- Tokens por sesión.
- Retención de logs.
- Consumo del modelo.
- Uso de servicios AWS.
- Efectividad de la alerta de presupuesto.

## 7.4 Plan de trabajo, cronograma e hitos

| Hito | Resultado verificable | Semana | Fecha |
|---|---|---:|---|
| H1 | Alcance y arquitectura aprobados | 3 | 16 ago. 2026 |
| H2 | Walking skeleton desplegado en AWS | 6 | 6 sep. 2026 |
| H3 | Demo 1: triaje y canalización | 9 | 27 sep. 2026 |
| H4 | Demo 2: cita agendada con contexto | 11 | 11 oct. 2026 |
| H5 | Demo 3: seguimiento y alertas | 13 | 25 oct. 2026 |
| H6 | Congelamiento de funcionalidad | 15 | 8 nov. 2026 |
| H7 | Sustentación final | 16 | 13 nov. 2026 |

El ritmo de trabajo contempla una reunión semanal de sincronización con los asesores, una demo interna al cierre de cada semana y un despliegue al entorno de demostración al final de cada fase. La semana final proporciona una holgura para el cierre y la sustentación.

---

# 8. Referencias

> **Nota:** Las referencias [1]–[10] corresponden a las fuentes externas consultadas para completar el estado del arte y el contexto técnico. La arquitectura, alcance, cronograma, objetivos y demás decisiones específicas de CareSync se derivan de la propuesta técnica proporcionada por el equipo.

[1] Ada Health. (2026). *How do I start a symptom assessment?* Ada. https://ada.com/help/how-do-i-start-a-symptom-assessment/

[2] Buoy Health. (2026). *Symptom Checker: Chat About Symptoms*. Buoy Health. https://www.buoyhealth.com/multi-symptom-checker

[3] World Health Organization. (2021). *Ethics and governance of artificial intelligence for health: WHO guidance*. World Health Organization. https://www.who.int/publications/i/item/9789240029200

[4] Tabassi, E. (2023). *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*. National Institute of Standards and Technology. https://doi.org/10.6028/NIST.AI.100-1

[5] Ada Health. (2026). *¿Ada puede proveer un diagnóstico, consejo médico u opciones de tratamiento? ¿Qué sucede con un diagnóstico erróneo?* Ada. https://ada.com/es/help/360000308945/

[6] Farkas, T. (s. f.). *LangDoc: Accessible open-source symptom checker and anamnesis tool*. GitHub. https://github.com/timfarkas/LangDoc

[7] ruslanmv. (s. f.). *AI Medical Chatbot*. GitHub. https://github.com/ruslanmv/ai-medical-chatbot

[8] Nyakuji. (s. f.). *Health Chatbot*. GitHub. https://github.com/Nyakuji/health-chatbot

[9] Amazon Web Services. (2026, 16 de junio). *Building a HIPAA-ready generative AI architecture for healthcare on AWS*. AWS for Industries. https://aws.amazon.com/blogs/industries/building-a-hipaa-ready-generative-ai-architecture-for-healthcare-on-aws/

[10] Amazon Web Services. (2026, 14 de agosto). *Architecting HIPAA-compliant AI agents to safeguard health data with AWS*. AWS Public Sector. https://aws.amazon.com/blogs/publicsector/architecting-hipaa-compliant-ai-agents-to-safeguard-health-data-with-aws/

---

## Observación sobre las fuentes

Las soluciones comerciales y open-source incluidas en el estado del arte se utilizaron para contextualizar y comparar el problema, no para afirmar que CareSync sea superior en términos clínicos. Las características de Ada, Buoy, LangDoc y los proyectos open-source se tomaron de sus páginas públicas consultadas. Las recomendaciones de gobernanza y gestión de riesgos se sustentan en las publicaciones de la OMS y NIST.

La propuesta de CareSync mantiene como condición fundamental que el prototipo utilice datos sintéticos y que cualquier evolución hacia datos reales requiera controles de seguridad adicionales y validación clínica.
