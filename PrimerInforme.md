# CareSync Agentic Network — Uninorte

## Resumen / Abstract

CareSync Agentic Network es un prototipo de una arquitectura multiagente orientada a mejorar la continuidad del proceso de atención en salud dentro de la comunidad de la Universidad del Norte. La propuesta busca coordinar las etapas de orientación, triaje, canalización, agendamiento y seguimiento mediante agentes especializados. El sistema contempla inicialmente tres agentes: Triaje, Agenda y Logística, y Seguimiento, junto con interfaces para usuarios, profesionales y administradores. El proyecto se desarrollará mediante prototipado iterativo, avanzando desde el análisis y diseño hasta la implementación, integración y validación mediante escenarios controlados. Actualmente, el equipo se encuentra en la etapa de definición del alcance, planificación de reuniones e investigación de tecnologías para una posible implementación.

---

# 1. Introducción

## Contexto

El sector salud ha incorporado progresivamente tecnologías como sistemas de información, inteligencia artificial, automatización y servicios digitales para mejorar la atención y gestión de los usuarios. En este contexto, los sistemas conversacionales y las arquitecturas multiagente permiten distribuir tareas entre componentes especializados y automatizar determinados procesos administrativos y de orientación.

En entornos universitarios, la atención puede involucrar diferentes servicios, actores y procesos. La gestión de una necesidad de salud puede requerir orientación inicial, identificación del servicio adecuado, agendamiento, atención profesional y seguimiento posterior. Cuando estas etapas se encuentran separadas, el usuario puede tener que realizar múltiples interacciones para completar su proceso.

Esto plantea una oportunidad para desarrollar una arquitectura capaz de mantener el contexto de un caso y coordinar diferentes etapas mediante agentes especializados. El principal reto técnico consiste en definir las responsabilidades de cada agente, establecer mecanismos de comunicación entre ellos y mantener la trazabilidad del proceso.

Como respuesta se propone **CareSync Agentic Network**, un prototipo orientado a la comunidad de la Universidad del Norte. La solución contempla agentes de Triaje, Agenda y Logística, y Seguimiento, con el objetivo de representar un flujo continuo desde la identificación inicial de una necesidad hasta el seguimiento posterior a la atención.

---

# 2. Planteamiento del problema

## 2.1 Descripción del problema

Los miembros de una comunidad universitaria pueden presentar necesidades relacionadas con su salud física o mental y requerir atención en diferentes servicios institucionales. El proceso puede involucrar varias etapas: identificar la necesidad, determinar el servicio adecuado, gestionar una cita, recibir atención y realizar seguimiento.

La problemática identificada es la **fragmentación del proceso de atención y la falta de continuidad entre sus diferentes etapas**, lo que puede generar una mayor carga administrativa y una experiencia menos integrada para los usuarios.

Esta problemática es aplicable a diferentes instituciones que cuentan con múltiples servicios de atención y diferentes actores involucrados en el proceso.

## 2.2 Justificación

La coordinación de las diferentes etapas de atención representa una oportunidad para aplicar tecnologías de automatización e inteligencia artificial sin reemplazar las funciones de los profesionales de la salud.

Desde el punto de vista técnico, el proyecto permite explorar arquitecturas multiagente, integración de servicios, gestión de información y sistemas conversacionales.

Desde el punto de vista académico, permite evaluar la aplicación de agentes inteligentes en un dominio sensible, considerando aspectos de trazabilidad, privacidad, seguridad y límites de automatización.

## 2.3 Restricciones y supuestos iniciales

- El proyecto se desarrollará como un prototipo académico.
- Se utilizarán datos ficticios durante las pruebas.
- Los protocolos de triaje serán básicos y deberán ser validados profesionalmente antes de cualquier uso real.
- El sistema no realizará diagnósticos ni prescripciones médicas.
- Las integraciones con sistemas reales de Uninorte estarán fuera del alcance inicial.
- La disponibilidad de profesionales y citas podrá ser simulada.
- El tiempo y recursos disponibles estarán limitados al periodo académico del proyecto.

---

# 3. Alcance del proyecto

## Incluye

