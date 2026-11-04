<!--
Base de orientación de los centros, v0. SIN VALIDAR POR EL CMU NI EL CAE.

La escribió el equipo de desarrollo el 2026-10-29 para que los agentes puedan
responder dudas de información sin inventarlas. Antes no había ninguna, y la regla
de no mandar a la persona a canales que no existen dejaba dos salidas: decir «no
sé» o canalizar la duda a un centro que no tiene cómo responderle.

Sólo dice lo que es cierto por cómo funciona CareSync, más la dirección de la
universidad. No inventa edificios, horarios ni costos: donde falta un dato, lo dice,
y el agente responde que no lo tiene. Los huecos marcados con «Pendiente» los
tienen que llenar los centros antes de cualquier uso real.

Es la única copia. `scripts/construir_paquetes.sh` la mete en el paquete del
orquestador, y `agentes.py` la pone en el prompt de los tres agentes sin estos
comentarios: lo que va entre comentarios es para quien mantiene el archivo.
-->

## Qué es CareSync

CareSync orienta a la comunidad de la Universidad del Norte en salud física y
mental, y la conecta con dos servicios del campus: el Centro Médico Uninorte (CMU)
y el Centro de Acompañamiento Estudiantil (CAE). Hace el triaje, agenda la cita y
acompaña después de la consulta. No responde preguntas sobre otros servicios de la
universidad, como la biblioteca, matrículas, notas o trámites académicos.

## Los dos centros

- **CMU**: salud física. Consulta por síntomas, lesiones, control de condiciones ya
  diagnosticadas, salud sexual y reproductiva, y certificados médicos.
- **CAE**: salud mental y acompañamiento psicológico. Ánimo bajo, ansiedad, estrés,
  duelo, conductas alimentarias, consumo de sustancias, y situaciones de violencia o
  acoso.
- Los dos están en el campus de la Universidad del Norte, km 5 de la vía a Puerto
  Colombia, en Barranquilla.
- El edificio de cada centro no está en esta información.
  <!-- Pendiente de los centros: edificio, piso y cómo llegar. -->
- Los horarios dependen de los espacios que publica cada centro. Los que hay los ve
  la persona cuando pide la cita.
  <!-- Pendiente de los centros: horario general de atención. -->
- Los costos no están en esta información.
  <!-- Pendiente de los centros: si la consulta tiene costo y para quién. -->

## Citas

- Se piden en esta conversación. El agente busca los espacios del centro que
  corresponde y los ofrece.
- Para cancelar o cambiar una cita, la persona lo escribe en esta misma
  conversación. Cancelarla a tiempo deja el espacio libre para otra persona.
- A la cita conviene llevar el documento de identidad o el carné, y la lista de
  medicamentos que se estén tomando.
- Conviene llegar unos minutos antes de la hora.
- Algunas citas son virtuales. La modalidad aparece en cada espacio que ofrece el
  agente.

## Certificados médicos

- Un certificado médico lo expide un profesional del CMU en una consulta. Por esta
  conversación no se expide ninguno.
- Si la persona necesita uno, se le ofrece una cita en el CMU.

## Después de la consulta

- El profesional deja un plan con indicaciones.
- El asistente de CareSync acompaña a la persona con ese plan: le pregunta cómo va,
  le recuerda las indicaciones y, si va peor, le deja una alerta al profesional.

## Quién ve lo que la persona escribe

- El profesional que la atiende ve el resumen que escribe el agente de triaje.
- La conversación completa la puede abrir el personal de su centro, para revisar si
  el triaje estuvo bien hecho, y cada vez que alguien la abre queda registrado.
