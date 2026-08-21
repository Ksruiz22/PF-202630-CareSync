data "aws_caller_identity" "actual" {}

locals {
  nombre = "${var.proyecto}-${var.entorno}"

  cuenta = data.aws_caller_identity.actual.account_id

  # Prefijo único de la configuración en Parameter Store. Todo lo que la
  # aplicación necesita saber del entorno cuelga de aquí.
  ssm_prefijo = "/${var.proyecto}/${var.entorno}"

  # Los .zip los produce `scripts/construir_paquetes.sh`; Terraform sólo los
  # consume. Es deliberado: instalar dependencias desde Terraform ataría el
  # plan a que haya pip en la máquina y a la plataforma del que aplica.
  dist = "${path.module}/../dist"

  paquetes = {
    capa          = "${local.dist}/capa.zip"
    orquestador   = "${local.dist}/orquestador.zip"
    herramientas  = "${local.dist}/herramientas.zip"
    recordatorios = "${local.dist}/recordatorios.zip"
  }

  # El perfil de inferencia enruta a varias regiones, así que el permiso de
  # InvokeModel tiene que cubrir el modelo base en todas ellas.
  modelo_base = replace(var.modelo_id, "us.", "")

  arns_modelo = concat(
    [for r in var.regiones_inferencia : "arn:aws:bedrock:${r}::foundation-model/${local.modelo_base}"],
    ["arn:aws:bedrock:${var.region}:${local.cuenta}:inference-profile/${var.modelo_id}"],
  )

  dominio_pwa = "https://${aws_amplify_branch.principal.branch_name}.${aws_amplify_app.pwa.default_domain}"

  origenes_cors = concat(
    ["http://localhost:5173", local.dominio_pwa],
    var.origenes_cors_extra,
  )

  con_correo = var.correo_remitente != ""
}
