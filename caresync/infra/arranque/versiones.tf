/*
 * Módulo de arranque: lo que tiene que existir antes de que exista todo lo demás.
 *
 * Crea cuatro cosas y ninguna más:
 *   1. el bucket de S3 donde vive el estado de `infra/`,
 *   2. la tabla de DynamoDB que lo bloquea,
 *   3. el proveedor de identidad de GitHub en la cuenta,
 *   4. los dos roles que asume GitHub Actions (planificar y aplicar).
 *
 * Esto no se puede ejecutar en GitHub Actions, y no por comodidad: aquí se crea
 * la identidad con la que Actions se autentica. Se aplica una vez desde la
 * máquina de quien administra la cuenta:
 *
 *   source scripts/entorno.sh
 *   cd infra/arranque
 *   terraform init
 *   terraform apply -var-file=arranque.tfvars
 *
 * Su propio estado es local, por la misma razón circular: no puede guardarlo en
 * el bucket que él mismo crea. No pasa nada si se pierde —son cuatro recursos con
 * nombre fijo y se recuperan importándolos, ver README.md— así que tampoco se
 * versiona (.gitignore excluye *.tfstate).
 */

terraform {
  required_version = ">= 1.5.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region

  # Sin `profile`, igual que el módulo principal: las credenciales vienen del
  # entorno (scripts/entorno.sh exporta AWS_PROFILE en una máquina).

  default_tags {
    tags = {
      Proyecto   = "caresync"
      Asignatura = "Proyecto Final - Uninorte"
      GestionPor = "terraform-arranque"
    }
  }
}

data "aws_caller_identity" "actual" {}
