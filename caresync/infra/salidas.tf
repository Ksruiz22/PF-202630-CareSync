output "api_url" {
  description = "Base del API. La PWA la consume como VITE_API_URL."
  value       = aws_apigatewayv2_stage.predeterminado.invoke_url
}

output "endpoint_agente" {
  description = "Ruta completa del orquestador."
  value       = "${aws_apigatewayv2_stage.predeterminado.invoke_url}agente"
}

output "endpoint_salud" {
  description = "Comprobación sin token: devuelve si la función alcanza su configuración y ROBLE."
  value       = "${aws_apigatewayv2_stage.predeterminado.invoke_url}salud"
}

output "pwa_url" {
  description = "Dirección pública de la aplicación web."
  value       = local.dominio_pwa
}

output "amplify_app_id" {
  description = "Necesario para publicar la aplicación con scripts/publicar_app.sh."
  value       = aws_amplify_app.pwa.id
}

output "guardrail" {
  description = "Guardrail y versión que consumen las Lambdas."
  value = {
    id      = aws_bedrock_guardrail.principal.guardrail_id
    version = aws_bedrock_guardrail_version.publicada.version
    activo  = var.usar_guardrail
  }
}

output "funciones" {
  description = "Nombres de las funciones, para leer logs y para invocarlas a mano."
  value = {
    orquestador   = aws_lambda_function.orquestador.function_name
    herramientas  = aws_lambda_function.herramientas.function_name
    recordatorios = aws_lambda_function.recordatorios.function_name
  }
}

output "roble" {
  description = "Configuración de ROBLE que también necesita la PWA."
  value = {
    base_url    = var.roble_base_url
    contract_id = var.roble_contract_id
  }
}

output "pendiente_manual" {
  description = "Lo que Terraform no puede hacer y hay que completar a mano."
  value = compact([
    "Cargar /caresync/${var.entorno}/roble/servicio/{email,password} en Parameter Store.",
    local.con_correo ? "Verificar el remitente ${var.correo_remitente} desde el correo que envía SES." : "Definir correo_remitente para activar SES, el presupuesto y los avisos.",
    local.con_correo ? "Confirmar la suscripción del tema SNS de avisos desde el correo." : "",
    "Crear las tablas y los permisos por rol en ROBLE: ver docs/runbook-roble.md.",
  ])
}
