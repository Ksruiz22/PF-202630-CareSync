# App móvil de CareSync

La app del paciente para el **Agente de Seguimiento**: ver el plan que escribió el
profesional, responder si cumplió cada indicación, recibir los recordatorios y contarle
al asistente cómo se siente. React Native con Expo; también corre en el navegador.

## Cómo encaja con el resto

| | Quién | Qué hace la app |
|---|---|---|
| **Triaje** | PWA y orquestador | Nada nuevo: un caso abierto en la PWA aparece aquí. Un problema distinto lo abre el agente con `nuevo_motivo` |
| **Agenda** | Orquestador | Muestra las citas y sus recordatorios. «Agendar» abre la conversación con `agente: 'agenda'` |
| **Seguimiento** | Esta app y orquestador | Reportar una toma va directo a `adherencia`; cómo se siente va siempre por el agente |

Por qué se reparte así, y por qué se aparta de la PWA: comentario de cabecera de
`src/fuenteRoble.ts`.

## Correrla

**No se instala dentro de esta carpeta**: está en OneDrive, y `node_modules` son cientos
de miles de archivos sincronizándose. Se copia a WSL, como las pruebas de la PWA:

```bash
wsl --cd "/mnt/c/Users/asantiago/OneDrive - Muebles Jamar/Documentos/Universidad/PF/caresync/movil" -e bash -lc "scripts/copia_de_trabajo.sh"
```

El script deja la copia en `~/_scratch/<fecha>/movil`, instala y arranca en
`http://localhost:5173`. **Ese puerto no es capricho**: es el único de desarrollo que el
API admite por CORS (`infra/locales.tf`). Con otro, ROBLE funciona y el asistente falla.

En un teléfono: `npx expo start` en esa copia y abrir el QR con Expo Go. Las notificaciones
programadas funcionan ahí; en el navegador sólo mientras la pestaña esté abierta.

Pruebas y tipos: `npm run prueba` y `npm run typecheck`.

## El modo de demostración

Con `EXPO_PUBLIC_DEMO=1` aparece «Ver demostración»: datos inventados en memoria, sin
cuenta, sin tocar ROBLE ni el agente. Sirve para recorrer todos los tipos de indicación,
que en la base real todavía nadie escribe (ver abajo).

## Lo que todavía no está

- **La vista del profesional no guarda `tipo`** ni las demás columnas de `indicaciones`.
  Hasta entonces toda indicación real es `otro`: se pregunta según su `frecuencia`, y no
  hay controles por agendar, series ni vigilancias.
- **No hay push.** Las notificaciones son locales: se programan al abrir la app, para tres
  días. Un push real necesita la tabla `dispositivos` y que la Lambda envíe.
- **Las horas de cada toma son una convención** (`src/agenda.ts`: desde las 7:00, la última
  a las 22:00), y falta que alguien con criterio clínico las valide.
- **Registrarse** sigue en la PWA.
