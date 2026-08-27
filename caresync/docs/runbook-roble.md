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
El resumen dice cuántas se crearon, cuántas ya estaban y cuántas fallaron.

Con una cuenta cualquiera del contrato **`--semilla` y `--perfil` funcionan, pero
crear tablas no**: hace falta el permiso `alter`, que el rol predeterminado no tiene.
La siguiente sección es la salida.

### Crear las tablas con la Consola SQL

`createTable` necesita `alter`, y el rol `user` —el que hereda toda cuenta que se
registre— no lo tiene ni debe tenerlo. Con una cuenta normal las trece fallan con
«No se pudo determinar el rol del usuario», que es un mensaje engañoso: el rol existe,
es el permiso el que falta.

La salida es la **Consola SQL** del proyecto (en la navegación de la consola web).
Ejecuta PostgreSQL arbitrario, acepta varias sentencias por ejecución y descarta los
comentarios. Fue así como se crearon las trece el 2026-08-27. El detalle que la hace
segura de usar aquí: **ROBLE inyecta `_id UUID PRIMARY KEY NOT NULL UNIQUE DEFAULT
gen_random_uuid()` en todo `CREATE TABLE` que no lo traiga**, que es exactamente la
columna que espera la aplicación; no hay que declararla y no se corre el riesgo de
declararla distinta.

El esquema de referencia sigue siendo la constante `ESQUEMA` de
`app/esquema/bootstrap_roble.mjs`: de ahí se leen las columnas y cuáles son nulables,
y se transcriben con `NOT NULL` en toda la que no esté marcada nulable. Después se
comprueba con

```sql
SELECT table_name, count(*) AS columnas FROM information_schema.columns
WHERE table_schema = 'public' GROUP BY table_name ORDER BY table_name;
```

contando **una columna más** que en `ESQUEMA`, la del `_id`.

Que exista este camino no convierte al script en código muerto: sigue siendo el que
siembra, el que escribe perfiles y el que documenta el esquema en el repositorio. Lo
que no puede es crear tablas con las credenciales de una cuenta normal.

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

## Permisos en la consola de ROBLE

