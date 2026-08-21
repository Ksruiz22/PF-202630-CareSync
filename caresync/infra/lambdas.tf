# Los tres agentes comparten un mismo tiempo de ejecución: el rol de quien
# llama decide el prompt, las herramientas y los permisos. Por eso hay tres
# funciones —orquestador, herramientas, recordatorios— y no tres por agente.

resource "aws_lambda_layer_version" "comun" {
  layer_name          = "${local.nombre}-comun"
  description         = "requests, el SDK de ROBLE y el módulo de acceso a datos compartido."
  filename            = local.paquetes.capa
  source_code_hash    = fileexists(local.paquetes.capa) ? filebase64sha256(local.paquetes.capa) : null
  compatible_runtimes = ["python3.12"]

  # arm64 sale ~20 % más barato y todas las dependencias son Python puro.
  compatible_architectures = ["arm64"]

  lifecycle {
    precondition {
      condition     = fileexists(local.paquetes.capa)
      error_message = "Falta ${local.paquetes.capa}. Ejecuta scripts/construir_paquetes.sh antes de aplicar."
    }
  }
}

locals {
  base_lambda = {
    runtime       = "python3.12"
    architectures = ["arm64"]
    layers        = [aws_lambda_layer_version.comun.arn]
  }
}

# ------------------------------------------------------------- orquestador
#
# Único punto de entrada del sistema. Autoriza al llamante contra ROBLE,
# elige el agente según su rol y corre el bucle de herramientas contra Bedrock.

resource "aws_lambda_function" "orquestador" {
  function_name    = "${local.nombre}-orquestador"
  description      = "Orquestador de agentes: autoriza, elige agente y corre el bucle de herramientas."
  role             = aws_iam_role.orquestador.arn
  handler          = "handler.manejar"
  filename         = local.paquetes.orquestador
  source_code_hash = fileexists(local.paquetes.orquestador) ? filebase64sha256(local.paquetes.orquestador) : null

  runtime       = local.base_lambda.runtime
  architectures = local.base_lambda.architectures
  layers        = local.base_lambda.layers

  memory_size = var.memoria_orquestador
  timeout     = var.timeout_orquestador

  environment {
    variables = {
      ENTORNO              = var.entorno
      SSM_PREFIJO          = local.ssm_prefijo
      MODELO_ID            = var.modelo_id
      GUARDRAIL_ID         = var.usar_guardrail ? aws_bedrock_guardrail.principal.guardrail_id : ""
      GUARDRAIL_VERSION    = var.usar_guardrail ? aws_bedrock_guardrail_version.publicada.version : ""
      FUNCION_HERRAMIENTAS = aws_lambda_function.herramientas.function_name
      MAX_VUELTAS          = "5"
      NIVEL_LOG            = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.orquestador]

  lifecycle {
    precondition {
      condition     = fileexists(local.paquetes.orquestador)
      error_message = "Falta ${local.paquetes.orquestador}. Ejecuta scripts/construir_paquetes.sh antes de aplicar."
    }
  }
}

# ------------------------------------------------------------ herramientas
#
# Las acciones con efecto: agendar, notificar, consultar, escalar. Está aparte
# del orquestador porque el modelo nunca debe poder ejecutar nada que no pase
# por este contrato, y porque así los permisos de escritura y de correo no
# viven en el proceso que habla con el modelo.

resource "aws_lambda_function" "herramientas" {
  function_name    = "${local.nombre}-herramientas"
  description      = "Herramientas del agente: agendar, notificar, consultar, escalar."
  role             = aws_iam_role.herramientas.arn
  handler          = "handler.manejar"
  filename         = local.paquetes.herramientas
  source_code_hash = fileexists(local.paquetes.herramientas) ? filebase64sha256(local.paquetes.herramientas) : null

  runtime       = local.base_lambda.runtime
  architectures = local.base_lambda.architectures
  layers        = local.base_lambda.layers

  memory_size = 256
  timeout     = 30

  environment {
    variables = {
      ENTORNO         = var.entorno
      SSM_PREFIJO     = local.ssm_prefijo
      SES_CONJUNTO    = local.con_correo ? aws_sesv2_configuration_set.principal[0].configuration_set_name : ""
      MINUTOS_RESERVA = "2"
      NIVEL_LOG       = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.herramientas]

  lifecycle {
    precondition {
      condition     = fileexists(local.paquetes.herramientas)
      error_message = "Falta ${local.paquetes.herramientas}. Ejecuta scripts/construir_paquetes.sh antes de aplicar."
    }
  }
}

# ----------------------------------------------------------- recordatorios
#
# La única función que corre sin un usuario detrás: la despierta el reloj, así
# que se autentica en ROBLE con la cuenta de servicio.

resource "aws_lambda_function" "recordatorios" {
  function_name    = "${local.nombre}-recordatorios"
  description      = "Materializa y envía recordatorios; detecta huecos de adherencia y de evolución."
  role             = aws_iam_role.recordatorios.arn
  handler          = "handler.manejar"
  filename         = local.paquetes.recordatorios
  source_code_hash = fileexists(local.paquetes.recordatorios) ? filebase64sha256(local.paquetes.recordatorios) : null

  runtime       = local.base_lambda.runtime
  architectures = local.base_lambda.architectures
  layers        = local.base_lambda.layers

  memory_size = 256
  timeout     = 120

  environment {
    variables = {
      ENTORNO              = var.entorno
      SSM_PREFIJO          = local.ssm_prefijo
      SES_CONJUNTO         = local.con_correo ? aws_sesv2_configuration_set.principal[0].configuration_set_name : ""
      VENTANA_MINUTOS      = "20"
      HORAS_SIN_ADHERENCIA = "36"
      DIAS_SIN_EVOLUCION   = "3"
      NIVEL_LOG            = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.recordatorios]

  lifecycle {
    precondition {
      condition     = fileexists(local.paquetes.recordatorios)
      error_message = "Falta ${local.paquetes.recordatorios}. Ejecuta scripts/construir_paquetes.sh antes de aplicar."
    }
  }
}

# El orquestador es el único invocable desde fuera, y sólo por este API.
resource "aws_lambda_permission" "api_invoca_orquestador" {
  statement_id  = "PermitirApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.orquestador.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.principal.execution_arn}/*/*"
}
