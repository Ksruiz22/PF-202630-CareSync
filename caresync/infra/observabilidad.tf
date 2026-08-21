# Los grupos de logs se declaran aquí y no se dejan crear a Lambda: así tienen
# retención (si los crea Lambda, es "nunca expiran") y los permisos de escritura
# del rol pueden apuntar a un ARN concreto en vez de a "*".

resource "aws_cloudwatch_log_group" "orquestador" {
  name              = "/aws/lambda/${local.nombre}-orquestador"
  retention_in_days = var.retencion_logs
}

resource "aws_cloudwatch_log_group" "herramientas" {
  name              = "/aws/lambda/${local.nombre}-herramientas"
  retention_in_days = var.retencion_logs
}

resource "aws_cloudwatch_log_group" "recordatorios" {
  name              = "/aws/lambda/${local.nombre}-recordatorios"
  retention_in_days = var.retencion_logs
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${local.nombre}"
  retention_in_days = var.retencion_logs
}

# ------------------------------------------------------------------- avisos

resource "aws_sns_topic" "avisos" {
  name = "${local.nombre}-avisos"
}

resource "aws_sns_topic_subscription" "avisos_correo" {
  count     = local.con_correo ? 1 : 0
  topic_arn = aws_sns_topic.avisos.arn
  protocol  = "email"
  endpoint  = var.correo_remitente

  # La suscripción queda en "pending confirmation" hasta que alguien haga clic en
  # el enlace que llega por correo. Terraform no puede confirmarla y tampoco hace
  # falta ignorar el atributo: `pending_confirmation` lo decide el proveedor, no la
  # configuración, así que un `ignore_changes` sobre él no tendría efecto.
}

# --- escalamientos ------------------------------------------------------------
#
# No es una alarma de infraestructura: es de producto. Cada vez que un agente
# escala un caso por urgencia deja la marca ESCALAMIENTO en el log, y eso
# tiene que llegarle a una persona aunque el correo de SES falle.

resource "aws_cloudwatch_log_metric_filter" "escalamientos" {
  name           = "${local.nombre}-escalamientos"
  log_group_name = aws_cloudwatch_log_group.herramientas.name
  pattern        = "ESCALAMIENTO"

  metric_transformation {
    name      = "Escalamientos"
    namespace = "CareSync/${var.entorno}"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "escalamientos" {
  alarm_name          = "${local.nombre}-escalamiento-de-urgencia"
  alarm_description   = "Un agente escaló un caso por urgencia. Revisar el log de herramientas."
  namespace           = "CareSync/${var.entorno}"
  metric_name         = "Escalamientos"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.avisos.arn]
}

# --- fallos de las funciones --------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "errores_lambda" {
  for_each = {
    orquestador   = aws_lambda_function.orquestador.function_name
    herramientas  = aws_lambda_function.herramientas.function_name
    recordatorios = aws_lambda_function.recordatorios.function_name
  }

  alarm_name          = "${local.nombre}-errores-${each.key}"
  alarm_description   = "La función ${each.value} está fallando."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 3
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.avisos.arn]

  dimensions = {
    FunctionName = each.value
  }
}

# --- coste --------------------------------------------------------------------

resource "aws_budgets_budget" "mensual" {
  count = local.con_correo ? 1 : 0

  name         = "${local.nombre}-mensual"
  budget_type  = "COST"
  limit_amount = tostring(var.presupuesto_mensual_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Avisa al 50 % de lo gastado y al 100 % de lo previsto. Lo segundo es lo que
  # da tiempo a reaccionar: llega antes de que el gasto ocurra.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.correo_remitente]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.correo_remitente]
  }
}
