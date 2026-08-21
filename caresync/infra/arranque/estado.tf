locals {
  bucket = "caresync-tfstate-${var.cuenta}"
  tabla  = "caresync-tflock"
}

resource "aws_s3_bucket" "estado" {
  bucket = local.bucket

  # Aquí, y no en un `check`, porque un `check` avisa y sigue. Esto tiene que
  # impedir el apply: el nombre del bucket lleva el número de cuenta, así que
  # aplicar con las credenciales equivocadas crearía en la cuenta ajena un bucket
  # bautizado con el número de la nuestra.
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.actual.account_id == var.cuenta
      error_message = "Las credenciales apuntan a ${data.aws_caller_identity.actual.account_id} y se esperaba ${var.cuenta}."
    }
  }
}

# El versionado es lo que convierte un `terraform state` mal escrito en algo
# reversible. Sin él, el estado corrupto es definitivo.
resource "aws_s3_bucket_versioning" "estado" {
  bucket = aws_s3_bucket.estado.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "estado" {
  bucket = aws_s3_bucket.estado.id

  rule {
    apply_server_side_encryption_by_default {
      # AES256 y no KMS: el estado no lleva secretos —las credenciales de ROBLE
      # están en Parameter Store y Terraform las ignora— y una clave gestionada
      # añade coste y una forma más de quedarse fuera del propio estado.
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "estado" {
  bucket                  = aws_s3_bucket.estado.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Sin esto el bucket crece para siempre: cada apply deja una versión más del
# estado. 90 días es más de lo que dura el proyecto y suficiente para volver atrás.
resource "aws_s3_bucket_lifecycle_configuration" "estado" {
  bucket = aws_s3_bucket.estado.id

  rule {
    id     = "caducar-versiones-antiguas"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# La tabla de bloqueo. Sin ella, dos apply simultáneos —CI y una persona, que es
# el caso realista— escriben el estado uno encima del otro.
resource "aws_dynamodb_table" "bloqueo" {
  name         = local.tabla
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
