# EventBridge Scheduler en vez de una regla de EventBridge Rules: el mismo
# precio (gratis a esta escala) y un solo recurso por horario, sin regla más
# target más permiso de recurso.

resource "aws_scheduler_schedule_group" "principal" {
  name = local.nombre
}

resource "aws_scheduler_schedule" "recordatorios" {
  name       = "${local.nombre}-recordatorios"
  group_name = aws_scheduler_schedule_group.principal.name

  schedule_expression          = var.cadencia_recordatorios
  schedule_expression_timezone = "America/Bogota"

  flexible_time_window {
    # Los recordatorios de medicación tienen hora; no se difieren.
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.recordatorios.arn
    role_arn = aws_iam_role.planificador.arn

    input = jsonencode({
      origen = "planificador"
      tareas = ["materializar", "enviar", "vigilar_adherencia", "liberar_reservas"]
    })

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 600
    }
  }
}
