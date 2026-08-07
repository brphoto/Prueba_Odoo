# Inteligencia de Clientes / RFM / Pareto (Odoo 19)

Módulo independiente que agrega clasificación de clientes (RFM/ABC),
alerta de oportunidades estancadas y análisis Pareto (80/20) de
productos — sin depender de ningún canal de comunicación específico
(WhatsApp, email marketing, etc.).

## Por qué existe separado

Nació dentro de `chatroom_sales_intelligence` (para mostrar esta misma
información en el chat de WhatsApp), pero clasificar clientes por valor
es útil para **cualquier equipo** — ventas, marketing, atención — no
solo para quien atiende WhatsApp. Depende únicamente de `crm`, `sale` y
`account` (módulos nativos de Odoo), así que se puede instalar en
cualquier base de Odoo sin arrastrar el chatroom.

`chatroom_sales_intelligence` ahora depende de **este** módulo (no al
revés) para no duplicar la lógica: sigue mostrando los mismos datos en
el panel lateral del chat, pero la fuente de verdad vive acá.

## Qué agrega

### Clasificación RFM / ABC (`res.partner`)

Cron diario (`_cron_compute_rfm_scores`) que calcula, para toda la
cartera de clientes con al menos una factura publicada, un score 1-100
combinando percentiles de Recencia (20%), Frecuencia (30%) y Monto
(50%), traducido a categoría **A** (≥70), **B** (≥40) o **C**. Al vivir
en `res.partner`, los campos `rfm_category`/`rfm_score` quedan
disponibles para **filtrar listas de destinatarios de Email/SMS
Marketing** o cualquier otra vista de contactos — no hace falta ni
tocar este módulo para usarlos ahí, son campos normales.

### Oportunidades estancadas (`crm.lead`)

`days_since_last_management` y `management_alert_state`
(verde/amarillo/rojo) según la fecha más reciente entre el cambio de
etapa nativo (`date_last_stage_update`), el último mensaje/nota humano
del chatter y la última actividad registrada. Los mensajes automáticos
del sistema (creación del registro, tracking) no cuentan como gestión.

### Métricas históricas y Pareto (`res.partner`)

Total facturado, cantidad de facturas, fecha de la última venta y
ticket promedio (facturas de venta en estado "Publicada"); más un
botón inteligente **Top Productos** en la ficha del contacto que abre
`account.invoice.report` agrupado por producto, y un método
`_get_top_products()` reutilizable por cualquier otro módulo que
necesite ese análisis (como `chatroom_sales_intelligence`).

## Alcance de esta versión

- El score RFM es relativo a la cartera de clientes con facturas en el
  momento del cálculo; agregar/quitar clientes cambia el ranking de
  todos, no solo del nuevo.
- El análisis Pareto usa `account.move.line` de facturas publicadas
  (`out_invoice`); no incluye presupuestos ni pedidos sin facturar.
