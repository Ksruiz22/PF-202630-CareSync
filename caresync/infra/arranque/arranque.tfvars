# Valores reales del arranque. Se versiona a propósito: aquí no hay secretos, y
# que el repositorio autorizado esté a la vista en el control de versiones es parte
# de la garantía —cambiarlo deja rastro en un commit.
#
#   terraform apply -var-file=arranque.tfvars
#
# `repositorio` decide qué repositorio de GitHub puede desplegar en la cuenta
# 539091491293. Escribirlo mal no da un error al aplicar: da un despliegue que falla
# con «Not authorized to perform sts:AssumeRoleWithWebIdentity» desde el repositorio
# correcto.
#
# El proyecto está dentro de este repositorio en la subcarpeta `caresync/`. Eso no
# afecta a este valor: el `sub` del token de OIDC identifica al repositorio, no a la
# carpeta desde la que corre el workflow.

repositorio = "Ksruiz22/PF-202630-CareSync"
