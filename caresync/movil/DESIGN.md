# Diseño de la app móvil

Las decisiones visuales de la app del paciente y su porqué. Los valores viven en
`src/tema.ts`; este archivo dice cuándo usar cada cosa. Si una pantalla nueva necesita
algo que no está aquí, se agrega aquí primero.

## Para quién y en qué escena

Estudiantes de Uninorte que siguen un tratamiento del CMU o del CAE. Miran el teléfono
entre clases, muchas veces al sol, y también de noche para la última toma. La pantalla
tiene que responder en segundos dos preguntas: **qué me toca ahora y qué sigue**.

Es una app de trabajo, no de presentación: lo familiar es una virtud. La marca está en
los detalles —el color, la letra, el horario de Hoy—, no en controles inventados.

## La pantalla de inicio: el resumen

Hoy abre con un panel en el color de marca —el único bloque así en la app— con el
saludo, la fecha y hasta tres puntos: lo diario por hacer hoy (contado, «3 pendientes
por hacer hoy», porque el detalle está justo debajo), la próxima cita, y lo que se hace
una sola vez con fecha límite (nombrado con su fecha, porque no es diario y un número
solo no dice qué hacer). «Cuéntanos cómo te sientes» se quitó: la escala tiene su
propia tarjeta. Cada punto tiene su versión resuelta en verde
con una marca («No tienes citas próximas»): saber que no falta nada también es
información, y sin ella la ausencia de un punto parecería un fallo de carga. El coral
marca lo que pide atención; el blanco, lo informativo.

## La idea: el día como horario de clases

La pantalla Hoy se lee como el horario que un estudiante ya mira cada día: horas en una
columna, una línea que las une y una marca de **Ahora**. Es el único elemento con
personalidad propia; todo lo demás es sobrio a propósito.

- Sólo lleva botones lo que ya se puede responder (desde una hora antes).
- Cada toma dice su frecuencia **y cuál es del día**: «Cada 8 horas, la 2 de 3 de hoy».
  La frecuencia es la regla del profesional; la posición dice dónde va la persona. Se
  quitó una vez pensando que el horario ya lo mostraba, y obligaba a contar puntos
  justo al marcar.
- Lo respondido queda en la línea con un punto verde y su etiqueta.
- Lo que falta va en gris, sin botones: no hay nada que hacer todavía.

## Color

Estrategia sobria: neutros con un tinte verde y un solo acento, el verde azulado de la
marca, que es el mismo de la PWA.

| Token | Para qué |
|---|---|
| `primario` | Acciones principales, la pestaña activa, la marca de Ahora |
| `coral` | Lo que espera respuesta (contador, puntos del horario) y las señales de alarma |
| `verde` | Lo hecho |
| `ambar` | Lo que no se pudo, y la etiqueta de demostración |
| `rojo` | Sólo la franja de emergencia y los errores |

El coral no se usa como decoración: si aparece, algo pide atención. Todos los pares de
texto sobre fondo pasan 4,5:1 en claro y en oscuro (medido el 2026-11-09).

## Letra

Una sola familia, **Atkinson Hyperlegible**, en regular y negrita. Está hecha para que
no se confundan caracteres parecidos (I, l, 1; O, 0), que es lo que importa al leer una
dosis o una hora. El peso va siempre en `fontFamily` (`F.regular`, `F.negrita`), nunca en
`fontWeight`: con una fuente cargada, el navegador inventa una negrita falsa y Android
la ignora.

Escala de 1,2 entre pasos: 13 (pie), 14 (fino), 16 (texto), 19 (título), 26 (pantalla).

## Estructura

- **`Seccion`** para listas: el título sobre el fondo y las filas en una sola superficie
  separadas por una línea fina, como los ajustes del teléfono.
- **`Tarjeta`** sólo para lo que es una unidad propia: la próxima cita, cómo te sientes.
  No es el contenedor por defecto: una pantalla de tarjetas iguales no deja ver qué
  importa.
- Superficies sin borde, separadas del fondo por contraste y una sombra corta.
- Espaciado en múltiplos de 4 (`S` en `tema.ts`); 24 entre bloques de una pantalla.

## Movimiento

Poco, rápido y siempre para explicar un cambio (`src/movimiento.tsx`). Nada de
entradas escalonadas al abrir una pantalla: obligan a esperar algo que ya está ahí.

| Qué | Cómo | Duración |
|---|---|---|
| Abrir la app, entrar o salir | Fundido desde 0 y escala desde 0,97 | 420 ms |
| Cambiar de pestaña | *Fade-through*: opacidad desde 0,4 y escala desde 0,98 | 220 ms |
| Marcar una toma | La etiqueta aparece; el punto del horario rebota al completarse la hora | 140 ms / resorte |
| Pulsar | Opacidad 0,8 mientras se mantiene | inmediato |

Con «Reducir movimiento» activado no hay escala ni rebote, sólo un fundido más corto.
Las marcas de «hecho» sólo se animan si la respuesta ocurrió con la pantalla abierta;
al abrir la app con tomas ya respondidas no se anima nada.

## Reglas que ya costaron un arreglo

- **Botones de al menos 44 de alto**, y los de dos en fila con etiquetas cortas: a
  360 px, «Sí, lo hice» partía en dos renglones.
- **Nada de etiquetas encima de los títulos** ni datos unidos con «·»: el título y una
  frase completa dicen lo mismo con menos ruido.
- **Un botón dice a dónde lleva** cuando abre el asistente («Cambiar o cancelar con el
  asistente»): el salto de pestaña sin aviso parecía un error.
- **Los iconos son de Ionicons**, contorno en reposo y relleno en la pestaña activa. Ni
  emoji ni caracteres sueltos como iconos.

## Cómo verificar un cambio visual

En el navegador (`npx expo start --web --port 5173`), en tamaño de teléfono, en claro y
en oscuro, y al menos una vez a 360 px de ancho. Lo propio del teléfono —la barra de
gestos de Android, el teclado sobre el chat, el botón Llamar— se confirma con Expo Go.
