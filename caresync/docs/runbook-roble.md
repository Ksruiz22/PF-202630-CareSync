# Runbook de ROBLE

Todo lo operativo del lado de los datos. ROBLE (OPENLAB, Uninorte) guarda **todo** lo
clínico: AWS no tiene ni una fila. Si algo va mal con los datos, se arregla aquí.

- API: `https://roble-api.test-openlab.uninorte.edu.co`
- Contrato: `caresync_cab021ce03`

Los dos valores viven en `infra/dev.tfvars` y de ahí los toman Terraform (para
Parameter Store) y `scripts/esquema_roble.sh`. Un segundo sitio donde escribirlos
sería un segundo sitio donde equivocarse.

## Crear el esquema

```bash
source scripts/entorno.sh
scripts/esquema_roble.sh                      # las 13 tablas
scripts/esquema_roble.sh --semilla            # + profesionales y horarios de prueba
```

Pide el correo y la contraseña por consola (entrada oculta). Si hace falta pasarlos
por entorno —en un CI— son `ROBLE_EMAIL` y `ROBLE_PASSWORD`. **Nunca en un archivo**:
el proyecto vive en una carpeta sincronizada con OneDrive y un `.env` con una
contraseña se sube a la nube sin preguntar.

Es **idempotente**: una tabla que ya existía se cuenta como tal y no es un error.
El resumen dice cuántas se crearon, cuántas ya estaban y cuántas fallaron. La cuenta
con la que se entra tiene que ser la dueña del contrato; una cuenta cualquiera puede
leer y escribir filas, pero no crear tablas.

### Las trece tablas

| Tabla | Para qué |
|---|---|
| `perfiles` | rol y centro de cada cuenta. Es la tabla que decide qué ve cada quien |
| `casos` | un caso por episodio; su `estado` decide qué agente atiende |
| `conversaciones` | los turnos de cada caso. El profesional **no** las ve |
| `profesionales` | quién atiende, en qué centro y con qué especialidad |
| `horarios` | plantilla semanal de cada profesional |
| `cupos` | los huecos concretos, generados desde `horarios`. Aquí vive `reserva_testigo` |
| `citas` | cupo reservado y confirmado para un caso |
| `planes` | el plan que escribe el profesional |
| `indicaciones` | las líneas del plan, con su frecuencia |
| `adherencia` | cada vez que el paciente reporta si cumplió una indicación |
| `evolucion` | la escala de 0 a 10 que reporta el paciente |
| `eventos` | traza de lo que hizo el sistema (`detalle` en jsonb) |
| `recordatorios` | lo que la Lambda de reloj tiene pendiente de enviar |

