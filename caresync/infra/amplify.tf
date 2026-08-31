# Amplify Hosting sin repositorio conectado: los despliegues son manuales, con
# un .zip que sube `scripts/publicar_app.sh`.
#
# Es a propósito. Conectar el repositorio exigiría un token de GitHub con
# permiso de administración de webhooks guardado en Terraform, y el equipo son
# tres personas que despliegan a mano hasta la Fase 4. La automatización llega
# cuando exista el repositorio compartido, y entonces es un solo bloque más.

resource "aws_amplify_app" "pwa" {
  name        = local.nombre
  description = "Aplicación web de CareSync: cinco vistas por rol."
  platform    = "WEB"

  # Sin esto, recargar /paciente en una SPA devuelve 404: Amplify busca un
  # fichero que no existe en lugar de entregar el index.
  custom_rule {
    source = "/<*>"
    target = "/index.html"
    status = "404-200"
  }
}

resource "aws_amplify_branch" "principal" {
  app_id      = aws_amplify_app.pwa.id
  branch_name = "main"
  description = "Rama única del prototipo."
  framework   = "React"
  stage       = "DEVELOPMENT"

  enable_auto_build = false
}