**Están en *Configuración*, no en *Base de datos* ni en *Autenticación*** —pestañas
**ROLES** y **PERMISOS**—, y no funcionan como los describe
[`/docs/roles`](https://roble.test-openlab.uninorte.edu.co/docs/roles). Un permiso es
un par *(recurso, acción)* donde el recurso es una tabla **o el comodín `all`**, y las
acciones son `create read update delete alter execute all`. Los permisos se asignan a
**roles**, y cada cuenta tiene un rol (se cambia en *Autenticación → Usuarios →
Editar rol*).

El contrato nació con cuatro roles —`user`, que es el **predeterminado** y por tanto el
de toda cuenta que se registre en la PWA, más `readonly`, `editor` y `admin`— y siete
permisos, todos con recurso `all`. `user` traía `all:create`, `all:read` y `all:execute`.

Que el comodín exista cambia la conclusión que este runbook daba antes: **las trece
tablas nuevas nacieron legibles y escribibles**, porque `all:read` y `all:create` no
enumeran tablas y no hay que dar de alta nada al crear una. Lo que de verdad faltaba
era `update`.

Estado a 2026-08-27, ya aplicado: al rol `user` se le añadieron seis permisos de tabla,
uno por cada tabla que el código actualiza.

| Permiso | Quién actualiza |
|---|---|
| `perfiles:update` | `bootstrap_roble.mjs --perfil` |
| `casos:update` | `actualizar_caso` en `roble_acceso.py` y `Profesional.tsx` |
| `cupos:update` | reservar, confirmar y liberar cupos |
| `citas:update` | marcar una cita como atendida |
| `indicaciones:update` | desactivar una indicación |
| `recordatorios:update` | `marcar_recordatorio` |

**Se hizo por tabla y no con `all:update` a propósito.** El comodín era un clic en vez
de doce, pero daba permiso para reescribir `conversaciones` y `eventos` —el hilo
clínico y la bitácora—, que el sistema sólo añade y nunca modifica. Si algún día una
escritura falla con un 500 en una tabla que no está en esa lista, la pregunta correcta
es si esa escritura debería existir; si debe, se añade su permiso. Recurrir a
`all:update` es apagar el detector de humo.

**Ningún rol de la aplicación tiene `delete` ni `alter`, y así debe quedarse.** Nada
del sistema borra filas clínicas —un cupo que se libera se marca `libre`, no se
borra—, así que un permiso de borrado sólo añadiría una forma de perder datos que no
están en ningún otro sitio. Y `alter` en el rol predeterminado significaría que
cualquier paciente registrado puede cambiar el esquema.

El síntoma de un permiso que falta no es un 403 limpio: es un **500 de ROBLE** que la
aplicación traduce a un 502 y que se lee igual que «no me puedo conectar».

Dos cosas más que ahorran una tarde:

- Los permisos viajan en el token, así que un cambio de rol o de permisos **toma
  efecto en el siguiente inicio de sesión**. Si se cambia algo y no parece cambiar
  nada, hay que salir y volver a entrar.
- El rol de ROBLE **no es** el rol de CareSync. `register` guarda
  `extra: { role: 'paciente' }`, pero eso es metadato de la cuenta: quien decide
  qué ve cada quien es la fila de `perfiles` (ver más abajo), y quien decide si la
  consulta a la tabla se permite es el rol de ROBLE. Son dos capas distintas y
  hacen falta las dos.

> **El 2026-08-21 la consola no dejaba entrar, y eso bloqueaba todo lo de arriba.** El
> login devolvía `401 No se pudo canjear el código de Microsoft con las credenciales
> del proyecto` en `/auth/microsoft/callback`: Microsoft emitía el código y el canje
> fallaba del lado de ROBLE, con dos cuentas distintas y también en incógnito. Las
> credenciales de Microsoft **son propias de cada proyecto** y se guardan en sus
> ajustes, así que desde fuera no se distingue «ROBLE está roto» de «este proyecto no
> las tiene configuradas». Se arregló del lado de ROBLE el 2026-08-27 sin que
> tocáramos nada.
>
> Si vuelve a pasar, no hay otra puerta a la consola: el botón llama a
> `${API}/auth/microsoft`, la ruta `/login` del SPA renderiza un `root` vacío y las
> alternativas sin Microsoft (`/auth/login`, `/users/login`, `/auth/signin`…) dan 404.
> Queda preguntar en el Discord de ROBLE. Lo único que no depende de la consola es
> autenticarse contra el pozo de usuarios del contrato, `/auth/<contrato>/login`, que
> funcionó todos esos días.

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

### `createTable` falla en las trece con «No se pudo determinar el rol del usuario»

No es el esquema, y **el mensaje engaña**: el rol existe. `createTable` autoriza antes
de mirar las columnas y lo que le falta a ese rol es el permiso `alter` —comprobado en
*Configuración → Roles*, donde `ajsantiago@uninorte.edu.co` figura con rol `user` y
`user` tiene `create`, `read`, `execute` y las seis actualizaciones por tabla, pero no
`alter`—. No hay nada que arreglar en el script: se crean las tablas con la Consola
SQL (ver arriba). Darle `alter` al rol predeterminado sería peor que el problema.

El script detecta este caso y lo dice en lugar de mandar a revisar los tipos.

Que la contraseña sea correcta no dice nada sobre el rol: ROBLE distingue
`Contraseña incorrecta` de `Usuario no verificado o no encontrado`, así que un login
que funciona sólo prueba que la cuenta existe en el contrato.

### `createTable` falla en una tabla

El script imprime la tabla y el mensaje de ROBLE. Casi siempre es un tipo que ROBLE
no acepta: los tipos están centralizados en la constante `T` de
`app/esquema/bootstrap_roble.mjs` (`text`, `int4`, `bool`, `timestamp`, `jsonb`).
Se corrige ahí y se vuelve a ejecutar: las tablas que ya existían no estorban.

Ojo con usar los alias de SQL —`integer`, `boolean`— que PostgreSQL aceptaría: quien
valida aquí es la API de ROBLE, y su lista es la de
[`/docs/database/types`](https://roble.test-openlab.uninorte.edu.co/docs/database/types).

**No borrar las tablas para «reintentar limpio».** Borrar una tabla con filas se
lleva por delante datos que no están en ningún otro sitio; AWS no tiene copia.

### `Esquema inesperado actualizando casos (¿columna que no existe?)`

Es una columna del payload que la tabla no tiene: ROBLE rechaza la actualización
**entera** con un 400. Pasó el 2026-08-27 con `canalizar_caso`, que enviaba
`canalizado_en`, y con `escalar_urgencia`, que enviaba `escalado_en`; ninguna de las
dos está en `ESQUEMA` y nada las leía. Se quitaron del payload en vez de añadirlas al
esquema: `actualizado_en` y la tabla `eventos` ya dicen cuándo pasó cada cosa.

Cuesta encontrarlo por dos razones que conviene tener presentes:

- El mensaje anterior era «ROBLE respondió 400 actualizando casos», que se lee como
  un problema de permisos cuando se acaban de tocar los permisos. Por eso ahora las
  escrituras tienen su propia rama para el 400, igual que las lecturas.
- `escalar_urgencia` **no lanza excepción a propósito** —la ruta de emergencia se
  entrega igual—, así que su 400 sólo quedaba en `fallos` y el caso se quedaba sin
  marcar urgente en silencio. Si se sospecha de una escritura que «funciona pero no
  guarda», mirar el log de `caresync-dev-herramientas`, no el del orquestador: el
  rechazo de la herramienta se registra ahí.

Comprobarlas todas de una vez es fácil y vale la pena cada vez que cambie el esquema:
recoger las claves de cada `create`/`update` y restarles las columnas de `ESQUEMA`.
Dos trampas al hacerlo, aprendidas haciéndolo: los diccionarios anidados dan falsos
positivos —el `{"texto": …}` que va dentro del `jsonb` de `eventos.detalle` no es una
columna— y hay que seguir los envoltorios de `AccesoRoble`, no sólo los `_crear` y
`_actualizar`, porque por ahí entraban estas dos. De los envoltorios, el único que
acepta carga libre es `actualizar_caso`; los demás construyen el payload ellos mismos.

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
