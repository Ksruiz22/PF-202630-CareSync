# Reglas del proyecto

Proyecto Final de la Universidad del Norte: **CareSync Agentic Network**. Los
entregables son la propuesta (`CareSync.md`) y el documento visual autocontenido
(`propuesta-caresync.html`); esos viven en la raíz.

## Artefactos temporales: carpeta `_scratch/` + header de marca

Todo archivo desechable que generes (scripts de diagnóstico, dumps de
respuestas de API, sondas, pruebas one-off) va a:

```
_scratch/<YYYY-MM-DD>/<nombre>
```

**Nunca en la raíz del proyecto.** Aplica igual si lo creas con la herramienta
`Write` o con un heredoc desde Bash (`cat > _scratch/2026-08-20/foo.sh <<'EOF'`).
Crea el directorio del día con `mkdir -p` antes de escribir.

Además, todo script generado lleva como **segunda línea** (tras el shebang):

```bash
#!/usr/bin/env bash
# generated-by: claude-code — <YYYY-MM-DD>
```

Para `.py` usa el mismo comentario con `#`; para `.json`, que no admite
comentarios, basta la ubicación en `_scratch/`.

Así el inventario de lo generado es `ls _scratch/` y la búsqueda de fugas a la
raíz es `grep -rl 'generated-by: claude-code' .`.

### Si el trabajo es en WSL: `~/_scratch/<YYYY-MM-DD>/`

Los temporales del lado Linux van al home de WSL, **no** al `_scratch/` del
proyecto y **nunca** sueltos en `~`. Dos razones concretas:

- El proyecto vive en OneDrive y su ruta tiene espacios
  (`OneDrive - Muebles Jamar`); escribir ahí desde WSL vía `/mnt/c/...` es un
  campo minado de quoting que ya causó un fallo silencioso en otro proyecto.
- `/mnt/c` va por el mount 9p y es lento comparado con el fs nativo.

`/tmp/` sirve para algo de un solo uso dentro del mismo comando, pero no para
nada que quieras volver a mirar: no es visible para el usuario y sobrevive
hasta el próximo reinicio de WSL, que pueden ser semanas.

Inventario del lado Linux: `ls ~/_scratch/`.

### Qué NO va a `_scratch/`
- Código de la aplicación, IaC y configuración que se despliega.
- Entregables que el usuario pidió: la propuesta, el HTML, diagramas, informes.

### Promoción: por uso real, no por predicción
**Nunca decidas al crearlo que un script es "reusable".** Todo nace en
`_scratch/`. Un script se promueve **solo cuando de hecho se vuelve a usar**
en otra sesión o tarea, y entonces:

1. Va a `scripts/<área>/` — **nunca a la raíz del proyecto**, que se mantiene
   sin scripts.
2. Se le quita el prefijo `_` si lo tenía.
3. Se le añade o actualiza un `README.md` en su carpeta, que remita a la
   memoria correspondiente para el contexto en vez de duplicarlo.
4. Se actualiza cualquier memoria que cite su ruta anterior.

Razón: en el proyecto hermano `DEVOPS/IAOpsJamar` se encontraron 200 scripts en
la raíz, 9 de ellos etiquetados "reusables" en una memoria al cierre de la
sesión que los creó. Al leerlos, solo 2 lo eran de verdad. Etiquetar por
intención infla; etiquetar por uso, no.

### Limpieza
`_scratch/` es borrable sin preguntar salvo que contenga algo del día en curso.
Si el usuario pide limpiar, mover a un `_archivo_<fecha>/` es preferible a
`rm` — es reversible.

## Verificación del HTML de la propuesta

El panel del navegador no compone frames en este entorno: **las capturas de
pantalla fallan** con un timeout. La verificación del render se hace por
inspección del DOM (`javascript_tool`): símbolos SVG referenciados que no
existen, iconos sin tamaño que se expanden a 300×150, desbordamiento
horizontal, alineación de la rejilla del Gantt y altura de las tarjetas. Al
reportar, decir que se verificó por DOM — no dar a entender que se vio.
