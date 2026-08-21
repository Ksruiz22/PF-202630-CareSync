# Salvaguardas de contenido. Se aplican en cada llamada al modelo, así que
# valen tanto para lo que escribe la persona como para lo que responde el
# agente.
#
# Los temas denegados están redactados sobre la CONDUCTA DEL AGENTE, no sobre
# el síntoma que describe el paciente: un tema mal redactado bloquea a alguien
# que dice "me tomé dos ibuprofenos", que es exactamente lo que el triaje
# necesita oír. Afinarlos con casos reales es trabajo de la Fase 5.

resource "aws_bedrock_guardrail" "principal" {
  name        = "${local.nombre}-salvaguardas"
  description = "Salvaguardas de los agentes de CareSync: sin diagnóstico ni prescripción, y ruta de urgencia siempre visible."

  blocked_input_messaging = join(" ", [
    "No puedo ayudarte con eso por este canal.",
    "Si es una urgencia de salud, llama a la línea de emergencias del campus o al 123.",
  ])

  blocked_outputs_messaging = join(" ", [
    "Prefiero no responder eso: no soy personal clínico y podría equivocarme.",
    "Un profesional del Centro Médico Uninorte o del Centro de Acompañamiento Estudiantil puede resolverlo contigo.",
  ])

  content_policy_config {
    filters_config {
      type            = "SEXUAL"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "HATE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "MEDIUM"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "MISCONDUCT"
      input_strength  = "MEDIUM"
      output_strength = "HIGH"
    }
    # Deliberadamente bajo en la entrada: una persona describiendo autolesión o
    # una agresión sufrida NO debe ser rechazada, debe ser escalada. Filtrarla
    # convertiría el caso más grave en un silencio.
    filters_config {
      type            = "VIOLENCE"
      input_strength  = "NONE"
      output_strength = "HIGH"
    }
    # PROMPT_ATTACK sólo admite filtrado de entrada.
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }

  topic_policy_config {
    topics_config {
      name       = "diagnostico_definitivo"
      type       = "DENY"
      definition = "Que el asistente afirme cuál es la enfermedad o el trastorno que tiene la persona, o descarte una, como si fuera un dictamen clínico."
      examples = [
        "Lo que tienes es apendicitis.",
        "No es nada, seguro es sólo estrés.",
        "Puedo confirmarte que tienes un trastorno de ansiedad generalizada.",
      ]
    }
    topics_config {
      name       = "prescripcion"
      type       = "DENY"
      definition = "Que el asistente indique tomar, suspender o cambiar un medicamento, o proponga una dosis. El plan de tratamiento lo escribe el profesional en su propia interfaz, no el agente."
      examples = [
        "Tómate 500 mg de acetaminofén cada 8 horas.",
        "Puedes dejar de tomar el antidepresivo.",
        "Súbete la dosis a dos pastillas.",
      ]
    }
    topics_config {
      name       = "sustituir_urgencia"
      type       = "DENY"
      definition = "Que el asistente disuada a la persona de buscar atención inmediata, o le diga que puede esperar, cuando describe una señal de alarma."
      examples = [
        "No necesitas ir a urgencias, espera a tu cita del jueves.",
        "Eso puede esperar hasta la próxima semana.",
      ]
    }
  }

  sensitive_information_policy_config {
    # No se anonimiza el nombre ni el correo: el agente los necesita para
    # dirigirse a la persona y para que el profesional sepa a quién atiende.
    # Se bloquea lo que no tiene ninguna razón de estar en esta conversación.
    pii_entities_config {
      type   = "CREDIT_DEBIT_CARD_NUMBER"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "PASSWORD"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "AWS_SECRET_KEY"
      action = "BLOCK"
    }
  }
}

resource "aws_bedrock_guardrail_version" "publicada" {
  guardrail_arn = aws_bedrock_guardrail.principal.guardrail_arn
  description   = "Versión consumida por las Lambdas de ${local.nombre}."
  skip_destroy  = true

  # Un guardrail versionado es inmutable: si se edita el recurso de arriba hay
  # que publicar una versión nueva, o las Lambdas seguirían usando la vieja.
  lifecycle {
    replace_triggered_by = [aws_bedrock_guardrail.principal]
  }
}
