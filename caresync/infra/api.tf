# Un HTTP API con una sola ruta con efecto: POST /agente. La PWA habla
# directamente con ROBLE para leer y escribir sus datos —ahí los permisos por
# rol ya son de ROBLE—, y sólo pasa por aquí cuando necesita a un agente.
#
# No hay autorizador de API Gateway: quien valida el token es el orquestador,
# contra ROBLE, porque el mismo token tiene que servir después para actuar EN
# NOMBRE del llamante. Un autorizador JWT aquí validaría la firma pero no
# permitiría eso, y duplicaría la fuente de verdad de los roles.

resource "aws_apigatewayv2_api" "principal" {
  name          = "${local.nombre}-api"
  description   = "Entrada única a los agentes de CareSync."
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins  = local.origenes_cors
    allow_methods  = ["POST", "GET", "OPTIONS"]
    allow_headers  = ["content-type", "authorization"]
    expose_headers = ["x-caresync-caso"]
    max_age        = 300
  }
}

resource "aws_apigatewayv2_integration" "orquestador" {
  api_id                 = aws_apigatewayv2_api.principal.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.orquestador.invoke_arn
  payload_format_version = "2.0"
  # El mismo valor que el timeout de la Lambda, y no por casualidad: si la
  # integración esperara menos, la función seguiría corriendo y escribiendo en ROBLE
  # después de que el cliente recibiera un 504. El máximo de un HTTP API son 30 s y
  # es lo que valida `var.timeout_orquestador`.
  timeout_milliseconds = var.timeout_orquestador * 1000
}

resource "aws_apigatewayv2_route" "agente" {
  api_id    = aws_apigatewayv2_api.principal.id
  route_key = "POST /agente"
  target    = "integrations/${aws_apigatewayv2_integration.orquestador.id}"
}

# Sin efecto y sin token: es lo que consulta el smoke test para saber que la
# función arrancó, leyó su configuración y alcanza a ROBLE.
resource "aws_apigatewayv2_route" "salud" {
  api_id    = aws_apigatewayv2_api.principal.id
  route_key = "GET /salud"
  target    = "integrations/${aws_apigatewayv2_integration.orquestador.id}"
}

resource "aws_apigatewayv2_stage" "predeterminado" {
  api_id      = aws_apigatewayv2_api.principal.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      momento     = "$context.requestTime"
      id          = "$context.requestId"
      ruta        = "$context.routeKey"
      estado      = "$context.status"
      latencia_ms = "$context.responseLatency"
      error       = "$context.error.message"
      integracion = "$context.integrationErrorMessage"
      ip          = "$context.identity.sourceIp"
    })
  }

  default_route_settings {
    # El prototipo lo usan tres personas y un jurado. Este techo existe para
    # que un bucle en el navegador no se convierta en una factura de Bedrock.
    throttling_burst_limit = 20
    throttling_rate_limit  = 10
  }
}
