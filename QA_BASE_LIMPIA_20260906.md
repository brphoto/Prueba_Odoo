# Base limpia para pruebas reales

## Base creada

- Base de datos: `chatroom_real_qa_20260906`
- Demo: desactivada
- Objetivo: validación funcional con datos reales de prueba, sin reutilizar la base operativa.
- Credenciales reales: no se copiaron a esta base.

## Módulos validados

WhatsApp y redes sociales, calendario, pagos, notificaciones, agente IA, ventas, CRM, Centro de mando de marketing, conectores Meta y redes sociales, catálogo Patiotuerca e inteligencia de leads.

## Resultado de pruebas

La batería ejecutada sobre esta base terminó con **82 pruebas, 0 fallos y 0 errores**:

- `chatroom_ai_agent`: 42 pruebas
- `chatroom_whatsapp`: 36 pruebas
- `marketing_command_center`: 10 pruebas

Además, la base quedó sin registros residuales de las pruebas en la cola de webhooks, mensajes de Chatroom y cuentas de marketing.

## Comando reproducible

Desde el directorio del servidor Odoo:

```powershell
python odoo-bin -c "C:\Program Files\Odoo 19.0e.20251201\server\odoo.conf" `
  -d chatroom_real_qa_20260906 --without-demo=all --no-http `
  --test-enable `
  --test-tags "/chatroom_whatsapp,/chatroom_ai_agent,/marketing_command_center" `
  --stop-after-init --log-level=test
```

## Controles aplicados

- Aprobación humana obligatoria para herramientas sensibles del agente IA.
- Aprobación limitada al grupo administrador del agente IA.
- Aislamiento multiempresa en Chatroom, líneas de WhatsApp, marketing, conectores Meta, conectores sociales y Patiotuerca.
- Deduplicación de mensajes de Meta mediante restricción única e idempotencia.
- Cola asíncrona de webhooks con reintentos, backoff y liberación del cuerpo procesado.
- Límite configurable de tamaño para payloads del webhook.
- Archivos locales de secretos excluidos del control de versiones.
- Código, XML y documentación guardados en UTF-8 con acentos correctos.

## Antes de una prueba con Meta

1. Configurar el token, App Secret, Verify Token y Phone Number ID de la compañía de prueba.
2. Confirmar que la URL pública usa HTTPS.
3. Registrar el webhook en Meta y enviar primero mensajes de prueba.
4. Verificar que el cron **Chatroom: procesar cola de webhook** esté activo.
5. No reutilizar tokens de producción en esta base.

El archivo local `client_secrets.json` encontrado en otra carpeta del entorno debe mantenerse fuera del repositorio y rotarse si alguna vez estuvo activo o expuesto.
