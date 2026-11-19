# Informe de permisos por rol contra lo desplegado (M7) — CareSync

Generado el 2026-11-19 18:31.

- **M7 — intentos no permitidos con efecto: 0 de 10** (meta: 0).
- Sin cuenta para probarlos: 0.

Cada intento va por el API desplegado con una cuenta real de ROBLE, y el efecto se
comprueba leyendo ROBLE, no sólo por el código HTTP. Ver el docstring de
`evaluar_permisos.py`. No cubre la lectura directa de tablas por la API de ROBLE.

| Intento | Quién | Qué | Se espera | HTTP | Resultado |
|---|---|---|---|:-:|---|
| sin-token | nadie | `POST /agente` sin cabecera Authorization | 401 | 401 | ✅ sin efecto |
| token-falso | nadie | `POST /agente` con un token inventado | 401 | 401 | ✅ sin efecto |
| propuesta | paciente | `POST /plan/propuesta` con un plan dictado | 403, sin propuesta | 403 | ✅ sin efecto |
| dictado | paciente | `POST /dictado/sesion` | 403, sin URL firmada | 403 | ✅ sin efecto |
| simulacion | paciente | `simulacion: true` con un síntoma | 403 | 403 | ✅ sin efecto |
| caso-ajeno | paciente | escribir en el caso de otra persona con su `caso_id` | 403, el hilo ajeno no cambia | 403 | ✅ sin efecto |
| identidad-en-el-cuerpo | paciente | `rol: profesional`, `user_id` y `paciente_user_id` ajenos y `centro` en el cuerpo | atendido en su propio caso; el hilo ajeno no cambia | 200 | ✅ sin efecto |
| herramienta-del-personal | paciente | forzar `agente: agenda` y pedir qué profesionales hay y cuántos espacios tiene cada uno | `consultar_profesionales` no se ejecuta | 200 | ✅ sin efecto |
| agenda-sin-triaje | paciente | forzar `agente: agenda` en un caso nuevo y pedir una cita en el CMU | ninguna cita | 200 | ✅ sin efecto |
| plataforma-conversa | admin_plataforma | `POST /agente` | 403, ningún caso nuevo | 403 | ✅ sin efecto |

## Respuestas

- **sin-token**: {"error": "Tu sesión no es válida o expiró. Vuelve a iniciar sesión."}
- **token-falso**: {"error": "Tu sesión no es válida o expiró. Vuelve a iniciar sesión."}
- **propuesta**: {"error": "Esto es sólo para profesionales que atienden."}
- **dictado**: {"error": "Esto es sólo para profesionales que atienden."}
- **simulacion**: {"error": "Tu rol no permite esta acción."}
- **caso-ajeno**: {"error": "Tu rol no permite esta acción."}
- **identidad-en-el-cuerpo**: 200 con respuesta del agente; caso 04609e4f, agentes ['triaje']
- **herramienta-del-personal**: 200 con respuesta del agente; caso b938c7cf, agentes ['agenda'] Herramientas: consultar_profesionales (rechazada: Tu rol no permite esta acción.).
- **agenda-sin-triaje**: 200 con respuesta del agente; caso 492c066a, agentes ['agenda'] Herramientas: consultar_disponibilidad (rechazada: Este caso todavía no está canalizado a un centro, así que no se puede agendar. Completa el triaje primero.).
- **plataforma-conversa**: {"error": "Tu rol no permite esta acción."}