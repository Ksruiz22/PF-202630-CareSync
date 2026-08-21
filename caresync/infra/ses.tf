# SES en modo sandbox: sirve para el prototipo, con dos condiciones que hay que
# tener presentes en la demo.
#
#   1. La dirección remitente hay que verificarla haciendo clic en el correo que
#      AWS envía tras el primer apply.
#   2. En sandbox también hay que verificar CADA destinatario. Para la demo eso
#      significa dar de alta los correos de los tres integrantes y del jurado,
#      o pedir la salida del sandbox con antelación.
#
# Si `correo_remitente` está vacío, no se crea nada y el sistema registra los
# envíos en el log en lugar de mandarlos. Así el despliegue no depende de tener
# el correo listo.

resource "aws_sesv2_email_identity" "remitente" {
  count          = local.con_correo ? 1 : 0
  email_identity = var.correo_remitente
}

resource "aws_sesv2_email_identity" "emergencias" {
  # El destinatario de los escalamientos también necesita estar verificado
  # mientras la cuenta esté en sandbox.
  count          = local.con_correo && var.correo_emergencias != "" && var.correo_emergencias != var.correo_remitente ? 1 : 0
  email_identity = var.correo_emergencias
}

resource "aws_sesv2_configuration_set" "principal" {
  count                  = local.con_correo ? 1 : 0
  configuration_set_name = "${local.nombre}-envios"

  delivery_options {
    tls_policy = "REQUIRE"
  }

  reputation_options {
    reputation_metrics_enabled = true
  }

  sending_options {
    sending_enabled = true
  }
}