No hay claves ajenas: ROBLE no las expone en `createTable`. La integridad la
sostiene el código, y eso está asumido —ver
[`arquitectura.md`](arquitectura.md#no-hay-claves-ajenas).

Los tipos que se le pasan a `createTable` son los nombres de ROBLE, no los alias
de SQL: `int4` y no `integer`, `bool` y no `boolean`. La lista está en
[`/docs/database/types`](https://roble.test-openlab.uninorte.edu.co/docs/database/types)
y centralizada en la constante `T` de `app/esquema/bootstrap_roble.mjs`.

## Permisos de tabla en la consola de ROBLE

**Crear las tablas no basta, y este es el paso que se olvida.** Lo dice la
documentación de ROBLE en
[`/docs/roles`](https://roble.test-openlab.uninorte.edu.co/docs/roles): al crear el
proyecto se genera un rol `user` con permisos de leer y actualizar **las tablas que
existían en ese momento**, los permisos sólo se pueden crear sobre tablas que ya
existen, y las tablas nuevas hay que darlas de alta a mano. Nuestras trece nacen
sin ningún permiso.

El síntoma de que falta esto no es un 403 limpio: es un **500 de ROBLE** que la
aplicación traduce a un 502 y que se lee igual que «no me puedo conectar».

En la consola: *Base de datos → Permisos* por cada tabla, y *Autenticación →
Roles* para asignarlos al rol que tienen las cuentas. Lo que necesita CareSync,
sacado de las llamadas que hay en el código:

| Tabla | read | insert | update | delete |
|---|:--:|:--:|:--:|:--:|
| `perfiles` | ✔ | ✔ | ✔ | |
| `casos` | ✔ | ✔ | ✔ | |
| `conversaciones` | ✔ | ✔ | | |
| `profesionales` | ✔ | ✔ | | |
| `horarios` | ✔ | ✔ | | |
| `cupos` | ✔ | ✔ | ✔ | |
| `citas` | ✔ | ✔ | ✔ | |
| `planes` | ✔ | ✔ | | |
| `indicaciones` | ✔ | ✔ | ✔ | |
| `adherencia` | ✔ | ✔ | | |
| `evolucion` | ✔ | ✔ | | |
| `eventos` | ✔ | ✔ | | |
| `recordatorios` | ✔ | ✔ | ✔ | |

**Ninguna tabla necesita `delete`**, y conviene dejarlo así: nada del sistema borra
filas clínicas, así que un permiso de borrado sólo añadiría una forma de perder
datos que no están en ningún otro sitio. Un cupo que se libera se marca `libre`,
no se borra.

Dos cosas que la documentación deja claras y que ahorran una tarde:

- El rol nuevo **toma efecto en el siguiente inicio de sesión**. Si se cambia y no
  parece cambiar nada, hay que salir y volver a entrar.
- El rol de ROBLE **no es** el rol de CareSync. `register` guarda
  `extra: { role: 'paciente' }`, pero eso es metadato de la cuenta: quien decide
  qué ve cada quien es la fila de `perfiles` (ver más abajo), y quien decide si la
  consulta a la tabla se permite es el rol de ROBLE. Son dos capas distintas y
  hacen falta las dos.

## Roles

Cinco: `paciente`, `profesional`, `admin_cmu`, `admin_cae`, `servicio`. Los dos
centros son `CMU` y `CAE`.

**Registrarse en la aplicación da siempre `paciente`, y es deliberado**: la pantalla
de acceso no permite pedir otro rol. Para dar un rol distinto hay que escribir la
fila de `perfiles` de esa cuenta, y sólo se puede hacer **entrando con esa cuenta**,
porque `user_id` tiene que ser el `sub` que devuelve `currentUser()`:

```bash
# Con el correo y la contraseña de la persona a la que se le da el rol
scripts/esquema_roble.sh --perfil profesional CMU
scripts/esquema_roble.sh --perfil admin_cmu
scripts/esquema_roble.sh --perfil admin_cae
```

No hay atajo de administrador para esto, y no es un descuido: ROBLE no da una forma
de averiguar el `sub` de otra cuenta, así que inventarse el `user_id` produciría un
perfil que apunta a nadie y una persona que entra y no ve nada.

Un rol administrativo **sin centro** no puede trabajar: la vista se lo dice en
lugar de mostrar una pantalla vacía.

## Profesionales, horarios y cupos

`--semilla` lee `app/esquema/semilla.json` (que **no** se versiona: lleva nombres y
correos). Se parte de `semilla.example.json`. Tres cosas que se olvidan:

- `dia_semana`: **0 = lunes** … 6 = domingo.
- `hora_inicio`/`hora_fin` son hora de Bogotá, sin zona. `minutos_cupo` es la
  duración de cada hueco.
- `user_id` puede quedar en `null`. La agenda funciona igual, pero ese profesional
  no puede entrar a ver sus citas, porque se buscan por `profesional_user_id`.

Los `cupos` **no** los crea la semilla ni una Lambda: los publica alguien del
personal administrativo con el botón «Publicar cupos (14 días)». Abrir dos semanas
de agenda es una decisión, no un automatismo. La operación es idempotente —no
duplica un cupo que ya exista para el mismo profesional y hora— y está topada en 400
cupos por tanda.

## La cuenta de servicio

La usa **sólo** la Lambda de recordatorios, que corre por reloj y no tiene un usuario
que la autorice. Su contraseña vive en Parameter Store como `SecureString` y
Terraform no la mira nunca (`ignore_changes = [value]`).

Rotarla:

```bash
source scripts/entorno.sh
aws ssm put-parameter --overwrite --name /caresync/dev/roble/servicio/password \
  --type SecureString --value '...'
```

Se cambia primero en ROBLE y después en Parameter Store, en ese orden: entre los dos
pasos la Lambda de recordatorios falla al autenticarse, y es preferible a que quede
autenticada con una contraseña que ya no se puede revocar. El fallo se ve en el log
de `/aws/lambda/caresync-dev-recordatorios` y no pierde recordatorios: el siguiente
disparo del reloj los recoge.

## Fallos y qué hacer

### `createTable` falla en una tabla

El script imprime la tabla y el mensaje de ROBLE. Casi siempre es un tipo que ROBLE
no acepta: los tipos están centralizados en la constante `T` de
`app/esquema/bootstrap_roble.mjs` (`text`, `integer`, `boolean`, `timestamp`,
`jsonb`). Se corrige ahí y se vuelve a ejecutar: las tablas que ya existían no
estorban.

**No borrar las tablas para «reintentar limpio».** Borrar una tabla con filas se
lleva por delante datos que no están en ningún otro sitio; AWS no tiene copia.

### 401 al usar la aplicación

El token de acceso caducó y el refresco falló. La aplicación guarda los dos tokens en
`localStorage` bajo `caresync.sesion`; salir y volver a entrar lo resuelve. Si pasa
en bucle, hay que mirar si el reloj de la máquina va muy desfasado.

### 403 en una herramienta del agente

Es lo esperado cuando alguien pide algo que su rol no permite: lo niegan las dos
capas —el catálogo de herramientas por rol y ROBLE con el token del llamante—. Antes
de tocar permisos, comprobar la fila de `perfiles` de esa cuenta: un rol mal escrito
ahí se comporta exactamente igual que un permiso que falta.

### Cupos que quedan «reservados» y nadie los usa

Pasa si el proceso muere entre reservar y confirmar. `liberar_reservas_vencidas()`
recoge las reservas de más de 2 minutos sin confirmar, y la Lambda de recordatorios
la ejecuta en su paso por el reloj. Si hay prisa, se puede provocar invocando esa
Lambda a mano. Lo que **no** hay que hacer es editar `reserva_testigo` en la consola:
es lo único que distingue una reserva propia de la de otro.

### Filas huérfanas

Sin claves ajenas, existen. Las que importan son indicaciones sin plan y citas sin
caso. Se detectan leyendo las dos tablas y comparando en memoria (que es como se
hace todo aquí; ver más abajo). El código evita crearlas donde puede: al registrar
un plan, si ROBLE no devuelve el identificador, se lanza un error **antes** de crear
las indicaciones.

### «Necesito filtrar por rango de fechas»

No se puede: `read` sólo compara por igualdad. No hay `LIKE`, ni rangos, ni orden, ni
paginación. Se lee y se filtra en memoria. Cuando el volumen deje de caber, la salida
es una *saved query* en ROBLE invocada con `executeQuery`, no paginar a mano.

## Mirar los datos

La consola de ROBLE sirve para inspeccionar y para arreglos puntuales. Para algo
repetible es mejor un script de un solo uso en `_scratch/<fecha>/` que use el SDK con
las mismas credenciales, y borrarlo después. Dos avisos:

- Editar a mano el `estado` de un caso cambia qué agente atiende la siguiente
  conversación (`agente_por_defecto` lo deduce de ahí). Es una herramienta de
  diagnóstico útil y una forma fácil de dejar a alguien atrapado en el agente
  equivocado.
- Cualquier cosa que se saque de ROBLE son datos de personas. No acaba en el
  repositorio, ni en `_scratch/` si son reales, ni pegada en un chat.
