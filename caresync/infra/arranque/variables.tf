variable "cuenta" {
  description = "Cuenta AWS esperada. Se comprueba contra las credenciales antes de crear nada."
  type        = string
  default     = "539091491293"
}

variable "region" {
  description = "Región del bucket de estado y de la tabla de bloqueo."
  type        = string
  default     = "us-east-1"
}

# Sin valor por omisión, y eso es deliberado.
#
# Este es el dato que decide quién puede desplegar en la cuenta. Un valor por
# omisión inventado aquí produciría una política de confianza que parece bien
# escrita y autoriza a un repositorio que no es el del equipo. Terraform lo pide
# por consola si falta; lo normal es escribirlo en arranque.tfvars.
variable "repositorio" {
  description = "Repositorio de GitHub autorizado, en la forma «propietario/nombre»."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$", var.repositorio))
    error_message = "Se espera «propietario/nombre», por ejemplo: kruiz-uninorte/caresync."
  }
}

variable "rama_despliegue" {
  description = "Rama desde la que se permite aplicar."
  type        = string
  default     = "main"
}

variable "entorno_github" {
  description = <<-TXT
    Nombre del «environment» de GitHub que usa el trabajo de despliegue. Al declarar
    un environment en el flujo, GitHub cambia el `sub` del token y por eso tiene que
    figurar en la política de confianza. Es además dónde se configuran los
    revisores que aprueban un despliegue a mano.
  TXT
  type        = string
  default     = "aws-dev"
}

variable "crear_proveedor_oidc" {
  description = <<-TXT
    Crear el proveedor de identidad de GitHub. Ponerlo en false si la cuenta ya lo
    tiene (otro equipo lo creó): sólo puede haber uno por cuenta y el segundo
    `apply` falla con EntityAlreadyExists. Con false se usa el que ya existe.
  TXT
  type        = bool
  default     = true
}
