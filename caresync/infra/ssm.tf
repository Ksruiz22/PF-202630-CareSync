# Toda la configuración del entorno vive aquí. Las Lambdas no llevan nada
# sensible en variables de entorno: sólo el prefijo del que leer.

resource "aws_ssm_parameter" "roble_base_url" {
  name        = "${local.ssm_prefijo}/roble/base_url"
  description = "Host de la API de ROBLE."
  type        = "String"
  value       = var.roble_base_url
  tier        = "Standard"
}

resource "aws_ssm_parameter" "roble_contract_id" {
  name        = "${local.ssm_prefijo}/roble/contract_id"
  description = "Identificador del contrato del proyecto en ROBLE."
  type        = "String"
  value       = var.roble_contract_id
  tier        = "Standard"
}

# --- Credenciales de la cuenta de servicio -----------------------------------
#
# Las usa SÓLO la Lambda de recordatorios, que corre por reloj y no tiene un
# usuario que la autorice. El resto del sistema actúa con el token del propio
# llamante.
#
# Terraform crea los parámetros con un valor de relleno y deja de mirarlos:
# el valor real lo carga una persona, nunca este repositorio.
#
#   aws ssm put-parameter --profile team_devops_jamar --overwrite \
#     --name /caresync/dev/roble/servicio/email --type String --value 'svc-caresync@uninorte.edu.co'
#   aws ssm put-parameter --profile team_devops_jamar --overwrite \
#     --name /caresync/dev/roble/servicio/password --type SecureString --value '...'

resource "aws_ssm_parameter" "roble_servicio_email" {
  name        = "${local.ssm_prefijo}/roble/servicio/email"
  description = "Correo de la cuenta de servicio de ROBLE. Lo carga una persona."
  type        = "String"
  value       = "PENDIENTE-DE-CARGAR"
  tier        = "Standard"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "roble_servicio_password" {
  name        = "${local.ssm_prefijo}/roble/servicio/password"
  description = "Contraseña de la cuenta de servicio de ROBLE. Lo carga una persona."
  type        = "SecureString"
  value       = "PENDIENTE-DE-CARGAR"
  tier        = "Standard"

  lifecycle {
    ignore_changes = [value]
  }
}

# --- Correo ------------------------------------------------------------------

resource "aws_ssm_parameter" "correo_remitente" {
  name        = "${local.ssm_prefijo}/correo/remitente"
  description = "Dirección verificada en SES desde la que se envía."
  type        = "String"
  value       = var.correo_remitente != "" ? var.correo_remitente : "PENDIENTE-DE-CARGAR"
  tier        = "Standard"
}

resource "aws_ssm_parameter" "correo_emergencias" {
  name        = "${local.ssm_prefijo}/correo/emergencias"
  description = "Buzón que recibe los escalamientos de urgencia."
  type        = "String"
  value       = var.correo_emergencias != "" ? var.correo_emergencias : "PENDIENTE-DE-CARGAR"
  tier        = "Standard"
}
