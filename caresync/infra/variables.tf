variable "proyecto" {
  description = "Prefijo de todos los recursos."
  type        = string
  default     = "caresync"
}

variable "entorno" {
  description = "Entorno desplegado. Sólo existe dev en el alcance del prototipo."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "demo"], var.entorno)
    error_message = "Sólo se contemplan los entornos dev y demo."
  }
}

variable "region" {
  description = "Región AWS. Debe ser una donde Bedrock sirva el modelo elegido."
  type        = string
  default     = "us-east-1"
}

# No hay variable para el perfil de AWS, a propósito.
#
# El bloque `backend` no admite variables ni interpolación —es lo primero que
# Terraform lee, antes de que exista un valor—, así que el perfil tendría que
# escribirse literal ahí y como variable en el proveedor. Dos sitios que dicen lo
# mismo terminan diciendo cosas distintas, y el síntoma es de los caros: el estado
# leído de una cuenta y los recursos aplicados en otra.
#
# La resolución de credenciales queda entonces en manos del entorno, que es el
# único mecanismo que funciona igual en las dos formas de ejecutar esto:
# `AWS_PROFILE=team_devops_jamar` en una máquina (lo pone scripts/entorno.sh) y las
# variables que inyecta OIDC en GitHub Actions. Que sea la cuenta correcta lo
# verifica scripts/desplegar.sh comparando con CARESYNC_CUENTA antes de aplicar.

# ---------------------------------------------------------------- Bedrock

variable "modelo_id" {
  description = <<-TXT
    Identificador del modelo en Bedrock. El prefijo `us.` indica un perfil de
    inferencia entre regiones: sin él la llamada falla con ValidationException.
  TXT
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "regiones_inferencia" {
  description = "Regiones a las que puede enrutar el perfil de inferencia `us.`; se permiten todas en IAM."
  type        = list(string)
  default     = ["us-east-1", "us-east-2", "us-west-2"]
}

variable "usar_guardrail" {
  description = "Aplica el guardrail en cada llamada. Se puede apagar para depurar prompts."
  type        = bool
  default     = true
}

# ------------------------------------------------------------------ ROBLE

variable "roble_base_url" {
  description = "Host de la API de ROBLE."
  type        = string
  default     = "https://roble-api.test-openlab.uninorte.edu.co"
}

variable "roble_contract_id" {
  description = "Identificador del proyecto (contrato) en la consola de ROBLE."
  type        = string
  default     = "caresync_cab021ce03"
}

# ------------------------------------------------------------------ Correo

variable "correo_remitente" {
  description = <<-TXT
    Dirección desde la que SES envía. Hay que verificarla haciendo clic en el
    correo que AWS manda tras el primer apply. Vacío desactiva SES y el
    presupuesto.
  TXT
  type        = string
  default     = ""
}

variable "correo_emergencias" {
  description = "Buzón que recibe los escalamientos del agente de triaje."
  type        = string
  default     = ""
}

# --------------------------------------------------------------- Operación

variable "retencion_logs" {
  description = "Días de retención de los grupos de logs. 14 mantiene el coste en cero."
  type        = number
  default     = 14
}

variable "cadencia_recordatorios" {
  description = "Cada cuánto despierta la Lambda de recordatorios."
  type        = string
  default     = "rate(15 minutes)"
}

variable "presupuesto_mensual_usd" {
  description = "Techo del presupuesto de AWS Budgets. Avisa, no bloquea."
  type        = number
  default     = 20
}

variable "origenes_cors_extra" {
  description = "Orígenes adicionales permitidos por el API además de localhost y Amplify."
  type        = list(string)
  default     = []
}

variable "memoria_orquestador" {
  description = "MB de la Lambda del orquestador. El cuello de botella es Bedrock, no la CPU."
  type        = number
  default     = 512
}

variable "timeout_orquestador" {
  description = "Segundos. El bucle de herramientas puede dar varias vueltas."
  type        = number
  default     = 60
}
