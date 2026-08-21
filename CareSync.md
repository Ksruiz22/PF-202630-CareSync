# CareSync Agentic Network — Uninorte

**Campo:** Salud

**Docente proponente:** Dadier Jabba

**Co-asesor:** Augusto Salazar

**Estudiantes:** 3

- **Alejandro Santiago** — Construcción de infraestructura y despliegues: cuenta AWS, infraestructura como código (Terraform, aplicada desde GitHub Actions con acceso por OIDC), proyecto y modelo de datos en ROBLE, módulo de acceso a datos, entornos de desarrollo y demo, despliegue continuo, observabilidad y control de costos.
- **Kevin Ruiz** — Agentes e inteligencia artificial: los tres agentes (Triaje, Agenda y Logística, Seguimiento), prompts y bucle de herramientas, protocolos de triaje y matriz de decisión CMU/CAE, salvaguardas de contenido y evaluación de la canalización.
- **Bernardo Álvarez** — Aplicación y experiencia: aplicación web con las cuatro vistas por rol (paciente, profesional, administrativa CMU y administrativa CAE), autenticación desde el cliente, dictado por voz del plan de tratamiento, sistema de diseño y accesibilidad.

Los tres comparten las pruebas de aceptación, la documentación, la sustentación y la revisión cruzada de código.

**Comunidad objetivo:** Miembros de la comunidad de la Universidad del Norte (estudiantes, docentes, colaboradores, egresados y sus familias).

**Centros de atención:**
- **Centro Médico Uninorte (CMU):** sede del Hospital Universidad del Norte dentro del campus, para atención en salud física.
- **Centro de Acompañamiento Estudiantil (CAE) – Bienestar y Vida Universitaria:** para atención en salud mental.

## Descripción corta

Red de agentes especializados que colaboran entre sí para acompañar a un miembro de la comunidad Uninorte desde que presenta los primeros síntomas o malestar hasta su recuperación. Según el tipo de necesidad, el sistema canaliza al usuario hacia el Centro Médico Uninorte (salud física) o hacia el Centro de Acompañamiento Estudiantil (salud mental), y le da seguimiento posterior a la atención.

## Objetivo

Ofrecer a la comunidad universitaria un acompañamiento continuo y coordinado a lo largo de todo su proceso de atención —triaje, canalización al servicio adecuado dentro del campus, agendamiento y seguimiento posterior— reduciendo la carga administrativa de los servicios de salud de Uninorte y evitando que casos tratables se agraven por falta de seguimiento oportuno.

## Alcance de la propuesta

El sistema se compone de tres agentes coordinados y de un conjunto de interfaces para los distintos actores, integrados con los servicios de salud de la Universidad del Norte.

### Agentes

**Agente de Triaje:** interactúa por texto con la persona, evalúa la gravedad de los síntomas siguiendo los protocolos de triaje definidos y determina el nivel de urgencia. Distingue entre necesidades de salud física y de salud mental para canalizar cada caso al servicio correcto: el Centro Médico Uninorte o el Centro de Acompañamiento Estudiantil.

**Agente de Agenda y Logística:** una vez definida la ruta, agenda la cita en el servicio correspondiente dentro del campus (CMU o CAE) y envía un resumen del caso al profesional que atenderá —médico o psicólogo— para que llegue con contexto. En situaciones que requieran urgencia, orienta al usuario hacia los canales de emergencia disponibles en el campus.

**Agente de Seguimiento:** tras la atención, acompaña al usuario a través de su interfaz. Monitorea de forma proactiva la adherencia a las indicaciones o a la medicación (mediante recordatorios) y hace seguimiento a la evolución de los síntomas o del estado reportado por la persona; ante cualquier anomalía o retroceso, alerta al equipo tratante correspondiente.

### Interfaces del sistema

**Interfaz del usuario/paciente:** de cara a la persona que busca atención. Es el punto de entrada al sistema: desde ella el usuario describe por texto sus síntomas o malestar e interactúa con el Agente de Triaje, recibe la canalización y confirmación de su cita, y durante el seguimiento reporta su evolución, registra la adherencia a las indicaciones y recibe los recordatorios y alertas del Agente de Seguimiento.

**Interfaz del profesional (médico o psicólogo):** de cara a quien presta el servicio. Le permite generar el plan de tratamiento del paciente a partir de un texto (que puede dictarse por voz para agilizar la redacción) y consultar el progreso del paciente a lo largo del seguimiento.

**Interfaz administrativa por centro de atención:** una para el CMU y otra para el CAE. Permite ingresar a los doctores del centro, definir sus horarios y tiempos de atención, y visualizar el agendamiento de citas.

El impacto esperado es aliviar la carga administrativa de los servicios de salud del campus, mejorar la continuidad del cuidado y ofrecer a la comunidad Uninorte un acompañamiento cercano y disponible.

## Alcance del prototipo

Esta propuesta se plantea como un **prototipo** para validar el flujo de atención de extremo a extremo (triaje, canalización, agendamiento, plan de tratamiento y seguimiento) más que como un sistema clínico de producción. En esta etapa, dado que el equipo aún no cuenta con un especialista del área de la salud, los **protocolos de triaje se mantendrán deliberadamente básicos**: sirven para demostrar la canalización y la lógica del sistema, y deberán ser revisados y refinados por personal clínico calificado antes de cualquier uso real.

## Riesgos

- **Privacidad y confidencialidad de datos sensibles:** el sistema maneja información de salud física y mental de la comunidad universitaria, lo que exige cumplimiento normativo estricto y especial cuidado con los datos de salud mental.
- **Protocolos de triaje sin validación clínica:** al ser un prototipo sin un especialista en el equipo, los criterios de triaje son básicos y podrían clasificar mal un caso; requieren validación profesional antes de un uso real.
- **Dependencia de la integración con los servicios de Uninorte:** el funcionamiento depende de la conexión con los sistemas de agendamiento del CMU y del CAE; fallos o falta de integración con estos servicios comprometen toda la cadena de atención.
