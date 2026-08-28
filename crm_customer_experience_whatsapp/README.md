# Experiencia del cliente - WhatsApp

Conector opcional para enviar campañas NPS de `crm_customer_experience` a través de `chatroom_whatsapp`.

- Añade los canales WhatsApp y Correo y WhatsApp.
- Permite seleccionar una plantilla aprobada de Meta.
- Inserta el enlace individual de la encuesta en `{{1}}`.
- Respeta bajas de WhatsApp y deja el resultado por destinatario.
- Procesa por lotes mediante la cola de campañas.

Si Chatroom no está instalado, el módulo base sigue funcionando con correo y no genera una dependencia innecesaria.
