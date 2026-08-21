terraform {
  required_version = ">= 1.5.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # El estado va a S3 con bloqueo en DynamoDB: ver backend.tf. Deja de ser
  # opcional en el momento en que aplica GitHub Actions, porque el ejecutor es
  # una máquina nueva en cada ejecución y un estado local se perdería con ella
  # —Terraform volvería a crear los cuarenta recursos en la siguiente vuelta.
}

provider "aws" {
  region = var.region

  # Sin `profile`. Las credenciales salen del entorno; el por qué está en
  # variables.tf, donde estaba la variable que se eliminó.

  default_tags {
    tags = {
      Proyecto   = var.proyecto
      Entorno    = var.entorno
      Asignatura = "Proyecto Final - Uninorte"
      GestionPor = "terraform"
    }
  }
}