- Prototipo web funcional.
- Agente de Triaje.
- Agente de Agenda y Logística.
- Agente de Seguimiento.
- Componente de coordinación entre agentes.
- Interfaz para usuarios.
- Interfaz para profesionales.
- Interfaz administrativa.
- Gestión de usuarios y casos.
- Gestión de profesionales, horarios y citas.
- Seguimiento posterior a la atención.
- Recordatorios y alertas básicas.
- Registro de las acciones realizadas por los agentes.
- Simulación de los servicios del CMU y CAE.
- Pruebas mediante escenarios controlados.

El flujo principal será:

**Triaje → Canalización → Agendamiento → Atención → Seguimiento**

### Nivel de madurez

El resultado será un **prototipo funcional/MVP académico**, orientado a validar el concepto y la arquitectura propuesta.

### Entornos

La solución se plantea inicialmente como una aplicación **web**, con frontend, backend, base de datos y servicios de inteligencia artificial.

## No incluye

- Diagnóstico médico autónomo.
- Prescripción de medicamentos.
- Uso de historias clínicas reales.
- Integración con sistemas clínicos institucionales.
- Implementación en producción.
- Infraestructura de alta disponibilidad.
- Integraciones externas no esenciales.
- Operación y soporte posterior al proyecto.

---

# 4. Objetivos

## 4.1 Objetivo general

**Desarrollar un prototipo de una arquitectura multiagente que permita coordinar la orientación, canalización, agendamiento y seguimiento de necesidades de salud física y mental dentro de la comunidad de la Universidad del Norte.**

## 4.2 Objetivos específicos

1. **Analizar** los requerimientos asociados al proceso de orientación, canalización, agendamiento y seguimiento de servicios de salud.

2. **Diseñar** una arquitectura multiagente que defina las responsabilidades y mecanismos de comunicación entre los agentes de Triaje, Agenda y Seguimiento.

3. **Implementar** un prototipo web que integre los agentes, las interfaces y los servicios de gestión de información necesarios.

4. **Integrar** mecanismos de almacenamiento y trazabilidad para mantener el estado de los casos y registrar las acciones realizadas por los agentes.

5. **Evaluar** el funcionamiento del prototipo mediante escenarios controlados de salud física, salud mental y atención prioritaria.

---

# 5. Solución propuesta

CareSync Agentic Network propone una arquitectura de agentes especializados que colaboran para coordinar el proceso de atención.

### Agente de Triaje

Recibe la información inicial del usuario, realiza una clasificación básica y determina la ruta correspondiente entre salud física y salud mental.

### Agente de Agenda y Logística

Gestiona la disponibilidad de profesionales y la asignación de citas de acuerdo con el servicio seleccionado.

### Agente de Seguimiento

Permite registrar la evolución del usuario después de la atención, generar recordatorios y detectar situaciones que requieran revisión.

### Orquestador

Coordina la interacción entre los agentes y mantiene el estado general de cada caso.

### Usuarios del sistema

- **Usuario/paciente:** inicia el proceso y consulta su seguimiento.
- **Profesional:** consulta el caso y registra la atención.
- **Administrador:** gestiona profesionales, horarios y citas.

---

# 6. Estado del arte / soluciones relacionadas

Actualmente existen soluciones que cubren diferentes partes del proceso de atención.

| Solución | Triaje | Agenda | Seguimiento | Agentes |
|---|---|---|---|---|
| Ada Health | ✓ | — | Limitado | — |
| Buoy Health | ✓ | — | Limitado | — |
| Zocdoc | — | ✓ | — | — |
| Microsoft Healthcare Agent Service | ✓ | Integrable | Integrable | ✓ |
| **CareSync** | ✓ | ✓ | ✓ | ✓ |

### Ada Health

Plataforma orientada a la evaluación de síntomas mediante interacción conversacional. Su principal enfoque está en la orientación inicial del usuario.

### Buoy Health

Utiliza inteligencia artificial para recopilar información sobre síntomas y orientar al usuario sobre posibles pasos de atención.

### Zocdoc

Plataforma enfocada principalmente en la búsqueda de profesionales y gestión de citas.

### Microsoft Healthcare Agent Service

Proporciona herramientas para construir agentes relacionados con escenarios de salud, incluyendo capacidades de interacción, orquestación e integración con otros servicios.

### Oportunidad identificada

Las soluciones existentes muestran que el triaje conversacional y la gestión digital de citas son técnicamente viables. Sin embargo, existe una oportunidad para explorar una solución que integre estas capacidades con seguimiento posterior y coordinación multiagente dentro de un contexto institucional específico.

