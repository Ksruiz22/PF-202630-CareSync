output "rol_plan" {
  description = "Rol que asumen los pull requests. Va en el flujo de CI como AWS_ROL_PLAN."
  value       = aws_iam_role.plan.arn
}

output "rol_apply" {
  description = "Rol que asume el despliegue desde main. Va en el flujo de CI como AWS_ROL_APPLY."
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
    "Guardar los ARN de los roles como variables del repositorio (Settings > Secrets and variables > Actions > Variables): AWS_ROL_PLAN y AWS_ROL_APPLY.",
    "Crear el environment «${var.entorno_github}» en GitHub y, si se quiere aprobación manual, añadirle revisores.",
    "Cargar las credenciales de ROBLE en Parameter Store a mano (ver infra/ssm.tf). No las pone ni este módulo ni CI.",
    "Empujar a ${var.rama_despliegue}: el flujo .github/workflows/infra.yml aplica el resto.",
  ]
}
