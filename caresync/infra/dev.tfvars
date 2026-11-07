# Valores del entorno dev. No hay secretos aquí: las credenciales de ROBLE
# viven en Parameter Store y las carga una persona.

entorno = "dev"
region  = "us-east-1"

# ROBLE producción desde el 2026-11-04. Antes era test-openlab (`caresync_cab021ce03`),
# donde el correo de recuperación de contraseña no funciona: ver
# docs/runbook-roble.md. Volver atrás es devolver estas dos líneas.
roble_base_url    = "https://roble-api.openlab.uninorte.edu.co"
roble_contract_id = "caresync_099060687b"

# Vacío, el sistema registra los envíos en el log en lugar de mandarlos, y no se
# crean ni el presupuesto ni los avisos por correo.
#
# Desde el 2026-11-07, para la demo y sólo mientras dure la prueba: las dos son
# direcciones de Kevin. Para apagar el correo se dejan las dos vacías; Terraform borra
# las identidades de SES, el aviso por correo y el presupuesto.
#
# El remitente es un Gmail y no la cuenta de Uninorte: uninorte.edu.co publica DMARC
# `p=quarantine`, y SES firma con su propio dominio, así que lo que saliera «desde»
# Uninorte podía caer en cuarentena. gmail.com publica `p=none`.
#
# Los escalamientos NO van al CAE real, que recibiría las alarmas de prueba del banco
# con pacientes ficticios: van al buzón de Uninorte de Kevin.
#
# Tras el apply, AWS manda un enlace de verificación a cada una, y hasta hacer clic no
# sale nada. En sandbox, cada destinatario (las cuentas de paciente y de médico de la
# demo) también tiene que estar verificado en SES. Los avisos de alarmas y del
# presupuesto llegan al remitente.
correo_remitente   = "kevinre739@gmail.com"
correo_emergencias = "ksruiz@uninorte.edu.co"

presupuesto_mensual_usd = 20
retencion_logs          = 14
cadencia_recordatorios  = "rate(15 minutes)"
usar_guardrail          = true
