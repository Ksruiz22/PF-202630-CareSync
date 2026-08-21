data "aws_kms_alias" "ssm" {
  name = "alias/aws/ssm"
}

data "aws_iam_policy_document" "asume_lambda" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

locals {
  # Configuración que puede leer cualquiera de las tres funciones.
  ssm_comun = [
    aws_ssm_parameter.roble_base_url.arn,
    aws_ssm_parameter.roble_contract_id.arn,
    aws_ssm_parameter.correo_remitente.arn,
    aws_ssm_parameter.correo_emergencias.arn,
  ]

  # Las credenciales de la cuenta de servicio las lee SÓLO recordatorios: es la
  # única función sin un usuario que la autorice. Enumerarlas en vez de dar el
  # prefijo entero es lo que hace real esa distinción.
  ssm_servicio = [
    aws_ssm_parameter.roble_servicio_email.arn,
    aws_ssm_parameter.roble_servicio_password.arn,
  ]
}

# ------------------------------------------------------------- orquestador

resource "aws_iam_role" "orquestador" {
  name               = "${local.nombre}-orquestador"
  assume_role_policy = data.aws_iam_policy_document.asume_lambda.json
}

data "aws_iam_policy_document" "orquestador" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.orquestador.arn}:*"]
  }

  statement {
    sid       = "InvocarModelo"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = local.arns_modelo
  }

  statement {
    sid       = "AplicarSalvaguardas"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = [aws_bedrock_guardrail.principal.guardrail_arn]
  }

  statement {
    sid       = "LeerConfiguracion"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = local.ssm_comun
  }

  statement {
    sid       = "DescifrarConfiguracion"
    actions   = ["kms:Decrypt"]
    resources = [data.aws_kms_alias.ssm.target_key_arn]
  }

  statement {
    sid       = "LlamarHerramientas"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.herramientas.arn]
  }
}

resource "aws_iam_role_policy" "orquestador" {
  name   = "permisos"
  role   = aws_iam_role.orquestador.id
  policy = data.aws_iam_policy_document.orquestador.json
}

# ------------------------------------------------------------ herramientas

resource "aws_iam_role" "herramientas" {
  name               = "${local.nombre}-herramientas"
  assume_role_policy = data.aws_iam_policy_document.asume_lambda.json
}

data "aws_iam_policy_document" "herramientas" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.herramientas.arn}:*"]
  }

  statement {
    sid       = "LeerConfiguracion"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = local.ssm_comun
  }

  statement {
    sid       = "DescifrarConfiguracion"
    actions   = ["kms:Decrypt"]
    resources = [data.aws_kms_alias.ssm.target_key_arn]
  }

  dynamic "statement" {
    for_each = local.con_correo ? [1] : []
    content {
      sid       = "EnviarCorreo"
      actions   = ["ses:SendEmail"]
      resources = ["*"]
      condition {
        test     = "StringEquals"
        variable = "ses:FromAddress"
        values   = [var.correo_remitente]
      }
    }
  }
}

resource "aws_iam_role_policy" "herramientas" {
  name   = "permisos"
  role   = aws_iam_role.herramientas.id
  policy = data.aws_iam_policy_document.herramientas.json
}

# ----------------------------------------------------------- recordatorios

resource "aws_iam_role" "recordatorios" {
  name               = "${local.nombre}-recordatorios"
  assume_role_policy = data.aws_iam_policy_document.asume_lambda.json
}

data "aws_iam_policy_document" "recordatorios" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.recordatorios.arn}:*"]
  }

  statement {
    sid       = "LeerConfiguracion"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = concat(local.ssm_comun, local.ssm_servicio)
  }

  statement {
    sid       = "DescifrarConfiguracion"
    actions   = ["kms:Decrypt"]
    resources = [data.aws_kms_alias.ssm.target_key_arn]
  }

  dynamic "statement" {
    for_each = local.con_correo ? [1] : []
    content {
      sid       = "EnviarCorreo"
      actions   = ["ses:SendEmail"]
      resources = ["*"]
      condition {
        test     = "StringEquals"
        variable = "ses:FromAddress"
        values   = [var.correo_remitente]
      }
    }
  }
}

resource "aws_iam_role_policy" "recordatorios" {
  name   = "permisos"
  role   = aws_iam_role.recordatorios.id
  policy = data.aws_iam_policy_document.recordatorios.json
}

# -------------------------------------------------- rol del planificador

data "aws_iam_policy_document" "asume_scheduler" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    # Sin esto, cualquier horario de la cuenta podría asumir este rol.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.cuenta]
    }
  }
}

resource "aws_iam_role" "planificador" {
  name               = "${local.nombre}-planificador"
  assume_role_policy = data.aws_iam_policy_document.asume_scheduler.json
}

data "aws_iam_policy_document" "planificador" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.recordatorios.arn]
  }
}

resource "aws_iam_role_policy" "planificador" {
  name   = "permisos"
  role   = aws_iam_role.planificador.id
  policy = data.aws_iam_policy_document.planificador.json
}
