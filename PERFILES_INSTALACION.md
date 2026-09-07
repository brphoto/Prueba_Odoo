# Perfiles de instalación de la solución Chatroom

La solución se mantiene modular. No es necesario instalar IA, pagos, marketing
o RFM si el cliente solo necesita el canal y su integración con CRM.

## Perfil 1: Chatroom + CRM

Instalar:

- `chatroom_whatsapp`
- `chatroom_ui` (opcional, solo para la experiencia visual)
- `chatroom_calendar` (opcional, para reuniones nativas de Odoo)
- `chatroom_payment` (opcional, para enlaces de pago)
- `chatroom_payment_payphone` (opcional, únicamente si PayPhone está instalado)

Este perfil permite recibir y atender conversaciones, relacionarlas con
contactos y oportunidades y usar el chatter nativo. La instalación actual de
`chatroom_whatsapp` conserva dependencias de CRM, ventas, compras,
contabilidad y `kpi_engine`; por eso debe verificarse la disponibilidad de
esas aplicaciones antes de instalarlo en una base nueva.

## Perfil 2: IA asistida

Instalar sobre el perfil 1:

- `chatroom_ai`
- `chatroom_ai_usage`
- `chatroom_ai_knowledge`

Opcionales:

- `chatroom_ai_odoo_bridge`, si se instalará la IA nativa de Enterprise como
  motor complementario.
- `chatroom_ai_agent`, si se necesitan planes, tareas, aprobaciones,
  automatizaciones y auditoría.
- `chatroom_ai_autonomy`, si se necesitan políticas de autonomía y evaluación
  por cliente o canal.

La IA asistida prepara respuestas, resúmenes, clasificación y siguientes
acciones. La aprobación humana y el envío se controlan por permisos y por la
política configurada.

## Perfil 3: Operación comercial autónoma

Instalar sobre el perfil 2:

- `chatroom_ai_sales`
- `chatroom_ai_sales_payment`
- `chatroom_ai_sales_fulfillment`
- `chatroom_ai_operations`
- `chatroom_notifications`

Este perfil añade catálogo vivo de Odoo, carritos, cotizaciones nativas,
validaciones de stock y precio, actividades, reuniones y avisos. Las acciones
de alto impacto siguen siendo aprobables; no se confirma una venta ni se envía
un mensaje sin que la política lo permita.

## Perfil 4: Inteligencia comercial y experiencia

Instalar según necesidad:

- `crm_customer_intelligence`: RFM/ABC, reglas, KPIs y clasificación.
- `crm_customer_history`: importación de históricos para alimentar RFM.
- `crm_stagnation_management` y `crm_stagnation_intelligence`: salud del
  pipeline y oportunidades estancadas.
- `crm_customer_experience`: NPS, LTV y campañas de experiencia.
- `crm_customer_experience_whatsapp`: envío de invitaciones por Chatroom.
- `crm_engagement_automation`: automatizaciones comerciales.
- `chatroom_sales_intelligence`: integración de inteligencia en la ficha y
  el chatter.

## Perfil 5: Marketing social

- `marketing_command_center`

Es independiente de Chatroom y consolida cuentas, publicaciones, métricas,
comentarios, engagement, campañas, alertas y un agente analítico local. Los
conectores reales de cada red se deben instalar o desarrollar por separado;
el importador CSV UTF-8 permite iniciar con datos exportados de cada
plataforma.

## Orden recomendado para una base nueva

1. Instalar el perfil mínimo y comprobar el chatter con un contacto y una
   oportunidad.
2. Instalar `chatroom_ui` y guardar el tema visual.
3. Instalar IA, configurar endpoint, clave y modelo; sincronizar modelos.
4. Crear o cargar conocimiento y probarlo en modo local antes de consumir
   tokens.
5. Activar el catálogo vivo y probar productos, precios, variantes y stock.
6. Activar agente, políticas y automatizaciones con aprobación humana.
7. Agregar ventas, pagos, calendario y notificaciones de forma progresiva.

## Reglas de seguridad y operación

- La clave de respuestas y la Admin API Key de consumo son credenciales
  distintas.
- El costo oficial solo puede consultarse con una clave con permisos de uso y
  facturación; el fondo registrado en Odoo es un control interno, no el saldo
  oficial de OpenAI.
- Las pruebas de laboratorio no deben enviar WhatsApp real.
- Las cotizaciones, facturas, actividades, reuniones y PDFs se crean con los
  modelos y reportes nativos de Odoo.
- En producción se deben probar las credenciales reales de Meta, PayPhone,
  Google Calendar y las redes sociales en una base de prueba antes de activar
  automatizaciones.
