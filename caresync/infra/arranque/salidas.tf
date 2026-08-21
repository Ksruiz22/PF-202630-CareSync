output "rol_plan" {
  description = "Rol que asumen los pull requests. Debe coincidir con el `role-to-assume` del trabajo `plan` en .github/workflows/infra.yml."
  value       = aws_iam_role.plan.arn
}

output "rol_apply" {
  description = "Rol que asume el despliegue desde main. Debe coincidir con el `role-to-assume` de los trabajos `aplicar` y `publicar`."
  value       = aws_iam_role.apply.arn
}

output "bucket_estado" {
  description = "Debe coincidir con el `bucket` de infra/backend.tf."
  value       = aws_s3_bucket.estado.id
}

output "tabla_bloqueo" {
  description = "Debe coincidir con el `dynamodb_table` de infra/backend.tf."
  value       = aws_dynamodb_table.bloqueo.name
}

output "siguiente_paso" {
  description = "Qué hacer con estas salidas."
  value = [
    "Comprobar que estos dos ARN son los que están escritos en .github/workflows/infra.yml y app.yml. Van literales en el YAML, no en variables del repositorio: administrarlas exige permiso de admin y un ARN de rol no es un secreto.",
    "Cargar las credenciales de ROBLE en Parameter Store a mano (ver infra/ssm.tf). No las pone ni este módulo ni CI.",
    "Empujar a ${var.rama_despliegue}: el flujo .github/workflows/infra.yml aplica el resto.",
    "Opcional, y sólo si el repositorio deja de ser privado de plan gratuito: crear el environment «${var.entorno_github}» con revisores y declararlo en el trabajo de despliegue. La política de confianza ya lo acepta.",
  ]
}
