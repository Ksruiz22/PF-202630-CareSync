# CareSync Agentic Network

## Resumen ejecutivo

CareSync Agentic Network es un prototipo funcional, desarrollado como Proyecto Final de la Universidad del Norte, que demuestra cómo una red de agentes de inteligencia artificial puede sostener la continuidad del cuidado de un miembro de la comunidad universitaria. Surge de una observación sobre los servicios de atención de Uninorte: las etapas del recorrido (orientación, canalización hacia el Centro Médico o hacia Bienestar Universitario, agendamiento y seguimiento) ya existen por separado, pero el contexto del caso se pierde entre una y otra, y nada comprueba de forma sistemática cómo sigue la persona después de la consulta.

La solución son tres agentes que comparten el estado del caso y se lo transfieren de forma explícita: uno hace el triaje y canaliza al centro correcto sin diagnosticar, otro agenda la cita y avisa al profesional con un resumen, y un tercero hace el seguimiento y alerta ante un retroceso. Ante cualquier señal de alarma, el sistema interrumpe todo y muestra la ruta de emergencia. Los agentes se usan desde una aplicación web con una vista por rol; los datos de salud se guardan en ROBLE, dentro de la infraestructura de la universidad, y el razonamiento corre en AWS.

El alcance es un prototipo de punta a punta con datos exclusivamente sintéticos y sin validación clínica. Su valor está en mostrar, con evidencia medida, que esta coordinación es viable y segura por diseño: en la evaluación contra el sistema desplegado, el agente derivó a emergencias el 100 % de los casos de alarma y acertó el centro en el 88,5 % de los casos.

**Aplicación publicada:** https://main.d1ndsh656qxmj8.amplifyapp.com/

## Documentación del repositorio

### Primer informe

- [Primer Informe.md](./Primer_Informe_CareSync.md): Documento que presenta el planteamiento del problema, los objetivos, la solución propuesta, el estado del arte, la metodología de desarrollo y el plan de trabajo del proyecto.

### Segundo informe

- [Segundo Informe.md](./SegundoInforme.md): Documento que presenta el estado actual del proyecto, incluyendo los avances logrados, las validaciones realizadas y los aspectos pendientes.

### Informe final

| Documento | Descripción |
|---|---|
| InformeFinal.md | Documento principal del proyecto (se entregará con la versión final) |
| Instalación.md | Guía de instalación, desarrollo y despliegue (se entregará con la versión final) |
| Desarrollo.md | Detalles técnicos del desarrollo (se entregará con la versión final) |

## Estudiantes

| Nombre | GitHub |
|---|---|
| Alejandro Santiago | [@calcoach](https://github.com/calcoach) |
| Kevin Ruiz Espitia | [@Ksruiz22](https://github.com/Ksruiz22) |
| Bernardo Álvarez | [@Bern723](https://github.com/Bern723) |

## Tutores

- Dadier Jabba
- Augusto Salazar
