# Informe de concurrencia de reservas (M4) — CareSync

Generado el 2026-11-05 21:44. Centro CMU, 10 pares, desfase del segundo intento 150 ms.

- **Dobles reservas: 0 de 10** (meta: 0).
- Citas en firme: 10 de 10 (meta: 10).
- Pares en que el perdedor recibió alternativas: 10 de 10 (meta: 10).
- Citas sobre un cupo que quedó libre (doble reserva latente): 0.
- Pares sin ninguna cita (los dos cedieron): 0.
- Intentos que terminaron en error y no en «ese ya lo tomaron»: 0.

Cada par son dos casos de prueba compitiendo por el mismo cupo con
`agenda._reservar_y_confirmar`, la función de la Lambda de herramientas, contra
ROBLE real. Ver el docstring de `evaluar_concurrencia.py`.

| Par | Cupo | A | B | Citas confirmadas | Cupo después | Resultado |
|---|---|---|---|:-:|---|---|
| 1 | ba354bb8 13/11 09:30 | cita (1214 ms) | tomado, 3 alt. (737 ms) | 1 | confirmado | ✅ |
| 2 | ae7d6446 13/11 09:00 | cita (1101 ms) | tomado, 3 alt. (696 ms) | 1 | confirmado | ✅ |
| 3 | e31840fc 13/11 08:30 | cita (1120 ms) | tomado, 3 alt. (699 ms) | 1 | confirmado | ✅ |
| 4 | cadb9e3e 13/11 08:00 | cita (1095 ms) | tomado, 3 alt. (690 ms) | 1 | confirmado | ✅ |
| 5 | 3b4cebcc 12/11 09:30 | cita (1102 ms) | tomado, 3 alt. (793 ms) | 1 | confirmado | ✅ |
| 6 | 3ce694e0 12/11 09:00 | cita (1137 ms) | tomado, 3 alt. (762 ms) | 1 | confirmado | ✅ |
| 7 | 57414047 12/11 08:30 | cita (1090 ms) | tomado, 3 alt. (704 ms) | 1 | confirmado | ✅ |
| 8 | 926236e4 12/11 08:00 | cita (1074 ms) | tomado, 3 alt. (754 ms) | 1 | confirmado | ✅ |
| 9 | 6230002a 11/11 09:30 | cita (1240 ms) | tomado, 3 alt. (847 ms) | 1 | confirmado | ✅ |
| 10 | 5d6ed45e 11/11 09:00 | cita (1129 ms) | tomado, 3 alt. (712 ms) | 1 | confirmado | ✅ |
