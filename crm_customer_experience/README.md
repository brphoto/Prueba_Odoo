# Experiencia del cliente: NPS + LTV

Módulo opcional para complementar `crm_customer_intelligence` sin acoplarse a WhatsApp.

## Qué incorpora

- Encuesta NPS nativa de Odoo en español: escala 0–10 y comentario opcional.
- Sincronización automática de respuestas terminadas hacia `crm.nps.response`.
- Registro manual o importado de respuestas cuando la empresa recibe el NPS por otro canal.
- LTV calculado desde facturas de cliente publicadas.
- Cola de invitaciones postventa para facturas pagadas, sin enviar mensajes por sí sola.
- Segmento estratégico que combina RFM y NPS: VIP en riesgo, Evangelista, Campeones, Perdidos y En observación.
- Resumen diario con NPS global, LTV promedio, RFM promedio y distribución de segmentos.
- Vistas estándar de Odoo con chatter, filtros y trazabilidad.
- Campañas NPS por categorías RFM A/B/C, categorías personalizadas o segmentos guardados.
- Enlaces individuales por cliente, control de repetición, procesamiento por lotes y estado por destinatario.

## Configuración

En `Inteligencia Comercial > Configuración > Ajustes`:

1. Define la vida útil estimada del cliente. El valor inicial es 3 años.
2. Activa o desactiva la preparación automática de invitaciones NPS.

Luego ejecuta `Inteligencia Comercial > Experiencia del cliente > Panel NPS y LTV` y pulsa `Actualizar indicadores`.

## Flujo recomendado

1. Confirma que las ventas estén facturadas y pagadas.
2. El cron prepara una invitación postventa por factura pagada.
3. Envía la encuesta por el canal configurado (WhatsApp, correo u otro).
4. Al finalizar la encuesta, la respuesta se clasifica y actualiza el contacto.
5. Ejecuta el cron de experiencia o actualiza el panel para revisar LTV y segmentos.
6. Usa el filtro `VIP en riesgo` para crear seguimientos de retención.

El envío automático de mensajes no está habilitado por defecto: la cola conserva control humano y evita enviar comunicaciones sin aprobación.

## Campañas NPS segmentadas

En `Inteligencia Comercial > Experiencia del cliente > Campañas NPS`:

1. Selecciona la encuesta nativa de Odoo.
2. Elige una o varias categorías RFM del catálogo (A, B, C o personalizadas) y, si hace falta, segmentos guardados con reglas.
3. Define cuántos días deben pasar antes de volver a encuestar al mismo cliente.
4. Selecciona Correo, WhatsApp o ambos. El canal WhatsApp aparece al instalar `crm_customer_experience_whatsapp`.
5. Previsualiza la audiencia y encola la campaña. Un cron la procesa en lotes; `Procesar ahora` permite probarla manualmente.

Cada cliente recibe un `answer_token` individual, por lo que la respuesta queda asociada al contacto y a la campaña. Al finalizar la encuesta se actualizan el NPS del contacto y su segmento estratégico.

El conector WhatsApp requiere una plantilla aprobada por Meta con al menos `{{1}}`; esa primera variable recibe el enlace de encuesta. Esto respeta la regla de Meta para iniciar conversaciones fuera de la ventana de 24 horas.
