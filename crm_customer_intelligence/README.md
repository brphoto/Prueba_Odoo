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
combinando percentiles de Recencia, Frecuencia y Monto, traducido a
categoría **A** (≥70), **B** (≥40) o **C**. Al vivir en `res.partner`,
los campos `rfm_category`/`rfm_score` quedan disponibles para
**filtrar listas de destinatarios de Email/SMS Marketing** o cualquier
otra vista de contactos — no hace falta ni tocar este módulo para
usarlos ahí, son campos normales.

**Pesos configurables** (Ajustes > Inteligencia de Clientes > Ajustes):
por defecto Monto 50% + Frecuencia 30% + Recencia 20%, pero se pueden
ajustar a lo que tenga sentido para el negocio — por ejemplo, los pesos
"clásicos" del análisis RFM original de Sears Roebuck son Recencia 50%
+ Frecuencia 35% + Monto 15%, más útiles para un negocio muy
estacional donde importa más "¿nos compró hace poco?" que "¿cuánto
gastó en total?". No hace falta que los tres sumen exactamente 1: se
normalizan solos dividiendo cada uno por la suma de los tres. Los
cambios se aplican en el próximo cálculo del cron (una vez por día; se
puede forzar antes desde Ajustes técnicos > Automatización > Acciones
Programadas).

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
- **Los pesos configurables son nuevos en esta iteración**: validado
  con `py_compile` y parseo de XML, sin correr el cron de verdad contra
  una base real todavía. Los cortes de categoría A/B/C siguen siendo
  umbrales fijos de score (70/40/0, no percentil de la cartera) — se
  evaluó cambiarlos a un corte por percentil real (20%/30%/50%, más
  fiel al Pareto clásico) pero se dejó como está a pedido explícito,
  para no mover la clasificación de clientes que ya pueda estar en uso
  para campañas.
