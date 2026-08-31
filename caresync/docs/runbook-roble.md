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
scripts/esquema_roble.sh                      # las 14 tablas
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
registre— no lo tiene ni debe tenerlo. Con una cuenta normal todas fallan con
«No se pudo determinar el rol del usuario», que es un mensaje engañoso: el rol existe,
es el permiso el que falta.

La salida es la **Consola SQL** del proyecto (en la navegación de la consola web).
Ejecuta PostgreSQL arbitrario, acepta varias sentencias por ejecución y descarta los
comentarios. Fue así como se crearon las trece primeras el 2026-08-27, y es el camino
para la que se añadió después (`ajustes`, más abajo). El detalle que la hace
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

### Las catorce tablas

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
| `ajustes` | `clave`/`valor` de la configuración de la plataforma. La escribe sólo la vista de plataforma |

No hay claves ajenas: ROBLE no las expone en `createTable`. La integridad la
sostiene el código, y eso está asumido —ver
[`arquitectura.md`](arquitectura.md#no-hay-claves-ajenas).

Los tipos que se le pasan a `createTable` son los nombres de ROBLE, no los alias
de SQL: `int4` y no `integer`, `bool` y no `boolean`. La lista está en
[`/docs/database/types`](https://roble.test-openlab.uninorte.edu.co/docs/database/types)
y centralizada en la constante `T` de `app/esquema/bootstrap_roble.mjs`.

### Crear la tabla `ajustes`

Es la última que se añadió, con la vista de plataforma, y **ya está creada** (2026-08-31).
Queda el `CREATE TABLE` por si hay que reponerla o crear otro contrato. En la
**Consola SQL**:

```sql
CREATE TABLE ajustes (
  clave           text        NOT NULL UNIQUE,
  valor           text,
  actualizado_en  timestamp   NOT NULL,
  actualizado_por text
);
```

`UNIQUE` en `clave` no es adorno: `guardarAjuste` decide entre `update` y `create`
leyendo primero por clave, y sin la restricción dos administradores guardando a la vez
dejarían dos filas con la misma clave y una configuración que depende de cuál devuelva
ROBLE primero. Con la restricción, la segunda escritura falla y se ve.

No hay que insertar ninguna fila: una clave que no está en la tabla vale su
predeterminado de fábrica —el del catálogo de `app/src/ajustes.ts`—, y la primera vez
que alguien guarda un ajuste se crea su fila. Una instalación sin la tabla también
funciona: `leerAjustes` avisa por consola y devuelve los valores de fábrica.

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

Que el comodín exista cambia la conclusión que este runbook daba antes: **las tablas
nuevas nacen legibles y escribibles**, porque `all:read` y `all:create` no
enumeran tablas y no hay que dar de alta nada al crear una. Lo que de verdad faltaba
era `update`.

Estado a 2026-08-31, ya aplicado. Hay **dos** roles de la aplicación, y la línea que
los separa es la única que impide que un paciente se ascienda solo.

#### `user`: el rol predeterminado, el de toda cuenta que se registra

`all:create`, `all:read`, `all:execute` y cinco permisos de tabla, uno por cada tabla
que el código actualiza **en nombre de quien la usa**:

| Permiso | Quién actualiza |
|---|---|
| `casos:update` | `actualizar_caso` en `roble_acceso.py` y `Profesional.tsx` |
| `cupos:update` | reservar, confirmar y liberar cupos |
| `citas:update` | marcar una cita como atendida |
| `indicaciones:update` | desactivar una indicación |
| `recordatorios:update` | `marcar_recordatorio` |

#### `plataforma`: el rol de las cuentas administrativas

`all:create`, `all:read`, `all:execute` y los cuatro `update` que sólo usa la vista de
plataforma. **Ninguno de estos cuatro está en `user`**, y eso es el punto:

| Permiso | Qué botón se rompe sin él |
|---|---|
| `perfiles:update` | cambiar el rol o el centro de una cuenta |
| `profesionales:update` | activar/desactivar un profesional y vincularlo a una cuenta |
| `horarios:update` | desactivar un horario |
| `ajustes:update` | guardar un ajuste que ya tenía fila (la primera vez es un `create` y sí funciona) |

Se le pone a una cuenta en *Autenticación → Usuarios → Editar rol*. La cuenta dueña
del contrato no lo necesita: tiene el rol nativo `admin`, que es `all:all`.

Y **no** se reutilizó `editor`, que ya existía y habría servido: es
`all:{create,read,update,delete,execute}`, o sea que también podría borrar filas
clínicas de cualquier tabla. La vista de plataforma no borra nada —los horarios se
desactivan—, así que un rol con exactamente siete permisos es más barato de auditar que
uno con cinco comodines.

El síntoma de que falta uno es el de siempre y engaña igual: un 500 que se lee como «no
me puedo conectar». La pantalla de plataforma lo detecta y, cuando el fallo es un 5xx,
nombra en el mensaje el permiso que probablemente falta en lugar de dejar el error crudo.
Si esa pantalla falla al guardar, **lo primero que se mira es el rol de ROBLE de la
cuenta**, no el código.

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
- El rol de ROBLE **no es** el rol de CareSync. El rol de CareSync está en la fila
  de `perfiles` y decide qué ve y qué puede hacer cada quien; el rol de ROBLE
  (`user` o `plataforma`) decide si la consulta a la tabla se permite. Son dos capas
  distintas y hacen falta las dos. En la consola sólo se toca la segunda: cambiarle a
  alguien el rol de ROBLE a `admin` no le da el tablero del centro, y quitarle `user` le
  rompe todas las lecturas. Un `admin_plataforma` necesita **las dos cosas**: el rol de
  CareSync en `perfiles` y el rol `plataforma` de ROBLE, o la pantalla se abre y falla
  al guardar.

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

Seis: `paciente`, `profesional`, `admin_cmu`, `admin_cae`, `admin_plataforma` y
`servicio`. Los dos centros son `CMU` y `CAE`. La lista está escrita en tres sitios
—`app/src/tipos.ts`, `app/esquema/bootstrap_roble.mjs` y
`lambdas/comun/caresync_comun/roble_acceso.py`— porque son tres lenguajes; se cambian
en el mismo commit.

`admin_plataforma` **no administra un centro**: administra la instalación —cuentas,
roles, profesionales, horarios y ajustes— y por eso no tiene centro ni ve casos ni
conversaciones. No tiene ninguna herramienta en el catálogo del orquestador, así que si
una cuenta con ese rol abre un chat recibe un 403 limpio; es lo correcto, quien reparte
roles no necesita leer historias clínicas.

**Registrarse en la aplicación da siempre `paciente`, y es deliberado**: la pantalla
de acceso no permite pedir otro rol.

### El primer administrador de plataforma

Es el huevo y la gallina: los roles se reparten desde la vista de plataforma, y para
entrar a esa vista hace falta ya tener el rol. Hay dos formas de romper el ciclo.

**Con el script, si la cuenta conserva `perfiles:update`.** Escribe la fila de
`perfiles` de la cuenta con la que se entra, porque `user_id` tiene que ser el `sub`
que devuelve `currentUser()` y ROBLE no da forma de averiguar el `sub` de otra cuenta:

```bash
# Con el correo y la contraseña de la persona a la que se le da el rol
scripts/esquema_roble.sh --perfil admin_plataforma
scripts/esquema_roble.sh --perfil profesional CMU
scripts/esquema_roble.sh --perfil admin_cmu
scripts/esquema_roble.sh --perfil admin_cae
```

Ojo con el orden desde que `perfiles:update` no está en `user`: si la fila **ya
existe**, `--perfil` hace un `update` y falla con un 500 salvo que la cuenta tenga el
rol `plataforma` o el `admin` del contrato. Si la fila no existe, es un `create` y
funciona con cualquier cuenta.

**Desde la Consola SQL, que es como se hizo el 2026-08-31.** Y con una vuelta: la
consola **sólo admite `SELECT`, `CREATE TABLE`, `INSERT`, `DELETE ... WHERE` y
`ALTER TABLE ADD COLUMN`** —rechaza `UPDATE` por seguridad—, así que cambiar un rol ahí
es borrar la fila y volver a insertarla **con el mismo `_id` y el mismo `creado_en`**:

```sql
SELECT _id, user_id, nombre, email, rol, centro, creado_en FROM perfiles WHERE email = '...';

DELETE FROM perfiles WHERE email = '...';
INSERT INTO perfiles (_id, user_id, nombre, email, rol, centro, creado_en)
VALUES ('<el mismo _id>', '<el mismo user_id>', '...', '...', 'admin_plataforma', NULL, '<el mismo creado_en>');
```

Conservar el `_id` no es superstición: es lo que evita que un `_id` nuevo aparezca en
una fila que otra pantalla ya tenía cargada. `centro` va a `NULL` porque
`admin_plataforma` no administra un centro.

Inventarse el `user_id` en cambio produciría un perfil que apunta a nadie y una persona
que entra y no ve nada.

### Los siguientes, desde la aplicación

Con un `admin_plataforma` ya creado, el resto de los roles se asignan desde la vista de
plataforma y no hace falta volver a la consola ni pedirle a nadie su contraseña. Lo que
lo hace posible es que esa pantalla **lee** `perfiles` completa: los `sub` de todas las
cuentas ya están ahí, escritos por cada quien al registrarse.

Tres consecuencias que conviene tener presentes:

- Una cuenta que se registró pero cuya fila de `perfiles` no se creó **no aparece en la
  lista**, porque no hay nada que listar. Esa persona tiene que entrar una vez a la
  aplicación para que su fila exista.
- Un cambio de rol **se ve en el siguiente inicio de sesión** de esa persona. La
  pantalla lo dice al guardar; recargar no basta si el token viejo sigue vivo.
- **Nombrar a otro `admin_plataforma` sí exige volver a la consola**, un paso más:
  darle también el rol `plataforma` de ROBLE en *Autenticación → Usuarios*. Sin eso la
  pantalla se le abre —el rol de CareSync ya está— y falla con un 500 al primer guardado.
  Los demás roles no necesitan nada de esto.

Un rol administrativo **sin centro** no puede trabajar: la vista se lo dice en
lugar de mostrar una pantalla vacía. La pantalla de plataforma fuerza el centro al
elegir `admin_cmu` o `admin_cae`, y lo borra al elegir `paciente` o `admin_plataforma`.

### Cerrado el 2026-08-31: `perfiles:update` ya no lo tiene el rol `user`

Estuvo abierto un tiempo y merece quedar escrito, porque el mecanismo de cierre no es
evidente en la consola.

**Qué pasaba.** `perfiles` es la fuente del rol en las **dos** capas —la PWA lo lee para
decidir la pantalla y `_resolver_actor` lo prefiere sobre lo que declara ROBLE—, y
`perfiles:update` estaba en el rol `user`, que hereda toda cuenta registrada. Lo único
que impedía que un paciente se pusiera `admin_cmu` desde la consola del navegador era no
saber cómo.

**Cómo se cerró.** Se creó el rol `plataforma` y se le dio `perfiles:update`; el rol
`user` se quedó sin él. Se descartó la otra opción —mover las escrituras de `perfiles` a
la Lambda de herramientas, que ya autoriza por rol— porque cuesta una herramienta nueva
y deja la pantalla dependiendo del orquestador para algo que un permiso resuelve.

**El truco, porque la consola no tiene «revocar».** En *Configuración → ROLES* los
permisos de un rol se muestran como etiquetas **sin botón de quitar**: se pueden asignar
y no desasignar. La única vía es borrar el permiso en *PERMISOS* —lo que lo quita de
todos los roles a la vez, en cascada— y volver a crearlo, que nace sin asignar. O sea:

1. *PERMISOS* → borrar `perfiles:update`. Avisa de que no se puede deshacer; se puede,
   es un par *(recurso, acción)* y se vuelve a crear en diez segundos.
2. Comprobar en *ROLES* que ni `user` ni `plataforma` lo tienen ya.
3. *PERMISOS* → *Nuevo permiso* → `perfiles` + `update`.
4. *ROLES* → `plataforma` → asignarlo. **Sólo ahí.**

El panel de detalles no refresca las etiquetas al asignar: hay que cerrarlo y volver a
abrir el rol para verlo. Si se hace al revés —crear antes de borrar— no sirve de nada,
porque el permiso es un objeto único y el nuevo colisiona con el viejo.

**Y lo que hay que recordar de por vida:** `bootstrap_roble.mjs --perfil` escribe
`perfiles`, así que la cuenta con la que se ejecute tiene que conservar el permiso —la
dueña del contrato (`admin`) o una con rol `plataforma`—. Con una cuenta normal, si la
fila ya existe, da un 500.

## Profesionales, horarios y cupos

`--semilla` lee `app/esquema/semilla.json` (que **no** se versiona: lleva nombres y
correos). Se parte de `semilla.example.json`. Tres cosas que se olvidan:

- `dia_semana`: **0 = lunes** … 6 = domingo.
- `hora_inicio`/`hora_fin` son hora de Bogotá, sin zona. `minutos_cupo` es la
  duración de cada hueco.
- `user_id` puede quedar en `null`. La agenda funciona igual, pero ese profesional
  no puede entrar a ver sus citas, porque se buscan por `profesional_user_id`.

La semilla es para arrancar rápido. En operación, los profesionales y sus horarios se
dan de alta desde la **vista de plataforma**, que también los activa, los desactiva y
los vincula a una cuenta. Un horario no se borra: se desactiva, porque ningún rol tiene
permiso de `delete` y no debería tenerlo.

Vincular un profesional a una cuenta es poner en `profesionales.user_id` el `user_id`
de una fila de `perfiles`; la pantalla ofrece la lista de cuentas con rol
`profesional` para no teclearlo. Sin ese vínculo la agenda funciona igual, pero esa
persona no ve sus citas al entrar.

Los `cupos` **no** los crea la semilla ni una Lambda: los publica alguien del
personal administrativo con el botón «Publicar cupos», que dice en su rótulo cuántos
días abre. Cuántos son sale del ajuste `dias_agenda` (14 de fábrica) y se cambia en la
vista de plataforma. Abrir dos semanas de agenda es una decisión, no un automatismo. La
operación es idempotente —no duplica un cupo que ya exista para el mismo profesional y
hora— y está topada en 400 cupos por tanda.

## Ajustes de la plataforma

La tabla `ajustes` es `clave`/`valor` y el catálogo de claves válidas está cerrado en
`app/src/ajustes.ts`. **La regla de ese archivo es que un ajuste sólo existe si algo lo
lee**, y cada definición lleva escrito quién lo consume; la pantalla lo muestra. Una
pantalla de configuración llena de interruptores desconectados se ve bien en una
demostración y es mentira.

Hoy son dos:

| Clave | Qué hace | Quién lo lee |
|---|---|---|
| `dias_agenda` | días que abre «Publicar cupos» (1 a 60) | `Administrativo.tsx` → `generarCupos()` |
| `aviso_global` | franja ámbar arriba de todas las pantallas; vacío para no mostrar nada | `App.tsx` → `<AvisoGlobal />` |

Los valores se guardan **siempre como texto** y se convierten al leer. El aviso global
se lee una vez por sesión, al entrar: no hay sondeo, porque el cubo de 100 peticiones
por minuto es por IP y en el campus se comparte.

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

### `createTable` falla en todas con «No se pudo determinar el rol del usuario»

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

### `ThrottlerException: Too Many Requests`

Es un **429**: ROBLE limita por IP. El mensaje no dice cuál de los tres cubos se
agotó ni cuánto hay que esperar, y son muy distintos entre sí. Medidos contra la API
el 2026-08-27 con `curl -D -`, que devuelve las cabeceras:

| Ruta | Límite | Ventana |
|---|---|---|
| `/auth/<contrato>/signup` | **5** | **1 hora** |
| `/auth/<contrato>/login` | **10** | **15 minutos** |
| Todo lo demás: leer, escribir, `refresh-token`, `verify-token` | 100 | 1 minuto |

```bash
# El cubo de 100/minuto de esta IP. Gratis: un token inválido da 401 y ya.
curl -s -o /dev/null -D - https://roble-api.test-openlab.uninorte.edu.co/auth/caresync_cab021ce03/verify-token \
  | grep -i ratelimit
```

**Ese `curl` no dice nada de los otros dos cubos**: cada ruta lleva el suyo y sólo
informa del propio. Para saber cómo va el de `login` hay que enviar un `login`, que
cuesta uno de los diez —un correo inexistente basta, devuelve 401 y sus cabeceras
dicen cuántos quedan—. Del de `signup` no hay forma de preguntar sin gastar un
registro, así que ahí se cuenta a mano o se espera la hora.

Lo que hay que hacer es **esperar**: la ventana es fija y reintentar no la acorta.
`X-Ratelimit-Reset` dice los segundos que faltan. Y son **por IP, no por cuenta**:
en el campus o detrás de una NAT compartida se gastan entre varios, así que «a mí
me funciona» no descarta nada.

El de 5 por hora es el que sorprende, porque una sesión de pruebas se lo come sin
darse cuenta. Dos cosas del código lo cuidan y conviene no deshacerlas:

- La pantalla de acceso hace **un solo** `login` al registrarse. Hacía dos —uno para
  escribir la fila de `perfiles` y otro para entrar—, o sea que gastaba el cupo de
  inicios de sesión al doble de velocidad.
- La contraseña se valida **antes** de llamar a `signup`, contra la política que
  ROBLE responde en su 400: mínimo 8 caracteres, una mayúscula, una minúscula, un
  número y un símbolo. Un rechazo por contraseña floja costaba un quinto del cupo de
  la hora.

Del lado de las Lambdas sólo hay un `login`: el de la cuenta de servicio, uno por
disparo del reloj. Con `cadencia_recordatorios` en `rate(15 minutes)` hay margen de
sobra; por debajo de minuto y medio ese cubo se agota solo.

### `El campo extra 'role' no está permitido` al crear cuenta

ROBLE dejó de aceptar el campo `extra` en `register`, y el 2026-08-27 eso rompió el
registro en la PWA: la pantalla de acceso declaraba ahí `role: 'paciente'`. Se quitó
el campo en vez de buscar cómo volver a permitirlo, porque el rol declarado en la
cuenta **no debía existir**: era una segunda fuente de verdad que competía con
`perfiles`.

Y competía ganando. `_resolver_actor` leía `extra` primero, así que una cuenta
registrada en la PWA se quedaba en `paciente` para la Lambda aunque su fila de
`perfiles` dijera `admin_cmu` —la PWA, que sólo mira `perfiles`, sí mostraba el
tablero del centro—. El resultado era el peor de los dos mundos: la vista
administrativa a la vista y un 403 en cada botón. Ahora manda `perfiles` y los
metadatos son sólo el respaldo de una cuenta sin fila; las cuentas que ya traen
`extra.role` no hay que limpiarlas.

Ojo con el orden de despliegue: quitar el campo es la PWA y cambiar la precedencia
es la Lambda. Van en el mismo PR, pero se publican por caminos distintos.

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
