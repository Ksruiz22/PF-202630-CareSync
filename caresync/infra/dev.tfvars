# Valores del entorno dev. No hay secretos aquí: las credenciales de ROBLE
# viven en Parameter Store y las carga una persona.

entorno = "dev"
region  = "us-east-1"

# ROBLE producción desde el 2026-11-04. Antes era test-openlab (`caresync_cab021ce03`),
# donde el correo de recuperación de contraseña no funciona: ver
# docs/runbook-roble.md. Volver atrás es devolver estas dos líneas.
roble_base_url    = "https://roble-api.openlab.uninorte.edu.co"
roble_contract_id = "caresync_099060687b"

# Rellenar con una dirección real y verificarla cuando llegue el correo de AWS.
# Mientras esté vacío, el sistema registra los envíos en el log en lugar de
# mandarlos, y no se crean ni el presupuesto ni los avisos por correo.
correo_remitente   = ""
correo_emergencias = ""

presupuesto_mensual_usd = 20
retencion_logs          = 14
cadencia_recordatorios  = "rate(15 minutes)"
usar_guardrail          = true
