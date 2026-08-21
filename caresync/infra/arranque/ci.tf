/*
 * Cómo entra GitHub Actions en la cuenta.
 *
 * Sin claves de acceso. Un `AWS_ACCESS_KEY_ID` guardado como secreto del
 * repositorio es una credencial permanente que hay que rotar a mano, que sirve
 * desde cualquier sitio y que se filtra completa en cuanto alguien la imprime en
 * un log. Con OIDC, el ejecutor presenta un token firmado por GitHub que dice de
 * qué repositorio, rama y flujo viene, AWS lo cambia por credenciales que duran
 * una hora, y la política de confianza de abajo decide si ese origen vale.
 *
 * Dos roles y no uno, que es lo que hace que esto sea seguro de verdad: los pull
 * requests ejecutan código que aún no ha revisado nadie. El rol que usan sólo lee.
 */

resource "aws_iam_openid_connect_provider" "github" {
  count = var.crear_proveedor_oidc ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  # AWS dejó de validar esta huella para los proveedores conocidos (entre ellos
  # GitHub), pero el argumento sigue siendo obligatorio. Si algún día cambia la
  # cadena de GitHub, este valor no es lo que rompe.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.crear_proveedor_oidc ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  oidc_arn = var.crear_proveedor_oidc ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
  clave    = "arn:aws:s3:::${local.bucket}/*"
}

# --- confianza ---------------------------------------------------------------

data "aws_iam_policy_document" "confianza_plan" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_arn]
    }

    # La audiencia también se comprueba: sin esta condición, un token emitido para
    # otro servicio con el mismo `sub` serviría igual.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Sólo desde un pull request de este repositorio. `StringEquals` y no
    # `StringLike`: un comodín mal puesto aquí (repo:mi-org/*) abre la cuenta a
    # cualquier repositorio de la organización.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.repositorio}:pull_request"]
    }
  }
}

data "aws_iam_policy_document" "confianza_apply" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Dos valores porque GitHub cambia el `sub` según cómo se declare el trabajo:
    # con `environment:` en el flujo llega la primera forma, sin él la segunda.
    # Están las dos para que activar o quitar la aprobación manual en GitHub no
    # exija volver a tocar IAM.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.repositorio}:environment:${var.entorno_github}",
        "repo:${var.repositorio}:ref:refs/heads/${var.rama_despliegue}",
      ]
    }
  }
}

# --- permisos comunes: el estado ---------------------------------------------

data "aws_iam_policy_document" "estado_lectura" {
  statement {
    sid       = "ListarElBucketDelEstado"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketVersioning"]
    resources = [aws_s3_bucket.estado.arn]
  }

  statement {
    sid       = "LeerElEstado"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = [local.clave]
  }

  # `terraform plan` también bloquea el estado, así que necesita escribir en la
  # tabla. Es lo que evita que un plan y un apply se pisen.
  statement {
    sid       = "BloquearElEstado"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:DescribeTable"]
    resources = [aws_dynamodb_table.bloqueo.arn]
  }
}

# --- rol de planificación (pull requests) ------------------------------------

resource "aws_iam_role" "plan" {
  name                 = "caresync-ci-plan"
  description          = "Planifica en los pull requests de ${var.repositorio}. Sólo lectura."
  assume_role_policy   = data.aws_iam_policy_document.confianza_plan.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_lectura" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "plan_extra" {
  source_policy_documents = [data.aws_iam_policy_document.estado_lectura.json]

  # Refrescar el estado obliga a leer los parámetros de SSM, y dos de ellos son
  # SecureString: sin kms:Decrypt el plan de cada pull request falla.
  #
  # La consecuencia hay que decirla clara: este rol puede leer la contraseña de la
  # cuenta de servicio de ROBLE. Lo que lo contiene es la política de confianza —un
  # único repositorio, y sólo en pull requests— más el hecho de que GitHub no emite
  # token de OIDC a los pull requests que vienen de un fork. Si el repositorio se
  # hace público, esto es lo primero que hay que revisar.
  statement {
    sid       = "DescifrarParametrosDeSSM"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.region}.amazonaws.com"]
    }
  }

  # El módulo no usa Secrets Manager. Negarlo explícitamente cierra la vía más
  # obvia de sacar algo de la cuenta con un rol de sólo lectura.
  statement {
    sid       = "NadaDeSecretsManager"
    effect    = "Deny"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "plan_extra" {
  name   = "caresync-ci-plan-estado"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.plan_extra.json
}

# --- rol de despliegue (main) ------------------------------------------------

resource "aws_iam_role" "apply" {
  name                 = "caresync-ci-apply"
  description          = "Aplica la infraestructura de CareSync desde ${var.repositorio}."
  assume_role_policy   = data.aws_iam_policy_document.confianza_apply.json
  max_session_duration = 3600
}

# PowerUserAccess: todo menos IAM. Escribir a mano la lista de permisos que
# necesitan cuarenta recursos de nueve servicios da una política de trescientas
# líneas que se queda obsoleta al añadir el primer recurso nuevo, y el fallo se
# manifiesta a mitad de un apply, con la infraestructura a medias. Lo que sí se
# acota es IAM, que es donde un permiso de más deja de ser un problema de este
# proyecto y pasa a ser un problema de la cuenta.
resource "aws_iam_role_policy_attachment" "apply_poweruser" {
  role       = aws_iam_role.apply.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

data "aws_iam_policy_document" "apply_extra" {
  source_policy_documents = [data.aws_iam_policy_document.estado_lectura.json]

  statement {
    sid       = "EscribirElEstado"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = [local.clave]
  }

  # IAM sólo sobre lo que se llama caresync-*. El módulo crea los roles de
  # ejecución de las Lambdas y el del planificador de EventBridge; nada más.
  # Ojo con el nombre: cualquier recurso nuevo tiene que respetar el prefijo o el
  # apply falla con AccessDenied, y eso es exactamente lo que se busca.
  statement {
    sid    = "GestionarLosRolesDelProyecto"
    effect = "Allow"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:UpdateRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:GetRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PassRole",
    ]
    resources = ["arn:aws:iam::${var.cuenta}:role/caresync-*"]
  }

  statement {
    sid    = "GestionarLasPoliticasDelProyecto"
    effect = "Allow"
    actions = [
      "iam:CreatePolicy",
      "iam:DeletePolicy",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListPolicyVersions",
      "iam:CreatePolicyVersion",
      "iam:DeletePolicyVersion",
      "iam:TagPolicy",
      "iam:UntagPolicy",
    ]
    resources = ["arn:aws:iam::${var.cuenta}:policy/caresync-*"]
  }

  # Ni tocar los roles de CI ni el proveedor de identidad: si el rol que aplica
  # pudiera reescribir su propia política de confianza, la restricción a un
  # repositorio sería decorativa.
  statement {
    sid    = "NoTocarLaPropiaIdentidad"
    effect = "Deny"
    actions = [
      "iam:*OpenIDConnectProvider*",
      "iam:UpdateAssumeRolePolicy",
      "iam:DeleteRole",
      "iam:PutRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
    ]
    resources = [
      aws_iam_role.plan.arn,
      aws_iam_role.apply.arn,
      local.oidc_arn,
    ]
  }
}

resource "aws_iam_role_policy" "apply_extra" {
  name   = "caresync-ci-apply-estado-e-iam"
  role   = aws_iam_role.apply.id
  policy = data.aws_iam_policy_document.apply_extra.json
}