Como referencia para el diseño de información sanitaria también se considerará **HL7 FHIR**, especialmente para conceptos como pacientes, profesionales, citas y planes de atención.

---

# 7. Metodología de desarrollo y plan de trabajo

## 7.1 Enfoque metodológico

Se utilizará un enfoque de **prototipado iterativo**, permitiendo construir la solución progresivamente mediante ciclos de:

**Diseño → Construcción → Prueba → Retroalimentación → Ajuste**

Este enfoque permitirá validar tempranamente la arquitectura, las interfaces y el comportamiento de los agentes.

## 7.2 Iteraciones o fases de desarrollo

### Fase 1 — Análisis

- Validación del problema.
- Levantamiento de requerimientos.
- Identificación de usuarios.
- Definición de casos de uso.

### Fase 2 — Diseño

- Arquitectura del sistema.
- Diseño de agentes.
- Modelo de datos.
- Diseño de interfaces.

### Fase 3 — Implementación

- Frontend.
- Backend.
- Base de datos.
- Agentes inteligentes.

### Fase 4 — Integración

- Comunicación entre agentes.
- Integración con la base de datos.
- Integración de interfaces.
- Flujo completo de atención.

### Fase 5 — Validación

- Pruebas funcionales.
- Pruebas de escenarios.
- Evaluación de agentes.
- Corrección de errores.

## 7.3 Estrategia de validación

La validación se realizará mediante escenarios controlados, incluyendo:

- Caso de salud física.
- Caso de salud mental.
- Caso prioritario.
- Ausencia de disponibilidad.
- Reprogramación de cita.
- Seguimiento favorable.
- Generación de alerta.

Se evaluará principalmente el cumplimiento del flujo, la correcta interacción entre agentes, la trazabilidad y el funcionamiento de las interfaces.

## 7.4 Plan de trabajo

| Etapa | Actividad | Resultado |
|---|---|---|
| 1 | Definir problema y alcance | Alcance validado |
| 2 | Reunión y revisión con profesor | Requerimientos iniciales |
| 3 | Investigar tecnologías | Stack tecnológico |
| 4 | Diseñar arquitectura | Arquitectura definida |
| 5 | Diseñar interfaces y BD | Diseño técnico |
| 6 | Implementar agentes | Agentes funcionales |
| 7 | Desarrollar aplicación | MVP |
| 8 | Integrar componentes | Prototipo integrado |
| 9 | Realizar pruebas | Resultados |
| 10 | Ajustar y documentar | Versión final |

### Progreso actual

El proyecto se encuentra actualmente en la **fase inicial de definición y planificación**.

Hasta el momento se ha trabajado en:

- Definición del alcance inicial.
- Definición de los tres agentes principales.
- Identificación de usuarios e interfaces.
- Definición preliminar del flujo de atención.
- Planificación de reuniones con el profesor.
- Investigación inicial de tecnologías para una posible implementación.

El siguiente paso consiste en validar el alcance y avanzar hacia el levantamiento detallado de requerimientos y el diseño de la arquitectura.

---

# Tecnologías inicialmente consideradas

| Tecnología | Propósito |
|---|---|
| **Next.js / React** | Frontend y estructura de la aplicación web |
| **TypeScript** | Lenguaje principal |
| **Supabase** | Backend, autenticación y servicios |
| **PostgreSQL** | Base de datos |
| **Anthropic API** | Capacidades de inteligencia artificial |
| **Agents SDK / Responses API** | Implementación de agentes |
| **Figma** | Diseño UI/UX |
| **GitHub** | Control de versiones y colaboración |
| **Postman** | Pruebas de API |
| **Vercel** | Despliegue |

El stack definitivo será seleccionado después del análisis de requerimientos y diseño técnico.

---

# 8. Referencias

- Ada Health. *Symptom Assessment*. https://ada.com/
- Buoy Health. *Symptom Checker*. https://www.buoyhealth.com/
- HL7 International. *FHIR Overview*. https://fhir.hl7.org/
- Microsoft. *Healthcare Agent Service*. https://learn.microsoft.com/
- Zocdoc. *Online Healthcare Appointment Platform*. https://www.zocdoc.com/
- Supabase. *Documentation*. https://supabase.com/docs
- OpenAI. *API Documentation*. https://platform.openai.com/docs
- Next.js. *Documentation*. https://nextjs.org/docs
