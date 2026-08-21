/*
 * Dónde vive el estado.
 *
 * El bucket y la tabla no los crea este módulo: los crea `infra/arranque/`, una
 * sola vez y desde una máquina. No es una preferencia de organización, es que no
 * se puede de otra forma — un módulo no puede guardar su estado en un bucket que
 * ese mismo estado tendría que haber creado.
 *
 * `key` incluye el entorno porque dev y demo comparten cuenta. Si algún día se
 * añade otro entorno, el `-backend-config=key=...` que pasa desplegar.sh es lo
 * único que cambia; aquí queda el valor por defecto.
 *
 * `dynamodb_table` y no el bloqueo nativo de S3 (`use_lockfile`): eso llegó en
 * Terraform 1.10 y aquí se fija 1.5.7, la versión instalada en la máquina del
 * equipo, para que CI y una persona apliquen con el mismo binario.
 *
 * Sin `profile`: el bloque backend se evalúa antes que las variables y no admite
 * interpolación, así que el perfil sólo podría escribirse literal. El motivo por
 * el que no se escribe está en variables.tf.
 */

terraform {
  backend "s3" {
    bucket         = "caresync-tfstate-539091491293"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "caresync-tflock"
    encrypt        = true
  }
}
